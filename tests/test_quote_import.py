"""Bulk Portal quote import tests: no data loss and no network required."""
from pathlib import Path
import contextlib
import io
import tempfile
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from jokes import add_quote, add_quotes, import_quotes, personal_quotes, pick
from assistant import main


class QuoteBulkTests(unittest.TestCase):
    def test_add_many_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'quotes.txt'
            added, skipped = add_quotes(['Alpha line', 'Beta line', '  alpha   line  ',
                                         '# ignore this', '', 'Gamma line'], path)
            self.assertEqual((added, skipped), (3, 1))
            self.assertEqual(personal_quotes(path), ['Alpha line', 'Beta line', 'Gamma line'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertIn(pick('personal_quote', path), personal_quotes(path))

    def test_preserves_comments_and_old_quotes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'quotes.txt'
            path.write_text('# My custom labels\nFirst already here\n', encoding='utf-8')
            self.assertEqual(add_quotes(['Second new one'], path), (1, 0))
            self.assertIn('# My custom labels', path.read_text())
            self.assertEqual(personal_quotes(path), ['First already here', 'Second new one'])

    def test_failed_batch_does_not_modify_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'quotes.txt'
            add_quote('Original', path)
            prior = path.read_bytes()
            with self.assertRaises(ValueError):
                add_quotes(['Acceptable', 'Too long ' + ('x' * 400)], path)
            self.assertEqual(path.read_bytes(), prior)

    def test_exceed_limit_is_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'quotes.txt'
            add_quotes([f'Line {i}' for i in range(199)], path)
            prior = path.read_bytes()
            with self.assertRaises(ValueError):
                add_quotes(['New 1', 'New 2'], path)
            self.assertEqual(path.read_bytes(), prior)

    def test_import_txt_file(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'input.txt'
            dest = Path(td) / 'stored.txt'
            file.write_text('Line one\nLine two\n# comment\nLine two\n', encoding='utf-8')
            self.assertEqual(import_quotes(str(file), dest), (2, 1))
            self.assertEqual(personal_quotes(dest), ['Line one', 'Line two'])

    def test_import_from_stdin(self):
        with tempfile.TemporaryDirectory() as td, patch('sys.stdin', io.StringIO('One\nTwo\n')):
            self.assertEqual(import_quotes('-', Path(td) / 'stored.txt'), (2, 0))

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            other = Path(td) / 'other.txt'
            other.write_text('Do not touch me')
            link = Path(td) / 'quotes.txt'
            link.symlink_to(other)
            with self.assertRaises(ValueError):
                add_quotes(['Quote'], link)
            self.assertEqual(other.read_text(), 'Do not touch me')

    def test_multi_cli(self):
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ', {'XDG_CONFIG_HOME': td}):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['add-quotes', 'First line', 'Second line']), 0)
            self.assertIn('Added 2 personal quotes', output.getvalue())

    def test_import_cli(self):
        with tempfile.TemporaryDirectory() as td, patch.dict('os.environ', {'XDG_CONFIG_HOME': td}):
            src = Path(td) / 'lines.txt'
            src.write_text('One\nTwo\n', encoding='utf-8')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(['import-quotes', str(src)]), 0)
            self.assertIn('Imported 2 personal quotes', output.getvalue())


if __name__ == '__main__':
    unittest.main()
