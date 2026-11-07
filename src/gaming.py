"""Gaming-specific helpers: highlight marks, brief locally saved voice notes.

No game/controller injection and no access to other applications' recordings.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import re
from recording import request as recorder_request


def highlights_dir() -> Path:
    return Path.home() / 'Videos' / 'SFRecorder'


def mark_moment(status_provider=recorder_request, out_dir: Path | None = None, now=None) -> str:
    status = status_provider('status')
    match = re.search(r'Recording active\.\s*(\d+)\s*seconds captured', status, re.I)
    if not match:
        return 'Nothing to mark. Start a recording first.'
    directory = out_dir or highlights_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = now or datetime.now().astimezone()
        path = directory / f'HeyFrame_markers_{stamp:%Y-%m-%d}.txt'
        with path.open('a', encoding='utf-8') as stream:
            stream.write(f'{stamp:%Y-%m-%d %H:%M:%S} | approximate recording time {int(match.group(1))} seconds\n')
        return 'Highlight marked. Timestamp saved beside your recordings.'
    except OSError:
        return 'Unable to save highlight marker.'


def notes_path() -> Path:
    return Path.home() / 'Documents' / 'HeyFrame' / 'notes.txt'


def save_note(text: str, path: Path | None = None) -> str:
    note = ' '.join(text.split()).strip()
    if not note or len(note) > 160:
        return 'Notes must be 1 to 160 characters.'
    dest = path or notes_path()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('a', encoding='utf-8') as f:
            f.write(datetime.now().astimezone().strftime('%Y-%m-%d %H:%M') + ' | ' + note + '\n')
        return 'Note saved.'
    except OSError:
        return 'Unable to save note.'


def last_note(path: Path | None = None) -> str:
    try:
        lines = (path or notes_path()).read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError):
        return 'No notes saved yet.'
    for line in reversed(lines):
        if ' | ' in line:
            return 'Last note: ' + line.split(' | ', 1)[1][:160]
    return 'No notes saved yet.'
