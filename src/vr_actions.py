"""Send narrow, local-only requests to the Hey Frame SteamVR dashboard.

No controller injection, no input grabs, no arbitrary command execution.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket

ALLOWED = {'open_dashboard', 'screenshot', 'recenter_view'}


def socket_path() -> Path:
    return Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}') / 'hey-frame' / 'vr-dashboard.sock'


def request(action: str, path: Path | None = None, timeout: float = 1.5) -> str:
    if action not in ALLOWED:
        raise ValueError('Unsupported SteamVR dashboard action')
    target = path or socket_path()
    if not target.is_socket():
        return 'Hey Frame dashboard is offline. Install the dashboard and open SteamVR.'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(target))
            client.sendall((action + '\n').encode('ascii'))
            raw = client.recv(2048)
        result = json.loads(raw.decode('utf-8'))
        if isinstance(result, dict) and isinstance(result.get('message'), str):
            return result['message'][:250]
    except (OSError, ValueError, UnicodeError):
        pass
    return 'SteamVR dashboard did not respond.'
