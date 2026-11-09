#!/usr/bin/env bash
# Safe install. Never starts the microphone background service.
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP="$HOME/.local/share/hey-frame-v3"
PREVIOUS="$HOME/.local/share/hey-frame"
BIN="$HOME/.local/bin/hey-frame"
UNIT="$HOME/.config/systemd/user/hey-frame.service"

printf '\nHey Frame 0.6.2 | Steam Frame offline assistant\n'
printf 'Installer will NOT start the microphone service.\n\n'
case "$(uname -m)" in aarch64|x86_64) : ;; *) echo 'Unsupported CPU: need Linux ARM64 (x86_64 for dev)' >&2; exit 1;; esac
for tool in python3 pw-record pw-play; do
  command -v "$tool" >/dev/null 2>&1 || { echo "Missing $tool" >&2; exit 1; }
done
python3 -c 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,14), "Python 3.10-3.14 required"'

# Remember whether this user opted in to persistent listening before updating.
WAS_ENABLED=0
if command -v systemctl >/dev/null 2>&1 && systemctl --user is-enabled --quiet hey-frame.service 2>/dev/null; then
  WAS_ENABLED=1
fi
# Stop only the Hey Frame user service; leave all other services untouched.
SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" && -x /usr/bin/systemctl ]]; then SYSTEMCTL=/usr/bin/systemctl; fi
if [[ -n "$SYSTEMCTL" ]]; then
  "$SYSTEMCTL" --user disable --now hey-frame.service >/dev/null 2>&1 || true
  if "$SYSTEMCTL" --user is-active --quiet hey-frame.service 2>/dev/null; then
    echo 'Old Hey Frame service did not stop. Abort, no files replaced.' >&2
    exit 1
  fi
else
  echo 'WARNING: systemctl is unavailable. Make sure old Hey Frame is stopped.' >&2
fi

if [[ -n "$SYSTEMCTL" ]] && "$SYSTEMCTL" --user is-active --quiet frame-dictation.service 2>/dev/null; then
  echo 'WARNING: frame-dictation.service is running. It may have caused Volume Up interference.'
  echo "This installer will NOT stop another developer's service. New Hey Frame cannot start until it is stopped."
fi

mkdir -p "$APP/src" "$APP/models" "$HOME/.local/bin" "$HOME/.config/systemd/user"
cp "$HERE"/src/*.py "$APP/src/"
cp "$HERE"/README.md "$APP/README.md"
cp "$HERE"/uninstall.sh "$APP/uninstall.sh"
chmod 755 "$APP/uninstall.sh"
if [[ ! -x "$APP/.venv/bin/python" ]]; then
  echo 'Creating isolated Python environment...'
  python3 -m venv "$APP/.venv" || {
    echo 'Python venv failed; nothing has been activated.' >&2
    exit 1
  }
fi
PY="$APP/.venv/bin/python"
"$PY" -m pip --version >/dev/null || {
  echo 'pip is missing inside the venv. Check the Steam Frame Python environment.' >&2
  exit 1
}
printf '\nInstalling ARM64 native wheels and small Python packages...\n'
"$PY" -m pip install --disable-pip-version-check \
    --only-binary=vosk,sherpa-onnx,numpy,cffi \
    'vosk==0.3.45' 'sherpa-onnx==1.13.8' 'numpy>=1.26,<3'
"$PY" -m pip check
"$PY" -c 'import vosk, numpy, sherpa_onnx; print("Verified: vosk, numpy, sherpa_onnx", numpy.__version__)'

# Reuse downloaded models only if complete. Copies stay independent of old install.
if [[ -d "$PREVIOUS/models" ]]; then
  for name in vosk-model-small-en-us-0.15 vits-piper-en_US-glados; do
    if [[ ! -d "$APP/models/$name" && -d "$PREVIOUS/models/$name" ]]; then
      case "$name" in
        vosk*) [[ -s "$PREVIOUS/models/$name/am/final.mdl" ]] || continue;;
        *) [[ -s "$PREVIOUS/models/$name/en_US-glados.onnx" && -s "$PREVIOUS/models/$name/tokens.txt" && -d "$PREVIOUS/models/$name/espeak-ng-data" ]] || continue;;
      esac
      echo "Reusing local model: $name"
      cp -a --reflink=auto "$PREVIOUS/models/$name" "$APP/models/$name"
    fi
  done
fi
printf '\nDownloading any missing offline models...\n'
"$PY" "$APP/src/download_models.py" "$APP/models"
# Verify synth BEFORE installing service or exposing listener.
printf '\nTesting offline voice synthesis (no microphone)...\n'
"$PY" "$APP/src/assistant.py" doctor
"$PY" "$APP/src/assistant.py" check-asr
"$PY" "$APP/src/assistant.py" check-voice

# Only after all tests pass, replace launch wrapper / user unit.
cat > "$BIN" <<'EOF'
#!/usr/bin/env bash
exec "$HOME/.local/share/hey-frame-v3/.venv/bin/python" "$HOME/.local/share/hey-frame-v3/src/assistant.py" "$@"
EOF
chmod 755 "$BIN"
cat > "$UNIT" <<'EOF'
[Unit]
Description=Hey Frame (offline, hands-free Steam Frame voice utility)
After=pipewire.service wireplumber.service
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=simple
ExecStart=%h/.local/bin/hey-frame run
Environment=PYTHONUNBUFFERED=1
Environment=HEY_FRAME_FAST_VOICE=1
EnvironmentFile=-%h/.config/hey-frame/settings.env
Restart=on-failure
RestartSec=6
Nice=12
NoNewPrivileges=true
TimeoutStopSec=8

[Install]
WantedBy=default.target
EOF
# Dedicated SteamVR dashboard, independent of SteamFlow Recorder's dashboard tab.
# Reuse the recorder's tested pyopenvr/Pillow ARM64 virtualenv + Valve loader.
DASH_BIN="$HOME/.local/bin/hey-frame-dashboard"
DASH_UNIT="$HOME/.config/systemd/user/hey-frame-dashboard.service"
cat > "$DASH_BIN" <<'DASH'
#!/usr/bin/env bash
set -euo pipefail
PY="$HOME/.local/share/sfrecorder/venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "Hey Frame dashboard requires SteamFlow Recorder's Python environment." >&2
  exit 1
fi
exec "$PY" "$HOME/.local/share/hey-frame-v3/src/dashboard.py"
DASH
chmod 755 "$DASH_BIN"
cat > "$DASH_UNIT" <<'DASH'
[Unit]
Description=Hey Frame dedicated SteamVR dashboard
After=sfrecorder.service
StartLimitIntervalSec=90
StartLimitBurst=3

[Service]
Type=simple
ExecStart=%h/.local/bin/hey-frame-dashboard
Restart=on-failure
RestartSec=8
Nice=13
NoNewPrivileges=true

[Install]
WantedBy=default.target
DASH

# Do not overwrite any personal quotes on reinstall/update.
QUOTES="$HOME/.config/hey-frame/portal-quotes.txt"
if [[ ! -e "$QUOTES" ]]; then
  mkdir -p "$HOME/.config/hey-frame"
  printf '%s\n' '# Personal Portal quotes. One quote per line. This file stays on your headset.' > "$QUOTES"
  chmod 600 "$QUOTES"
fi

if [[ -n "$SYSTEMCTL" ]]; then
  "$SYSTEMCTL" --user daemon-reload || true
  # Leave Hey Frame listening OFF on a fresh install, but show the dashboard
  # toggle whenever the already-installed SFRecorder Python is available.
  SF_PY="$HOME/.local/share/sfrecorder/venv/bin/python"
  if [[ -x "$SF_PY" ]] && "$SF_PY" -c 'import openvr, PIL' >/dev/null 2>&1; then
    echo 'Enabling dedicated Hey Frame SteamVR dashboard tab...'
    "$SYSTEMCTL" --user enable --now hey-frame-dashboard.service || true
  else
    echo 'Hey Frame dashboard requires SteamFlow Recorder. Install/update SFRecorder first.'
  fi
  if [[ "$WAS_ENABLED" = 1 ]] && ! "$SYSTEMCTL" --user is-active --quiet frame-dictation.service 2>/dev/null; then
    echo 'Restoring your previously enabled Hey Frame background service...'
    "$SYSTEMCTL" --user enable --now hey-frame.service || true
  fi
fi
cat <<'EOF'

Install complete. Existing listening preference preserved when safe.

1) Test speakers: ~/.local/bin/hey-frame say "Frame voice system online"
2) Test microphone while speaking: ~/.local/bin/hey-frame mic-test
3) ONLY IF both work: ~/.local/bin/hey-frame start (enables future boot autostart)
4) Stop/disable at any time: ~/.local/bin/hey-frame stop

For GLaDOS mode: say "Hey Frame, is GLaDOS there?" or use dashboard toggle.
For normal mode: ~/.local/bin/hey-frame mode normal
For personal Portal quotes: ~/.local/bin/hey-frame add-quote "Your chosen quote"
For a separate SteamVR panel: look for the Hey Frame tab in Dashboard.
For diagnostic info: ~/.local/bin/hey-frame doctor
For testing without voice: ~/.local/bin/hey-frame test-command "battery"

No hardware button access or volume write capability is installed.
EOF
