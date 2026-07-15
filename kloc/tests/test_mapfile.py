import json
import os
import tempfile
import unittest

from kloc.mapfile import load_map, resolve_loc, iter_loc_ids, find_map_file, LOC_ID_RE


class TestLocIdRe(unittest.TestCase):
    def test_match_simple(self):
        self.assertTrue(LOC_ID_RE.match('L_00000001'))
        self.assertTrue(LOC_ID_RE.match('L_FFFFFFFF'))

    def test_no_match_invalid(self):
        self.assertIsNone(LOC_ID_RE.match('L_0000000'))   # too short
        self.assertIsNone(LOC_ID_RE.match('L_0000000G'))  # invalid char
        self.assertIsNone(LOC_ID_RE.match('X_00000001'))   # wrong prefix

    def test_find_in_text(self):
        text = "UVM_ERROR L_00000001 @ 100ns: mismatch\nUVM_WARNING L_00000002 @ 200ns: timeout\n"
        ids = list(iter_loc_ids(text))
        self.assertEqual(ids, ['L_00000001', 'L_00000002'])


class TestMapFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.map_path = os.path.join(self.tmpdir.name, 'test.kloc.jsonl')

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_jsonl(self, lines):
        with open(self.map_path, 'w') as f:
            for entry in lines:
                f.write(json.dumps(entry) + '\n')

    def test_load_empty_file(self):
        entries = load_map('/nonexistent/path.jsonl')
        self.assertEqual(entries, {})

    def test_load_and_resolve(self):
        self._write_jsonl([
            {'loc_id': 'L_00000001', 'file': 'tb/scoreboard.sv', 'line': 238, 'msg_id': 'PKT_MISMATCH'},
            {'loc_id': 'L_00000002', 'file': 'tb/monitor.sv', 'line': 117, 'msg_id': 'BAD_PKT'},
        ])
        entries = load_map(self.map_path)
        self.assertEqual(len(entries), 2)

        e = resolve_loc(entries, 'L_00000001')
        self.assertIsNotNone(e)
        self.assertEqual(e['file'], 'tb/scoreboard.sv')
        self.assertEqual(e['line'], 238)

        e = resolve_loc(entries, 'L_99999999')
        self.assertIsNone(e)

    def test_load_skips_malformed(self):
        with open(self.map_path, 'w') as f:
            f.write('not json\n')
            f.write('{"loc_id":"L_00000001","file":"x.sv","line":1,"msg_id":"X"}\n')
            f.write('\n')
        entries = load_map(self.map_path)
        self.assertEqual(len(entries), 1)

    def test_skip_entry_without_loc_id(self):
        self._write_jsonl([
            {'file': 'x.sv', 'line': 1},
        ])
        entries = load_map(self.map_path)
        self.assertEqual(len(entries), 0)

    def test_find_map_file(self):
        log = os.path.join(self.tmpdir.name, 'sim.log')
        mapf = log + '.kloc.jsonl'
        with open(mapf, 'w') as f:
            f.write('{}')
        self.assertEqual(find_map_file(log), mapf)

    def test_find_map_file_not_found(self):
        self.assertIsNone(find_map_file('/nonexistent.log'))


if __name__ == '__main__':
    unittest.main()
