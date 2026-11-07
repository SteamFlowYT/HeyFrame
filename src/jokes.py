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


def add_quote(text: str, path: Path | None = None) -> Path:
    """Add a quote explicitly supplied by the owner; no arbitrary filenames."""
    line = ' '.join(text.split())
    if not line or len(line) > MAX_LENGTH or '\x00' in line or line.startswith('#'):
        raise ValueError('Quote must be 1 to 350 characters and not start with #.')
    target = path or quotes_path()
    if len(personal_quotes(target)) >= MAX_QUOTES:
        raise ValueError('Personal quote limit reached (200).')
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not target.exists():
        target.write_text('# Your own Portal lines, one per line. Stored only on this headset.\n', encoding='utf-8')
        target.chmod(0o600)
    with target.open('a', encoding='utf-8') as out:
        out.write(line + '\n')
    return target


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
