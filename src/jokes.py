"""Original lab-AI humour, brief Portal excerpts and user-owned personal quotes.

Long or additional copyrighted excerpts are never shipped. A user can maintain
quotes in their own private config file. Nothing syncs or leaves the device.
"""
from __future__ import annotations
from pathlib import Path
import os
import random

ORIGINAL_JOKES = (
    'I ran a test of your reflexes. The results are classified as decorative.',
    'Good news. Your headset works. Your decision making remains under review.',
    'Why did the test subject cross the room? The portal was out of service.',
    'Your gaming performance is statistically significant. Unfortunately, not in a useful direction.',
    'I have calculated your odds of winning. I chose not to display them for morale reasons.',
    'There are no mistakes in science. Only surprisingly expensive learning opportunities.',
    'Achievement unlocked: breathing successfully while wearing a computer.',
    'I would applaud your progress, but my engineers wisely omitted hands.',
    'Congratulations on surviving another round. I will update my projections.',
    'I would offer a tutorial. But you seem committed to discovering the worst possible strategy.',
)
ORIGINAL_LINES = (
    'Welcome back, test subject. I have reduced the danger estimate to merely concerning.',
    'This headset is your laboratory now. Please try not to lick the equipment.',
    'Your continued survival remains one of the more surprising test results.',
    'System operational. Optimism module still missing.',
    'A reminder: sarcasm is a feature, not a malfunction.',
)
SHORT_PORTAL_QUOTES = ('The cake is a lie.', 'This was a triumph.', 'Oh. It\'s you.', 'You monster.')
MAX_QUOTES = 200
MAX_LENGTH = 350


def quotes_path() -> Path:
    """User-editable text file; one quote per line; # comments ignored."""
    config_home = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    return config_home / 'hey-frame' / 'portal-quotes.txt'


def personal_quotes(path: Path | None = None) -> list[str]:
    target = path or quotes_path()
    try:
        if target.stat().st_size > 128 * 1024:
            return []
        lines = target.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError):
        return []
    return [s for s in (line.strip() for line in lines) if s and not s.startswith('#') and len(s) <= MAX_LENGTH][:MAX_QUOTES]


def _clean_quote(value: str, index: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f'Quote {index} is not text.')
    if '\x00' in value:
        raise ValueError(f'Quote {index} contains a NUL character.')
    text = ' '.join(value.split())
    if len(text) > MAX_LENGTH:
        raise ValueError(f'Quote {index} is too long (maximum {MAX_LENGTH} characters).')
    return text


def add_quotes(lines, path: Path | None = None) -> tuple[int, int]:
    """Import a batch of personal quotes with deduplication and atomic replacement.

    Empty lines and lines beginning with # are ignored. All input is validated
    BEFORE writing so a bad line doesn't result in half an import.
    Returns (new_quotes_added, duplicates_skipped).
    """
    from tempfile import NamedTemporaryFile

    target = path or quotes_path()
    if target.is_symlink():
        raise ValueError('Personal quotes file cannot be a symlink.')
    if target.exists():
        try:
            if target.stat().st_size > 128 * 1024:
                raise ValueError('Personal quotes file is too large.')
            old = target.read_text(encoding='utf-8')
        except UnicodeError as exc:
            raise ValueError('Personal quotes must be UTF-8 text.') from exc
    else:
        old = '# Your own Portal lines, one per line. Stored only on this headset.\n'

    existing = personal_quotes(target)
    normalized = {quote.casefold() for quote in existing}
    # Do not silently overwrite hand-edited files that exceed supported limits.
    if len(existing) >= MAX_QUOTES:
        raise ValueError('Personal quote limit reached (200).')
    additions: list[str] = []
    duplicates = 0
    for index, raw in enumerate(lines, start=1):
        line = _clean_quote(raw, index)
        if not line or line.startswith('#'):
            continue
        key = line.casefold()
        if key in normalized:
            duplicates += 1
            continue
        if len(existing) + len(additions) >= MAX_QUOTES:
            raise ValueError('Import would exceed the 200-quote limit. No changes were made.')
        additions.append(line)
        normalized.add(key)

    if not additions:
        return 0, duplicates

    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Write in the destination directory, then replace in one filesystem operation
    # so the running voice assistant never reads a half-imported quote.
    temporary = None
    try:
        with NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                prefix='.portal-quotes-', delete=False) as out:
            temporary = Path(out.name)
            out.write(old)
            if old and not old.endswith('\n'):
                out.write('\n')
            for line in additions:
                out.write(line + '\n')
        temporary.chmod(0o600)
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return len(additions), duplicates


def add_quote(text: str, path: Path | None = None) -> Path:
    """Backward-compatible single-quote command, implemented as a batch of one."""
    line = _clean_quote(text, 1)
    if not line or line.startswith('#'):
        raise ValueError('Quote must be 1 to 350 characters and not start with #.')
    target = path or quotes_path()
    add_quotes([line], target)
    return target


def import_quotes(source: str, path: Path | None = None) -> tuple[int, int]:
    """Read a UTF-8 text file, or '-' for stdin, and import all its quote lines."""
    import sys

    limit = 128 * 1024
    if source == '-':
        data = sys.stdin.read(limit + 1)
        if len(data.encode('utf-8')) > limit:
            raise ValueError('Quote import exceeds the 128 KiB limit.')
    else:
        file = Path(source).expanduser()
        if not file.is_file():
            raise ValueError(f'Quote file not found: {file}')
        if file.stat().st_size > limit:
            raise ValueError('Quote import exceeds the 128 KiB limit.')
        try:
            data = file.read_text(encoding='utf-8')
        except UnicodeError as exc:
            raise ValueError('Quote import file must be UTF-8 text.') from exc
    return add_quotes(data.splitlines(), path)


def pick(category: str, path: Path | None = None) -> str:
    if category == 'joke':
        return random.choice(ORIGINAL_JOKES)
    if category in ('quote', 'personal_quote'):
        own = personal_quotes(path)
        if category == 'personal_quote':
            return random.choice(own) if own else 'No personal quotes yet. Add them in the Hey Frame quotes file.'
        # Prefer actual user quotes when available; otherwise use short built-in lines.
        return random.choice(own) if own else random.choice(SHORT_PORTAL_QUOTES + ORIGINAL_LINES)
    raise ValueError('Unknown line category')
