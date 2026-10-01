"""测试：任务状态机 + 全流水线编排。"""
import tempfile
import unittest
from pathlib import Path

from superagent.core.config import Config
from superagent.core.errors import StateMachineError
from superagent.core.orchestrator import Orchestrator
from superagent.core.runtime import build_runtime
from superagent.core.state import TaskState, TaskStateMachine
from superagent.hitl.approval import Decision


class TestStateMachine(unittest.TestCase):
    def test_happy_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.PLANNED)
        sm.transition(TaskState.RETRIEVING)
        sm.transition(TaskState.PRODUCING)
        sm.transition(TaskState.SELF_CHECKING)
        sm.transition(TaskState.PENDING_APPROVAL)
        sm.transition(TaskState.APPROVED)
        sm.transition(TaskState.ARCHIVED)
        sm.transition(TaskState.DELIVERED)
        self.assertEqual(sm.state, TaskState.DELIVERED)

    def test_illegal(self):
        sm = TaskStateMachine()
        with self.assertRaises(StateMachineError):
            sm.transition(TaskState.DELIVERED)


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        config = Config(project_root=Path(self.tmp.name))
        self.runtime = build_runtime(config)
        self.runtime.approver = lambda req: (Decision.APPROVE, "auto")
        self.orch = Orchestrator(self.runtime)

    def tearDown(self):
        self.runtime.close()
        self.tmp.cleanup()

    def test_short_input_enumerates(self):
        result = self.orch.run("hi")
        self.assertTrue(result["await_confirmation"])
        self.assertGreater(len(result["enumeration"]), 0)

    def test_full_pipeline(self):
        result = self.orch.run("请帮我开发一个响应式登录页面，包含用户名密码表单和验证码")
        self.assertFalse(result["await_confirmation"])
        self.assertEqual(result["state"], "archived")
        self.assertIn("delivery_package", result["artifacts"])
        # 审计应记录 delivery.submit 审批
        rows = self.runtime.audit.query(action="delivery.submit")
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
