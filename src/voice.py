"""On-demand offline TTS, with optional subtle sci-fi suit-announcer effect.

The neural TTS library and its ONNX model live in a short-lived subprocess,
keeping the always-on wake recognizer small in memory. No voice cloning or
Half-Life audio is distributed; voice is the upstream open sherpa/Piper GLaDOS.
"""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import wave

VOICE_NAME = 'vits-piper-en_US-glados'


def suit_filter(samples, sample_rate: int):
    """Band-limit and lightly compress audio for a radio/suit-announcer sound.

    No scipy dependency. Modest settings avoid clipping and preserve speech.
    """
    import numpy as np
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        return samples
    # 1-pole high pass ~120 Hz, low pass ~3,800 Hz.
    dt = 1.0/sample_rate
    rc_high, rc_low = 1.0/(2.0*3.14159*120), 1.0/(2.0*3.14159*3800)
    ah = rc_high/(rc_high+dt)
    al = dt/(rc_low+dt)
    out = np.empty_like(samples)
    low = prev_x = high = 0.0
    for idx, x in enumerate(samples):
        high = ah*(high + float(x) - prev_x)
        low += al*(high-low)
        prev_x = float(x)
        out[idx] = low
    return np.tanh(out*1.28)/np.tanh(1.28)


def synthesize(text: str, destination: Path, model_dir: Path) -> None:
    import numpy as np
    import sherpa_onnx
    model = model_dir/'en_US-glados.onnx'
    tokens = model_dir/'tokens.txt'
    data = model_dir/'espeak-ng-data'
    if not (model.is_file() and tokens.is_file() and data.is_dir()):
        raise RuntimeError('The voice model files are missing or incomplete')
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(tokens), data_dir=str(data)),
            num_threads=2, provider='cpu'), max_num_sentences=1)
    if not config.validate():
        raise RuntimeError('Voice model configuration rejected by sherpa-onnx')
    engine = sherpa_onnx.OfflineTts(config)
    options = sherpa_onnx.GenerationConfig()
    options.speed = 0.96
    options.silence_scale = 0.15
    audio = engine.generate(text[:350], options)
    samples = np.asarray(audio.samples, dtype=np.float32)
    if samples.size == 0:
        raise RuntimeError('No speech audio generated')
    if os.environ.get('HEY_FRAME_VOICE_STYLE', 'hev').lower() == 'hev':
        samples = suit_filter(samples, audio.sample_rate)
    try:
        gain = max(0.25, min(1.5, float(os.environ.get('HEY_FRAME_VOICE_GAIN', '1.0'))))
    except ValueError:
        gain = 1.0
    pcm = (np.clip(samples*gain, -1, 1)*32767).astype('<i2').tobytes()
    with wave.open(str(destination),'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(audio.sample_rate)
        f.writeframes(pcm)


class Speaker:
    def __init__(self, app_root: Path):
        self.app_root = app_root

    @staticmethod
    def _execute(args, timeout: int):
        try:
            subprocess.run(args, check=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Speech engine timed out') from None
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b'').decode('utf-8','replace').strip()[-500:]
            raise RuntimeError('Voice command failed: ' + (detail or str(exc))) from None

    def speak(self, text: str, play: bool = True, timeout: float = 55):
        with tempfile.TemporaryDirectory(prefix='hey-frame-voice-') as folder:
            wav = Path(folder)/'synth.wav'
            self._execute([sys.executable, str(self.app_root/'src'/'voice_worker.py'),
                           str(wav), text], int(timeout))
            if not wav.is_file() or wav.stat().st_size < 44:
                raise RuntimeError('Voice synth did not create a valid WAV file')
            if play:
                args = ['pw-play']
                if os.environ.get('HEY_FRAME_AUDIO_TARGET'):
                    args += ['--target',os.environ['HEY_FRAME_AUDIO_TARGET']]
                args.append(str(wav))
                self._execute(args, 30)
            return wav.stat().st_size
