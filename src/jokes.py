"""Short original laboratory-AI jokes, plus two brief recognizable Portal lines.

The original material is homage, not official GLaDOS dialogue or Valve audio.
"""
import random

ORIGINAL_JOKES = (
    'I ran a test of your reflexes. The results are classified as decorative.',
    'Good news. Your headset is functioning. The same cannot be said for your decision making.',
    'Why did the test subject cross the room? The portal was out of service.',
    'Your gaming performance is statistically significant. Unfortunately, not in a useful direction.',
    'I have calculated your odds of winning. I chose not to display them for morale reasons.',
    'Remember: there are no mistakes in science. Only surprisingly expensive learning opportunities.',
    'Achievement unlocked: breathing successfully while wearing a computer.',
    'You are doing science. It is going about as well as expected.',
    'I would applaud your progress, but my engineers wisely omitted hands.',
    'The experiment was a success. I will not disclose which experiment.',
)

ORIGINAL_LINES = (
    'Welcome back, test subject. I have reduced the danger estimate to merely concerning.',
    'This headset is your laboratory now. Please try not to lick the equipment.',
    'Your continued survival remains one of the more surprising test results.',
    'System operational. Optimism module still missing.',
    'I am pleased to report that you remain mostly biological.',
    'A reminder: sarcasm is a feature, not a malfunction.',
)

# Two tiny recognizable excerpts, NOT the game's dialogue database.
SHORT_PORTAL_QUOTES = ('The cake is a lie.', 'This was a triumph.')


def pick(category: str) -> str:
    if category == 'joke':
        return random.choice(ORIGINAL_JOKES)
    if category == 'quote':
        return random.choice(SHORT_PORTAL_QUOTES + ORIGINAL_LINES)
    raise ValueError('Unknown line category')
