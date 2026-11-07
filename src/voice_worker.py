"""One-shot voice synthesizer, called only after a request (or self-test)."""
import sys
from pathlib import Path
from voice import synthesize, VOICE_NAME


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: voice_worker.py WAV_PATH TEXT')
    base = Path(__file__).resolve().parent.parent
    synthesize(sys.argv[2],Path(sys.argv[1]),base/'models'/VOICE_NAME)

if __name__ == '__main__':
    main()
