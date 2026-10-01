"""测试：HITL 审批队列。"""
import tempfile
import threading
import unittest
from pathlib import Path

from superagent.core.errors import ApprovalTimeout
from superagent.hitl.approval import ApprovalQueue, Decision


class TestApproval(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.q = ApprovalQueue(Path(self.tmp.name) / "approvals.jsonl", timeout_s=1.0)

    def tearDown(self):
        self.q.close()
        self.tmp.cleanup()

    def test_decide_flow(self):
        req = self.q.request("software.install", resource="C:/apps/foo")
        self.assertIsNone(req.decision)
        result = self.q.decide(req.id, Decision.APPROVE)
        self.assertEqual(result.decision, Decision.APPROVE)
        self.assertTrue(result.decided_at)

    def test_wait_timeout(self):
        req = self.q.request("software.install", timeout_s=0.3)
        with self.assertRaises(ApprovalTimeout):
            self.q.wait(req, poll_s=0.05)

    def test_concurrent_decide(self):
        req = self.q.request("delivery.submit")

        def decider():
            import time
            time.sleep(0.2)
            self.q.decide(req.id, Decision.APPROVE, "ok")

        t = threading.Thread(target=decider)
        t.start()
        decision = self.q.wait(req, poll_s=0.05)
        t.join()
        self.assertEqual(decision, Decision.APPROVE)
        self.assertEqual(req.feedback, "ok")


if __name__ == "__main__":
    unittest.main()
