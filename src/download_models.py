"""Download only known upstream model archives; reject unsafe archive paths."""
from pathlib import Path
from urllib.request import urlretrieve
import shutil
import tarfile
import tempfile
import zipfile

MAX_UNPACKED_BYTES = 450 * 1024 * 1024  # stop accidental archive bombs

MODEL_URLS = {
    'vosk-model-small-en-us-0.15': 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip',
    'vits-piper-en_US-glados': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-en_US-glados.tar.bz2',
}


def _validate(name: str, root_name: str):
    # Tar tools may prefix a safe path with ./, but cannot traverse upward.
    while name.startswith('./'):
        name = name[2:]
    p = Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != root_name:
        raise ValueError(f'Invalid model archive path: {name!r}')


def _extract_zip(archive: Path, output: Path, root_name: str):
    with zipfile.ZipFile(archive) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED_BYTES:
            raise ValueError('ZIP model is unexpectedly large')
        for entry in z.infolist():
            _validate(entry.filename, root_name)
            mode = (entry.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError('Symlinks not permitted in model archives')
        z.extractall(output)


def _extract_tar(archive: Path, output: Path, root_name: str):
    with tarfile.open(archive, 'r:bz2') as t:
        if sum(i.size for i in t.getmembers() if i.isfile()) > MAX_UNPACKED_BYTES:
            raise ValueError('TAR model is unexpectedly large')
        for entry in t.getmembers():
            _validate(entry.name, root_name)
            if not (entry.isfile() or entry.isdir()):
                raise ValueError(f'Unexpected archive entry type: {entry.name}')
        for entry in t.getmembers():
            target = output / entry.name
            if entry.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with t.extractfile(entry) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)


def ensure_models(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        output = destination / name
        valid = (output / 'am/final.mdl').is_file() and (output / 'am/final.mdl').stat().st_size > 1048576 if name.startswith('vosk') else \
                (output / 'en_US-glados.onnx').is_file() and (output / 'en_US-glados.onnx').stat().st_size > 1048576 and (output / 'tokens.txt').is_file() and \
                (output / 'espeak-ng-data').is_dir()
        if valid:
            print(f'Model already present: {name}', flush=True)
            continue
        if output.exists():
            raise RuntimeError(f'Incomplete model folder at {output}; remove it before retrying')
        print(f'Downloading {name} from {url}', flush=True)
        with tempfile.TemporaryDirectory(prefix='hey-frame-download-') as tmp:
            tmp = Path(tmp)
            archive = tmp / ('download.zip' if name.startswith('vosk') else 'download.tar.bz2')
            urlretrieve(url, archive)
            if name.startswith('vosk'):
                _extract_zip(archive, tmp, name)
            else:
                _extract_tar(archive, tmp, name)
            extracted = tmp / name
            if not extracted.is_dir():
                raise RuntimeError('Upstream model archive layout changed')
            shutil.move(str(extracted), str(output))
            print(f'Installed {name}', flush=True)


if __name__ == '__main__':
    import sys
    ensure_models(Path(sys.argv[1]))
