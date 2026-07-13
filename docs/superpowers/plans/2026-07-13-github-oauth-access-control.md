# GitHub OAuth 登录与用户白名单实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 为 Media Manager 增加内置 GitHub OAuth 登录，以环境变量维护用户名白名单，并默认保护全部页面和 API。

**架构：** 新增独立的 `auth.py`，集中处理认证配置、PKCE、GitHub API、签名 Cookie 和认证页面；`server.py` 只负责路由、中间件和 Cookie 生命周期。前端不接触 OAuth token，只通过后端退出接口清除会话。

**技术栈：** Python 3.11+ 标准库、FastAPI、现有 `httpx`/TestClient 测试栈、React 19、TypeScript、Vite、Docker Compose。

---

## 文件边界

- 新建 `backend/src/media_manager/auth.py`：认证配置、PKCE、GitHub OAuth 客户端、HMAC Cookie、登录与错误 HTML。
- 新建 `backend/tests/test_auth.py`：认证模块单元测试及登录流程集成测试。
- 修改 `backend/src/media_manager/server.py`：应用工厂认证参数、全局中间件、登录/回调/退出路由。
- 修改 `backend/tests/test_server.py`：现有业务接口测试显式使用 `auth_enabled=False`。
- 修改 `frontend/src/App.tsx`：顶部工具栏增加退出按钮并调用后端接口。
- 修改 `docker-compose.yml`：传入五个必需的认证环境变量。
- 修改 `README.md`：补充 GitHub OAuth App、secret、Docker 和 Compose 配置说明。

### 任务 1：实现认证配置与签名 Cookie

**文件：**
- 新建：`backend/src/media_manager/auth.py`
- 新建：`backend/tests/test_auth.py`

- [ ] **步骤 1：先写配置和 Cookie 失败测试**

创建 `backend/tests/test_auth.py`，先加入以下测试基线：

```python
from __future__ import annotations

from unittest.mock import patch
import base64
import hashlib
import json
import os
import unittest

from media_manager.auth import (
    AuthConfig,
    AuthConfigError,
    GitHubUser,
    create_oauth_request,
    issue_session_cookie,
    load_auth_config,
    read_session_cookie,
    verify_oauth_state,
)


VALID_ENV = {
    "MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com",
    "MEDIA_MANAGER_SESSION_SECRET": "s" * 32,
    "GITHUB_OAUTH_CLIENT_ID": "client-id",
    "GITHUB_OAUTH_CLIENT_SECRET": "client-secret",
    "GITHUB_ALLOWED_USERS": " Wang-YN, other-user ",
}


class AuthConfigTest(unittest.TestCase):
    def test_loads_and_normalizes_auth_config(self) -> None:
        config = load_auth_config(VALID_ENV)

        self.assertEqual(config.public_url, VALID_ENV["MEDIA_MANAGER_PUBLIC_URL"])
        self.assertEqual(config.callback_url, f"{VALID_ENV['MEDIA_MANAGER_PUBLIC_URL']}/auth/github/callback")
        self.assertTrue(config.allows("wang-yn"))
        self.assertTrue(config.allows("WANG-YN"))
        self.assertFalse(config.allows("not-allowed"))

    def test_rejects_missing_required_values(self) -> None:
        for name in VALID_ENV:
            with self.subTest(name=name):
                values = dict(VALID_ENV)
                values.pop(name)
                with self.assertRaises(AuthConfigError):
                    load_auth_config(values)

    def test_rejects_invalid_public_url_secret_and_users(self) -> None:
        invalid_values = [
            {**VALID_ENV, "MEDIA_MANAGER_PUBLIC_URL": "http://example.com"},
            {**VALID_ENV, "MEDIA_MANAGER_PUBLIC_URL": "https://example.com/"},
            {**VALID_ENV, "MEDIA_MANAGER_PUBLIC_URL": "https://example.com/path"},
            {**VALID_ENV, "MEDIA_MANAGER_SESSION_SECRET": "short"},
            {**VALID_ENV, "GITHUB_ALLOWED_USERS": " , "},
        ]

        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(AuthConfigError):
                    load_auth_config(values)


class SignedCookieTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_auth_config(VALID_ENV)
        self.user = GitHubUser(id=123, login="wang-yn")

    def test_session_round_trip_and_case_insensitive_allowlist(self) -> None:
        token = issue_session_cookie(self.config, self.user, now=1_000)

        self.assertEqual(read_session_cookie(self.config, token, now=1_001), self.user)

    def test_rejects_tampered_and_expired_session(self) -> None:
        token = issue_session_cookie(self.config, self.user, now=1_000)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        self.assertIsNone(read_session_cookie(self.config, tampered, now=1_001))
        self.assertIsNone(read_session_cookie(self.config, token, now=1_000 + 7 * 24 * 60 * 60 + 1))

    def test_rechecks_allowlist_when_session_is_read(self) -> None:
        token = issue_session_cookie(self.config, self.user, now=1_000)
        changed = AuthConfig(
            public_url=self.config.public_url,
            session_secret=self.config.session_secret,
            client_id=self.config.client_id,
            client_secret=self.config.client_secret,
            allowed_users=frozenset({"other-user"}),
        )

        self.assertIsNone(read_session_cookie(changed, token, now=1_001))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **步骤 2：运行测试，确认因认证模块不存在而失败**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
```

预期：失败，错误包含 `ModuleNotFoundError: No module named 'media_manager.auth'`。

- [ ] **步骤 3：实现配置、PKCE 和签名 Cookie 的最小代码**

创建 `backend/src/media_manager/auth.py`，先实现以下完整内容；GitHub HTTP 客户端和页面函数在任务 2 追加：

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit
import base64
import hashlib
import hmac
import json
import os
import secrets
import time


OAUTH_COOKIE_NAME = "media_manager_oauth"
SESSION_COOKIE_NAME = "media_manager_session"
OAUTH_TTL_SECONDS = 10 * 60
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"


class AuthConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AuthConfig:
    public_url: str
    session_secret: bytes
    client_id: str
    client_secret: str
    allowed_users: frozenset[str]

    @property
    def callback_url(self) -> str:
        return f"{self.public_url}/auth/github/callback"

    def allows(self, login: str) -> bool:
        return login.casefold() in self.allowed_users


@dataclass(frozen=True)
class GitHubUser:
    id: int
    login: str


@dataclass(frozen=True)
class OAuthRequest:
    authorize_url: str
    cookie_value: str


def load_auth_config(environ: Mapping[str, str] | None = None) -> AuthConfig:
    values = os.environ if environ is None else environ
    public_url = _required(values, "MEDIA_MANAGER_PUBLIC_URL")
    parsed = urlsplit(public_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or public_url.endswith("/")
    ):
        raise AuthConfigError("MEDIA_MANAGER_PUBLIC_URL 必须是无末尾斜杠的 HTTPS 地址")

    secret = _required(values, "MEDIA_MANAGER_SESSION_SECRET").encode("utf-8")
    if len(secret) < 32:
        raise AuthConfigError("MEDIA_MANAGER_SESSION_SECRET 至少需要 32 字节")

    users = frozenset(
        login.strip().casefold()
        for login in _required(values, "GITHUB_ALLOWED_USERS").split(",")
        if login.strip()
    )
    if not users:
        raise AuthConfigError("GITHUB_ALLOWED_USERS 至少需要一个用户名")

    return AuthConfig(
        public_url=public_url,
        session_secret=secret,
        client_id=_required(values, "GITHUB_OAUTH_CLIENT_ID"),
        client_secret=_required(values, "GITHUB_OAUTH_CLIENT_SECRET"),
        allowed_users=users,
    )


def create_oauth_request(config: AuthConfig, now: int | None = None) -> OAuthRequest:
    issued_at = _now(now)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    cookie = _encode_signed(
        {
            "kind": "oauth",
            "state": state,
            "verifier": verifier,
            "iat": issued_at,
            "exp": issued_at + OAUTH_TTL_SECONDS,
        },
        config.session_secret,
    )
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.callback_url,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"
    return OAuthRequest(authorize_url=authorize_url, cookie_value=cookie)


def verify_oauth_state(config: AuthConfig, token: str | None, returned_state: str | None, now: int | None = None) -> str | None:
    payload = _decode_signed(token, config.session_secret, "oauth", now)
    if payload is None or not returned_state:
        return None
    expected_state = payload.get("state")
    verifier = payload.get("verifier")
    if not isinstance(expected_state, str) or not isinstance(verifier, str):
        return None
    if not hmac.compare_digest(expected_state, returned_state):
        return None
    return verifier


def issue_session_cookie(config: AuthConfig, user: GitHubUser, now: int | None = None) -> str:
    issued_at = _now(now)
    return _encode_signed(
        {
            "kind": "session",
            "id": user.id,
            "login": user.login,
            "iat": issued_at,
            "exp": issued_at + SESSION_TTL_SECONDS,
        },
        config.session_secret,
    )


def read_session_cookie(config: AuthConfig, token: str | None, now: int | None = None) -> GitHubUser | None:
    payload = _decode_signed(token, config.session_secret, "session", now)
    if payload is None:
        return None
    user_id = payload.get("id")
    login = payload.get("login")
    if not isinstance(user_id, int) or not isinstance(login, str) or not login or not config.allows(login):
        return None
    return GitHubUser(id=user_id, login=login)


def _required(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise AuthConfigError(f"缺少必需环境变量 {name}")
    return value


def _encode_signed(payload: dict[str, object], secret: bytes) -> str:
    body = _base64url(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _base64url(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def _decode_signed(token: str | None, secret: bytes, kind: str, now: int | None) -> dict[str, object] | None:
    if not token:
        return None
    try:
        body, signature = token.split(".", 1)
        expected = _base64url(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_decode_base64url(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("kind") != kind:
        return None
    expires_at = payload.get("exp")
    if not isinstance(expires_at, int) or expires_at < _now(now):
        return None
    return payload


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _now(value: int | None) -> int:
    return int(time.time()) if value is None else value
```

- [ ] **步骤 4：运行认证测试并确认通过**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
```

预期：`AuthConfigTest` 和 `SignedCookieTest` 全部通过。

- [ ] **步骤 5：提交配置与 Cookie 基线**

```bash
git add backend/src/media_manager/auth.py backend/tests/test_auth.py
git commit -m "feat: add GitHub auth configuration and sessions"
```

### 任务 2：实现 PKCE 参数校验和 GitHub 身份查询

**文件：**
- 修改：`backend/src/media_manager/auth.py`
- 修改：`backend/tests/test_auth.py`

- [ ] **步骤 1：补充 PKCE 与 GitHub 客户端失败测试**

在 `backend/tests/test_auth.py` 导入列表中加入 `GitHubOAuthClient`、`GitHubOAuthError`，并追加：

```python
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class OAuthProtocolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_auth_config(VALID_ENV)

    def test_authorize_url_contains_fixed_callback_state_and_pkce_s256(self) -> None:
        request = create_oauth_request(self.config, now=1_000)
        query = parse_qs(urlparse(request.authorize_url).query)
        verifier = verify_oauth_state(self.config, request.cookie_value, query["state"][0], now=1_001)
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")

        self.assertEqual(query["client_id"], ["client-id"])
        self.assertEqual(query["redirect_uri"], [self.config.callback_url])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code_challenge"], [expected_challenge])
        self.assertNotIn("scope", query)

    def test_oauth_state_rejects_mismatch_tampering_and_expiry(self) -> None:
        request = create_oauth_request(self.config, now=1_000)
        state = parse_qs(urlparse(request.authorize_url).query)["state"][0]
        tampered = request.cookie_value[:-1] + "A"

        self.assertIsNone(verify_oauth_state(self.config, request.cookie_value, "wrong", now=1_001))
        self.assertIsNone(verify_oauth_state(self.config, tampered, state, now=1_001))
        self.assertIsNone(verify_oauth_state(self.config, request.cookie_value, state, now=1_601))


class GitHubOAuthClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_auth_config(VALID_ENV)

    def test_exchanges_code_then_reads_user(self) -> None:
        seen: list[Request] = []

        def opener(request: Request, timeout: int) -> FakeResponse:
            seen.append(request)
            if request.full_url == "https://github.com/login/oauth/access_token":
                return FakeResponse({"access_token": "temporary-token", "token_type": "bearer"})
            return FakeResponse({"id": 123, "login": "wang-yn"})

        user = GitHubOAuthClient(opener=opener).authenticate(self.config, "code", "verifier")

        token_body = seen[0].data.decode("utf-8")
        self.assertIn("client_secret=client-secret", token_body)
        self.assertIn("redirect_uri=https%3A%2F%2Fmedia.example.com%2Fauth%2Fgithub%2Fcallback", token_body)
        self.assertIn("code_verifier=verifier", token_body)
        self.assertEqual(seen[1].get_header("Authorization"), "Bearer temporary-token")
        self.assertEqual(user, GitHubUser(id=123, login="wang-yn"))

    def test_maps_http_and_malformed_payloads_to_safe_error(self) -> None:
        def http_failure(request: Request, timeout: int) -> FakeResponse:
            raise HTTPError(request.full_url, 500, "failure", {}, None)

        def malformed_token(request: Request, timeout: int) -> FakeResponse:
            return FakeResponse({"token_type": "bearer"})

        def user_http_failure(request: Request, timeout: int) -> FakeResponse:
            if request.full_url == "https://github.com/login/oauth/access_token":
                return FakeResponse({"access_token": "temporary-token"})
            raise HTTPError(request.full_url, 500, "failure", {}, None)

        def malformed_user(request: Request, timeout: int) -> FakeResponse:
            if request.full_url == "https://github.com/login/oauth/access_token":
                return FakeResponse({"access_token": "temporary-token"})
            return FakeResponse({"id": 123})

        for opener in (http_failure, malformed_token, user_http_failure, malformed_user):
            with self.subTest(opener=opener):
                with self.assertRaisesRegex(GitHubOAuthError, "GitHub OAuth 请求失败"):
                    GitHubOAuthClient(opener=opener).authenticate(self.config, "code", "verifier")
```

- [ ] **步骤 2：运行新增测试并确认 GitHub 客户端尚未定义**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
```

预期：失败，错误指出 `GitHubOAuthClient` 或 `GitHubOAuthError` 尚未定义。

- [ ] **步骤 3：实现同步 GitHub OAuth 客户端**

在 `backend/src/media_manager/auth.py` 补充导入：

```python
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import json
```

在常量区加入：

```python
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
Opener = Callable[[Request, int], object]
```

在 `AuthConfigError` 后加入：

```python
class GitHubOAuthError(RuntimeError):
    pass
```

在文件末尾加入完整客户端：

```python
class GitHubOAuthClient:
    def __init__(self, opener: Opener | None = None) -> None:
        self.opener = opener or urlopen

    def authenticate(self, config: AuthConfig, code: str, verifier: str) -> GitHubUser:
        token_payload = self._request_json(
            Request(
                GITHUB_TOKEN_URL,
                data=urlencode(
                    {
                        "client_id": config.client_id,
                        "client_secret": config.client_secret,
                        "code": code,
                        "redirect_uri": config.callback_url,
                        "code_verifier": verifier,
                    }
                ).encode("utf-8"),
                headers={"Accept": "application/json"},
                method="POST",
            )
        )
        access_token = token_payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise GitHubOAuthError("GitHub OAuth 请求失败")

        user_payload = self._request_json(
            Request(
                GITHUB_USER_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "User-Agent": "Media-Manager",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        )
        user_id = user_payload.get("id")
        login = user_payload.get("login")
        if not isinstance(user_id, int) or not isinstance(login, str) or not login:
            raise GitHubOAuthError("GitHub OAuth 请求失败")
        return GitHubUser(id=user_id, login=login)

    def _request_json(self, request: Request) -> dict[str, Any]:
        try:
            with self.opener(request, 10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise GitHubOAuthError("GitHub OAuth 请求失败") from exc
        if not isinstance(payload, dict):
            raise GitHubOAuthError("GitHub OAuth 请求失败")
        return payload
```

注意：`access_token` 只存在于 `authenticate()` 局部变量中，不写日志、Cookie、配置或文件。

- [ ] **步骤 4：运行认证模块全部测试**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
```

预期：配置、Cookie、PKCE、GitHub token 和 `/user` 测试全部通过。

- [ ] **步骤 5：提交 OAuth 协议实现**

```bash
git add backend/src/media_manager/auth.py backend/tests/test_auth.py
git commit -m "feat: implement GitHub OAuth identity lookup"
```

### 任务 3：接入登录路由和全局访问控制

**文件：**
- 修改：`backend/src/media_manager/auth.py`（文件末尾增加页面渲染函数）
- 修改：`backend/src/media_manager/server.py:8-176`
- 修改：`backend/tests/test_auth.py`
- 修改：`backend/tests/test_server.py:42-654`

- [ ] **步骤 1：先写服务端访问控制测试**

在 `backend/tests/test_auth.py` 补充导入：

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import warnings

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")
from fastapi.testclient import TestClient

from media_manager.config import AppConfig
from media_manager.auth import OAUTH_COOKIE_NAME, SESSION_COOKIE_NAME
```

追加以下测试类：

```python
class FakeGitHubClient:
    def __init__(self, user: GitHubUser | None = None, error: Exception | None = None) -> None:
        self.user = user or GitHubUser(id=123, login="wang-yn")
        self.error = error
        self.calls: list[tuple[str, str]] = []

    def authenticate(self, config: AuthConfig, code: str, verifier: str) -> GitHubUser:
        self.calls.append((code, verifier))
        if self.error:
            raise self.error
        return self.user


class AuthServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app_config = AppConfig(path=root / "config.toml", raw={"paths": {"media_dir": str(root / "media")}}, libraries=[])
        self.auth_config = load_auth_config(VALID_ENV)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def client(self, github_client: FakeGitHubClient | None = None) -> TestClient:
        from media_manager.server import create_app

        app = create_app(config=self.app_config, auth_config=self.auth_config, github_client=github_client or FakeGitHubClient())
        return TestClient(app, base_url="https://testserver")

    def test_unauthenticated_api_is_json_401_and_page_redirects_to_login(self) -> None:
        client = self.client()

        api = client.get("/api/health")
        page = client.get("/", follow_redirects=False)

        self.assertEqual(api.status_code, 401)
        self.assertEqual(api.json()["error"]["code"], "authentication_required")
        self.assertEqual(page.status_code, 303)
        self.assertEqual(page.headers["location"], "/login")

    def test_login_and_callback_are_public_and_issue_secure_cookies(self) -> None:
        github = FakeGitHubClient()
        client = self.client(github)

        login_page_response = client.get("/login")
        authorize = client.get("/auth/github/login", follow_redirects=False)
        oauth_cookie = authorize.cookies.get(OAUTH_COOKIE_NAME)
        state = parse_qs(urlparse(authorize.headers["location"]).query)["state"][0]
        verifier = verify_oauth_state(self.auth_config, oauth_cookie, state)
        callback = client.get(f"/auth/github/callback?code=code&state={state}", follow_redirects=False)

        self.assertEqual(login_page_response.status_code, 200)
        self.assertIn("使用 GitHub 登录", login_page_response.text)
        self.assertEqual(authorize.status_code, 303)
        self.assertIn("Secure", authorize.headers["set-cookie"])
        self.assertIn("HttpOnly", authorize.headers["set-cookie"])
        self.assertEqual(github.calls, [("code", verifier)])
        self.assertEqual(callback.status_code, 303)
        self.assertEqual(callback.headers["location"], "/")
        self.assertIn(SESSION_COOKIE_NAME, callback.headers["set-cookie"])
        self.assertIn("Max-Age=604800", callback.headers["set-cookie"])
        self.assertIn("SameSite=lax", callback.headers["set-cookie"])
        self.assertIn("Secure", callback.headers["set-cookie"])
        self.assertIn("HttpOnly", callback.headers["set-cookie"])
        self.assertEqual(client.get("/api/health").status_code, 200)

    def test_callback_rejects_bad_state_github_failure_and_disallowed_user(self) -> None:
        cases = [
            (FakeGitHubClient(), "wrong", 400, "登录请求无效"),
            (FakeGitHubClient(error=GitHubOAuthError("GitHub OAuth 请求失败")), None, 502, "GitHub 登录失败"),
            (FakeGitHubClient(user=GitHubUser(id=999, login="intruder")), None, 403, "该账号未获授权"),
        ]

        for github, forced_state, expected_status, expected_text in cases:
            with self.subTest(expected_status=expected_status):
                client = self.client(github)
                authorize = client.get("/auth/github/login", follow_redirects=False)
                state = parse_qs(urlparse(authorize.headers["location"]).query)["state"][0]
                callback_state = forced_state or state
                response = client.get(f"/auth/github/callback?code=code&state={callback_state}", follow_redirects=False)
                self.assertEqual(response.status_code, expected_status)
                self.assertIn(expected_text, response.text)

    def test_missing_code_state_or_temporary_cookie_is_400(self) -> None:
        missing_cookie = self.client().get("/auth/github/callback?code=code&state=state")

        client = self.client()
        authorize = client.get("/auth/github/login", follow_redirects=False)
        state = parse_qs(urlparse(authorize.headers["location"]).query)["state"][0]
        missing_code = client.get(f"/auth/github/callback?state={state}")

        second_client = self.client()
        second_client.get("/auth/github/login", follow_redirects=False)
        missing_state = second_client.get("/auth/github/callback?code=code")

        for response in (missing_cookie, missing_code, missing_state):
            self.assertEqual(response.status_code, 400)
            self.assertIn("登录请求无效", response.text)

    def test_logout_clears_session_and_returns_login_location(self) -> None:
        client = self.client()
        client.cookies.set(SESSION_COOKIE_NAME, issue_session_cookie(self.auth_config, GitHubUser(123, "wang-yn")))

        response = client.post("/auth/logout")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"redirect": "/login"})
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        self.assertEqual(client.get("/api/health").status_code, 401)

    def test_auth_configuration_is_required_by_default_but_can_be_disabled_only_in_factory(self) -> None:
        from media_manager.server import create_app

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(AuthConfigError):
                create_app(config=self.app_config)
            self.assertEqual(TestClient(create_app(config=self.app_config, auth_enabled=False)).get("/api/health").status_code, 200)
```

- [ ] **步骤 2：运行服务端认证测试并确认路由和工厂参数尚未实现**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
```

预期：失败，错误包含 `unexpected keyword argument 'auth_config'` 或登录路由返回 404。

- [ ] **步骤 3：在认证模块中加入内联 HTML 页面**

在 `backend/src/media_manager/auth.py` 增加 `from html import escape`，并加入：

```python
def login_page(message: str | None = None) -> str:
    notice = f'<p class="notice">{escape(message)}</p>' if message else ""
    return _page(
        "Media Manager",
        f"""
        <p class="eyebrow">Media Manager</p>
        <h1>影视媒体库</h1>
        {notice}
        <a class="primary" href="/auth/github/login">使用 GitHub 登录</a>
        """,
    )


def login_error_page(title: str, message: str) -> str:
    return _page(
        title,
        f"""
        <p class="eyebrow">Media Manager</p>
        <h1>{escape(title)}</h1>
        <p class="notice">{escape(message)}</p>
        <a class="primary" href="/auth/github/login">重新登录</a>
        """,
    )


def forbidden_page(login: str) -> str:
    return login_error_page("该账号未获授权", f"GitHub 用户 {login} 不在允许名单中。")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ color: #1f2933; background: #eef2f3; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ min-height: 100vh; margin: 0; display: grid; place-items: center; padding: 24px; }}
    main {{ width: min(420px, 100%); }}
    .eyebrow {{ color: #52616b; font-size: 13px; margin: 0 0 8px; }}
    h1 {{ margin: 0 0 24px; font-size: 30px; letter-spacing: 0; }}
    .notice {{ margin: 0 0 20px; color: #8a2f2f; line-height: 1.6; }}
    .primary {{ display: inline-flex; min-height: 44px; align-items: center; padding: 0 18px; border-radius: 6px; background: #1f6f64; color: white; text-decoration: none; }}
  </style>
</head>
<body><main>{body}</main></body>
</html>"""
```

- [ ] **步骤 4：修改应用工厂并注册认证中间件与路由**

在 `backend/src/media_manager/server.py` 调整导入：

```python
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from .auth import (
    OAUTH_COOKIE_NAME,
    OAUTH_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    AuthConfig,
    GitHubOAuthClient,
    GitHubOAuthError,
    create_oauth_request,
    forbidden_page,
    issue_session_cookie,
    load_auth_config,
    login_error_page,
    login_page,
    read_session_cookie,
    verify_oauth_state,
)
```

在 `STATIC_DIR` 后加入：

```python
PUBLIC_AUTH_PATHS = {"/login", "/auth/github/login", "/auth/github/callback"}
```

将应用工厂签名和初始化改为：

```python
def create_app(
    config: AppConfig | None = None,
    *,
    auth_enabled: bool = True,
    auth_config: AuthConfig | None = None,
    github_client: GitHubOAuthClient | None = None,
) -> FastAPI:
    app = FastAPI(title="Media Manager")
    app.state.config = config or load_config()
    app.state.auth_config = (auth_config or load_auth_config()) if auth_enabled else None
    app.state.github_client = (github_client or GitHubOAuthClient()) if auth_enabled else None
```

紧接 `AppError` 异常处理器之后加入中间件和认证路由：

```python
    @app.middleware("http")
    async def require_authentication(request: Request, call_next: Any) -> Response:
        if not auth_enabled or request.url.path in PUBLIC_AUTH_PATHS:
            return await call_next(request)
        auth = _auth_config(app)
        user = read_session_cookie(auth, request.cookies.get(SESSION_COOKIE_NAME))
        if user is None:
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    {"error": {"code": "authentication_required", "message": "需要登录"}},
                    status_code=401,
                )
            return RedirectResponse("/login", status_code=303)
        request.state.github_user = user
        return await call_next(request)

    @app.get("/login")
    def auth_login_page(request: Request) -> Response:
        auth = _auth_config(app)
        if read_session_cookie(auth, request.cookies.get(SESSION_COOKIE_NAME)) is not None:
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(login_page())

    @app.get("/auth/github/login")
    def auth_github_login() -> Response:
        oauth_request = create_oauth_request(_auth_config(app))
        response = RedirectResponse(oauth_request.authorize_url, status_code=303)
        response.set_cookie(
            OAUTH_COOKIE_NAME,
            oauth_request.cookie_value,
            max_age=OAUTH_TTL_SECONDS,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/auth/github/callback")
    def auth_github_callback(request: Request) -> Response:
        auth = _auth_config(app)
        code = request.query_params.get("code")
        returned_state = request.query_params.get("state")
        verifier = verify_oauth_state(auth, request.cookies.get(OAUTH_COOKIE_NAME), returned_state)
        if not code or verifier is None:
            return _clear_oauth_cookie(
                HTMLResponse(login_error_page("登录请求无效", "登录请求已失效，请重新登录。"), status_code=400)
            )
        try:
            user = _github_client(app).authenticate(auth, code, verifier)
        except GitHubOAuthError:
            return _clear_oauth_cookie(
                HTMLResponse(login_error_page("GitHub 登录失败", "暂时无法完成 GitHub 登录，请稍后重试。"), status_code=502)
            )
        if not auth.allows(user.login):
            return _clear_oauth_cookie(HTMLResponse(forbidden_page(user.login), status_code=403))

        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            issue_session_cookie(auth, user),
            max_age=SESSION_TTL_SECONDS,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return _clear_oauth_cookie(response)

    @app.post("/auth/logout")
    def auth_logout() -> Response:
        response = JSONResponse({"redirect": "/login"})
        response.delete_cookie(SESSION_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
        return response
```

在 `server.py` 的辅助函数区加入：

```python
def _auth_config(app: FastAPI) -> AuthConfig:
    config = app.state.auth_config
    if not isinstance(config, AuthConfig):
        raise RuntimeError("authentication is disabled")
    return config


def _github_client(app: FastAPI) -> GitHubOAuthClient:
    return app.state.github_client


def _clear_oauth_cookie(response: Response) -> Response:
    response.delete_cookie(OAUTH_COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
    return response
```

`run()` 保持调用 `create_app(config)`，因此实际启动始终要求五个认证环境变量；不要增加 `MEDIA_MANAGER_AUTH_ENABLED` 一类部署绕过配置。

- [ ] **步骤 5：让既有业务接口测试显式关闭认证**

在 `backend/tests/test_server.py` 中将全部 18 处：

```python
create_app()
```

替换为：

```python
create_app(auth_enabled=False)
```

这只隔离既有业务测试，不改变生产启动路径。

- [ ] **步骤 6：运行认证测试和完整后端回归测试**

运行：

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover -s backend/tests -p 'test_auth.py' -v
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
```

预期：认证测试全部通过；完整后端测试输出 `OK`，原有媒体库、TMDB、ASSRT、重命名和删除行为无回归。

- [ ] **步骤 7：提交服务端认证接入**

```bash
git add backend/src/media_manager/auth.py backend/src/media_manager/server.py backend/tests/test_auth.py backend/tests/test_server.py
git commit -m "feat: protect application with GitHub OAuth"
```

### 任务 4：增加前端退出入口

**文件：**
- 修改：`frontend/src/App.tsx:211-228`
- 修改：`frontend/src/App.tsx:618-625`

- [ ] **步骤 1：实现退出命令**

在 `App()` 中、`refresh()` 后加入：

```tsx
  async function logout() {
    setBusy("logout");
    setError(null);
    try {
      const result = await request<{ redirect: string }>("/auth/logout", { method: "POST" });
      window.location.assign(result.redirect);
    } catch (err) {
      setError(messageFrom(err));
      setBusy(null);
    }
  }
```

在 `.top-actions` 内的“设置”按钮后加入：

```tsx
          <button type="button" onClick={logout} disabled={busy === "logout"}>
            {busy === "logout" ? "退出中" : "退出"}
          </button>
```

复用现有按钮样式，不新增图标依赖，也不在浏览器中保存用户资料或 OAuth token。

- [ ] **步骤 2：运行 TypeScript 和生产构建验证**

运行：

```bash
npm run build --prefix frontend
```

预期：`tsc --noEmit` 和 Vite build 成功，生成 `frontend/dist`。

- [ ] **步骤 3：提交前端退出入口**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add authenticated logout action"
```

### 任务 5：补齐 Docker 与 README 部署配置

**文件：**
- 修改：`docker-compose.yml:1-18`
- 修改：`README.md:4-75`

- [ ] **步骤 1：让 Compose 显式传递认证环境变量**

在 `docker-compose.yml` 的 `environment` 列表中加入：

```yaml
      - MEDIA_MANAGER_PUBLIC_URL=${MEDIA_MANAGER_PUBLIC_URL}
      - MEDIA_MANAGER_SESSION_SECRET=${MEDIA_MANAGER_SESSION_SECRET}
      - GITHUB_OAUTH_CLIENT_ID=${GITHUB_OAUTH_CLIENT_ID}
      - GITHUB_OAUTH_CLIENT_SECRET=${GITHUB_OAUTH_CLIENT_SECRET}
      - GITHUB_ALLOWED_USERS=${GITHUB_ALLOWED_USERS}
```

不要把实际 client secret 或 session secret 写入 Compose 文件。

- [ ] **步骤 2：在 README 说明 OAuth App 和环境变量**

在 `README.md` 的部署章节前加入：

````markdown
## GitHub 登录配置

在 GitHub 的 **Settings -> Developer settings -> OAuth Apps** 创建 OAuth App：

- Homepage URL：`https://media.example.com`
- Authorization callback URL：`https://media.example.com/auth/github/callback`

生成独立的会话签名 secret：

```bash
openssl rand -hex 32
```

部署前设置以下环境变量：

```bash
export MEDIA_MANAGER_PUBLIC_URL=https://media.example.com
export MEDIA_MANAGER_SESSION_SECRET=上一步生成的随机值
export GITHUB_OAUTH_CLIENT_ID=你的_OAuth_App_Client_ID
export GITHUB_OAUTH_CLIENT_SECRET=你的_OAuth_App_Client_Secret
export GITHUB_ALLOWED_USERS=wang-yn,other-user
```

`GITHUB_ALLOWED_USERS` 使用英文逗号分隔。任一认证变量缺失或不合法时，应用会拒绝启动。
````

在现有 `docker run` 示例中追加：

```bash
  -e MEDIA_MANAGER_PUBLIC_URL="$MEDIA_MANAGER_PUBLIC_URL" \
  -e MEDIA_MANAGER_SESSION_SECRET="$MEDIA_MANAGER_SESSION_SECRET" \
  -e GITHUB_OAUTH_CLIENT_ID="$GITHUB_OAUTH_CLIENT_ID" \
  -e GITHUB_OAUTH_CLIENT_SECRET="$GITHUB_OAUTH_CLIENT_SECRET" \
  -e GITHUB_ALLOWED_USERS="$GITHUB_ALLOWED_USERS" \
```

在 README 的 Compose 示例中加入与仓库 `docker-compose.yml` 相同的五行变量，并把访问地址说明改为正式 HTTPS 地址或用户实际配置的 `MEDIA_MANAGER_PUBLIC_URL`。

- [ ] **步骤 3：验证 Compose 展开和镜像构建**

使用测试值验证，不写入仓库：

```bash
MEDIA_MANAGER_PUBLIC_URL=https://media.example.com \
MEDIA_MANAGER_SESSION_SECRET=ssssssssssssssssssssssssssssssss \
GITHUB_OAUTH_CLIENT_ID=test-client \
GITHUB_OAUTH_CLIENT_SECRET=test-secret \
GITHUB_ALLOWED_USERS=wang-yn \
docker compose config

docker build -t media-manager:github-oauth .
```

预期：Compose 配置可解析；Docker 多阶段构建完成，前端静态资源被复制到最终镜像。

- [ ] **步骤 4：运行完整自动化验证**

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
npm run build --prefix frontend
git status --short
```

预期：后端测试 `OK`；前端构建成功；工作区只包含本任务计划内的部署与文档改动。

- [ ] **步骤 5：执行真实 OAuth 冒烟验证**

使用真实 OAuth App 凭据和反向代理启动容器，验证：

1. 未登录访问 `/` 返回到 `/login`，未登录访问 `/api/health` 得到 JSON `401`。
2. 登录按钮跳转 GitHub，回调地址严格为 `https://media.example.com/auth/github/callback`。
3. 白名单用户登录后可以访问首页和 API，Cookie 包含 `Secure`、`HttpOnly`、`SameSite=Lax`。
4. 非白名单用户得到 `403` 页面，不产生登录会话。
5. 点击退出后回到 `/login`，原会话不能继续访问 API。
6. 删除当前用户名并使用相同 session secret 重启应用后，旧 Cookie 立即失效。

- [ ] **步骤 6：提交部署文档**

```bash
git add docker-compose.yml README.md
git commit -m "docs: configure GitHub OAuth deployment"
```

### 任务 6：最终安全与回归复核

**文件：**
- 检查：`backend/src/media_manager/auth.py`
- 检查：`backend/src/media_manager/server.py`
- 检查：`backend/tests/test_auth.py`
- 检查：`backend/tests/test_server.py`
- 检查：`frontend/src/App.tsx`
- 检查：`docker-compose.yml`
- 检查：`README.md`

- [ ] **步骤 1：扫描敏感信息和认证绕过配置**

```bash
rg -n "temporary-token|client-secret|MEDIA_MANAGER_AUTH|access_token|code_verifier" \
  backend/src frontend/src docker-compose.yml README.md
```

预期：

- `temporary-token` 和 `client-secret` 只出现在测试夹具中。
- `access_token` 与 `code_verifier` 只存在于认证协议实现的局部变量/参数中。
- 不存在可由部署环境变量关闭认证的 `MEDIA_MANAGER_AUTH*` 配置。

- [ ] **步骤 2：确认所有现有测试显式声明认证策略**

```bash
rg -n "create_app\(" backend/tests
```

预期：原有 `test_server.py` 全部使用 `create_app(auth_enabled=False)`；`test_auth.py` 只在访问控制测试中使用默认启用认证。

- [ ] **步骤 3：执行最终验证并检查提交序列**

```bash
PYTHONPATH=backend/src .venv/bin/python -m unittest discover backend/tests
npm run build --prefix frontend
git log --oneline -6
git status --short --branch
```

预期：全部自动化检查通过；提交按配置/Cookie、OAuth 客户端、服务端接入、前端退出、部署文档顺序排列；工作区干净。
