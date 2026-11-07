"""Atomic, privacy-light timer state surviving a background-service restart."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import time


def state_path() -> Path:
    # No transcript or microphone data is persisted.
    root = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    return root / 'hey-frame' / 'timer.json'


def load_deadline(path: Path, now=None) -> float | None:
    now = time.time() if now is None else now
    try:
        data = json.loads(path.read_text())
        value = data.get('deadline')
        if isinstance(value, (float, int)) and not isinstance(value, bool) and now - 86400 < value < now + 7201:
            return float(value)
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return None


def save_deadline(path: Path, deadline: float | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if deadline is None:
        path.unlink(missing_ok=True)
        return
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', prefix='.timer-', suffix='.json',
                                     dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        os.chmod(tmp, 0o600)
        json.dump({'deadline': float(deadline)}, f)
        f.write('\n')
    os.replace(tmp, path)
