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
import os
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

# A restricted SECOND recognizer, only used during the brief post-wake command
# window. The open-grammar recognizer remains in place for notes and timers.
# Short utterances can get badly mangled by an unrestricted small Vosk model;
# a tiny grammar gives it the actual words to listen for. These shortcuts are
# non-destructive voice/personality commands only.
SHORTCUT_COMMANDS = (
    'sarcastic mode', 'sarcasm mode', 'be sarcastic', 'turn on sarcasm',
    'normal mode', 'back to normal', 'turn off sarcasm',
    'portal quote', 'portal quotes', 'glados quote', 'tell me a portal quote',
    'tell me a quote', 'give me a quote',
    'is glados there', 'glados mode', 'activate glados',
)
SHORTCUT_SET = frozenset(SHORTCUT_COMMANDS)
SHORTCUT_GRAMMAR = json.dumps(
    list(SHORTCUT_COMMANDS)
    + ['hey frame ' + phrase for phrase in SHORTCUT_COMMANDS]
    + ['hay frame ' + phrase for phrase in SHORTCUT_COMMANDS]
    + ['[unk]']
)


def shortcut_match(raw: str) -> str:
    """Accept only complete, explicitly enumerated shortcut utterances."""
    phrase = re.sub(r'\s+', ' ', raw.lower()).strip(' ,.!?')
    phrase = re.sub(r'^(?:hey|hay) frame\s+', '', phrase).strip()
    return phrase if phrase in SHORTCUT_SET else ''



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
                 clock=time.monotonic, min_wake_hits=5, silence_level=175):
        self.model, self.factory, self.on_command, self.clock = model, factory, on_command, clock
        self.min_wake_hits = min_wake_hits
        self.silence_level = silence_level
        self.history = deque(maxlen=35)  # at most 3.5 s, no disks
        self.wake_hits = 0
        self.wake_voice_samples = 0
        self.arm_time = 0.0
        self.state = ''
        self.reset()

    def reset(self):
        self.state = 'wake'
        self.wake = self.factory(self.model, RATE, WAKE_GRAMMAR)
        self.command = None
        self.shortcut = None
        self.shortcut_text = ''
        self.history.clear()
        self.wake_hits = 0
        self.wake_voice_samples = 0
        self.last_voice_at = self.clock()
        self.arm_time = self.clock()
        self.last_phrase = ''
        self.has_command_voice = False

    @staticmethod
    def strip_wake(text: str) -> str:
        return re.sub(r'^.*?\b(?:hey|hay) frame\b', '', text, flags=re.I).strip(' ,.!?')

    def _commit(self, text: str):
        result = self.strip_wake(text)
        hint = self.shortcut_text
        if self.shortcut is not None:
            # A complete FinalResult can be more accurate than the last partial.
            try:
                finish = recognized(self.shortcut.FinalResult(), 'text')
                hint = shortcut_match(finish) or hint
            except (ValueError, RuntimeError):
                pass
        # Never override a different clear command such as "start recording".
        # Only rescue empty or approximately related, mangled short transcripts.
        looks_related = any(term in result for term in (
            'sarcast', 'sarcas', 'normal', 'glad', 'g l a d', 'portal',
            'port all', 'quote', 'coat', 'mode',
        ))
        if hint and (not result or result == '[unk]' or looks_related):
            result = hint
        if os.environ.get('HEY_FRAME_DEBUG_TRANSCRIPTS') == '1':
            LOG.warning('ASR debug (may contain private words): open=%r shortcut=%r resolved=%r',
                        text, hint, result)
        self.reset()  # reset before invoking callbacks (may temporarily stop mic)
        if result and result != '[unk]':
            self.on_command(result)

    def _activate(self):
        self.state = 'command'
        self.arm_time = self.clock()
        self.last_voice_at = self.arm_time
        self.command = self.factory(self.model, RATE)  # free grammar for timer/notes
        # Constrain only the short-command backup; never constrain dictation.
        try:
            self.shortcut = self.factory(self.model, RATE, SHORTCUT_GRAMMAR)
        except (ValueError, RuntimeError, TypeError):
            self.shortcut = None
        self.last_phrase = ''
        self.has_command_voice = False
        candidate = ''
        # Replay wake audio because users naturally say the whole question.
        for buf in self.history:
            if self.command.AcceptWaveform(buf):
                text = recognized(self.command.Result(), 'text')
                if self.strip_wake(text):
                    candidate = text
            if self.shortcut is not None:
                complete = self.shortcut.AcceptWaveform(buf)
                raw = recognized(self.shortcut.Result(), 'text') if complete else (
                    recognized(self.shortcut.PartialResult(), 'partial'))
                self.shortcut_text = shortcut_match(raw) or self.shortcut_text
        partial = recognized(self.command.PartialResult(), 'partial')
        self.last_phrase = partial or candidate
        # The entire command may already be present in one breath, inside the
        # preroll. Previously only later audio could set has_command_voice,
        # losing short commands after silence.
        self.has_command_voice = bool(self.strip_wake(self.last_phrase) or self.shortcut_text)
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
            # A constrained recognizer can hallucinate the wake phrase from
            # unrelated sounds. Require consecutive stable matches AND evidence
            # of real microphone activity; never activate on silent PCM.
            level = audio_level(buf)
            if WAKE.search(phrase) and level >= self.silence_level:
                self.wake_hits += 1
                self.wake_voice_samples += 1
                if self.wake_hits >= self.min_wake_hits:
                    self._activate()
            elif level < self.silence_level:
                self.wake_hits = 0
                self.wake_voice_samples = 0
            else:
                self.wake_hits = 0
                self.wake_voice_samples = 0
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
        if self.shortcut is not None:
            short_complete = self.shortcut.AcceptWaveform(buf)
            raw = recognized(self.shortcut.Result(), 'text') if short_complete else \
                  recognized(self.shortcut.PartialResult(), 'partial')
            match = shortcut_match(raw)
            if match:
                self.shortcut_text = match
                self.has_command_voice = True
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
