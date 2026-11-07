"""Benchmark reports CPU/RSS only and never mutates service state."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'src'))
from perf import main_pid, process_stats, measure, describe

class PerfTests(unittest.TestCase):
    def test_stat_parser_with_spaces_in_name(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'123';f.mkdir()
            # proc stat fields after ')' start at state (3); utime/ stime fields 14,15.
            fields=['S'] + ['0']*19
            fields[11]='200';fields[12]='100'
            (f/'stat').write_text('123 (hey frame voice) '+ ' '.join(fields))
            (f/'status').write_text('Name: heyframe\nVmRSS:   45000 kB\n')
            self.assertEqual(process_stats(123,Path(d)),(300,45000))

    def test_process_sampler_is_readonly(self):
        values=[(100,25000),(300,26000)]
        clock=[100.]
        def sample(pid):return values.pop(0)
        def wait(n):clock[0]+=n
        with patch('perf.process_stats',side_effect=sample),patch('perf.os.sysconf',return_value=100):
            result=measure(10,pid=123,clock=lambda:clock[0],pause=wait)
        self.assertEqual(result['cpu_percent'],20.0)
        self.assertGreater(result['rss_mib'],20)
        self.assertIn('one core',describe(result))

    def test_missing_service_is_not_started(self):
        with patch('perf.main_pid',return_value=None):
            with self.assertRaisesRegex(RuntimeError,'not running'):
                measure(10)

if __name__=='__main__': unittest.main()
