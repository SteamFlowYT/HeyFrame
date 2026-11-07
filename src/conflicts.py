"""Detect potentially competing Steam Frame dictation software, read-only."""
from __future__ import annotations
from pathlib import Path
import shutil
import subprocess


def frame_dictation_active() -> bool:
    """This older third-party service can grab gpio-keys and swallow Volume Up.

    Some newer versions forward the key, but multiple microphone daemons can
    still conflict. Never stop/disable another developer's service automatically.
    """
    binary = shutil.which('systemctl') or ('/usr/bin/systemctl' if Path('/usr/bin/systemctl').exists() else None)
    if not binary:
        return False
    try:
        r = subprocess.run([binary, '--user', 'is-active', '--quiet', 'frame-dictation.service'],
                           timeout=3, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


WARNING = ('Another headset dictation daemon, frame-dictation.service, is running. '
           'Older versions grabbed gpio-keys and disabled physical Volume Up. '
           'Stop that service before starting Hey Frame; this app will not stop it for you.')
