"""One-shot / persistent offline TTS worker.

The long-lived mode only runs under Hey Frame's own user service, never as a
network service. Incoming paths are created by the trusted local parent app.
"""
from __future__ import annotations
import json
from pathlib import Path
import sys
from voice import create_engine, synthesize, synthesize_with_engine, VOICE_NAME


def main():
    model_dir = Path(__file__).resolve().parent.parent / 'models' / VOICE_NAME
    if len(sys.argv) == 2 and sys.argv[1] == '--server':
        try:
            engine, options = create_engine(model_dir)
        except Exception as exc:
            print(json.dumps({'status': 'error', 'error': str(exc)[:180]}), flush=True)
            return 1
        print(json.dumps({'status': 'ready'}), flush=True)
        for line in sys.stdin:
            try:
                item = json.loads(line)
                if not isinstance(item, dict) or not isinstance(item.get('text'), str) or not isinstance(item.get('path'), str):
                    raise ValueError('Malformed speech request')
                synthesize_with_engine(item['text'], Path(item['path']), engine, options)
                result = {'status': 'ok'}
            except Exception as exc:
                result = {'status': 'error', 'error': str(exc)[:180]}
            print(json.dumps(result), flush=True)
        return 0
    if len(sys.argv) != 3:
        raise SystemExit('Usage: voice_worker.py WAV_PATH TEXT | --server')
    synthesize(sys.argv[2], Path(sys.argv[1]), model_dir)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
