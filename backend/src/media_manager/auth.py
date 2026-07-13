from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import html
import http.client
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Mapping, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request
import urllib.request


OAUTH_COOKIE_NAME = "media_manager_oauth"
SESSION_COOKIE_NAME = "media_manager_session"
OAUTH_TTL_SECONDS = 600
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"


class AuthConfigError(ValueError):
    pass


class GitHubOAuthError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("GitHub OAuth 请求失败")


@dataclass(frozen=True)
class AuthConfig:
    public_url: str
    session_secret: bytes = field(repr=False)
    client_id: str
    client_secret: str = field(repr=False)
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


class GitHubOAuthClient:
    def __init__(self, opener=None) -> None:
        self._opener = urllib.request.urlopen if opener is None else opener

    def authenticate(self, config: AuthConfig, code: str, verifier: str) -> GitHubUser:
        try:
            token_request = Request(
                GITHUB_TOKEN_URL,
                data=urlencode({
                    "client_id": config.client_id,
                    "client_secret": config.client_secret,
                    "code": code,
                    "redirect_uri": config.callback_url,
                    "code_verifier": verifier,
                }).encode(),
                headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )
            token_payload = self._read_json_object(token_request)
            access_token = token_payload.get("access_token")
            if not isinstance(access_token, str) or not access_token:
                raise GitHubOAuthError()

            user_request = Request(
                GITHUB_USER_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Media-Manager",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                method="GET",
            )
            user_payload = self._read_json_object(user_request)
            user_id = user_payload.get("id")
            login = user_payload.get("login")
            if isinstance(user_id, bool) or not isinstance(user_id, int) or not isinstance(login, str) or not login:
                raise GitHubOAuthError()
            return GitHubUser(id=user_id, login=login)
        except (HTTPError, URLError, TimeoutError, http.client.HTTPException, UnicodeDecodeError, json.JSONDecodeError, GitHubOAuthError):
            pass
        raise GitHubOAuthError()

    def _read_json_object(self, request: Request) -> dict[str, Any]:
        with self._opener(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise GitHubOAuthError()
        return payload


def load_auth_config(environ: Mapping[str, str] | None = None) -> AuthConfig:
    source = os.environ if environ is None else environ
    public_url = _required(source, "MEDIA_MANAGER_PUBLIC_URL")
    session_secret = _required(source, "MEDIA_MANAGER_SESSION_SECRET")
    client_id = _required(source, "GITHUB_OAUTH_CLIENT_ID")
    client_secret = _required(source, "GITHUB_OAUTH_CLIENT_SECRET")
    allowed = _required(source, "GITHUB_ALLOWED_USERS")

    _validate_public_url(public_url)
    secret_bytes = session_secret.encode("utf-8")
    if len(secret_bytes) < 32:
        raise AuthConfigError("MEDIA_MANAGER_SESSION_SECRET must be at least 32 bytes")
    allowed_users = frozenset(item.strip().casefold() for item in allowed.split(",") if item.strip())
    if not allowed_users:
        raise AuthConfigError("GITHUB_ALLOWED_USERS must include at least one user")

    return AuthConfig(
        public_url=public_url,
        session_secret=secret_bytes,
        client_id=client_id,
        client_secret=client_secret,
        allowed_users=allowed_users,
    )


def create_oauth_request(config: AuthConfig, now: int | None = None) -> OAuthRequest:
    issued_at = _now(now)
    state = secrets.token_urlsafe()
    verifier = secrets.token_urlsafe()
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    authorize_url = f"{GITHUB_AUTHORIZE_URL}?{urlencode({
        'client_id': config.client_id,
        'redirect_uri': config.callback_url,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })}"
    cookie_value = _sign(config, {
        "kind": "oauth",
        "state": state,
        "verifier": verifier,
        "iat": issued_at,
        "exp": issued_at + OAUTH_TTL_SECONDS,
    })
    return OAuthRequest(authorize_url=authorize_url, cookie_value=cookie_value)


def verify_oauth_state(config: AuthConfig, token: str | None, returned_state: str | None, now: int | None = None) -> str | None:
    payload = _read_signed(config, token, _now(now))
    if payload is None or payload.get("kind") != "oauth":
        return None
    state = payload.get("state")
    verifier = payload.get("verifier")
    if not isinstance(state, str) or not isinstance(verifier, str) or not isinstance(returned_state, str):
        return None
    if not hmac.compare_digest(state, returned_state):
        return None
    return verifier


def issue_session_cookie(config: AuthConfig, user: GitHubUser, now: int | None = None) -> str:
    issued_at = _now(now)
    return _sign(config, {
        "kind": "session",
        "id": user.id,
        "login": user.login,
        "iat": issued_at,
        "exp": issued_at + SESSION_TTL_SECONDS,
    })


def read_session_cookie(config: AuthConfig, token: str | None, now: int | None = None) -> GitHubUser | None:
    payload = _read_signed(config, token, _now(now))
    if payload is None or payload.get("kind") != "session":
        return None
    user_id = payload.get("id")
    login = payload.get("login")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or not isinstance(login, str):
        return None
    if not config.allows(login):
        return None
    return GitHubUser(id=user_id, login=login)


def login_page() -> str:
    return _page("Media Manager", '<a class="button" href="/auth/github/login">使用 GitHub 登录</a>')


def error_page() -> str:
    return _page("登录失败", "<p>请重新登录。</p>")


def forbidden_page(login: str) -> str:
    return _page("该账号未获授权", f"<p>{html.escape(login)} 该账号未获授权。</p>")


def _required(environ: Mapping[str, str], name: str) -> str:
    value = environ.get(name)
    if value is None or not value.strip():
        raise AuthConfigError(f"{name} is required")
    return value.strip()


def _page(title: str, body: str) -> str:
    safe_title = html.escape(title)
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{safe_title}</title><style>body{{font-family:system-ui,sans-serif;margin:4rem auto;max-width:28rem;padding:0 1rem;line-height:1.5}}"
        ".button{display:inline-block;background:#111;color:white;padding:.7rem 1rem;border-radius:6px;text-decoration:none}</style></head>"
        f"<body><h1>{safe_title}</h1>{body}</body></html>"
    )


def _validate_public_url(public_url: str) -> None:
    parsed = urlparse(public_url)
    try:
        parsed.port
    except ValueError as exc:
        raise AuthConfigError("MEDIA_MANAGER_PUBLIC_URL must include a valid port") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or public_url.endswith("/")
    ):
        raise AuthConfigError("MEDIA_MANAGER_PUBLIC_URL must be an HTTPS origin without path, query, or fragment")


def _now(now: int | None) -> int:
    return int(time.time()) if now is None else now


def _sign(config: AuthConfig, payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    payload_part = _b64(payload_json)
    signature = hmac.new(config.session_secret, payload_part.encode(), hashlib.sha256).digest()
    return f"{payload_part}.{_b64(signature)}"


def _read_signed(config: AuthConfig, token: str | None, now: int) -> dict[str, Any] | None:
    if not isinstance(token, str):
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_part, signature_part = parts
        signature = _unb64(signature_part)
        expected = hmac.new(config.session_secret, payload_part.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(_unb64(payload_part))
    except (binascii.Error, ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int) or exp <= now:
        return None
    return payload


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
