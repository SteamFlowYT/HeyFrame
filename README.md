# Hey Frame v0.5.1 — Offline voice assistant for Steam Frame

A practical, locally-running Steam Frame assistant: hands-free recording controls, headset battery, short timers, highlights, screenshots and sci-fi humour, plus a **dedicated Hey Frame tab in the SteamVR dashboard**. It is an experimental SteamOS ARM64 project. Native performance and the dashboard UI still require physical headset testing.

**No cloud AI, gaming PC, controller interception or system volume changes.** Speech recognition is local Vosk. Replies use the on-device sherpa-onnx GLaDOS-style synthetic voice (not original game audio). The recognizer is focused on simple English requests, not general conversation.

## Install / update directly on the Frame

Open **Konsole on the headset**. Update SteamFlow Recorder first if you haven't already updated the recorder's voice-control bridge, then update Hey Frame:

```bash
# Only if your SteamFlow Recorder has not been updated for voice integration:
curl -fsSL https://raw.githubusercontent.com/SteamFlowYT/SFRecorder/main/steamflow-bootstrap.sh | bash
# Then update Hey Frame:
curl -fsSL https://raw.githubusercontent.com/SteamFlowYT/HeyFrame/main/steamflow-bootstrap.sh | bash
```

**Stop any active recording before updating SFRecorder.** The SFRecorder installation restarts its dashboard service. It retains recorded files. Both installers should be reviewed before piping their contents to bash. Neither command requires a Windows PC.

The Hey Frame installer reuses already-downloaded recognition/TTS models, verifies its packages, and **preserves your previous listening-on preference** if enabled. For a first install, the microphone stays off until you enable it. The **Hey Frame** SteamVR dashboard tab runs independently of the microphone listener, as long as SFRecorder's dashboard environment is installed.

If you don't see the tab after installing, inspect:

```bash
systemctl --user status hey-frame-dashboard.service --no-pager
journalctl --user -u hey-frame-dashboard.service -n 50 --no-pager
```

The dedicated dashboard uses SFRecorder's installed isolated Python (`~/.local/share/sfrecorder/venv/bin/python`) containing the working Steam Frame ARM64 OpenVR loader and Pillow. If the recorder is absent, the assistant can still listen, but the SteamVR dashboard needs SFRecorder installed. The dashboard is installed as a separate user service and auto-starts with your user session.

## Dashboard toggle

Open the SteamVR dashboard and choose the separate **Hey Frame** tab (green microphone icon). Controls:

- **TURN LISTENING ON / OFF**: enables/disables the Hey Frame user service and its future autostart. OFF means the assistant is no longer capturing the microphone.
- **START RECORDING** and **STOP / SAVE**: use the existing SteamFlow Recorder engine through its private local socket (no duplicate recorder).
- **MARK HIGHLIGHT**: writes an approximate recording timestamp to `~/Videos/SFRecorder/HeyFrame_markers_YYYY-MM-DD.txt`.
- **TAKE VR SCREENSHOT**: asks the SteamVR compositor for a stereo screenshot. Intended destination: `~/Pictures/HeyFrame`. Exact result still needs physical Steam Frame validation.

If the headset has another dictation service running, starting Hey Frame is blocked to avoid the known Steam Frame Volume Up input-grab conflict. The assistant itself never accesses `/dev/input`, evdev, uinput or controller bindings.

Listening also starts automatically on later sessions **after you enable it once**. You don't need to type the start command on every boot. It can still be controlled in Konsole with `~/.local/bin/hey-frame start` and `~/.local/bin/hey-frame stop`.

## Gaming-first voice commands

Say **"Hey Frame"**, then the command. Short commands typically recognize more reliably than long ones.

| Say | Result |
|---|---|
| **"Start recording"** | Start the installed SFRecorder with your existing settings |
| **"Stop recording"** | Stop and finalize the recording |
| **"Am I recording?"** | Recorder status and elapsed time |
| **"Mark this moment"** | Write a timestamp to a highlights sidecar while recording |
| **"Take a screenshot"** | Request a stereo SteamVR screenshot through the dashboard service |
| **"How much battery is left?"** | Headset battery level; time estimate if available |
| **"Battery alerts on"** | Speak low-battery warnings at 20%, 10% and 5% |
| **"Set a timer for ten minutes"** | Start a local timer (up to 2 hours) |
| **"Timer remaining" / "Cancel timer"** | Check or cancel the timer |
| **"Note to self test the new lens"** | Save a brief locally transcribed note in `~/Documents/HeyFrame/notes.txt` |
| **"Read last note"** | Speak your latest saved note |
| **"Tell me a joke"** | Original sarcastic lab-AI joke |
| **"Portal quote" / "GLaDOS quote"** | Prefer lines from your personal quote collection; otherwise very short built-in lines/original humour |
| **"Personal quote"** | Only from your personally maintained quotes file |
| **"Open dashboard"** | Open the SteamVR dashboard |
| **"Pause game"** | Opens the SteamVR dashboard as a best-effort interruption; **does not press the game's Start/Menu button** |
| **"Resume game"** | Explains how to close the dashboard manually; does not inject a gamepad event |

The older date, uptime, free-memory, storage and volume queries remain available for backward compatibility, but the feature focus is now recording and gaming.

### Pause / resume limitation

A SteamVR overlay has no supported generic API to spoof a **Menu/Start button press into the current VR game**. VR games handle the Frame's `/user/hand/right/input/menu` or `/user/hand/left/input/view` through game-specific input bindings. Non-VR streaming may use Steam Input or different key mappings. We do **not** use input grabs, fake system controllers or privileged `/dev/uinput` injection, because these could break other hardware controls (as happened with the original unrelated dictation addon).

**"Pause game" currently opens the dashboard**, and the game may or may not pause behind it. **"Resume game" does not close the SteamVR dashboard**, because OpenVR exposes `ShowDashboard` but not a universal `HideDashboard`. Use the Steam button to exit. Actual in-game pause requires a separate, tested binding for each game/runtime and is **not claimed in this version**.

## Actual Portal quotes — personal collection

The public project ships only a few very short familiar lines and original GLaDOS-like jokes. It **does not bundle Portal dialogue archives or extracted game audio**. Add the dialogue that you choose **on your headset**, without uploading it to GitHub.

**Add several quotes in one command:**

```bash
~/.local/bin/hey-frame add-quotes "Your first quote" "Your second quote" "Your third quote"
```

**Import a whole text file** (one quote per line, optional # comments):

```bash
~/.local/bin/hey-frame import-quotes ~/Downloads/portal-quotes.txt
```

**Or paste multiple lines directly into Konsole** as a single block:

```bash
~/.local/bin/hey-frame import-quotes - <<'QUOTES'
Your first personal quote goes here.
Your second quote goes here.
Your third quote goes here.
QUOTES
```

You can still add only one line with `hey-frame add-quote "Your quote"`. The bulk commands preserve existing quotes, skip duplicates ignoring capitalization, and reject an over-limit batch **without modifying** your collection. Once imported, say **"Hey Frame, Portal quote"** or **"Hey Frame, personal quote"**. Changes are read on the next command; no restart is required.

To find or edit the file:

```bash
~/.local/bin/hey-frame quotes-path
~/.local/bin/hey-frame list-quotes
```

File: `~/.config/hey-frame/portal-quotes.txt`, one quote per line, maximum 200 lines of 350 characters each. Lines starting `#` are ignored. Your custom quotes are **not uploaded to GitHub, overwritten by updates or sent to servers**. The voice synthesizes them locally; it doesn't replay Valve's original voice samples.

## Response speed

The default `HEY_FRAME_FAST_VOICE=1` keeps the GLaDOS speech engine loaded while listening, so it doesn't reload the model for every spoken response. The voice filter is NumPy-vectorized. This trades some RAM for lower reply latency; exact startup time, CPU and headset battery impact need on-device measurements. To use less RAM (but slower responses), add `HEY_FRAME_FAST_VOICE=0` to `~/.config/hey-frame/settings.env` then restart the service. Set `HEY_FRAME_VOICE_STYLE=clean` there to disable the HEV-like radio filter.

To benchmark idle listener CPU/RAM (not battery drain):

```bash
~/.local/bin/hey-frame benchmark --seconds 30
```

## Tests and troubleshooting

```bash
~/.local/bin/hey-frame doctor
~/.local/bin/hey-frame check-asr
~/.local/bin/hey-frame mic-test
~/.local/bin/hey-frame say "Frame voice system online"
~/.local/bin/hey-frame recorder status
~/.local/bin/hey-frame vr open_dashboard
~/.local/bin/hey-frame mark
~/.local/bin/hey-frame status
```

To run listening in a terminal and see diagnostics, first disable the background service:

```bash
~/.local/bin/hey-frame stop
~/.local/bin/hey-frame run
```

Use Ctrl+C to exit. `~/.local/bin/hey-frame start` enables the background service again. Service output is in `journalctl --user -u hey-frame.service -n 80 --no-pager`. The systemd listener unit is restarted only on failures, not after a normal exit.

To uninstall the current assistant and its separate dashboard (personal quotes and notes are retained), run:

```bash
bash ~/.local/share/hey-frame-v3/uninstall.sh
```

## Security and implementation

- Linux user services only, no system-wide installation, no global input/volume configuration changes.
- Only the recognizer and locally generated speech run on the headset; no outside network after first installation.
- Voice actions are allowlisted. Record control runs through a private UNIX socket owned by the SFRecorder dashboard, not via a shell or another recorder process.
- The dedicated SteamVR dashboard uses its own private UNIX socket for safe `open_dashboard` and `screenshot` requests. Sockets are user-owned (`0600`), in user-only runtime directories (`0700`).
- Spoken notes and markers are written locally only when explicitly requested. Recognized speech/audio isn't archived by the listener.
- The project is experimental. Automated tests and syntax checks are **not equivalent** to physical Steam Frame validation of OpenVR/PipeWire timing, game-specific behaviour, battery drain, or recording reliability.

See [SteamFlow Recorder](https://github.com/SteamFlowYT/SFRecorder) for recording engine details and third-party licenses for Vosk and sherpa-onnx.
