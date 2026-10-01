"""测试：资料溯源。"""
import tempfile
import unittest
from pathlib import Path

from superagent.sourcing.registry import SourceRegistry


class TestSourcing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.manifest = Path(self.tmp.name) / "01_需求文档" / "参考资料清单.md"
        self.registry = SourceRegistry(self.manifest)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_source_writes_manifest(self):
        rec = self.registry.add("url", "示例文档", "https://example.com/a", content=b"hello")
        self.assertTrue(rec.content_hash)
        self.assertTrue(self.manifest.exists())
        text = self.manifest.read_text(encoding="utf-8")
        self.assertIn("https://example.com/a", text)
        self.assertIn(rec.content_hash[:12], text)

    def test_recheck_dead_file(self):
        self.registry.add("file", "本地文件", str(Path(self.tmp.name) / "nope.txt"))
        dead = self.registry.recheck()
        self.assertEqual(len(dead), 1)
        self.assertEqual(dead[0].status, "dead")


if __name__ == "__main__":
    unittest.main()
