#!/usr/bin/env python3
"""Hey Frame 0.5 — offline Steam Frame utility with safe voice activation.

Only reads PipeWire microphone / system status; owns no hardware inputs.
No arbitrary commands, network use, changes to microphone defaults or volume.
"""
from __future__ import annotations
from array import array
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from commands import answer, read_battery, battery_reply
from conflicts import frame_dictation_active, WARNING as CONFLICT_WARNING
from listener import Microphone, Recognizer, audio_level
from state import state_path, load_deadline, save_deadline
from voice import Speaker, VOICE_NAME
from recording import request as recorder_request
from jokes import pick as pick_line, add_quote, quotes_path, personal_quotes
from gaming import mark_moment, save_note, last_note
from vr_actions import request as vr_request

VERSION = '0.5.0'
ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger('hey-frame')


def diagnose() -> bool:
    print(f'Hey Frame {VERSION} | read-only diagnostics')
    checks = []
    for tool in ('pw-record', 'pw-play'):
        found = shutil.which(tool)
        print(f'{tool}: {found or "MISSING"}')
        checks.append(bool(found))
    print('Interpreter:', sys.version.split()[0], sys.executable)
    print('Machine:', os.uname().machine)
    for module in ('vosk','numpy','sherpa_onnx'):
        try:
            o = __import__(module)
            print(f'{module}: OK', getattr(o, '__version__', ''))
            checks.append(True)
        except Exception as exc:
            print(f'{module}: FAIL ({exc})')
            checks.append(False)
    models = {
        'Vosk recognition': ROOT/'models'/'vosk-model-small-en-us-0.15'/'am'/'final.mdl',
        'GLaDOS voice': ROOT/'models'/VOICE_NAME/'en_US-glados.onnx',
        'TTS tokens': ROOT/'models'/VOICE_NAME/'tokens.txt',
        'TTS phonemes': ROOT/'models'/VOICE_NAME/'espeak-ng-data',
    }
    for label, path in models.items():
        valid = path.is_file() if label != 'TTS phonemes' else path.is_dir()
        print(f'{label}: {"OK" if valid else "MISSING"}')
        checks.append(valid)
    print('Battery:', battery_reply(read_battery()))
    if frame_dictation_active():
        print('CONFLICT WARNING:', CONFLICT_WARNING)
    print('No volume or hardware-button settings were changed.')
    print('RESULT:', 'PASS' if all(checks) else 'FAIL')
    return all(checks)


def asr_test() -> bool:
    """Load the actual native Vosk model and instantiate both recognizer modes."""
    try:
        import vosk
        vosk.SetLogLevel(-1)
        model = vosk.Model(str(ROOT/'models'/'vosk-model-small-en-us-0.15'))
        wake = vosk.KaldiRecognizer(model, 16000, '["hey frame", "hay frame", "[unk]"]')
        command = vosk.KaldiRecognizer(model, 16000)
        silence = b'\0' * 3200
        wake.AcceptWaveform(silence)
        command.AcceptWaveform(silence)
        print('Recognition check: PASS. Both wake and command recognizers loaded.')
        return True
    except Exception as exc:
        print('Recognition check: FAILED.',exc,file=sys.stderr)
        return False


def mic_test(seconds: float = 2.0) -> bool:
    """Record transiently in memory without writing speech to disk."""
    print(f'Checking default PipeWire microphone for {seconds:g} seconds...')
    mic = Microphone(os.environ.get('HEY_FRAME_MIC_TARGET',''))
    n = 0
    loudest = 0
    end = time.monotonic() + seconds
    try:
        mic.start()
        while time.monotonic() < end:
            buf = mic.read(timeout=4)
            n += len(buf)
            loudest = max(loudest, audio_level(buf))
    except (OSError, RuntimeError) as exc:
        print('MIC FAILED:', exc)
        return False
    finally:
        mic.stop()
    print(f'MIC OK: received {n} bytes; peak 100ms mean level {loudest}')
    if loudest < 100:
        print('NOTE: Speech is very quiet or the microphone is muted. Speak during the test.')
    return n >= 3200


def user_service(*args) -> int:
    binary = shutil.which('systemctl') or ('/usr/bin/systemctl' if Path('/usr/bin/systemctl').is_file() else None)
    if not binary:
        print('User systemd is unavailable; use hey-frame run for foreground mode.', file=sys.stderr)
        return 1
    return subprocess.run([binary,'--user',*args], check=False).returncode


def preference_file() -> Path:
    return Path.home()/'.config'/'hey-frame'/'prefs.json'


def load_alerts() -> bool:
    try:
        return json.loads(preference_file().read_text()).get('battery_alerts') is True
    except (OSError, ValueError, AttributeError):
        return False


def save_alerts(enabled: bool) -> None:
    dest = preference_file()
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = dest.with_suffix('.json.tmp')
    temp.write_text(json.dumps({'battery_alerts': enabled}) + '\n')
    temp.chmod(0o600)
    temp.replace(dest)


class Engine:
    def __init__(self, model, recognizer_factory, speaker, mic=None,
                 monotonic=time.monotonic, wall=time.time, timer_file=None):
        self.monotonic = monotonic
        self.wall = wall
        self.mic = mic or Microphone(os.environ.get('HEY_FRAME_MIC_TARGET',''))
        self.speaker = speaker
        self.running = True
        self.timer_file = timer_file or state_path()
        self.deadline = load_deadline(self.timer_file, self.wall())
        self.alerts = load_alerts()
        self.last_alert_level = 101
        self.next_battery_check = self.monotonic() + 60
        self.recognizer = Recognizer(model, recognizer_factory, self.handle, clock=monotonic)

    def speak(self, message: str) -> None:
        # Stop microphone before speaking so generated voice can't self-trigger.
        self.mic.stop()
        try:
            self.speaker.speak(message)
        except Exception as exc:
            LOG.error('Voice playback failed: %s', exc)
            # No transcript/audio is logged. Response is a non-sensitive system report.
            print('VOICE RESPONSE (not played):', message, flush=True)
        finally:
            if self.running:
                self.mic.start()

    def handle(self, phrase: str) -> None:
        remaining = None if self.deadline is None else max(0,round(self.deadline-self.wall()))
        reply = answer(phrase, timer_seconds_left=remaining)
        LOG.info('Handled command type: %s', reply.action)
        if reply.action in ('record_start', 'record_stop', 'record_status'):
            command = reply.action.removeprefix('record_')
            self.speak(recorder_request(command))
            return
        if reply.action == 'mark_moment':
            self.speak(mark_moment())
            return
        if reply.action == 'screenshot':
            self.speak(vr_request('screenshot'))
            return
        if reply.action in ('open_dashboard', 'pause_game'):
            response = vr_request('open_dashboard')
            if reply.action == 'pause_game' and response.startswith('Dashboard opened'):
                response += ' This does not send a gamepad pause button.'
            self.speak(response)
            return
        if reply.action == 'resume_game':
            self.speak(reply.text)
            return
        if reply.action == 'save_note':
            self.speak(save_note(reply.text))
            return
        if reply.action == 'last_note':
            self.speak(last_note())
            return
        if reply.action in ('joke', 'quote', 'personal_quote'):
            self.speak(pick_line(reply.action))
            return
        if reply.action == 'set_timer':
            self.deadline = self.wall() + reply.seconds
            save_deadline(self.timer_file, self.deadline)
        elif reply.action == 'cancel_timer':
            self.deadline = None
            save_deadline(self.timer_file, None)
        elif reply.action in ('alerts_on', 'alerts_off'):
            self.alerts = reply.action == 'alerts_on'
            save_alerts(self.alerts)
        elif reply.action == 'shutdown':
            self.running = False
        self.speak(reply.text)

    def tick(self) -> None:
        if self.deadline is not None and self.wall() >= self.deadline:
            self.deadline = None
            save_deadline(self.timer_file, None)
            self.recognizer.reset()
            self.speak('Attention. Timer complete.')
        now = self.monotonic()
        if self.alerts and now >= self.next_battery_check:
            self.next_battery_check = now + 60
            b = read_battery()
            if b and b.charging:
                self.last_alert_level = 101
            elif b:
                for threshold in (5,10,20):
                    if b.percentage <= threshold and threshold < self.last_alert_level:
                        self.last_alert_level = threshold
                        self.speak(f'Warning. Headset battery at {b.percentage} percent.')
                        break
        elif now >= self.next_battery_check:
            self.next_battery_check = now + 60

    def stop(self, *_):
        self.running = False
        self.mic.stop()

    def run(self):
        LOG.info('Hey Frame running. No hardware-button access. No volume changes.')
        failures = 0
        try:
            while self.running:
                try:
                    self.mic.start()
                    self.recognizer.feed(self.mic.read())
                    self.tick()
                    failures = 0
                except (OSError, RuntimeError) as exc:
                    LOG.warning('Microphone problem: %s', exc)
                    failures += 1
                    self.mic.stop()
                    if failures >= 5:
                        raise RuntimeError('Microphone failed five times. Stopping to save battery.')
                    self.recognizer.reset()
                    time.sleep(min(10, 2 * failures))
        finally:
            self.mic.stop()
            if hasattr(self.speaker, 'close'):
                self.speaker.close()
        return 0


def run_foreground():
    import vosk
    vosk.SetLogLevel(-1)
    lock_file = state_path().with_name('listener.lock')
    lock_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock_file.open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another Hey Frame listener is already running.', file=sys.stderr)
            return 1
        model = vosk.Model(str(ROOT/'models'/'vosk-model-small-en-us-0.15'))
        speaker = Speaker(ROOT, fast=os.environ.get('HEY_FRAME_FAST_VOICE', '1') != '0')
        if speaker.fast:
            if speaker.warmup():
                LOG.info('Warm voice engine ready; replies avoid repeated model loading.')
            else:
                LOG.warning('Warm voice unavailable; using slower on-demand synthesis.')
        e = Engine(model, vosk.KaldiRecognizer, speaker)
        signal.signal(signal.SIGINT, e.stop)
        signal.signal(signal.SIGTERM, e.stop)
        return e.run()


def main(argv=None):
    p = argparse.ArgumentParser(description='Hey Frame 0.5 — offline voice assistant for Steam Frame')
    sub = p.add_subparsers(dest='op', required=True)
    for name in ('version','doctor','mic-test','check-voice','check-asr','run','start','stop','status'):
        sub.add_parser(name)
    quote_add = sub.add_parser('add-quote', help='append a line to your private Portal quotes file')
    quote_add.add_argument('text')
    sub.add_parser('quotes-path', help='show private quotes file location')
    sub.add_parser('list-quotes', help='list personally added quotes')
    vr = sub.add_parser('vr', help='safe dashboard/screenshot actions')
    vr.add_argument('action', choices=('open_dashboard', 'screenshot'))
    sub.add_parser('mark', help='mark a moment in an active recording')
    recorder = sub.add_parser('recorder', help='query/control linked SFRecorder over local socket')
    recorder.add_argument('command', choices=('start','stop','status'))
    perf = sub.add_parser('benchmark', help='measure running listener CPU and RAM (read-only)')
    perf.add_argument('--seconds', type=int, default=10)
    for name in ('say','test-command'):
        s = sub.add_parser(name)
        s.add_argument('text')
    opts = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    if opts.op == 'version':
        print(VERSION)
    elif opts.op == 'doctor':
        return 0 if diagnose() else 1
    elif opts.op == 'mic-test':
        return 0 if mic_test() else 1
    elif opts.op == 'check-asr':
        return 0 if asr_test() else 1
    elif opts.op == 'check-voice':
        size = Speaker(ROOT).speak('Frame voice system online.', play=False)
        print('Voice synthesis passed:', size, 'WAV bytes')
    elif opts.op == 'say':
        Speaker(ROOT).speak(opts.text)
    elif opts.op == 'test-command':
        print(answer(opts.text).text)
    elif opts.op == 'add-quote':
        print('Personal quote added:', add_quote(opts.text))
    elif opts.op == 'quotes-path':
        print(quotes_path())
    elif opts.op == 'list-quotes':
        print('\n'.join(personal_quotes()) or 'No personal quotes yet.')
    elif opts.op == 'mark':
        print(mark_moment())
    elif opts.op == 'vr':
        print(vr_request(opts.action))
    elif opts.op == 'recorder':
        print(recorder_request(opts.command))
    elif opts.op == 'stop':
        return user_service('disable', '--now', 'hey-frame.service')
    elif opts.op == 'status':
        return user_service('status', '--no-pager', 'hey-frame.service')
    elif opts.op == 'benchmark':
        from perf import measure, describe
        print(describe(measure(opts.seconds)))
    elif opts.op == 'start':
        if frame_dictation_active():
            print('ERROR:', CONFLICT_WARNING, file=sys.stderr)
            return 1
        if not diagnose():
            return 1
        if not asr_test():
            return 1
        print('Testing offline voice generation...')
        Speaker(ROOT).speak('Frame online.', play=False)
        print('Testing microphone stream (no recording saved)...')
        if not mic_test(1.5):
            print('ERROR: microphone test failed. Service has NOT started.', file=sys.stderr)
            return 1
        return user_service('enable', '--now', 'hey-frame.service')
    elif opts.op == 'run':
        return run_foreground()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print('Hey Frame error:', exc, file=sys.stderr)
        raise SystemExit(1)
