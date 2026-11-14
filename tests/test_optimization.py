"""Optimization regressions: idle memory, ASR silence and fast dashboard start."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / 'src'))
from voice import Speaker
from listener import Recognizer
from dashboard import invoke_hey_frame


class OptimizationTests(unittest.TestCase):
    def test_voice_model_not_preloaded_by_constructor(self):
        sp = Speaker(BASE, fast=True)
        self.assertIsNone(sp.worker)
        self.assertIsNone(sp.last_activity)

    def test_warm_voice_reaped_after_timeout(self):
        now = [100.0]
        sp = Speaker(BASE, fast=True, idle_timeout=60, clock=lambda: now[0])
        worker = MagicMock()
        worker.poll.return_value = None
        sp.worker = worker
        sp.last_activity = now[0]
        now[0] = 159
        self.assertFalse(sp.reap_idle())
        self.assertIs(sp.worker, worker)
        now[0] = 160
        self.assertTrue(sp.reap_idle())
        self.assertIsNone(sp.worker)
        worker.terminate.assert_called_once()

    def test_fast_voice_fallback_when_worker_cannot_start(self):
        # No real voice model or playback needed; the fallback writes a mock WAV.
        sp = Speaker(BASE, fast=True)
        def fake_execute(args, timeout):
            Path(args[2]).write_bytes(b'RIFF' + bytes(60))
        with patch.object(sp, 'warmup', return_value=False) as warm, patch.object(
                sp, '_execute', side_effect=fake_execute) as execute:
            self.assertEqual(sp.speak('One reply', play=False), 64)
        warm.assert_called_once()
        execute.assert_called_once()
        self.assertIsNone(sp.worker)

    def test_warm_worker_error_falls_back_to_oneshot(self):
        now = [10.0]
        sp = Speaker(BASE, fast=True, clock=lambda: now[0])
        broken = MagicMock()
        broken.poll.return_value = None
        broken.stdin.write.side_effect = BrokenPipeError('closed')
        sp.worker = broken
        def fake_execute(args, timeout):
            Path(args[2]).write_bytes(b'RIFF' + bytes(60))
        with patch.object(sp, '_execute', side_effect=fake_execute):
            self.assertEqual(sp.speak('Another', play=False), 64)
        self.assertIsNone(sp.worker)
        self.assertGreater(sp.retry_after, now[0])

    def test_idle_speech_detection_skips_vosk_work(self):
        made = []
        class FakeRecognizer:
            def __init__(self, *args):
                self.count = 0
                self.resets = 0
                made.append(self)
            def AcceptWaveform(self, data):
                self.count += 1
                return False
            def PartialResult(self):
                return json.dumps({'partial':'hey frame'})
            def Result(self):
                return json.dumps({'text':'hey frame'})
            def FinalResult(self):
                return json.dumps({'text':''})
            def Reset(self):
                self.resets += 1
        r = Recognizer(object(), FakeRecognizer, lambda _: None)
        for _ in range(50):
            r.feed(bytes(3200))
        self.assertEqual(r.state, 'wake')
        self.assertLessEqual(made[0].count, 9)
        self.assertEqual(made[0].resets, 1)
        # Upon 5 real-volume frames, recognition resumes immediately.
        for _ in range(5):
            r.feed(b'\\x10\\x27' * 1600)
        self.assertEqual(r.state, 'command')

    def test_native_wake_reset_reused(self):
        constructed = []
        class FakeRecognizer:
            def __init__(self, *a):
                constructed.append(self)
                self.resets=0
            def Reset(self):
                self.resets+=1
        r=Recognizer(object(), FakeRecognizer, lambda _: None)
        first=r.wake
        r.reset()
        self.assertIs(first,r.wake)
        self.assertEqual(len(constructed),1)
        self.assertEqual(first.resets,1)

    def test_dashboard_start_skips_expensive_asr_validation(self):
        with patch('dashboard.source_available', return_value=True), patch(
                'conflicts.frame_dictation_active', return_value=False), patch(
                'dashboard.is_listening', return_value=True), patch(
                'dashboard.subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertIn('Listening enabled', invoke_hey_frame('start'))
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0],
                             ['systemctl','--user','enable','--now','hey-frame.service'])

    def test_dashboard_refuses_concurrent_dictation(self):
        with patch('dashboard.source_available', return_value=True), patch(
                'conflicts.frame_dictation_active', return_value=True), patch(
                'dashboard.subprocess.run') as run:
            self.assertIn('Cannot start',invoke_hey_frame('start'))
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
