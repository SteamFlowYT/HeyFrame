"""Offline speech playback with an on-demand, idle-reaped warm TTS worker.

Avoid keeping a large synthesizer in memory for hours when nobody is speaking.
Multiple nearby replies still share one worker. HEY_FRAME_FAST_VOICE=0 forces
the one-shot, minimum-idle-memory mode.
"""
from __future__ import annotations
import json
import logging
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import wave

VOICE_NAME = 'vits-piper-en_US-glados'
LOG = logging.getLogger('heyframe.voice')


def suit_filter(samples, sample_rate: int):
    """Efficient vectorized band-limiting, replacing a slow Python per-sample loop."""
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if not samples.size:
        return samples
    # Rounded second-order high/low-pass curves in frequency domain.
    # One FFT is dramatically faster than the prior sample-at-a-time filter.
    spectrum = np.fft.rfft(samples)
    frequencies = np.fft.rfftfreq(samples.size, 1.0 / sample_rate)
    low = 1.0 / (1.0 + (frequencies / 3800.0) ** 4) ** 0.5
    high = np.sqrt((frequencies / 120.0) ** 4 /
                   (1.0 + (frequencies / 120.0) ** 4))
    spectrum *= high * low
    filtered = np.fft.irfft(spectrum, n=samples.size).astype(np.float32)
    return (np.tanh(filtered * 1.28) / np.tanh(1.28)).astype(np.float32)


def create_engine(model_dir: Path):
    import sherpa_onnx
    model = model_dir / 'en_US-glados.onnx'
    tokens = model_dir / 'tokens.txt'
    data = model_dir / 'espeak-ng-data'
    if not (model.is_file() and tokens.is_file() and data.is_dir()):
        raise RuntimeError('The voice model files are missing or incomplete')
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(tokens), data_dir=str(data)),
            num_threads=2, provider='cpu'), max_num_sentences=1)
    if not config.validate():
        raise RuntimeError('Voice model configuration rejected by sherpa-onnx')
    return sherpa_onnx.OfflineTts(config), sherpa_onnx.GenerationConfig


def synthesize_with_engine(text: str, destination: Path, engine, config_factory):
    import numpy as np
    options = config_factory()
    options.speed = 1.08  # Faster speech cadence, independent of loading latency.
    options.silence_scale = 0.1
    audio = engine.generate(text[:350], options)
    samples = np.asarray(audio.samples, dtype=np.float32)
    if not samples.size:
        raise RuntimeError('No speech audio generated')
    if os.environ.get('HEY_FRAME_VOICE_STYLE', 'hev').lower() == 'hev':
        samples = suit_filter(samples, audio.sample_rate)
    try:
        gain = max(0.25, min(1.5, float(os.environ.get('HEY_FRAME_VOICE_GAIN', '1.0'))))
    except ValueError:
        gain = 1.0
    pcm = (np.clip(samples * gain, -1, 1) * 32767).astype('<i2').tobytes()
    with wave.open(str(destination), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(pcm)


def synthesize(text: str, destination: Path, model_dir: Path) -> None:
    engine, config_factory = create_engine(model_dir)
    synthesize_with_engine(text, destination, engine, config_factory)


class Speaker:
    def __init__(self, app_root: Path, fast: bool = False,
                 idle_timeout: float = 90.0, clock=time.monotonic):
        self.app_root = app_root
        self.fast = fast
        self.worker = None
        self.clock = clock
        self.idle_timeout = max(10.0, float(idle_timeout))
        self.last_activity = None
        self.retry_after = 0.0

    @staticmethod
    def _execute(args, timeout: int):
        try:
            subprocess.run(args, check=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Speech engine timed out') from None
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b'').decode('utf-8', 'replace').strip()[-500:]
            raise RuntimeError('Voice command failed: ' + (detail or str(exc))) from None

    @staticmethod
    def _message(process, seconds: float):
        """Read one newline-delimited worker message with a strict timeout."""
        deadline = time.monotonic() + seconds
        message = bytearray()
        while True:
            remain = deadline - time.monotonic()
            if remain <= 0:
                raise RuntimeError('Warm speech engine timed out')
            readable, _, _ = select.select([process.stdout], [], [], min(0.5, remain))
            if not readable:
                if process.poll() is not None:
                    raise RuntimeError('Warm speech engine exited unexpectedly')
                continue
            char = os.read(process.stdout.fileno(), 1)
            if not char:
                raise RuntimeError('Warm speech engine closed its output')
            if char == b'\n':
                try:
                    return json.loads(message.decode('utf-8'))
                except (ValueError, UnicodeError):
                    raise RuntimeError('Invalid warm speech engine response') from None
            message.extend(char)
            if len(message) > 8192:
                raise RuntimeError('Oversized warm speech response')

    def warmup(self) -> bool:
        if not self.fast:
            return False
        if self.worker and self.worker.poll() is None:
            return True
        self.close()
        try:
            proc = subprocess.Popen(
                [sys.executable, '-u', str(self.app_root / 'src' / 'voice_worker.py'), '--server'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                bufsize=0)
            self.worker = proc
            result = self._message(proc, 25)
            if result.get('status') != 'ready':
                raise RuntimeError(str(result.get('error', 'Warm voice failed')))
            return True
        except (OSError, ValueError, RuntimeError):
            self.close()
            # When the warm worker cannot start, avoid a 25-second startup
            # penalty on every voice request. Cold TTS remains available.
            self.retry_after = self.clock() + 300.0
            return False

    def reap_idle(self) -> bool:
        """Release the resident model after prolonged silence; no disk I/O."""
        if (self.worker is not None and self.last_activity is not None
                and self.clock() - self.last_activity >= self.idle_timeout):
            self.close()
            return True
        return False

    def close(self) -> None:
        proc, self.worker = self.worker, None
        self.last_activity = None
        if not proc:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()

    def speak(self, text: str, play: bool = True, timeout: float = 55):
        began = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='hey-frame-voice-') as folder:
            wav = Path(folder) / 'synth.wav'
            # A long-lived worker is loaded only after the first voice
            # command, then freed during idle listening.
            if self.fast and self.clock() >= self.retry_after and (
                    self.worker is None or self.worker.poll() is not None):
                self.warmup()
            if self.worker is not None and self.worker.poll() is None:
                try:
                    request = json.dumps({'text': text[:350], 'path': str(wav)}, ensure_ascii=True)
                    self.worker.stdin.write((request + '\n').encode('utf-8'))
                    self.worker.stdin.flush()
                    answer = self._message(self.worker, min(timeout, 45))
                    if answer.get('status') != 'ok':
                        raise RuntimeError(str(answer.get('error', 'Warm voice failed')))
                except (OSError, RuntimeError, ValueError):
                    # Fail open to a fresh one-shot synthesizer if the warm IPC
                    # worker dies, rather than silently losing voice output.
                    self.close()
                    self.retry_after = self.clock() + 300.0
                    wav.unlink(missing_ok=True)
                    self._execute([sys.executable, str(self.app_root / 'src' / 'voice_worker.py'),
                                   str(wav), text], int(timeout))
            else:
                self._execute([sys.executable, str(self.app_root / 'src' / 'voice_worker.py'),
                               str(wav), text], int(timeout))
            if self.worker is not None and self.worker.poll() is None:
                self.last_activity = self.clock()
            if not wav.is_file() or wav.stat().st_size < 44:
                raise RuntimeError('Voice synthesis did not create a valid WAV file')
            synthesised = time.monotonic()
            if play:
                args = ['pw-play']
                if os.environ.get('HEY_FRAME_AUDIO_TARGET'):
                    args += ['--target', os.environ['HEY_FRAME_AUDIO_TARGET']]
                args.append(str(wav))
                self._execute(args, 30)
            LOG.info('Speech timing: synthesis %.2fs, playback %.2fs; warm=%s',
                     synthesised - began, time.monotonic() - synthesised,
                     self.worker is not None and self.worker.poll() is None)
            return wav.stat().st_size
