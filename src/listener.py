"""Offline wake phrase detector + short, unrestricted command transcription.

Always-on CPU work is a small Vosk constrained recognizer. Once the wake phrase
is detected, a SECOND recognizer with unrestricted grammar handles natural
commands for up to 7 seconds; old audio is replayed to capture one-breath
'Hey Frame, ...' sentences.

No evdev, uinput, controller APIs, SteamVR input, audio settings or file writes.
"""
from __future__ import annotations
from array import array
from collections import deque
import json
import logging
import re
import select
import subprocess
import time
from typing import Callable

LOG = logging.getLogger('heyframe.listener')
RATE = 16000
CHUNK = 3200  # ~100 ms of mono 16-bit audio
WAKE = re.compile(r'\b(?:hey|hay) frame\b', re.I)
WAKE_GRAMMAR = json.dumps(['hey frame', 'hay frame', '[unk]'])


def recognized(raw: str, field: str) -> str:
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            value = obj.get(field, '')
            return value.lower().strip() if isinstance(value, str) else ''
    except (ValueError, TypeError):
        pass
    return ''


def audio_level(buf: bytes) -> int:
    """Peak-independent mean absolute level, no numpy in the hot path."""
    if len(buf) < 2:
        return 0
    sample = array('h')
    sample.frombytes(buf[:len(buf) & ~1])
    return int(sum(abs(x) for x in sample) / max(1, len(sample)))


class Microphone:
    """Read PipeWire PCM through a subprocess, never set default audio devices."""
    def __init__(self, target: str = ''):
        self.target = target
        self.proc = None

    def start(self):
        if self.proc is not None:
            return
        cmd = ['pw-record', '--rate', str(RATE), '--channels', '1', '--format', 's16', '--raw']
        if self.target:
            cmd += ['--target', self.target]
        cmd.append('-')
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=0)

    def read(self, timeout: float = 4.0) -> bytes:
        if not self.proc or not self.proc.stdout:
            raise RuntimeError('microphone stream is not open')
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise RuntimeError('microphone has not delivered audio; check PipeWire routing')
        data = self.proc.stdout.read(CHUNK)
        if not data:
            raise RuntimeError('PipeWire microphone stream ended')
        return data

    def stop(self):
        p, self.proc = self.proc, None
        if not p:
            return
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=2)
        if p.stdout:
            p.stdout.close()


class Recognizer:
    """Wake and command state machine using actual Vosk recognizer instances.

    on_command receives only text after the wake phrase. No history/audio/logs
    are stored beyond short in-memory preroll. Quiet periods end commands even
    when Vosk has not generated an endpoint yet.
    """
    def __init__(self, model, factory: Callable, on_command: Callable[[str], None],
                 clock=time.monotonic, min_wake_hits=2, silence_level=175):
        self.model, self.factory, self.on_command, self.clock = model, factory, on_command, clock
        self.min_wake_hits = min_wake_hits
        self.silence_level = silence_level
        self.history = deque(maxlen=35)  # at most 3.5 s, no disks
        self.wake_hits = 0
        self.arm_time = 0.0
        self.state = ''
        self.reset()

    def reset(self):
        self.state = 'wake'
        self.wake = self.factory(self.model, RATE, WAKE_GRAMMAR)
        self.command = None
        self.history.clear()
        self.wake_hits = 0
        self.last_voice_at = self.clock()
        self.arm_time = self.clock()
        self.last_phrase = ''
        self.has_command_voice = False

    @staticmethod
    def strip_wake(text: str) -> str:
        return re.sub(r'^.*?\b(?:hey|hay) frame\b', '', text, flags=re.I).strip(' ,.!?')

    def _commit(self, text: str):
        result = self.strip_wake(text)
        self.reset()  # reset before invoking callbacks (may temporarily stop mic)
        if result and result != '[unk]':
            self.on_command(result)

    def _activate(self):
        self.state = 'command'
        self.arm_time = self.clock()
        self.last_voice_at = self.arm_time
        self.command = self.factory(self.model, RATE)  # no huge fixed grammar
        self.last_phrase = ''
        self.has_command_voice = False
        candidate = ''
        # Replay wake audio because users naturally say the whole question.
        for buf in self.history:
            if self.command.AcceptWaveform(buf):
                text = recognized(self.command.Result(), 'text')
                if self.strip_wake(text):
                    candidate = text
        partial = recognized(self.command.PartialResult(), 'partial')
        self.last_phrase = partial or candidate
        self.history.clear()
        LOG.info('Wake phrase detected; listening for a command')
        # If Vosk already has a complete one-breath sentence, answer promptly.
        if candidate:
            self._commit(candidate)

    def feed(self, buf: bytes):
        now = self.clock()
        if self.state == 'wake':
            self.history.append(buf)
            complete = self.wake.AcceptWaveform(buf)
            phrase = recognized(self.wake.Result(), 'text') if complete else \
                     recognized(self.wake.PartialResult(), 'partial')
            if WAKE.search(phrase):
                self.wake_hits += 1
                if complete or self.wake_hits >= self.min_wake_hits:
                    self._activate()
            else:
                self.wake_hits = 0
            if complete and self.state == 'wake':
                self.history.clear()
            return
        # Command mode: wait for actual voice, then natural endpoint or silence.
        level = audio_level(buf)
        if level >= self.silence_level:
            self.last_voice_at = now
        complete = self.command.AcceptWaveform(buf)
        phrase = recognized(self.command.Result(), 'text') if complete else \
                 recognized(self.command.PartialResult(), 'partial')
        if self.strip_wake(phrase):
            self.last_phrase = phrase
            self.has_command_voice = True
        if complete and self.strip_wake(phrase):
            self._commit(phrase)
            return
        # Don't treat a wake-only phrase as a command. Let user pause between.
        if now - self.last_voice_at >= 0.95 and self.has_command_voice:
            final = recognized(self.command.FinalResult(), 'text')
            self._commit(final if self.strip_wake(final) else self.last_phrase)
        elif now - self.arm_time >= 7.0:
            final = recognized(self.command.FinalResult(), 'text')
            self._commit(final if self.strip_wake(final) else self.last_phrase)
