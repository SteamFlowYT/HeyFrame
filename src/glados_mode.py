"""Optional, persistent GLaDOS-style response personality.

Only changes what the assistant says. Command execution, actual status values
and failures remain unchanged. No game audio, controller access or network use.
Original quips were supplied by the Hey Frame project owner.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import tempfile

MODES = ("normal", "glados")

# Short asides keep the verified result first and avoid unnecessary TTS delay.
ASIDES = {
    "record_start": (
        "Try to do something worth watching this time.",
        "This next session will be monitored, evaluated, and quietly mocked.",
    ),
    "record_stop": (
        "Your reaction time has been recorded for future disappointment.",
        "Science requires sacrifice. Today, that sacrifice is your free time.",
    ),
    "record_status": (
        "I have analyzed your gameplay. The data suggests you should consider a different hobby.",
        "Your reaction time has been recorded for future disappointment.",
    ),
    "mark_moment": (
        "Please hold still while I pretend to care about your highlights.",
        "Congratulations. You pressed a button. I will notify the scientific community.",
    ),
    "screenshot": (
        "Congratulations. You pressed a button. I will notify the scientific community.",
        "Please hold still while I pretend to care about your highlights.",
    ),
    "battery": (
        "Do not worry about the battery. Worry about what happens when it reaches zero.",
        "Your battery is draining faster than my patience. Impressive, given how little patience I have.",
    ),
    "set_timer": (
        "When it ends, nothing exciting will happen. Much like your aim.",
        "Your reaction time has been recorded for future disappointment.",
    ),
    "timer_status": (
        "For the record, I am not sarcastic. I am accurately unimpressed.",
    ),
    "cancel_timer": (
        "Science requires sacrifice. Today, that sacrifice is your free time.",
    ),
    "save_note": (
        "Excellent. Another test subject who talks to his headset.",
    ),
    "last_note": (
        "For the record, I am not sarcastic. I am accurately unimpressed.",
    ),
    "status": (
        "This next session will be monitored, evaluated, and quietly mocked.",
    ),
    "open_dashboard": (
        "Congratulations. You pressed a button. I will notify the scientific community.",
    ),
    "pause_game": (
        "You have been in VR for a while. Your real room misses you. I do not.",
    ),
    "resume_game": (
        "Your real room misses you. I do not.",
    ),
    "alerts_on": (
        "Do not worry about the battery. Worry about what happens when it reaches zero.",
    ),
    "help": (
        "I would offer you cake, but the testing budget went to lens inserts.",
    ),
}
GENERIC_ASIDES = (
    "For the record, I am not sarcastic. I am accurately unimpressed.",
    "Excellent. Another test subject who talks to his headset.",
    "Science requires sacrifice. Today, that sacrifice is your free time.",
    "I would offer you cake, but the testing budget went to lens inserts.",
)

# Never make a failed operation sound successful. These actions must contain
# their verified result. If the recorder bridge is down, say so plainly.
SUCCESS_PREFIXES = {
    "record_start": ("recorder started", "recording started"),
    "record_stop": ("stopping recording", "recording stopped", "recording finished"),
    "mark_moment": ("highlight marked",),
    "screenshot": ("screenshot requested",),
    "set_timer": ("timer set",),
    "save_note": ("note saved",),
    "open_dashboard": ("dashboard opened",),
    "pause_game": ("dashboard opened",),
}
FAILURE_MARKERS = (
    "unavailable", "not connected", "not responding", "could not",
    "unable", "failed", "not recognized", "not installed", "no timer",
    "no recording", "nothing to mark", "did not", "error:", "try:",
)


def mode_path() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "hey-frame" / "mode.json"


def get_mode(path: Path | None = None) -> str:
    """Missing or invalid preference files are normal mode, never a crash."""
    path = path or mode_path()
    try:
        if path.stat().st_size > 2048:
            return "normal"
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("mode") if isinstance(data, dict) else None
        return value if value in MODES else "normal"
    except (OSError, ValueError, UnicodeError):
        return "normal"


def set_mode(mode: str, path: Path | None = None) -> str:
    if mode not in MODES:
        raise ValueError("Mode must be normal or glados.")
    path = path or mode_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked mode file.")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".hey-frame-mode-", delete=False,
        ) as out:
            temporary = Path(out.name)
            json.dump({"mode": mode}, out)
            out.write("\n")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return mode


def decorate(action: str, response: str, mode: str | None = None,
             chooser=None) -> str:
    """Append a sarcastic aside while preserving the unmodified factual reply.

    Error and safety messages remain completely plain. No speech for these
    commands is altered: quotes, jokes, shutdown, and low-battery alarms.
    """
    if (mode if mode is not None else get_mode()) != "glados":
        return response
    if action in ("joke", "quote", "personal_quote", "shutdown", "mode_on",
                  "mode_off", "mode_status", "unknown"):
        return response
    short = response.strip()
    lower = short.casefold()
    if not short or len(short) > 260 or any(term in lower for term in FAILURE_MARKERS):
        return response
    starts = SUCCESS_PREFIXES.get(action)
    if starts is not None and not lower.startswith(starts):
        return response
    # If charging, never say the headset is draining.
    choices = ASIDES.get(action, GENERIC_ASIDES)
    if action == "battery" and "charging" in lower:
        choices = choices[:1]
    chooser = chooser or random.choice
    aside = chooser(choices)
    return response + " " + aside if len(response) + len(aside) + 1 <= 350 else response
