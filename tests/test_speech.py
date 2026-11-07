"""Exercise the real voice.py WAV writer and Engine against fake native modules."""
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
import wave
from unittest.mock import patch

import numpy as np
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from voice import synthesize
from assistant import Engine


class TTSFake:
    def __init__(self, **kwargs):
        self.kwargs=kwargs
        self.speed=1
        self.silence_scale=0.2
    def validate(self):return True
    def generate(self,text,config):
        return types.SimpleNamespace(samples=np.sin(np.linspace(0,30,4000)).astype('f'), sample_rate=22050)


def sherpa_stub():
    return types.SimpleNamespace(OfflineTtsConfig=TTSFake,
       OfflineTtsModelConfig=TTSFake,
       OfflineTtsVitsModelConfig=TTSFake,
       OfflineTts=lambda _:TTSFake(),GenerationConfig=TTSFake)


class VoiceNativeTests(unittest.TestCase):
    def test_full_wav_export_with_mock_native_onnx(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'espeak-ng-data').mkdir()
            (root/'en_US-glados.onnx').write_bytes(b'x')
            (root/'tokens.txt').write_text('tokens')
            dest=root/'test.wav'
            with patch.dict(sys.modules,{'sherpa_onnx':sherpa_stub()}):
                synthesize('Frame online',dest,root)
            with wave.open(str(dest),'rb') as w:
                self.assertEqual(w.getframerate(),22050)
                self.assertEqual(w.getnchannels(),1)
                self.assertEqual(w.getnframes(),4000)

    def test_missing_native_voice_files_error(self):
        with tempfile.TemporaryDirectory() as td,patch.dict(sys.modules,{'sherpa_onnx':sherpa_stub()}):
            with self.assertRaises(RuntimeError):
                synthesize('sample',Path(td)/'text.wav',Path(td))


class RecordingMic:
    def __init__(self):self.stops=0;self.starts=0
    def stop(self):self.stops+=1
    def start(self):self.starts+=1

class RecordingSpeaker:
    def __init__(self):self.messages=[]
    def speak(self,message):self.messages.append(message)

class StubRec:
    def __init__(self,*args,**kwargs):self.resets=0
    def reset(self):self.resets+=1


class EngineTests(unittest.TestCase):
    def test_timer_persistence_and_expiration(self):
        now=[1000.0]
        mic=RecordingMic();speaker=RecordingSpeaker()
        with tempfile.TemporaryDirectory() as d,patch('assistant.load_alerts',return_value=False):
            f=Path(d)/'timer.json'
            e=Engine(object(),lambda *a:None,speaker,mic=mic,monotonic=lambda:now[0],wall=lambda:now[0],timer_file=f)
            e.recognizer=StubRec()
            e.handle('set a timer for two minutes')
            self.assertTrue(f.exists())
            self.assertIn('2 minutes',speaker.messages[-1])
            self.assertEqual(mic.stops,1)
            self.assertEqual(mic.starts,1)
            now[0]=1050
            e.handle('timer remaining')
            self.assertIn('1 minute',speaker.messages[-1])
            now[0]=1120
            e.tick()
            self.assertIn('Timer complete',speaker.messages[-1])
            self.assertFalse(f.exists())
            self.assertEqual(e.recognizer.resets,1)

    def test_repeated_microphone_failure_stops_instead_of_looping_forever(self):
        class FailingMic(RecordingMic):
            def read(self):raise RuntimeError('no stream')
        mic=FailingMic();speaker=RecordingSpeaker()
        with tempfile.TemporaryDirectory() as d,patch('assistant.load_alerts',return_value=False),patch('assistant.time.sleep') as sleep:
            e=Engine(object(),lambda *a:None,speaker,mic=mic,timer_file=Path(d)/'timer.json')
            with self.assertRaisesRegex(RuntimeError,'five times'):
                e.run()
            self.assertEqual(sleep.call_count,4)
            self.assertEqual(mic.starts,5)
            self.assertGreaterEqual(mic.stops,5)

    def test_shutdown_never_reopens_mic(self):
        mic=RecordingMic();speaker=RecordingSpeaker()
        with tempfile.TemporaryDirectory() as d,patch('assistant.load_alerts',return_value=False):
            e=Engine(object(),lambda *a:None,speaker,mic=mic,timer_file=Path(d)/'timer.json')
            e.handle('stop listening')
            self.assertFalse(e.running)
            self.assertEqual(mic.stops,1)
            self.assertEqual(mic.starts,0)

    def test_battery_warning_only_after_opt_in_and_no_spam(self):
        from commands import Battery
        now=[0.]
        mic=RecordingMic();speaker=RecordingSpeaker()
        with tempfile.TemporaryDirectory() as d,patch('assistant.load_alerts',return_value=False),patch('assistant.read_battery',return_value=Battery(19,False,None)):
            e=Engine(object(),lambda *a:None,speaker,mic=mic,monotonic=lambda:now[0],wall=lambda:1000,timer_file=Path(d)/'timer.json')
            e.recognizer=StubRec()
            e.tick();self.assertEqual(speaker.messages,[])
            with patch('assistant.save_alerts'):
                e.handle('battery alerts on')
            now[0]=61;e.tick()
            self.assertIn('19 percent',speaker.messages[-1])
            count=len(speaker.messages)
            now[0]=122;e.tick()
            self.assertEqual(len(speaker.messages),count)


if __name__=='__main__':unittest.main()
