"""Local-only, bounded IPC to the existing SteamFlow Recorder dashboard.

The recorder dashboard owns start/stop/save of its engine. Never spawn a
second recorder or manipulate its PID/temporary MP4 files.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket


def recorder_socket() -> Path:
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}')
    return runtime / 'sfrecorder' / 'voice-control.sock'


def request(command: str, socket_path: Path | None = None, timeout: float = 1.5) -> str:
    if command not in ('start', 'stop', 'status'):
        raise ValueError('Unsupported recorder command')
    path = socket_path or recorder_socket()
    if not path.is_socket():
        return 'SteamFlow Recorder is not connected. Update it and open SteamVR.'
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall(command.encode('ascii') + b'\n')
            data = client.recv(2048)
        reply = json.loads(data.decode('utf-8'))
        if not isinstance(reply, dict) or not isinstance(reply.get('message'), str):
            return 'Recorder did not return a valid status.'
        return reply['message'][:220]
    except (OSError, ValueError, UnicodeError, socket.timeout):
        return 'Recorder is not responding. Try reopening its SteamVR dashboard service.'
