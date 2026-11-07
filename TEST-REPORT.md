# Hey Frame v0.5 — validation report

Local verification: 72 passing unittest cases; Python `compileall`; bash `-n` on install/uninstall.

New automated coverage: voice command intent matching, two-stage recording marker status, locally persisted short notes, personal quotes file read/write and bounds, dedicated dashboard button layout, UNIX socket request/response, safe allowlisted actions, pause-game disclaimer, and voice-action dispatch.

Existing coverage: recognition state machine with mock Vosk, model checks, on-demand and warmed TTS with fake sherpa-onnx backend, installer failure handling, timer persistence, microphone lifecycle, recorder socket integration and NumPy radio filter.

**Limitations:** No physical Steam Frame was attached. OpenVR dashboard registration, screenshot compositor API, exact game pause, microphone routing, ARM64 performance and battery use are unverified. SteamVR documentation supports opening a dashboard, but does not document universal gamepad input injection or a matching HideDashboard call. No native game controller event emulation is implemented.
