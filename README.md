# Hey Frame v0.6.4 (optimization candidate)

Hey Frame is a small offline voice assistant I made for the Steam Frame. You say "Hey Frame" and you can start and stop recordings, mark highlights, take screenshots, check the battery, set timers and get the occasional sarcastic GLaDOS-style line back. It also adds its own Hey Frame tab to the SteamVR dashboard so you can do most of this with buttons too.

Everything runs on the headset. There's no cloud AI, you don't need a gaming PC, and it doesn't touch your controllers or your system volume. Speech recognition is Vosk running locally and the voice is a sherpa-onnx GLaDOS-style synthetic voice (it's not the original game audio). It's built for short English commands, so don't expect to have a conversation with it.

This is still an experimental project. A lot of it is tested in code, but things like the dashboard tab, screenshots and how it actually performs on the Frame still need proper testing on the headset, so if something doesn't work for you, let me know.

## Installing or updating

Everything is done in Konsole on the headset, no Windows PC needed.

Hey Frame uses SteamFlow Recorder for recording, so if you haven't updated SFRecorder since I added voice control, update that first. Then install or update Hey Frame:

```bash
# Only if your SteamFlow Recorder hasn't been updated for voice control yet:
curl -fsSL https://raw.githubusercontent.com/SteamFlowYT/SFRecorder/main/steamflow-bootstrap.sh | bash
# Then Hey Frame:
curl -fsSL https://raw.githubusercontent.com/SteamFlowYT/HeyFrame/main/steamflow-bootstrap.sh | bash
```

Stop any recording you have running before you update SFRecorder, because the installer restarts its dashboard service. Your recordings are kept. And as with anything you pipe into bash, it's a good idea to have a look at the scripts first.

If you've installed Hey Frame before, the installer reuses the speech models you already downloaded and keeps your listening setting the way you left it. On a fresh install the microphone stays off until you turn it on yourself.

The dashboard tab works separately from the microphone, so you can use the buttons even with listening off. It does need SFRecorder installed though, since it runs on SFRecorder's Python environment (`~/.local/share/sfrecorder/venv/bin/python`), which has the OpenVR loader that works on the Frame. Without SFRecorder the voice assistant still works, you just won't get the tab.

If the tab doesn't show up after installing, these two commands should tell you what's going on:

```bash
systemctl --user status hey-frame-dashboard.service --no-pager
journalctl --user -u hey-frame-dashboard.service -n 50 --no-pager
```

## Optional GLaDOS Mode

Want a less cooperative personality while keeping the same practical commands? Say **"Hey Frame, is GLaDOS there?"**. Since the headset's speech recognition sometimes spells out the name as **G L A D O S**, v0.6.1 understands the letter names too. For the most reliable activation, simply say **"Hey Frame, sarcastic mode"**. The voice assistant replies:

> "Oh. You put the headset back on. I had almost finished enjoying the silence."

From then on, actions still happen normally, but the spoken result gets a sarcastic comment. For example:

- **"Hey Frame, start recording"** — Starts SFRecorder first, then responds with the real recorder result and something like "Try to do something worth watching this time."
- **"Hey Frame, battery"** — Reads the actual headset battery percentage first, then adds a remark about the battery or your survival prospects.
- **"Hey Frame, set a timer for ten minutes"** — Sets a real timer, then tells you that when it ends nothing exciting will happen.
- **"Hey Frame, mark this moment"** — Saves the highlight and comments on your editing decisions.

**Important:** This is a response personality, **not** another assistant or a generative chatbot. It does not analyze gameplay, add controller access, or change what any command does. If a recorder or screenshot action fails, it reports the failure without falsely claiming success. Low-battery alerts, shutdown messages, and your own Portal quotes remain clear and unmodified.

To switch back, say **"Hey Frame, normal mode"** or **"Hey Frame, turn off GLaDOS"**. Ask **"Hey Frame, what mode are you in?"** to hear which is active.

You can also toggle **GLaDOS: ON/OFF** in the dedicated Hey Frame SteamVR dashboard, next to the microphone on/off control. This switch also works when the microphone listener is disabled.

The mode is saved privately to `~/.config/hey-frame/mode.json`, survives reboot and updates, and switches immediately without restarting the service. If you prefer Konsole:

```bash
~/.local/bin/hey-frame mode glados
~/.local/bin/hey-frame mode normal
~/.local/bin/hey-frame mode status
```

The sarcastic lines are original lines you supplied and other original lab-AI quips, delivered in the existing synthetic voice. They do not use game audio.

## The dashboard tab

Open the SteamVR dashboard and look for the Hey Frame tab with the green microphone icon. You get these buttons:

- **Turn listening on / off** turns the voice assistant on or off, including whether it starts automatically next time. Off means it's not using the microphone at all.
- **GLaDOS: ON/OFF** switches between sarcastic and normal replies without changing the listening setting.
- **Start recording** and **Stop / save** control SteamFlow Recorder directly, so it's the same recorder with your same settings, not a second one.
- **Mark highlight** saves a rough timestamp of the current recording to `~/Videos/SFRecorder/HeyFrame_markers_YYYY-MM-DD.txt`, so you can find the good moments later when editing.
- **Take VR screenshot** asks SteamVR for a stereo screenshot, which should end up in `~/Pictures/HeyFrame`. I still need to confirm this one properly on the headset.

Once you turn listening on, it'll start by itself every time you boot, so you only have to do it once. If you prefer Konsole, `~/.local/bin/hey-frame start` and `~/.local/bin/hey-frame stop` do the same thing.

One thing worth knowing: if you have another dictation add-on running, Hey Frame won't start. There's a known issue on the Frame where dictation add-ons can grab the Volume Up button, and I didn't want to make that worse. Hey Frame itself never reads your controllers or input devices.

## Voice commands

Say "Hey Frame" and then the command. Shorter commands get picked up more reliably than long ones. You can optionally enable GLaDOS Mode for sarcastic replies while keeping the same actions.

| Say | What it does |
|---|---|
| "Start recording" | Starts SFRecorder with your usual settings |
| "Stop recording" | Stops and saves the recording |
| "Am I recording?" | Tells you if you're recording and for how long |
| "Mark this moment" | Saves a highlight timestamp while recording |
| "Take a screenshot" | Takes a stereo SteamVR screenshot |
| "How much battery is left?" | Headset battery, plus a time estimate when it has one |
| "Battery alerts on" | Warns you out loud at 20%, 10% and 5% |
| "Set a timer for ten minutes" | Starts a timer, up to 2 hours |
| "Timer remaining" / "Cancel timer" | Checks or cancels the timer |
| "Note to self test the new lens" | Saves a short note to `~/Documents/HeyFrame/notes.txt` |
| "Read last note" | Reads your last note back to you |
| "Tell me a joke" | A sarcastic lab AI joke |
| "Portal quote" / "GLaDOS quote" | A line from your own quotes file if you've added any, otherwise one of the built-in lines |
| "Personal quote" | Only from your own quotes file |
| "Open dashboard" | Opens the SteamVR dashboard |
| "Pause game" | Opens the SteamVR dashboard (see below, it doesn't actually pause the game) |
| "Resume game" | Tells you how to close the dashboard |

The older commands for date, uptime, free memory, storage and volume still work, I just don't focus on them anymore since recording and gaming is what I actually use it for.

### About pause and resume

I'd love for "pause game" to actually pause the game, but there's no clean way to do it right now. A SteamVR overlay can't press the menu button inside a VR game for you, because every game handles its pause button through its own bindings, and streamed flat games can use completely different ones. The only ways around that are things like faking a controller or grabbing input devices, and that's exactly the kind of thing that broke the Volume Up button with another dictation add-on, so I'm not doing it.

So for now "pause game" just opens the dashboard, and depending on the game it may or may not pause behind it. "Resume game" can't close the dashboard either, because OpenVR lets you open it but doesn't have a way to close it, so you'll need to press the Steam button. Proper pausing would need a tested setup for each game and that's not in this version.

## Adding your own Portal quotes

Hey Frame only comes with a handful of short familiar lines and some original GLaDOS-style jokes. I'm not shipping Portal dialogue or game audio with it, but you can add whatever quotes you want yourself on your headset. They stay on your headset and never end up on GitHub.

To add a few quotes in one go:

```bash
~/.local/bin/hey-frame add-quotes "Your first quote" "Your second quote" "Your third quote"
```

To import a whole text file, one quote per line (lines starting with # are skipped):

```bash
~/.local/bin/hey-frame import-quotes ~/Downloads/portal-quotes.txt
```

Or you can paste a bunch of lines straight into Konsole like this:

```bash
~/.local/bin/hey-frame import-quotes - <<'QUOTES'
Your first personal quote goes here.
Your second quote goes here.
Your third quote goes here.
QUOTES
```

If you just want to add one, `hey-frame add-quote "Your quote"` still works. Importing keeps your existing quotes and skips duplicates (it ignores capitalization), and if a batch would take you over the limit it gets rejected without changing anything. After that just say "Hey Frame, Portal quote" or "Hey Frame, personal quote". No restart needed, it picks up changes on the next command.

To find or check the file:

```bash
~/.local/bin/hey-frame quotes-path
~/.local/bin/hey-frame list-quotes
```

The file lives at `~/.config/hey-frame/portal-quotes.txt`. You can have up to 200 quotes, each up to 350 characters. Updates won't overwrite it and it's never sent anywhere. The voice reads your quotes using the synthetic voice, it doesn't play Valve's original audio.

## False wake-ups and dashboard listening control

Version 0.6.3 tightens wake-word detection: the wake phrase must be heard consistently for five consecutive non-silent audio frames (about half a second), rather than acting on two short, potentially false partial recognitions. This reduces false triggers but may require a more deliberate "Hey Frame" and cannot entirely eliminate false positives from background conversations.

The separate SteamVR **Hey Frame** dashboard has an explicit **LISTEN: OFF** button when listening is active. Unlike a general toggle, this STOP action remains available during other dashboard work, calls `systemctl --user disable --now hey-frame.service` directly and checks that the service actually stopped. If the dashboard itself is missing, open Konsole and run the same command to stop the microphone immediately.

A new installation does not activate listening automatically. Existing listening preferences are preserved when updating, so **manually stop listening before updating if you want it to stay off**.

## Short voice command recognition

Version 0.6.2 fixes one-breath commands that could be dropped during the switch from the wake word recognizer to the command recognizer. It also adds a small, focused recognizer for **"Hey Frame, portal quote"**, **"Hey Frame, sarcastic mode"** and **"Hey Frame, normal mode"**. Regular dictation, notes, recording commands and timers still use the unrestricted recognizer.

For best results, say **"Hey Frame"**, pause briefly, then say **"portal quote"** or **"sarcastic mode"**. This updated recognition has automated tests but still needs testing with the physical headset microphone.

If a command still comes back as unrecognized, you can temporarily enable **ASR text diagnostics** by adding `HEY_FRAME_DEBUG_TRANSCRIPTS=1` to `~/.config/hey-frame/settings.env` and restarting `hey-frame.service`. Its recognized words are then written to the user service journal, so **turn this off after testing** if you speak private notes. No recordings are saved and logging is off by default.

## Optimization-focused v0.6.4 candidate

This branch is an **optimization-only development version**, not a new feature release. It has not been validated on physical Steam Frame hardware yet. The current v0.6.3 release remains available.

- **Lower idle native-memory footprint:** The GLaDOS synthesizer is no longer loaded when the listening service starts. It loads on the first spoken reply, stays warm briefly for subsequent requests, and exits after 90 seconds of inactivity. This means the **first reply after idle may be slower**.
- **Less CPU activity in silence:** After around one second of low-level PCM, the Vosk wake recognizer stops processing empty chunks until microphone activity returns. Existing five-frame wake confirmation remains intact.
- **Less repeated allocation:** Reuse the Vosk wake recognizer through its native `Reset()` method.
- **Faster dashboard toggle:** Starting listening no longer reloads/test-runs every speech model. It still refuses to start alongside `frame-dictation.service` and checks the listener's actual service state.
- **Less polling:** A hidden SteamVR dashboard checks listening/personality state less frequently.
- **Safer upgrades:** Download and validate a staging copy **before** stopping the current listener; restore its previous source if installation fails. A running dashboard service is restarted so it gets the updated code.
- **Better resource measurements:** The benchmark now periodically samples the listener **and its child microphone/voice processes**, plus the SteamVR tab service when running.

This does **not** add passthrough controls, dictation, PC integrations, macros, or an LLM; preserving existing functionality and hardware safety is the purpose of this release.

### Memory versus response speed

By default (`HEY_FRAME_FAST_VOICE=1`), the voice loads **on demand** and unloads after 90 seconds without a spoken reply. You can adjust the idle timeout by putting `HEY_FRAME_VOICE_IDLE_SECONDS=120` in `~/.config/hey-frame/settings.env`. Supported values are clamped to 30–600 seconds.

For the **lowest idle memory consumption**, set `HEY_FRAME_FAST_VOICE=0`. Then each reply uses a short-lived speech worker (slower, but it leaves no resident model between replies). To disable the voice filter, use `HEY_FRAME_VOICE_STYLE=clean`.

After editing that settings file, restart the listener with `systemctl --user restart hey-frame.service` only if it is currently running; restarting does not re-enable an intentionally disabled service.

### Measure CPU and RAM on the actual headset

```bash
~/.local/bin/hey-frame benchmark --seconds 30
```

Run once after startup without speaking, again just after requesting a spoken reply, and again after at least 90 seconds of silence. Keep the same game/SteamVR conditions for comparisons. CPU is **% of one core**, even on a multicore headset. Memory is sampled **RSS summed across processes**, not proportional shared memory, and the tool does not directly measure battery life, GPU load or game FPS.

Review [OPTIMIZATION-REPORT.md](OPTIMIZATION-REPORT.md) for validation and test limitations.

## Troubleshooting

These are the commands I use to check that everything is working:

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

If you want to see what it's hearing and doing live, stop the background service and run it in the terminal:

```bash
~/.local/bin/hey-frame stop
~/.local/bin/hey-frame run
```

Ctrl+C gets you out, and `~/.local/bin/hey-frame start` turns the background service back on. The service logs are in `journalctl --user -u hey-frame.service -n 80 --no-pager`. It only restarts by itself if it crashes, not if you exit it normally.

To uninstall Hey Frame and its dashboard tab (your quotes and notes are kept):

```bash
bash ~/.local/share/hey-frame-v3/uninstall.sh
```

## Privacy and how it works

- It installs as user services only, nothing system-wide, and it doesn't change your input or volume settings.
- Once it's installed it doesn't need the internet. The speech recognition and the voice both run on the headset.
- It only does the commands listed above, nothing else. Recording goes through SFRecorder's own private socket, not through a shell or a separate recorder.
- The dashboard tab talks to Hey Frame through its own private socket and can only open the dashboard or take a screenshot. Both sockets are only accessible to your user.
- Notes and highlight markers are only saved when you ask for them. It doesn't keep recordings of what you say.
- It's still experimental. The automated tests pass, but that's not the same as testing it on a real Frame, so things like timing, how different games behave, battery drain and recording reliability still need to be checked on the headset.

For more on the recording side, and the licenses for Vosk and sherpa-onnx, check out [SteamFlow Recorder](https://github.com/SteamFlowYT/SFRecorder).
