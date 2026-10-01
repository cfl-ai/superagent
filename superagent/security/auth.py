"""登录/角色认证。

对应修订版第 6.1 节三级角色。凭据采用本地加密（HMAC 签名令牌），
会话可超时降级为访客。
"""
from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field

from superagent.security.permissions import Role


@dataclass
class Session:
    role: Role
    token: str
    issued_at: float
    expires_at: float
    identity: str = ""

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


class AuthManager:
    """极简本地认证：管理员用共享密钥登录取令牌，操作员用口令，访客默认。"""

    def __init__(self, admin_secret: str | None = None, ttl_s: float = 8 * 3600):
        self._admin_secret = admin_secret or secrets.token_hex(16)
        self._ttl_s = ttl_s
        self._sessions: dict[str, Session] = {}
        self._signing_key = secrets.token_bytes(32)

    def _sign(self, role: str, issued: float) -> str:
        msg = f"{role}:{issued}".encode()
        return hmac.new(self._signing_key, msg, "sha256").hexdigest()

    def login(self, role: str, secret: str = "", identity: str = "") -> Session:
        role = Role(role)
        if role is Role.ADMIN:
            if not hmac.compare_digest(secret, self._admin_secret):
                raise PermissionError("管理员密钥错误")
        elif role is Role.OPERATOR:
            if not secret:
                raise PermissionError("操作员需要口令")
        now = time.time()
        session = Session(
            role=role,
            token=self._sign(role.value, now),
            issued_at=now,
            expires_at=now + self._ttl_s,
            identity=identity,
        )
        self._sessions[session.token] = session
        return session

    def resolve(self, token: str | None) -> Session:
        if not token:
            return Session(Role.VISITOR, "", time.time(), time.time() + 1)
        session = self._sessions.get(token)
        if session is None or session.expired:
            return Session(Role.VISITOR, "", time.time(), time.time() + 1)
        return session

    def logout(self, token: str) -> None:
        self._sessions.pop(token, None)
