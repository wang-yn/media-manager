from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlparse
import unittest
from unittest.mock import patch

from media_manager.auth import (
    AuthConfigError,
    GitHubUser,
    create_oauth_request,
    issue_session_cookie,
    load_auth_config,
    read_session_cookie,
    verify_oauth_state,
)


SECRET = "x" * 32


def valid_environ(**overrides: str) -> dict[str, str]:
    environ = {
        "MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com",
        "MEDIA_MANAGER_SESSION_SECRET": SECRET,
        "GITHUB_OAUTH_CLIENT_ID": "client-id",
        "GITHUB_OAUTH_CLIENT_SECRET": "client-secret",
        "GITHUB_ALLOWED_USERS": "Alice, bob",
    }
    environ.update(overrides)
    return environ


def payload_from(token: str) -> dict[str, object]:
    payload, signature = token.split(".", 1)
    expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    self_check = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    if not hmac.compare_digest(expected, self_check):
        raise AssertionError("bad test token signature")
    raw = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    return json.loads(raw)


class AuthConfigTest(unittest.TestCase):
    def test_valid_config_normalizes_callback_and_allowlist(self) -> None:
        config = load_auth_config(valid_environ(GITHUB_ALLOWED_USERS=" Alice ,BOB "))

        self.assertEqual(config.public_url, "https://media.example.com")
        self.assertEqual(config.session_secret, SECRET.encode())
        self.assertEqual(config.client_id, "client-id")
        self.assertEqual(config.client_secret, "client-secret")
        self.assertEqual(config.allowed_users, frozenset({"alice", "bob"}))
        self.assertEqual(config.callback_url, "https://media.example.com/auth/github/callback")
        self.assertTrue(config.allows("ALICE"))
        self.assertFalse(config.allows("carol"))

    def test_config_repr_does_not_include_secrets(self) -> None:
        config = load_auth_config(valid_environ())

        self.assertNotIn(SECRET, repr(config))
        self.assertNotIn("client-secret", repr(config))

    def test_rejects_each_missing_required_variable(self) -> None:
        for name in valid_environ():
            with self.subTest(name=name):
                environ = valid_environ()
                del environ[name]
                with self.assertRaises(AuthConfigError):
                    load_auth_config(environ)

    def test_rejects_invalid_config_without_leaking_secret(self) -> None:
        cases = [
            {"MEDIA_MANAGER_PUBLIC_URL": "http://media.example.com"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com/"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com/path"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com?next=/"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com#top"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://user@media.example.com"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com:99999"},
            {"MEDIA_MANAGER_PUBLIC_URL": "https://media.example.com:bad"},
            {"MEDIA_MANAGER_SESSION_SECRET": "short"},
            {"GITHUB_ALLOWED_USERS": " , "},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(AuthConfigError) as raised:
                    load_auth_config(valid_environ(**overrides))
                self.assertNotIn(SECRET, str(raised.exception))


class SessionCookieTest(unittest.TestCase):
    def test_session_roundtrip(self) -> None:
        config = load_auth_config(valid_environ())
        token = issue_session_cookie(config, GitHubUser(id=42, login="Alice"), now=1000)

        self.assertEqual(read_session_cookie(config, token, now=1000), GitHubUser(id=42, login="Alice"))

    def test_session_rejects_tamper_bad_format_expiry_and_removed_user(self) -> None:
        config = load_auth_config(valid_environ())
        token = issue_session_cookie(config, GitHubUser(id=42, login="Alice"), now=1000)
        locked_out = load_auth_config(valid_environ(GITHUB_ALLOWED_USERS="bob"))

        self.assertIsNone(read_session_cookie(config, token + "x", now=1000))
        self.assertIsNone(read_session_cookie(config, "not-a-token", now=1000))
        self.assertIsNone(read_session_cookie(config, None, now=1000))
        self.assertIsNone(read_session_cookie(config, token, now=1000 + 7 * 24 * 60 * 60))
        self.assertIsNone(read_session_cookie(locked_out, token, now=1000))


class OAuthRequestTest(unittest.TestCase):
    def test_authorize_url_uses_fixed_callback_no_scope_and_pkce_s256(self) -> None:
        config = load_auth_config(valid_environ())
        with patch("secrets.token_urlsafe", side_effect=["state-value", "verifier-value"]):
            request = create_oauth_request(config, now=1000)

        parsed = urlparse(request.authorize_url)
        params = parse_qs(parsed.query)
        payload = payload_from(request.cookie_value)
        expected_challenge = base64.urlsafe_b64encode(hashlib.sha256(b"verifier-value").digest()).decode().rstrip("=")

        self.assertEqual(f"{parsed.scheme}://{parsed.netloc}{parsed.path}", "https://github.com/login/oauth/authorize")
        self.assertEqual(params, {
            "client_id": ["client-id"],
            "redirect_uri": ["https://media.example.com/auth/github/callback"],
            "state": ["state-value"],
            "code_challenge": [expected_challenge],
            "code_challenge_method": ["S256"],
        })
        self.assertNotIn("scope", params)
        self.assertEqual(payload["kind"], "oauth")
        self.assertEqual(payload["state"], "state-value")
        self.assertEqual(payload["verifier"], "verifier-value")
        self.assertEqual(payload["iat"], 1000)
        self.assertEqual(payload["exp"], 1600)

    def test_oauth_state_rejects_mismatch_tamper_missing_and_expiry(self) -> None:
        config = load_auth_config(valid_environ())
        with patch("secrets.token_urlsafe", side_effect=["state-value", "verifier-value"]):
            request = create_oauth_request(config, now=1000)

        self.assertEqual(verify_oauth_state(config, request.cookie_value, "state-value", now=1000), "verifier-value")
        self.assertIsNone(verify_oauth_state(config, request.cookie_value, "other", now=1000))
        self.assertIsNone(verify_oauth_state(config, request.cookie_value + "x", "state-value", now=1000))
        self.assertIsNone(verify_oauth_state(config, None, "state-value", now=1000))
        self.assertIsNone(verify_oauth_state(config, request.cookie_value, None, now=1000))
        self.assertIsNone(verify_oauth_state(config, "", "state-value", now=1000))
        self.assertIsNone(verify_oauth_state(config, request.cookie_value, "state-value", now=1600))


if __name__ == "__main__":
    unittest.main()
