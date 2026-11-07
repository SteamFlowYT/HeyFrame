"""Hey Frame v0.5: dedicated dashboard, private quotes, gaming-first actions."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

from commands import answer
from jokes import add_quote, pick, personal_quotes, quotes_path, SHORT_PORTAL_QUOTES
from gaming import mark_moment, save_note, last_note
from dashboard import Panel, DashboardSocket, split_lines, invoke_hey_frame
from vr_actions import request
from assistant import Engine


class SpokenCommands(unittest.TestCase):
    def test_actions(self):
        for spoken, action in [
            ('Hey Frame mark this moment', 'mark_moment'),
            ('Hey Frame mark highlight', 'mark_moment'),
            ('Hey Frame take a screenshot', 'screenshot'),
            ('Hey Frame open dashboard', 'open_dashboard'),
            ('Hey Frame pause game', 'pause_game'),
            ('Hey Frame resume game', 'resume_game'),
            ('Hey Frame tell me a joke', 'joke'),
            ('Hey Frame Portal quote', 'quote'),
            ('Hey Frame personal quote', 'personal_quote'),
            ('Hey Frame note to self test the battery', 'save_note'),
            ('Hey Frame last note', 'last_note'),
        ]:
            with self.subTest(spoken=spoken):
                self.assertEqual(answer(spoken).action, action)

    def test_pause_is_not_false_button_emulation(self):
        self.assertIn('Close the SteamVR dashboard', answer('resume game').text)
        self.assertNotEqual(answer('press start on controller').action, 'pause_game')

    def test_note_payload(self):
        self.assertEqual(answer('Note to self check the lens').text, 'check the lens')


class PersonalQuotes(unittest.TestCase):
    def test_add_quotes_and_random_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            quotes = Path(tmp)/'q.txt'
            add_quote('A line I own', quotes)
            add_quote('Another personal line', quotes)
            self.assertEqual(personal_quotes(quotes), ['A line I own', 'Another personal line'])
            self.assertIn(pick('personal_quote', quotes), personal_quotes(quotes))
            self.assertIn(pick('quote', quotes), personal_quotes(quotes))

    def test_unpopulated_quote_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = pick('personal_quote', Path(tmp)/'absent.txt')
            self.assertIn('No personal quotes', result)

    def test_reject_empty_oversized_and_injection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'quotes.txt'
            for value in ('', 'x'*351, '# comment'):
                with self.subTest(value=value[:10]):
                    with self.assertRaises(ValueError):
                        add_quote(value,path)

    def test_quotes_use_private_config_path(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'XDG_CONFIG_HOME':tmp}):
            self.assertEqual(quotes_path(), Path(tmp)/'hey-frame'/'portal-quotes.txt')


class GamingFunctions(unittest.TestCase):
    def test_mark_only_when_recorder_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)
            self.assertIn('Nothing to mark', mark_moment(lambda _: 'No recording in progress.',dest))
            self.assertFalse(list(dest.iterdir()))
            m=mark_moment(lambda _: 'Recording active. 123 seconds captured.',dest,
                          now=datetime(2026,11,8,21,30,0))
            self.assertIn('Highlight marked',m)
            self.assertIn('123 seconds',(dest/'HeyFrame_markers_2026-11-08.txt').read_text())

    def test_save_and_recall_private_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'notes.txt'
            self.assertEqual(save_note('test the recording',dest),'Note saved.')
            self.assertIn('test the recording',last_note(dest))

    def test_oversized_note_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'notes.txt'
            self.assertIn('1 to 160',save_note('x'*200,dest))
            self.assertFalse(dest.exists())


class OverlayProtocol(unittest.TestCase):
    def test_private_unix_socket_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'socket'
            server=DashboardSocket(path)
            try:
                responses=[]
                def call():responses.append(request('open_dashboard', path))
                t=threading.Thread(target=call);t.start()
                t.join(timeout=0.01)
                server.poll(lambda cmd: 'Dashboard opened.' if cmd=='open_dashboard' else 'bad')
                t.join(timeout=2)
                self.assertEqual(responses,['Dashboard opened.'])
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
            finally:
                server.close()
            self.assertFalse(path.exists())

    def test_unsupported_request(self):
        with self.assertRaises(ValueError):request('inject_controller_button')

    def test_panel_click_target(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed on test runner')
        panel=Panel()
        image=panel.draw(listening=False,busy=False,info='Ready',rec='connected')
        self.assertEqual(image.size,(800,990))
        self.assertEqual(panel.clicked(350,260),'toggle')
        self.assertEqual(panel.clicked(350,710),'screenshot')
        self.assertIsNone(panel.clicked(50,50))

    def test_no_sh_command_from_dashboard(self):
        with self.assertRaises(ValueError):invoke_hey_frame('bash anything')


class LiveDispatch(unittest.TestCase):
    class FakeMic:
        def start(self):pass
        def stop(self):pass

    class FakeSpeaker:
        def __init__(self):self.spoken=[]
        def speak(self,text):self.spoken.append(text)

    def engine(self,d):
        speaker=self.FakeSpeaker()
        e=Engine(object(),MagicMock(),speaker,mic=self.FakeMic(),timer_file=Path(d)/'timer.json')
        return e,speaker

    def test_handler_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp, patch('assistant.vr_request',return_value='Screenshot requested.') as vr:
            e,speaker=self.engine(tmp)
            e.handle('take screenshot')
            vr.assert_called_once_with('screenshot')
            self.assertIn('Screenshot',speaker.spoken[0])

    def test_handler_pauses_without_pretending(self):
        with tempfile.TemporaryDirectory() as tmp, patch('assistant.vr_request',return_value='Dashboard opened.'):
            e,speaker=self.engine(tmp)
            e.handle('pause game')
            self.assertIn('does not send a gamepad pause button',speaker.spoken[0])

    def test_personal_quotes(self):
        with tempfile.TemporaryDirectory() as tmp, patch('assistant.pick_line',return_value='My line'):
            e,speaker=self.engine(tmp)
            e.handle('personal quote')
            self.assertEqual(speaker.spoken,['My line'])


if __name__ == '__main__': unittest.main()
