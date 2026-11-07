#!/usr/bin/env bash
set -Eeuo pipefail
SYSTEMCTL="$(command -v systemctl || true)"
if [[ -z "$SYSTEMCTL" && -x /usr/bin/systemctl ]]; then SYSTEMCTL=/usr/bin/systemctl; fi
if [[ -n "$SYSTEMCTL" ]]; then
  "$SYSTEMCTL" --user disable --now hey-frame.service >/dev/null 2>&1 || true
  if "$SYSTEMCTL" --user is-active --quiet hey-frame.service 2>/dev/null; then
    echo 'Hey Frame is still running. Nothing removed.' >&2
    exit 1
  fi
fi
rm -f -- "$HOME/.local/bin/hey-frame" "$HOME/.config/systemd/user/hey-frame.service"
if [[ -n "$SYSTEMCTL" ]]; then "$SYSTEMCTL" --user daemon-reload || true; fi
rm -rf -- "$HOME/.local/share/hey-frame-v3"
# The old v0.1/v0.2 folder is intentionally untouched; remove it manually if desired.
echo 'Hey Frame v0.3 disabled and removed. No SteamOS or hardware control settings changed.'
