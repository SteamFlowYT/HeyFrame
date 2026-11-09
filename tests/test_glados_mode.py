"""GLaDOS Mode: activation, persistence, truthful actions and dashboard tests."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from assistant import Engine, main
from commands import answer
from dashboard import Panel, invoke_hey_frame
from glados_mode import ASIDES, decorate, get_mode, mode_path, set_mode


class CommandParserTests(unittest.TestCase):
    def test_activation_phrases(self):
        for phrase in (
            "Hey Frame is GLADOS there?",
            "Hey Frame, is glad os there",
            "hey frame is glad us ther",
            "is gladys there",
            "GLaDOS mode",
            "activate GLADOS",
            "switch to glados",
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual(answer(phrase).action, "mode_on")

    def test_deactivation_phrases(self):
        for phrase in ("normal mode", "back to normal", "turn off glados mode",
                       "glados off", "switch to normal"):
            with self.subTest(phrase=phrase):
                self.assertEqual(answer(phrase).action, "mode_off")

    def test_status_not_activation(self):
        self.assertEqual(answer("is GLaDOS mode on?").action, "mode_status")
        self.assertEqual(answer("what mode are you in").action, "mode_status")

    def test_mode_not_confused_with_quotes_or_gaming_commands(self):
        self.assertEqual(answer("GLaDOS quote").action, "quote")
        self.assertEqual(answer("start recording").action, "record_start")
        self.assertEqual(answer("mark this moment").action, "mark_moment")
        self.assertEqual(answer("take a screenshot").action, "screenshot")
        self.assertEqual(answer("battery").action, "battery")


class PersistenceTests(unittest.TestCase):
    def test_default_normal_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            location = Path(td) / "hey-frame" / "mode.json"
            self.assertEqual(get_mode(location), "normal")
            self.assertEqual(set_mode("glados", location), "glados")
            self.assertEqual(get_mode(location), "glados")
            self.assertEqual(json.loads(location.read_text())["mode"], "glados")
            self.assertEqual(location.stat().st_mode & 0o777, 0o600)
            self.assertEqual(set_mode("normal", location), "normal")
            self.assertEqual(get_mode(location), "normal")

    def test_invalid_file_defaults_to_normal(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "mode.json"
            target.write_text("{corrupt", encoding="utf-8")
            self.assertEqual(get_mode(target), "normal")

    def test_bad_mode_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "mode.json"
            set_mode("normal", target)
            contents = target.read_bytes()
            with self.assertRaises(ValueError):
                set_mode("godmode", target)
            self.assertEqual(target.read_bytes(), contents)

    def test_cli_mode(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"XDG_CONFIG_HOME": td}):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertEqual(main(["mode", "glados"]), 0)
                self.assertEqual(main(["mode", "status"]), 0)
                self.assertEqual(main(["mode", "normal"]), 0)
            lines = buffer.getvalue().splitlines()
            self.assertEqual(lines, [
                "Response mode: glados", "Response mode: glados", "Response mode: normal"
            ])


class ResponseTests(unittest.TestCase):
    choose_first = staticmethod(lambda values: values[0])

    def test_normal_mode_unchanged(self):
        fact = "Headset battery, 48 percent."
        self.assertEqual(decorate("battery", fact, "normal"), fact)

    def test_real_result_precedes_sarcasm(self):
        tests = (
            ("record_start", "Recorder started. Recording will begin now."),
            ("record_stop", "Stopping recording. Saving video."),
            ("set_timer", "Timer set for 10 minutes."),
            ("mark_moment", "Highlight marked. Timestamp saved beside your recordings."),
            ("screenshot", "Screenshot requested. Check Pictures/HeyFrame."),
            ("battery", "Headset battery, 45 percent."),
            ("save_note", "Note saved."),
            ("open_dashboard", "Dashboard opened."),
        )
        for action, fact in tests:
            with self.subTest(action=action):
                result = decorate(action, fact, "glados", self.choose_first)
                self.assertTrue(result.startswith(fact))
                self.assertGreater(len(result), len(fact))
                self.assertLessEqual(len(result), 350)

    def test_failed_or_unavailable_actions_not_obscured(self):
        for action, message in (
            ("record_start", "SteamFlow Recorder is not connected. Update it and open SteamVR."),
            ("record_stop", "There is no active recording."),
            ("mark_moment", "Nothing to mark. Start a recording first."),
            ("screenshot", "SteamVR screenshot failed."),
            ("battery", "Headset battery data is unavailable."),
            ("set_timer", "Try: set a timer for five minutes. Maximum two hours."),
            ("unknown", "Command not recognized. Say Hey Frame, then help."),
        ):
            with self.subTest(action=action):
                self.assertEqual(decorate(action, message, "glados"), message)

    def test_charging_battery_does_not_claim_drain(self):
        result = decorate("battery", "Headset battery, 85 percent. Charging.",
                          "glados", self.choose_first)
        self.assertIn("Charging", result)
        self.assertNotIn("draining", result)

    def test_quotes_jokes_critical_exit_are_plain(self):
        for action in ("joke", "quote", "personal_quote", "shutdown"):
            with self.subTest(action=action):
                self.assertEqual(decorate(action, "Exact original text.", "glados"),
                                 "Exact original text.")

    def test_user_examples_are_included(self):
        all_quips = " ".join(v for group in ASIDES.values() for v in group)
        for phrase in ("lens inserts", "much like your aim", "scientific community",
                       "my patience", "quietly mocked", "future disappointment"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase.lower(), all_quips.lower())


class EndToEndDispatchTests(unittest.TestCase):
    class Mic:
        def start(self): pass
        def stop(self): pass

    class Voice:
        def __init__(self): self.spoken = []
        def speak(self, text): self.spoken.append(text)

    def test_speech_switches_mode_without_restart(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": td}):
                speaker = self.Voice()
                engine = Engine(object(), MagicMock(), speaker, mic=self.Mic(),
                                timer_file=Path(td) / "timer.json")
                engine.handle("Hey Frame is GLaDOS there")
                self.assertEqual(get_mode(), "glados")
                self.assertIn("enjoying the silence", speaker.spoken[-1])
                engine.handle("set a timer for five minutes")
                self.assertIn("Timer set for 5 minutes.", speaker.spoken[-1])
                self.assertTrue(any(aside in speaker.spoken[-1]
                                    for aside in ASIDES["set_timer"]))
                engine.handle("Normal mode")
                self.assertEqual(get_mode(), "normal")
                engine.handle("set a timer for five minutes")
                self.assertEqual(speaker.spoken[-1], "Timer set for 5 minutes.")

    def test_recorder_failure_stays_truthful(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(
                os.environ, {"XDG_CONFIG_HOME": td}):
            set_mode("glados")
            speaker = self.Voice()
            engine = Engine(object(), MagicMock(), speaker, mic=self.Mic(),
                            timer_file=Path(td) / "timer.json")
            with patch("assistant.recorder_request", return_value="SteamFlow Recorder is not connected."):
                engine.handle("start recording")
            self.assertEqual(speaker.spoken[-1], "SteamFlow Recorder is not connected.")

    def test_low_battery_warning_not_sarcastic(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"XDG_CONFIG_HOME": td}):
            set_mode("glados")
            speaker = self.Voice()
            engine = Engine(object(), MagicMock(), speaker, mic=self.Mic(),
                            timer_file=Path(td) / "timer.json")
            engine.speak("Warning. Headset battery at 5 percent.")
            self.assertEqual(speaker.spoken[-1], "Warning. Headset battery at 5 percent.")


class DashboardTests(unittest.TestCase):
    def test_persona_toggle_available_even_when_mic_off(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow not installed")
        panel = Panel()
        panel.draw(False, False, "Ready", glados=False)
        self.assertEqual(panel.clicked(200, 250), "toggle")
        self.assertEqual(panel.clicked(550, 250), "mode_toggle")
        panel.draw(True, False, "Ready", glados=True)
        self.assertEqual(panel.clicked(550, 250), "mode_toggle")
        panel.draw(False, True, "Busy", glados=True)
        self.assertIsNone(panel.clicked(550, 250))

    def test_mode_switch_invokes_only_named_cli(self):
        with patch("dashboard.source_available", return_value=True), patch(
                "dashboard.subprocess.run") as run:
            run.return_value.returncode = 0
            self.assertEqual(invoke_hey_frame("mode-glados"), "GLaDOS mode enabled.")
            run.assert_called_once()
            args = run.call_args.args[0]
            self.assertEqual(args[-2:], ["mode", "glados"])


if __name__ == "__main__":
    unittest.main()
