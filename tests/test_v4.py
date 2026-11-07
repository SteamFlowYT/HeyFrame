"""Tests for recording integration, original jokes, and responsive speech worker."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from commands import answer
from jokes import ORIGINAL_JOKES, ORIGINAL_LINES, SHORT_PORTAL_QUOTES, pick
from recording import request
from assistant import Engine
from voice import Speaker, suit_filter

class TestCommands(unittest.TestCase):
    def test_recording_commands_recognized_explicitly(self):
        for phrase,action in (
            ('Hey Frame start recording','record_start'),
            ('begin recording','record_start'),
            ('Hey Frame stop recording','record_stop'),
            ('end recording','record_stop'),
            ('am I recording','record_status'),
            ('recording status','record_status'),
            ('tell me a joke','joke'),
            ('portal quote','quote'),
            ('say something sarcastic','quote')):
            with self.subTest(phrase=phrase):
                self.assertEqual(answer(phrase).action,action)

    def test_manual_recorder_status_parser(self):
        from assistant import main
        with patch('assistant.recorder_request', return_value='No recording in progress.') as ipc:
            import contextlib, io
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['recorder','status']),0)
            ipc.assert_called_once_with('status')
            self.assertIn('No recording',output.getvalue())

    def test_does_not_trigger_recording_for_ambiguous_words(self):
        self.assertNotEqual(answer('record').action,'record_start')
        self.assertNotEqual(answer('quit my game').action,'record_stop')

    def test_jokes_are_local_and_safe(self):
        self.assertGreaterEqual(len(ORIGINAL_JOKES), 6)
        self.assertGreaterEqual(len(ORIGINAL_LINES), 4)
        self.assertIn(pick('joke'), ORIGINAL_JOKES)
        self.assertIn(pick('quote'), SHORT_PORTAL_QUOTES + ORIGINAL_LINES)
        with self.assertRaises(ValueError):pick('shell')

class TestRecorderSocket(unittest.TestCase):
    def test_local_recording_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'recorder.sock'
            server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            server.bind(str(path))
            server.listen(1)
            def respond():
                conn,_=server.accept()
                with conn:
                    self.assertEqual(conn.recv(100),b'start\n')
                    conn.sendall(json.dumps({'message':'Recording started.'}).encode())
            thread=threading.Thread(target=respond);thread.start()
            try:
                self.assertEqual(request('start',path),'Recording started.')
            finally:
                thread.join(timeout=2)
                server.close()

    def test_unavailable_socket_and_invalid_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'none.sock'
            self.assertIn('not connected',request('status',path).lower())
            with self.assertRaises(ValueError):request('shutdown',path)

class TestEngineRecorder(unittest.TestCase):
    def test_record_action_fires_safe_ipc(self):
        class FakeMic:
            def start(self):pass
            def stop(self):pass
        class FakeSpeaker:
            def __init__(self):self.spoken=[]
            def speak(self,text):self.spoken.append(text)
        sp=FakeSpeaker()
        with tempfile.TemporaryDirectory() as d,patch('assistant.recorder_request',return_value='Recording started.') as req:
            e=Engine(object(),MagicMock(),sp,mic=FakeMic(),timer_file=Path(d)/'timer.json')
            e.handle('start recording')
            req.assert_called_once_with('start')
            self.assertEqual(sp.spoken,['Recording started.'])

class TestFastSpeech(unittest.TestCase):
    def test_prewarmer_not_used_if_opted_out(self):
        self.assertFalse(Speaker(BASE,fast=False).warmup())

    def test_vectorized_suit_filter_large_audio(self):
        import numpy as np
        x=np.sin(np.linspace(0,4000,22050*10,dtype=np.float32))
        y=suit_filter(x,22050)
        self.assertEqual(x.shape,y.shape)
        self.assertTrue(np.isfinite(y).all())
        self.assertLessEqual(float(np.abs(y).max()),1.01)

if __name__=='__main__':unittest.main()

class TestWarmWorkerIntegration(unittest.TestCase):
    def test_two_speech_requests_share_one_engine(self):
        """Actual subprocess protocol with a fake TTS backend, no downloaded models."""
        import os
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'src').mkdir()
            for name in ('voice.py','voice_worker.py'):
                shutil.copy2(BASE/'src'/name,root/'src'/name)
            model=root/'models'/'vits-piper-en_US-glados'
            (model/'espeak-ng-data').mkdir(parents=True)
            (model/'en_US-glados.onnx').write_bytes(b'mock')
            (model/'tokens.txt').write_text('mock')
            (root/'src'/'sherpa_onnx.py').write_text('''
import numpy as np
class Config:
    def __init__(self,*a,**kw): pass
    def validate(self): return True
class TTS:
    def __init__(self, config): pass
    def generate(self, text, config):
        from types import SimpleNamespace
        return SimpleNamespace(samples=np.sin(np.linspace(0,50,3000)).astype(np.float32),sample_rate=22050)
class Generation:
    speed = 1.0
    silence_scale = 0.0
OfflineTtsConfig=OfflineTtsModelConfig=OfflineTtsVitsModelConfig=Config
OfflineTts=TTS
GenerationConfig=Generation
''')
            speaker=Speaker(root,fast=True)
            self.assertTrue(speaker.warmup())
            worker=speaker.worker
            try:
                self.assertGreater(speaker.speak('A test',play=False),44)
                self.assertGreater(speaker.speak('Another test',play=False),44)
                self.assertIs(speaker.worker,worker)
                self.assertIsNone(worker.poll())
            finally:
                speaker.close()
            self.assertIsNotNone(worker.poll())
