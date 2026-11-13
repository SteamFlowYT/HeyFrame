"""Opt-in, non-destructive local game launching and file exports.

Games: user-approved Steam app IDs, no arbitrary shell/process commands.
Exports: only regular media files from two fixed directories, with a user-
configured target. Originals never deleted or overwritten. No network service.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

MAX_ITEMS = 500
MAX_FILE = 8 * 1024**3
MEDIA_EXT = {'.mp4', '.mkv', '.webm', '.mov', '.png', '.jpg', '.jpeg', '.txt'}
GAME_NAME = re.compile(r'^[a-z0-9][a-z0-9 _-]{0,45}$', re.I)


def config_path() -> Path:
    base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return base / 'hey-frame' / 'workflows.json'


def read_config(path: Path | None = None) -> dict:
    target = path or config_path()
    try:
        if target.stat().st_size > 16384:
            return {}
        data = json.loads(target.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def write_config(config: dict, path: Path | None = None):
    target = path or config_path()
    if target.is_symlink():
        raise ValueError('Configuration file cannot be a symlink')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                dir=target.parent, prefix='.hey-frame-workflows-', delete=False) as output:
            name = Path(output.name)
            json.dump(config, output, indent=2)
            output.write('\n')
        name.chmod(0o600)
        name.replace(target)
    finally:
        if name and name.exists():
            name.unlink()


def add_game(name: str, app_id: str, path: Path | None = None) -> str:
    key = ' '.join(name.lower().split())
    if not GAME_NAME.fullmatch(key):
        raise ValueError('Game name must be 1-46 simple letters, digits, spaces, dash or underscore')
    if not app_id.isdecimal() or not (1 <= int(app_id) <= 9999999999):
        raise ValueError('Steam app ID must be a positive decimal number')
    data = read_config(path)
    games = data.get('games', {})
    if not isinstance(games, dict):
        games = {}
    if len(games) >= 32 and key not in games:
        raise ValueError('Maximum 32 allowed games')
    games[key] = str(int(app_id))
    data['games'] = games
    write_config(data, path)
    return f'Allowed game {key} with Steam app ID {games[key]}.'


def launch_game(name: str, path: Path | None = None, run=subprocess.Popen) -> str:
    key = ' '.join(name.lower().split())
    games = read_config(path).get('games', {})
    app_id = games.get(key) if isinstance(games, dict) else None
    if not isinstance(app_id, str) or not app_id.isdecimal():
        return 'That game is not configured. Add its Steam app ID first.'
    steam = shutil.which('steam')
    if not steam:
        return 'Steam launcher is not available.'
    try:
        run([steam, f'steam://rungameid/{app_id}'], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return f'Steam launch requested for {key}. The game may take a moment to open.'
    except OSError:
        return 'Unable to request game launch.'


def set_transfer_target(directory: str, path: Path | None = None) -> str:
    dest = Path(directory).expanduser()
    if not dest.is_dir() or dest.is_symlink():
        raise ValueError('Transfer destination must already exist and be a real directory')
    resolved = dest.resolve(strict=True)
    home = Path.home().resolve()
    if resolved == home or resolved == Path('/'):
        raise ValueError('Choose a dedicated destination folder, not your entire home or disk')
    data = read_config(path)
    data['transfer_target'] = str(resolved)
    write_config(data, path)
    return f'Transfer target saved: {resolved}. Files will be copied, never moved.'


def transfer_media(path: Path | None = None,
                   sources: tuple[Path, ...] | None = None,
                   max_items: int = MAX_ITEMS) -> str:
    configured = read_config(path).get('transfer_target')
    if not configured or not isinstance(configured, str):
        return 'No transfer destination configured. Set it in Konsole first.'
    dest = Path(configured)
    if not dest.is_dir() or dest.is_symlink() or str(dest.resolve()) != configured:
        return 'Transfer destination is unavailable. Connect or mount it first.'
    sources = sources or (Path.home() / 'Videos' / 'SFRecorder',
                          Path.home() / 'Pictures' / 'HeyFrame')
    originals = [source.resolve() for source in sources if source.is_dir()]
    if any(dest.resolve() == origin or dest.resolve().is_relative_to(origin)
           for origin in originals):
        return 'Transfer destination cannot be inside a source folder.'
    copied, skipped, errors = 0, 0, 0
    for source in sources:
        if not source.is_dir() or source.is_symlink():
            continue
        for file in sorted(source.iterdir()):
            if copied + skipped + errors >= max_items:
                return f'Transfer limit reached. Copied {copied}, skipped {skipped}, errors {errors}.'
            try:
                if (file.is_symlink() or not file.is_file() or
                        file.suffix.lower() not in MEDIA_EXT):
                    continue
                stat = file.stat()
                if stat.st_size > MAX_FILE:
                    skipped += 1
                    continue
                # Separate directories avoid recording/screenshot name collisions.
                folder = dest / ('recordings' if source.name.lower() == 'sfrecorder' else 'screenshots')
                folder.mkdir(parents=True, exist_ok=True)
                output = folder / file.name
                if output.exists():
                    skipped += 1
                    continue
                # Exclusive create prevents overwrites; remove partial file on failure.
                try:
                    with file.open('rb') as src, output.open('xb') as out:
                        shutil.copyfileobj(src, out, length=1024 * 1024)
                    # If source changed while copying, do not keep an incomplete export.
                    if file.stat().st_size != stat.st_size:
                        output.unlink(missing_ok=True)
                        errors += 1
                    else:
                        copied += 1
                except OSError:
                    output.unlink(missing_ok=True)
                    errors += 1
            except OSError:
                errors += 1
    return f'Transfer complete. Copied {copied} files, skipped {skipped}, errors {errors}. Originals kept.'
