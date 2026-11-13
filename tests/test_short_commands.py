"""Recognition regressions for short commands that previously failed on headset.

These mock recognizers deliberately mangle the open-grammar Vosk transcript while
returning a valid result from a tiny command grammar. No microphone files stored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from commands import answer
from listener import Recognizer, SHORTCUT_GRAMMAR, shortcut_match


class SimulatedVosk:
    def __init__(self, model, rate, grammar=None):
        self.grammar = grammar
        self.last = ''
        self.words = b''

    def AcceptWaveform(self, audio):
        # A mock acoustic result, not actual PCM. Consecutive synthetic wake
        # chunks repeat the same words; do not concatenate their fake labels.
        if audio:
            self.words = audio
        return audio.endswith(b'|end')

    def _phrase(self):
        text = self.words.decode('ascii', 'ignore').replace('|end', '').strip()
        if self.grammar and 'sarcastic mode' not in self.grammar:
            return 'hey frame' if 'hey frame' in text else ''
        if self.grammar and 'sarcastic mode' in self.grammar:
            return text  # restricted grammar finds the actual command
        return text.replace('sarcastic mode', 'sarcastic coat').replace(
            'portal quote', 'portal coat')  # unrestricted ASR got it wrong

    def PartialResult(self):
        return json.dumps({'partial': self._phrase()})

    def Result(self):
        return json.dumps({'text': self._phrase()})

    def FinalResult(self):
        return json.dumps({'text': self._phrase()})


class RecognitionTests(unittest.TestCase):
    def test_keyword_grammar_contains_both_problematic_commands(self):
        a = json.loads(SHORTCUT_GRAMMAR)
        self.assertIn('portal quote', a)
        self.assertIn('sarcastic mode', a)
        self.assertIn('hey frame portal quote', a)
        self.assertIn('[unk]', a)

    def test_shortcut_matching_is_exact_not_partial(self):
        self.assertEqual(shortcut_match('hey frame portal quote'), 'portal quote')
        self.assertEqual(shortcut_match('sarcastic mode'), 'sarcastic mode')
        self.assertEqual(shortcut_match('look at my portal quote video'), '')
        self.assertEqual(shortcut_match('[unk]'), '')
        self.assertEqual(shortcut_match('start recording'), '')

    def test_one_breath_portal_quote_from_preroll(self):
        calls = []
        clock = [0.0]
        r = Recognizer(object(), SimulatedVosk, calls.append, clock=lambda: clock[0])
        for _ in range(5):
            r.feed(b'hey frame portal quote')
        self.assertEqual(r.state, 'command')
        self.assertTrue(r.has_command_voice, 'Preroll must flag one-breath speech')
        clock[0] = 1.2
        r.feed(b'')
        self.assertEqual(calls, ['portal quote'])
        self.assertEqual(answer(calls[0]).action, 'quote')

    def test_one_breath_sarcastic_mode_recovered(self):
        calls = []
        clock = [0.0]
        r = Recognizer(object(), SimulatedVosk, calls.append, clock=lambda: clock[0])
        for _ in range(5):
            r.feed(b'hey frame sarcastic mode')
        clock[0] = 1.2
        r.feed(b'')
        self.assertEqual(calls, ['sarcastic mode'])
        self.assertEqual(answer(calls[0]).action, 'mode_on')

    def test_unrelated_clear_commands_unchanged(self):
        calls = []
        clock = [0.0]
        r = Recognizer(object(), SimulatedVosk, calls.append, clock=lambda: clock[0])
        for _ in range(5):
            r.feed(b'hey frame set a timer for five minutes')
        clock[0] = 1.2
        r.feed(b'')
        self.assertEqual(calls, ['set a timer for five minutes'])
        self.assertEqual(answer(calls[0]).action, 'set_timer')

    def test_wake_requires_five_stable_non_silent_matches(self):
        calls = []
        recognizer = Recognizer(object(), SimulatedVosk, calls.append)
        for _ in range(4):
            recognizer.feed(b'hey frame')
        self.assertEqual(recognizer.state, 'wake')
        recognizer.feed(b'hey frame')
        self.assertEqual(recognizer.state, 'command')

    def test_silence_never_activates(self):
        class HallucinatingVosk(SimulatedVosk):
            def _phrase(self):
                if self.grammar and 'sarcastic mode' not in self.grammar:
                    return 'hey frame'
                return ''
        recognizer = Recognizer(object(), HallucinatingVosk, lambda _: None)
        for _ in range(30):
            recognizer.feed(bytes(3200))
        self.assertEqual(recognizer.state, 'wake')

    def test_transcripts_are_not_logged_by_default(self):
        calls = []
        clock = [0.0]
        with patch.dict(os.environ, {'HEY_FRAME_DEBUG_TRANSCRIPTS': '0'}), patch(
                'listener.LOG.warning') as warning:
            r = Recognizer(object(), SimulatedVosk, calls.append, clock=lambda: clock[0])
            for _ in range(5):
                r.feed(b'hey frame portal quote')
            clock[0] = 1.2
            r.feed(b'')
        warning.assert_not_called()
        self.assertEqual(calls, ['portal quote'])


if __name__ == '__main__':
    unittest.main()
