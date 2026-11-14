"""Fake-install end-to-end tests. No network or native ARM64 packages needed."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest

BASE=Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setup_fake(self, home):
        bindir=home/'stubs'
        bindir.mkdir()
        # python3 entrypoint that handles only venv creation and version gate.
        py=bindir/'python3'
        py.write_text('''#!/bin/bash
if [ "$1" = -c ]; then exit 0; fi
if [ "$1" = -m ] && [ "$2" = venv ]; then
    mkdir -p "$3/bin"
    cp "$HOME/stubs/virtual-python" "$3/bin/python"
    chmod +x "$3/bin/python"
    exit 0
fi
exit 19
''')
        vpy=bindir/'virtual-python'
        vpy.write_text('''#!/bin/bash
case "$1" in
 -m)
    if [ "$2" = pip ] && [ "$3" = install ] && [ "${FAIL_PIP:-0}" = 1 ]; then exit 24; fi
    exit 0;;
 -c) exit 0;;
 *)
    case "$1" in
      *download_models.py)
        mkdir -p "$HOME/.local/share/hey-frame-v3/models/vosk-model-small-en-us-0.15/am"
        mkdir -p "$HOME/.local/share/hey-frame-v3/models/vits-piper-en_US-glados/espeak-ng-data"
        echo dummy > "$HOME/.local/share/hey-frame-v3/models/vosk-model-small-en-us-0.15/am/final.mdl"
        echo dummy > "$HOME/.local/share/hey-frame-v3/models/vits-piper-en_US-glados/en_US-glados.onnx"
        echo tokens > "$HOME/.local/share/hey-frame-v3/models/vits-piper-en_US-glados/tokens.txt"
        exit 0;;
      *assistant.py)
        if [ "$FAIL_VOICE" = 1 ] && [ "$2" = check-voice ]; then exit 41; fi
        exit 0;;
    esac;;
esac
exit 77
''')
        sys=bindir/'systemctl'
        sys.write_text('''#!/bin/sh
printf '%s\\n' "$*" >> "$HOME/service-calls.txt"
if [ "$2" = is-active ]; then exit 3; fi
if [ "$2" = is-enabled ]; then [ "${PREVIOUS_ENABLED:-0}" = 1 ]; exit $?; fi
exit 0
''')
        for name in ('python3','virtual-python','systemctl'):
            (bindir/name).chmod(0o755)
        for name in ('pw-record','pw-play'):
            p=bindir/name;p.write_text('#!/bin/sh\nexit 0\n');p.chmod(0o755)
        env=dict(os.environ,HOME=str(home),PATH=str(bindir)+':'+os.environ['PATH'])
        return env

    def test_installs_disabled_and_does_not_touch_previous(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            env=self.setup_fake(home)
            old=home/'.local/share/hey-frame/models'; old.mkdir(parents=True)
            (old/'unchanged.txt').write_text('old version')
            p=subprocess.run(['bash',str(BASE/'install.sh')],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr+'\n'+p.stdout)
            self.assertTrue((home/'.local/bin/hey-frame').exists())
            self.assertTrue((home/'.config/systemd/user/hey-frame.service').exists())
            calls=(home/'service-calls.txt').read_text()
            self.assertIn('--user disable --now hey-frame.service',calls)
            self.assertNotIn('--user enable --now hey-frame.service',calls)
            self.assertEqual((old/'unchanged.txt').read_text(),'old version')

    def test_enabled_user_service_stays_enabled_during_upgrade(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            env=self.setup_fake(home)
            env['PREVIOUS_ENABLED']='1'
            p=subprocess.run(['bash',str(BASE/'install.sh')],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stdout+'\n'+p.stderr)
            calls=(home/'service-calls.txt').read_text()
            self.assertIn('--user enable --now hey-frame.service',calls)

    def test_failed_validation_preserves_previous_running_service_and_sources(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            env=self.setup_fake(home)
            env['PREVIOUS_ENABLED']='1'
            env['FAIL_VOICE']='1'
            original=home/'.local/share/hey-frame-v3/src'
            original.mkdir(parents=True)
            (original/'assistant.py').write_text('old stable version')
            p=subprocess.run(['bash',str(BASE/'install.sh')],env=env,
                             capture_output=True,text=True,timeout=15)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual((original/'assistant.py').read_text(),'old stable version')
            calls=(home/'service-calls.txt').read_text()
            self.assertNotIn('--user disable --now hey-frame.service',calls)
            self.assertFalse((home/'.config/systemd/user/hey-frame.service').exists())

    def test_existing_dashboard_is_restarted_after_source_replacement(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            env=self.setup_fake(home)
            sf=home/'.local/share/sfrecorder/venv/bin/python'
            sf.parent.mkdir(parents=True)
            sf.write_text('#!/bin/sh\nexit 0\n')
            sf.chmod(0o755)
            p=subprocess.run(['bash',str(BASE/'install.sh')],env=env,
                             capture_output=True,text=True,timeout=15)
            self.assertEqual(p.returncode,0,p.stderr+'\n'+p.stdout)
            calls=(home/'service-calls.txt').read_text()
            self.assertIn('--user restart hey-frame-dashboard.service',calls)

    def test_failed_dependency_install_does_not_replace_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            env=self.setup_fake(home)
            env['FAIL_PIP']='1'
            binfile=home/'.local/bin/hey-frame';binfile.parent.mkdir(parents=True)
            binfile.write_text('existing launcher')
            p=subprocess.run(['bash',str(BASE/'install.sh')],env=env,capture_output=True,text=True,timeout=15)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(binfile.read_text(),'existing launcher')
            self.assertFalse((home/'.config/systemd/user/hey-frame.service').exists())


if __name__=='__main__': unittest.main()
