"""测试：权限分级 S0-S3。"""
import unittest

from superagent.core.config import SecurityConfig
from superagent.core.errors import ApprovalRequired, PermissionDenied
from superagent.security.permissions import (
    Action,
    ActionLevel,
    PermissionGate,
    PermissionPolicy,
    Role,
)


class TestPermissionPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = PermissionPolicy(SecurityConfig())

    def test_blocked(self):
        self.assertEqual(self.policy.classify("system.delete.core"), ActionLevel.S0_BLOCKED)
        self.assertEqual(self.policy.classify("registry.write"), ActionLevel.S0_BLOCKED)
        self.assertEqual(self.policy.classify("watermark.remove.third_party"), ActionLevel.S0_BLOCKED)

    def test_approval(self):
        self.assertEqual(self.policy.classify("software.install"), ActionLevel.S1_APPROVAL)
        self.assertEqual(self.policy.classify("delivery.submit"), ActionLevel.S1_APPROVAL)
        self.assertEqual(self.policy.classify("file.delete"), ActionLevel.S1_APPROVAL)

    def test_whitelist(self):
        self.assertEqual(self.policy.classify("cache.clean.temp"), ActionLevel.S2_WHITELIST)
        self.assertEqual(self.policy.classify("venv.pip.install.requests"), ActionLevel.S2_WHITELIST)

    def test_auto_default(self):
        # 不匹配任何前缀的动作默认 S3（只读自动审计）
        self.assertEqual(self.policy.classify("analyze.text"), ActionLevel.S3_AUTO)
        self.assertEqual(self.policy.classify("preview.report"), ActionLevel.S3_AUTO)


class TestPermissionGate(unittest.TestCase):
    def setUp(self):
        self.policy = PermissionPolicy(SecurityConfig())

    def test_blocked_raises(self):
        gate = PermissionGate(self.policy, Role.ADMIN)
        with self.assertRaises(PermissionDenied):
            gate.enforce(Action("registry.write"))

    def test_approval_raises(self):
        gate = PermissionGate(self.policy, Role.OPERATOR)
        with self.assertRaises(ApprovalRequired):
            gate.enforce(Action("software.install"))

    def test_whitelist_passes(self):
        gate = PermissionGate(self.policy, Role.OPERATOR)
        self.assertEqual(gate.enforce(Action("cache.clean.temp")), ActionLevel.S2_WHITELIST)


if __name__ == "__main__":
    unittest.main()
