"""测试：审计日志。"""
import tempfile
import unittest
from pathlib import Path

from superagent.security.audit import AuditLogger


class TestAudit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "audit.db"
        self.audit = AuditLogger(self.db)

    def tearDown(self):
        self.audit.close()
        self.tmp.cleanup()

    def test_record_and_query(self):
        eid = self.audit.record(
            subject="operator",
            action="software.install",
            level="S1",
            result="approved",
            obj="C:/apps/foo",
            approval_chain=[{"decision": "approve", "feedback": ""}],
        )
        self.assertTrue(eid)
        rows = self.audit.query(action="software.install")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["level"], "S1")
        self.assertEqual(rows[0]["approval_chain"], [{"decision": "approve", "feedback": ""}])


if __name__ == "__main__":
    unittest.main()
