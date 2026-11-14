# Hey Frame v0.6.4 — Optimization audit

**Scope:** A lightweight, reliable optimization-only candidate, based on Hey Frame v0.6.3. No new voice commands, no arbitrary OS commands, no new hardware-button handling, and no changes to the SFRecorder control protocol.

**Status:** Automated Linux CI validates the code path and mocked installation. Real Steam Frame (ARM64) resource measurements, wake recognition, dashboard input and VR interaction are **not yet verified**. This is a development branch, not a measured performance claim.

## Code audit: findings and changes

| Area | v0.6.3 behavior / risk | v0.6.4 change | Trade-off / validation |
|---|---|---|---|
| Voice memory | On service start, persistent sherpa-onnx TTS worker loaded and held model for the entire session even if never used | Lazy-load on first reply; automatically terminate worker after 90s unused | Lower idle model residency expected; first spoken response after idle can be slower |
| Warm worker failure | A broken warm subprocess could leave a voice reply unsaid | Close failed warm worker, throttle restarts for 300s and retry one-shot synthesis | Failure still possible if the model itself is broken |
| Idle wake CPU | Vosk was fed around ten chunks per second even with silent microphone PCM | After ten quiet chunks, suspend recognition until real sound is detected | Must verify wake sensitivity against the real microphone noise floor |
| Native recognizer churn | A new constrained wake recognizer was created after each command | Reuse native Vosk KaldiRecognizer via its documented Reset method | Tested with fakes; ARM64 validation recommended |
| Dashboard startup | Start-listening button executed heavy model, speech and microphone diagnostics on every click | Direct systemd activation after the installer's validation, with a competing-dictation guard | A newly corrupted install could fail on service launch; dashboard reports status |
| Dashboard hidden polling | Two systemctl checks every 2 seconds while the tab was hidden | Hidden poll interval increased to ten seconds | Delayed indicator updates while hidden; visible panel remains responsive |
| Dashboard start/stop race | An emergency STOP could race with an in-progress START | Serialize service activation/stop operations using a lock | STOP is still available while unrelated dashboard work is busy |
| Installer disruption | Stopped a functioning listener before model downloads and validation | Stage replacement Python source, validate dependencies/models/voice before stopping, and preserve source backup until success | Does not fully snapshot every generated unit file; OS-level installer failure still warrants testing |
| Dashboard stale code | An already-running SteamVR dashboard remained on old Python code after an update | Restart the dashboard service after installing new code | Momentarily closes its tab on upgrade |
| Benchmark accuracy | Measured the main PID only, excluding native voice worker, pw-record and dashboard | Sample listener descendant processes and the dashboard periodically | Summed RSS double-counts shared pages; sampling can miss short-lived processes |

## What was intentionally *not* changed

- Mic stays controlled by user-service state; voice responses still stop the microphone stream to prevent self-activation.
- Existing five-frame wake-word confirmation remains in place.
- Command recognition stays offline through Vosk. No new LLM runtime or expensive vision model.
- Recording is handled only via SFRecorder's local socket. No duplicate recording process.
- Existing GLaDOS mode, quotes, private notes, timers, safe read-only queries, and dashboard controls remain.
- No volume changes, controller-input injection or background cloud service.

## Benchmarks to run on a physical Steam Frame

Install or test the candidate carefully and compare against a controlled baseline. Keep the same SteamVR state, power source, battery level range, scene, streaming status and microphone route.

1. **Idle:** After opening SteamVR, wait 120 seconds without asking for anything. Run `hey-frame benchmark --seconds 30`. Note sampled CPU (% of one core), total RSS and process count.
2. **First voice reply:** Say `Hey Frame, battery` and review `journalctl --user -u hey-frame.service -n 50 --no-pager` for `Speech timing`. Note responsiveness and whether it triggers correctly.
3. **Warm reply:** Ask again within 20 seconds; compare logged synthesis time.
4. **Unload:** Wait 100 seconds without voice requests. Benchmark again. The separate native voice-worker process should be gone.
5. **False activation:** Test in a quiet room, with speakers/game audio playing, and during natural conversation. Count false wakeups over the same observation period.
6. **Dashboard:** Start and stop listening while recording and while the dashboard is busy; verify Stop wins and the service stays disabled across reboot.
7. **Update failure:** On a non-production copy, simulate failing model validation and confirm the previous listener/source remains intact.

The benchmark reads sampled Linux process CPU and RSS. It **does not measure battery drain, FPS, GPU utilization, thermal throttling or the system's unique proportional memory (PSS)**. Don't turn a short benchmark into claims of battery-life improvements.

## Release criteria

- All existing and new CI tests pass on the candidate commit.
- Real headset wake-word and microphone behavior remain acceptable.
- No new persistent child processes after 90 seconds idle.
- Dashboard STOP works, including during a pending START.
- Record start/stop/status still work with the installed SFRecorder.
- A/B measurements recorded for CPU and memory before claiming numerical gains.
- Publish a GitHub release **only after** hardware smoke testing; keep v0.6.3 stable until then.

## Further work (not included in this optimization candidate)

A dedicated wake-word model could reduce false positives from the extremely constrained two-word Vosk grammar, but it requires ARM64 benchmarking and user-spoken samples before replacing a working recognizer. Likewise, redesigning the FFT-based synthetic-voice filter or swapping the native TTS model could affect audio quality. Neither is a risk worth taking in an unmeasured optimization release.
