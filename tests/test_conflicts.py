from pathlib import Path
import sys
import unittest
from unittest.mock import patch,MagicMock
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from conflicts import frame_dictation_active
import assistant

class Conflicts(unittest.TestCase):
    def test_detects_active_competing_service_readonly(self):
        with patch('conflicts.shutil.which',return_value='/usr/bin/systemctl'),patch('conflicts.subprocess.run',return_value=MagicMock(returncode=0)) as run:
            self.assertTrue(frame_dictation_active())
            self.assertEqual(run.call_args.args[0],['/usr/bin/systemctl','--user','is-active','--quiet','frame-dictation.service'])

    def test_inactive_service_has_no_warning(self):
        with patch('conflicts.shutil.which',return_value='/usr/bin/systemctl'),patch('conflicts.subprocess.run',return_value=MagicMock(returncode=3)):
            self.assertFalse(frame_dictation_active())

    def test_active_conflict_blocks_start_before_audio(self):
        with patch('assistant.frame_dictation_active',return_value=True),patch('assistant.diagnose') as diagnose:
            self.assertEqual(assistant.main(['start']),1)
            diagnose.assert_not_called()

if __name__=='__main__':unittest.main()
