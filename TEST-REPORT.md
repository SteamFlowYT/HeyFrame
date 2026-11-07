# Hey Frame 0.3.0 — test and implementation report

Date: November 3, 2026. Development platform: Linux x86_64 Python 3.13.5 (not a Steam Frame).

## Findings from prior releases

- v0.1/v0.1.1: pip's binary-only install policy prevented installation of Vosk's source-distributed `srt` dependency; the first build also did not explicitly install NumPy for TTS.
- v0.2: fixed the dependency pinning but used a large fixed command grammar rather than normal dictation after the wake word; a model import check alone was insufficient proof of real recognition. It also lacked end-to-end microphone testing before enabling the user service.
- A physical Volume Up button ceased working on the user's headset while Volume Down still worked. Source inspection of v0.1 and v0.2 found no Linux input grabs, uinput, controller event interception, or volume writes in Hey Frame. An **exact symptom match** was found in `khvn26/steam-frame-dictation` GitHub issue #1, and PR #2 documented the cause: exclusive `EVIOCGRAB` of `gpio-keys` consumed `KEY_VOLUMEUP` while the separate Volume Down device remained functional. If that separate service was installed, it is a credible direct explanation. However, we cannot establish that the user installed it, and Hey Frame itself did not call `EVIOCGRAB`. This release does not access any hardware buttons.

## Test coverage

The project includes 44 Python automated tests, run with `python -m unittest discover -s tests -v`:

- Headset-vs-controller battery selection, charging, unavailable/invalid battery data and time estimate behaviour
- Spoken command routing, time, date, Wi-Fi signal privacy, read-only SteamVR / volume queries, timer parsing and upper bounds
- Wake-only, one-breath command, pause-then-command, partial false-positive, timeout, and rejected command cases using a fake Vosk recognizer
- Persistent timer atomic file and corrupted-state protection
- Known external input-device conflict detection and safe refusal to start when a competing daemon is active
- Fake waveform-to-WAV generation through a mocked sherpa-onnx native API with NumPy
- HEV-inspired voice radio filter numerical range
- Engine timer expiry, failure to reopen microphone after shutdown, battery-warning deduplication, limited retries on microphone errors
- Installer stubbed clean-install path: new user unit remains disabled; old install files unchanged
- Installer stubbed `pip` failure: prior launcher preserved, no partially activated service installed
- Python syntax, shell script syntax, CLI command dispatch, process CPU/RSS parser and read-only sampler

Also verified zip checksum/structure after packaging.

## On-device validation deliberately NOT claimed

Physical Steam Frame ARM64 validation has **not** been performed, including real Vosk wake sensitivity under game audio, microphone source name, PipeWire routing under SteamVR, exact model inference performance, the sherpa-onnx ARM64 library's behaviour on SteamOS, screen-off/suspend state, CPU use and battery drain. An automated test with mocked native speech APIs cannot prove those work. The installer now performs real model imports AND initialization, microphone stream sampling and real TTS generation on the headset before enabling listening.

## Primary third-party references

- `https://github.com/alphacep/vosk-api` and `https://alphacephei.com/vosk/models`
- `https://github.com/k2-fsa/sherpa-onnx` voice model: `vits-piper-en_US-glados`
- `https://github.com/baketnk/frame-yap` battery discovery method
- `https://github.com/khvn26/steam-frame-dictation` Steam Frame PipeWire recording invocation

No existing Half-Life game recordings or voice assets are included.