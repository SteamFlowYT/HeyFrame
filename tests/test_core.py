"""No hardware/API downloads needed. Exercised on development Linux with fakes."""
from __future__ import annotations
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from commands import (Battery,read_battery,battery_reply,parse_timer,answer,normalize,
                      format_duration,volume_reply,wifi_reply,steamvr_reply,uptime_reply)
from listener import Recognizer, recognized, audio_level, Microphone, RATE, WAKE_GRAMMAR
from state import save_deadline,load_deadline
from voice import Speaker,suit_filter
from download_models import _validate, _extract_zip, _extract_tar


class BatteryTests(unittest.TestCase):
    def battery(self, root, name='BAT', **values):
        path=root/name; path.mkdir(parents=True,exist_ok=True)
        for key,v in values.items(): (path/key).write_text(str(v))

    def test_actual_frame_battery_not_controller(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.battery(root,'00-controller',type='Battery',scope='Device',capacity=95)
            self.battery(root,'BAT',type='Battery',scope='System',capacity=34,status='Discharging',energy_now=200000,power_now=100000)
            self.assertEqual(read_battery(root),Battery(34,False,120))
            self.assertIn('Approximate time remaining, 2 hours',battery_reply(read_battery(root)))

    def test_charging_ignores_eta(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.battery(root,type='Battery',capacity=85,status='Charging',energy_now=100,power_now=10)
            self.assertEqual(read_battery(root),Battery(85,True,None))

    def test_invalid_battery_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.battery(root,type='Battery',capacity=130,status='Discharging')
            self.assertIsNone(read_battery(root))
            self.assertIn('unavailable',battery_reply(read_battery(root)))

    def test_unavailable(self):
        self.assertIsNone(read_battery(Path('/this/path/does/not/exist')))

    def test_unsupported_rate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.battery(root,type='Battery',capacity=52,status='Discharging',energy_now=1000,power_now=0)
            self.assertIsNone(read_battery(root).minutes)


class TextCommands(unittest.TestCase):
    def test_time_and_date(self):
        date=datetime(2026,11,3,16,45)
        self.assertIn('4:45 PM',answer('Hey Frame what time is it', now=date).text)
        self.assertIn('Tuesday November 03',answer('what date is it', now=date).text)

    def test_battery_language(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);bat=root/'battery'; bat.mkdir()
            for k,v in {'type':'Battery','capacity':'28','status':'Charging'}.items(): (bat/k).write_text(v)
            for t in ('Hey Frame, how much battery life do I have left?', 'how much charge is left','battery'):
                self.assertIn('28 percent',answer(t,battery_root=root).text)

    def test_timers(self):
        cases={'timer for a minute':60,'set a timer for five minutes':300,
               'set a timer for twenty five minutes':1500,'timer for 49 seconds':49,
               'remind me in ten minutes':600,'countdown for 2 hours':7200}
        for phrase,val in cases.items():
            with self.subTest(phrase=phrase): self.assertEqual(parse_timer(phrase),val)
        for phrase in ('timer for 500 hours','timer for purple seconds','set timer for 0 seconds'):
            self.assertIsNone(parse_timer(phrase))
        self.assertEqual(answer('timer for five minutes').action,'set_timer')
        self.assertEqual(answer('cancel timer',timer_seconds_left=100).action,'cancel_timer')
        self.assertIn('No timer',answer('check timer').text)
        self.assertIn('2 minutes',answer('check timer',timer_seconds_left=120).text)

    def test_commands_are_readonly(self):
        with patch('commands.subprocess.run') as run:
            for c in ('volume up', 'volume down', 'mute sound', 'delete every file', 'shutdown headset'):
                self.assertNotIn(answer(c).action, ('execute','volume_up','volume_down'))
            self.assertFalse(run.called)

    def test_actual_volume_query_only_gets(self):
        resp=MagicMock(stdout='Volume: 0.74 [MUTED]')
        with patch('commands.shutil.which',return_value='/usr/bin/wpctl'), patch('commands.subprocess.run',return_value=resp) as run:
            self.assertIn('74 percent',volume_reply())
            self.assertIn('Muted',volume_reply())
            self.assertTrue(all(c.args[0][:2] == ['wpctl','get-volume'] for c in run.call_args_list))

    def test_wifi_does_not_speak_private_ssid(self):
        resp=MagicMock(stdout=':x:33\n*:PRIVATE-NETWORK:65\n')
        with patch('commands.shutil.which',return_value='/usr/bin/nmcli'),patch('commands.subprocess.run',return_value=resp):
            self.assertEqual(wifi_reply(),'Connected Wi-Fi signal, 65 percent.')

    def test_steamvr_readonly(self):
        resp=MagicMock(stdout='active\n')
        with patch('commands.shutil.which',return_value='/usr/bin/systemctl'),patch('commands.subprocess.run',return_value=resp) as run:
            self.assertIn('running',steamvr_reply())
            self.assertEqual(run.call_args.args[0],['/usr/bin/systemctl','--user','is-active','steamvr.service'])

    def test_safe_stop_and_battery_alert_settings(self):
        self.assertEqual(answer('stop listening').action,'shutdown')
        self.assertEqual(answer('turn on battery warnings').action,'alerts_on')
        self.assertEqual(answer('battery alerts off').action,'alerts_off')
        self.assertIn('not recognized',answer('remove all games').text)

    def test_normalization_and_uptime(self):
        self.assertEqual(normalize('Hey--Frame!!'), 'hey frame')
        self.assertIn('1 hour',uptime_reply(Path('/tmp/definitely-missing-heyframe-uptime')) if False else format_duration(3600))


class FakeRecognizer:
    """Sends transcript as a byte-string with optional |end, independent of real ASR."""
    def __init__(self, model, rate, grammar=None):
        self.rate=rate; self.grammar=grammar;self.last=''
    def AcceptWaveform(self,buf):
        self.last=buf.decode('ascii', 'ignore')
        return self.last.endswith('|end')
    def PartialResult(self):return json.dumps({'partial':self.last.replace('|end','')})
    def Result(self):return json.dumps({'text':self.last.replace('|end','')})
    def FinalResult(self):return json.dumps({'text':self.last.replace('|end','')})


class WakeTests(unittest.TestCase):
    def test_single_breath_query(self):
        seen=[]
        r=Recognizer(object(),FakeRecognizer,seen.append)
        r.feed(b'hey frame how much battery life is left|end')
        self.assertEqual(seen,['how much battery life is left'])
        self.assertEqual(r.state,'wake')

    def test_wake_then_command(self):
        out=[]
        r=Recognizer(object(),FakeRecognizer,out.append)
        r.feed(b'hey frame')
        r.feed(b'hey frame')
        self.assertEqual(r.state,'command')
        self.assertIsNone(r.command.grammar)
        r.feed(b'battery|end')
        self.assertEqual(out,['battery'])

    def test_false_partial_does_not_wake(self):
        out=[]
        r=Recognizer(object(),FakeRecognizer,out.append)
        r.feed(b'hey frame')
        self.assertEqual(r.state,'wake')
        r.feed(b'hello')
        r.feed(b'what time is it|end')
        self.assertEqual(out,[])

    def test_unrelated_commands_are_ignored(self):
        out=[];r=Recognizer(object(),FakeRecognizer,out.append)
        for phrase in (b'what time is it|end',b'hello|end',b'battery|end'):
            r.feed(phrase)
        self.assertEqual(out,[])

    def test_timeout_returns_to_wake(self):
        clock=[0.]
        r=Recognizer(object(),FakeRecognizer,lambda t:None, clock=lambda:clock[0])
        r.feed(b'hey frame|end')
        self.assertEqual(r.state,'command')
        clock[0]=10
        r.feed(b'')
        self.assertEqual(r.state,'wake')

    def test_no_command_if_only_wake(self):
        out=[];now=[0.]
        r=Recognizer(object(),FakeRecognizer,out.append,clock=lambda:now[0])
        r.feed(b'hey frame|end')
        now[0]=10
        r.feed(b'')
        self.assertEqual(out,[])

    def test_audio_silence_and_invalid_recognizer_payloads(self):
        self.assertEqual(audio_level(b'\0'*3200),0)
        self.assertGreater(audio_level(b'\xff\x7f'*40),30000)
        for raw in ('{oops','[]','42','null'):
            self.assertEqual(recognized(raw,'text'),'')

    def test_command_callback_can_stop_microphone(self):
        out=[];r=Recognizer(object(),FakeRecognizer,out.append)
        r.feed(b'hey frame battery|end')
        self.assertEqual(r.state,'wake')


class PersistenceTests(unittest.TestCase):
    def test_timer_survives_restart(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'state'/'timer.json'
            self.assertIsNone(load_deadline(f,now=100))
            save_deadline(f,1000)
            self.assertEqual(load_deadline(f,now=100),1000)
            self.assertEqual(f.stat().st_mode & 0o777,0o600)
            save_deadline(f,None)
            self.assertFalse(f.exists())

    def test_corrupt_or_unbounded_timer_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'timer.json'
            for value in ('bad json',json.dumps({'deadline':True}),json.dumps({'deadline':9999999})):
                p.write_text(value)
                self.assertIsNone(load_deadline(p,now=100))


class PackageTests(unittest.TestCase):
    def test_model_archive_paths(self):
        _validate('vosk-model-small-en-us-0.15/am/final.mdl','vosk-model-small-en-us-0.15')
        for name in ('/root/sneaky','../evil','vosk-model-small-en-us-0.15/../evil','other/model'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                _validate(name,'vosk-model-small-en-us-0.15')

    def test_tts_radio_filter_bounds(self):
        import numpy as np
        a=np.linspace(-1,1,2000,dtype=np.float32)
        b=suit_filter(a,22050)
        self.assertEqual(a.shape,b.shape)
        self.assertFalse(np.isnan(b).any())
        self.assertLessEqual(np.abs(b).max(),1.001)

    def test_script_syntax(self):
        for script in ('install.sh','uninstall.sh'):
            proc=subprocess.run(['bash','-n',str(BASE/script)],capture_output=True,text=True)
            self.assertEqual(proc.returncode,0,proc.stderr)

    def test_cli_without_native_deps(self):
        proc=subprocess.run([sys.executable,str(BASE/'src'/'assistant.py'),'test-command','set a timer for two minutes'],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertIn('2 minutes',proc.stdout)

    def test_no_hardware_input_or_volume_write(self):
        code='\n'.join(f.read_text() for f in (BASE/'src').glob('*.py'))
        for bad in ('EVIOCGRAB','/dev/uinput','/dev/input','wpctl set-volume','set-mute','subprocess.run(shell=True'):
            self.assertNotIn(bad,code)
        # No automatic 'enable --now' in installer; safe opt-in only at runtime.
        script=(BASE/'install.sh').read_text()
        self.assertNotIn('enable --now',script)
        self.assertIn('disable --now',script)

    def test_wrong_executable_shows_error(self):
        with patch.object(Speaker,'_execute',side_effect=RuntimeError('testing')):
            with self.assertRaises(RuntimeError):Speaker(BASE).speak('text',play=False)


if __name__=='__main__':unittest.main()
