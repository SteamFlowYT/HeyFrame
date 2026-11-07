# Hey Frame 0.3.0 — offline Steam Frame voice utility

> **SteamFlow GitHub edition — experimental.** Install and runtime have not been validated on a physical Steam Frame yet. Test speaker and microphone before enabling the wake-word service. If your physical Volume Up button still fails, resolve that separately first.

## Install directly from Steam Frame (no PC)

When this source is published at **SteamFlowYT/HeyFrame**, open Konsole **on the headset** and run:

```bash
curl -fsSL https://raw.githubusercontent.com/SteamFlowYT/HeyFrame/main/steamflow-bootstrap.sh | bash
```

The bootstrap downloads this GitHub repo into a temporary folder and runs `install.sh`. It does **not** automatically start listening. For safety, review `steamflow-bootstrap.sh` and `install.sh` before execution. After installation, test output and input before enabling:

```bash
~/.local/bin/hey-frame say "Frame voice system online"
~/.local/bin/hey-frame mic-test
~/.local/bin/hey-frame start
```

Stop and disable the wake listener any time with `~/.local/bin/hey-frame stop`. See the detailed manual installation and diagnostics below.

Wake phrase **"Hey Frame"**. Follow it immediately with a command or pause briefly and speak your command. English commands only. Runs directly on the headset; no gaming PC or online AI needed **after installation**. Installs entirely in the current user's home directory. It is a specialized, keyword-driven utility, **not** a general-purpose LLM.

## What changed after the v0.1/v0.2 failures

- Pins `vosk==0.3.45` and `sherpa-onnx==1.13.8`; explicitly installs NumPy and permits Vosk's pure-Python `srt` dependency to build from source, while requiring precompiled native libraries.
- Creates a separate v0.3 install path and does **not** overwrite old version files.
- Does **not** start the background microphone service automatically. First verifies packages, downloads offline models, tests native speech recognition and real TTS generation; manual `mic-test` and audible `say` are available before `start`.
- `start` independently tests imports, voice generation, and microphone bytes before enabling the service. Run `hey-frame stop` to disable the background microphone.
- Uses a small, fixed Vosk wake grammar; switches to a natural-language Vosk recognizer only for ~7s after the wake word, replaying up to 3.5s of recent audio so one-breath commands are less likely to be clipped.
- Never uses `/dev/input`, `evdev`, `uinput`, controller bindings, SteamVR input overrides, `wpctl set-volume`, input grabs, or audio default-device changes. Existing one-sided hardware volume-button bugs require separate troubleshooting; **this app does not repair hardware-button faults**.
- Serializes listener instances; bounds microphone retry failures instead of restart-spamming indefinitely; on failed voice output prints a diagnostic fallback to the service logs.
- Timers are persisted in a private JSON file and resume after service restarts. No raw audio or transcripts are stored to disk.
- Voice is upstream `vits-piper-en_US-glados`, with a subtle optional radio/HEV-inspired EQ. **Not the original Half-Life HEV voice**, not cloned from copyrighted recordings.

## Download / install on Steam Frame

Download `hey-frame-v0.3.0.zip` to Downloads, then run commands **one by one**, pressing Enter each time. Never prefix `cd` with `bash`:

```bash
cd ~/Downloads
unzip -o hey-frame-v0.3.0.zip
cd hey-frame
bash install.sh
```

Requires `python3` (3.10–3.14), Python `venv` and `pip`, PipeWire `pw-record` and `pw-play`, and internet for initial Python packages and model downloads. Model sources are Vosk and the sherpa-onnx model release. Native ARM64 wheels are available upstream for the Steam Frame's expected Python 3.12 environment, but **this exact package has not been tested on a physical Steam Frame**. Installation can take time due to model downloads; follow terminal output. No `sudo` required.

You can also use the ZIP on another Linux machine for static testing; an x86_64 install may fail due to platform-specific binaries, and no Steam Frame support should be inferred.

## Safe first-run checklist

**Do not activate if the physical Volume Up button remains faulty.** First resolve the headset issue independently.

1. Check real local speech-recognition model: `~/.local/bin/hey-frame check-asr`
2. Generate (no playback):
   ```bash
   ~/.local/bin/hey-frame check-voice
   ```
3. Verify audible playback:
   ```bash
   ~/.local/bin/hey-frame say "Frame voice system online"
   ```
4. Verify microphone routing. **Speak during the test**; audio is not saved:
   ```bash
   ~/.local/bin/hey-frame mic-test
   ```
5. Enable wake listening only after these succeed:
   ```bash
   ~/.local/bin/hey-frame start
   ```
6. Stop and **disable boot autostart** any time:
   ```bash
   ~/.local/bin/hey-frame stop
   ```

To test without enabling service or asking for mic permission:
```bash
~/.local/bin/hey-frame doctor
~/.local/bin/hey-frame test-command "set a timer for five minutes"
```

To run in Konsole foreground for real-time logs, stop the background service first and use:
```bash
~/.local/bin/hey-frame stop
~/.local/bin/hey-frame run
```
Press **Ctrl+C** to exit. Only one instance is permitted. The service uses a systemd user unit and may be autostarted on future boots **only after `start` succeeds**; a spoken "stop listening" ends the current process but does not permanently disable the service at boot. Use `hey-frame stop` to disable startup.

## Useful commands

| Say | Result |
|---|---|
| "Hey Frame, how much battery life do I have left?" | Read headset battery percentage; approximate remaining time **only when sysfs exposes usable data** |
| "Hey Frame, set a timer for five minutes" | Starts a 5-minute timer; max 2 hours; survives restart |
| "Hey Frame, timer remaining" | Reports active timer time |
| "Hey Frame, cancel timer" | Cancels active timer |
| "Hey Frame, battery alerts on" | Enable spoken alerts at 20%, 10%, 5% (default OFF) |
| "Hey Frame, battery alerts off" | Disable battery alerts |
| "Hey Frame, Wi-Fi signal" | Reports connected signal strength if NetworkManager exposes it |
| "Hey Frame, SteamVR status" | Read-only check whether `steamvr.service` is active |
| "Hey Frame, storage" | Free storage on the user home partition |
| "Hey Frame, memory" | Available RAM |
| "Hey Frame, volume" | Reads the default sink level; **cannot change volume** |
| "Hey Frame, uptime" | System uptime |
| "Hey Frame, what time is it?" | Current time |
| "Hey Frame, what's today's date?" | Current date |
| "Hey Frame, status report" | Short system/battery announcement |
| "Hey Frame, help" | Command overview |
| "Hey Frame, stop listening" | Exits foreground service process (autostart remains enabled until `stop` command) |

No remote control, game launching, shell execution, account interaction, cloud inference, or fabricated answers. Limited English voice recognition is deliberate for low power and safety. Battery duration is approximate, depends on instantaneous power use, and can be unavailable.

## Audio routing / voice style

If audio is routed to the wrong device, list nodes using `wpctl status` (read-only) and configure a target as an environment variable. Example for **one command only**:

```bash
HEY_FRAME_AUDIO_TARGET=42 ~/.local/bin/hey-frame say "Testing speaker routing"
```

Do not assume node 42 is your output: it is only an example. `HEY_FRAME_MIC_TARGET` similarly specifies an explicit PipeWire capture node. For persistent service overrides, create `~/.config/hey-frame/settings.env` with e.g. `HEY_FRAME_MIC_TARGET=<correct source>`; restart only Hey Frame. Never edit SteamOS global audio settings on the app's behalf.

Voice filter defaults to `hev`. For a clean version of the underlying GLaDOS model:

```bash
HEY_FRAME_VOICE_STYLE=clean ~/.local/bin/hey-frame say "Welcome to the Frame"
```

Voice output is generated into a temporary WAV under `/tmp` then played with `pw-play`. It is deleted afterward. The on-demand synthesizer process exits after each answer to reduce idle RAM. **No direct Half-Life voice assets are included**.

## Diagnostics and removal

```bash
~/.local/bin/hey-frame status
journalctl --user -u hey-frame.service -n 80 --no-pager
```

Measure actual listener CPU and RAM on your own headset (no changes made):

```bash
~/.local/bin/hey-frame benchmark --seconds 30
```

The CPU result uses process time divided by wall time, so 100% means one fully occupied CPU core, not 100% of the entire headset. It does **not** establish battery drain; compare actual discharge in repeated conditions for that.

The log records command categories and error messages, **not raw speech or recognized transcripts**. The generated response text appears in logs only if voice playback fails, and can include a spoken timer duration or battery report; don't share logs unreviewed.

If you downloaded the archive and are still inside its `hey-frame` directory, uninstall with:
```bash
bash uninstall.sh
```

Or uninstall using the copy installed in the app home:
```bash
bash ~/.local/share/hey-frame-v3/uninstall.sh
```

It removes the new v0.3 install and service but deliberately keeps older v0.1/v0.2 files intact; it cannot repair a separate SteamOS audio or hardware issue. Timer and preferences JSON are retained unless you delete them manually.

## Development checks

```bash
~/.local/share/hey-frame-v3/.venv/bin/python -m unittest discover -s tests -v
bash -n install.sh
bash -n uninstall.sh
~/.local/share/hey-frame-v3/.venv/bin/python -m compileall -q src
```

Automated tests use a fake Vosk recognizer, mocked system queries and Python wheel installs. Testing on a development Linux machine **is not** a substitute for actual Steam Frame ARM64 package installation, real microphone source validation, GPU/CPU load or battery drain measurements, native TTS compatibility, and in-game background wake accuracy.

## Third-party components / privacy

Downloads code and models only at installation from PyPI, alphacephei.com and GitHub. Package URLs are documented in `src/download_models.py`. The listener does not make network calls after installation. No analytics, no recorded speech archive, no credentials, no direct controller interception. Vosk and sherpa-onnx have separate open-source licences; see their upstream repositories. The GLaDOS model is distributed **by sherpa-onnx upstream**, not bundled with this source ZIP; review its model licence before redistribution.