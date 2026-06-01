import json
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from xloc.resolver import cmd_resolve, cmd_context


class TestResolver(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.map_path = os.path.join(self.tmpdir.name, 'test.xloc.jsonl')
        with open(self.map_path, 'w') as f:
            entry = json.dumps({'loc_id': 'L_00000001', 'file': 'tb/scoreboard.sv', 'line': 238, 'msg_id': 'PKT_MISMATCH'})
            f.write(entry + '\n')

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_resolve_found(self):
        out = StringIO()
        with patch('sys.stdout', out):
            cmd_resolve('L_00000001', self.map_path)
        output = out.getvalue()
        self.assertIn('L_00000001', output)
        self.assertIn('tb/scoreboard.sv', output)
        self.assertIn('238', output)
        self.assertIn('PKT_MISMATCH', output)

    def test_resolve_not_found(self):
        with self.assertRaises(SystemExit):
            cmd_resolve('L_99999999', self.map_path)

    def test_context_not_found(self):
        with self.assertRaises(SystemExit):
            cmd_context('L_99999999', self.map_path)

    def test_context_file_not_exist(self):
        out = StringIO()
        with patch('sys.stdout', out):
            cmd_context('L_00000001', self.map_path)
        output = out.getvalue()
        self.assertIn('source file not found', output)


if __name__ == '__main__':
    unittest.main()
