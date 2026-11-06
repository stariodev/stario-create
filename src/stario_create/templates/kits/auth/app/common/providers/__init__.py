"""What every sign-in provider shares. Each provider is one class in its own file:
`google.py` (OpenID Connect, on the code in `oidc.py`) and `github.py` (OAuth 2).

A provider is two steps: `authorize_url` sends the browser away, and
`identity` turns the code from the callback into an `Identity`. The app
names each provider in a dict in `app/main.py` (`/login/<name>`), and the
page writes its button text.
"""

import asyncio
import base64
import hashlib
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from stario import json


class LoginFailed(Exception):
    """The provider did not answer, refused the code, or sent data that does not check out."""


@dataclass(frozen=True, slots=True)
class Identity:
    """Who signed in. (issuer, subject) is the key; the email can change."""

    issuer: str
    subject: str
    email: str
    email_verified: bool
    name: str


@dataclass(frozen=True, slots=True)
class Flow:
    """The secrets of one sign-in. The browser keeps them in a signed cookie."""

    state: str
    nonce: str
    verifier: str

    @classmethod
    def new(cls) -> Flow:
        return cls(secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48))

    @property
    def challenge(self) -> str:
        """PKCE S256: the provider gets the hash now and the verifier at the exchange."""
        digest = hashlib.sha256(self.verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class Provider(Protocol):
    async def authorize_url(self, redirect_uri: str, flow: Flow) -> str: ...
    async def identity(self, code: str, redirect_uri: str, flow: Flow) -> Identity: ...


def plain_email(raw: object) -> str:
    """The email in lower case, or "" when it is not ASCII. Lower case folds some
    Unicode letters into ASCII ("K", the Kelvin sign, becomes "k"), and the allow
    list and the join compare emails."""
    email = str(raw or "").strip()
    return email.lower() if email.isascii() else ""


def is_secure(url: str) -> bool:
    """HTTPS, or plain HTTP to this machine for a local issuer."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" or (
        parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1")
    )


class Http:
    """The calls to a provider, through urllib on a worker thread. Tests replace it."""

    async def get_json(self, url: str, headers: dict[str, str] | None = None) -> Any:
        return await asyncio.to_thread(_send, urllib.request.Request(url, None, headers or {}))

    async def post_form(self, url: str, form: dict[str, str], headers: dict[str, str]) -> Any:
        body = urllib.parse.urlencode(form).encode()
        return await asyncio.to_thread(_send, urllib.request.Request(url, body, headers))


def _send(request: urllib.request.Request) -> Any:
    request.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:  # the body names the cause: invalid_grant, ...
        raise LoginFailed(f"{request.full_url}: {e.code} {e.read()[:300]!r}") from e
    except (OSError, ValueError) as e:  # no answer, or not JSON
        raise LoginFailed(f"{request.full_url}: {e}") from e
