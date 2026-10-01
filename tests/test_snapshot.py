"""测试：快照与回滚。"""
import tempfile
import unittest
from pathlib import Path

from superagent.security.snapshot import SnapshotManager


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.snap_dir = Path(self.tmp.name) / "snaps"
        self.manager = SnapshotManager(self.snap_dir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_file_snapshot_rollback(self):
        target = Path(self.tmp.name) / "data.txt"
        target.write_text("v1", encoding="utf-8")
        snap = self.manager.create(target)
        target.write_text("v2", encoding="utf-8")
        self.manager.rollback(snap)
        self.assertEqual(target.read_text(encoding="utf-8"), "v1")

    def test_dir_snapshot(self):
        target = Path(self.tmp.name) / "d"
        target.mkdir()
        (target / "a.txt").write_text("a", encoding="utf-8")
        snap = self.manager.create(target)
        (target / "a.txt").write_text("changed", encoding="utf-8")
        self.manager.rollback(snap)
        self.assertEqual((target / "a.txt").read_text(encoding="utf-8"), "a")


if __name__ == "__main__":
    unittest.main()
