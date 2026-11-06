"""Sign-in providers: Google, GitHub, and any OpenID Connect issuer.

A provider is two steps: `authorize_url` sends the browser away, and
`identity` turns the code from the callback into an `Identity`. The app
names each provider in a dict (`/login/<name>`); the page writes its label.

For OIDC, the ID token comes straight from the token endpoint over TLS, so
its signature needs no check (OpenID Connect Core 3.1.3.7). Its claims do:
iss, aud, azp, exp, and nonce. GitHub is plain OAuth 2: the user comes from
its API, and state plus PKCE tie the callback to this browser.
"""

import asyncio
import base64
import hashlib
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

from stario import json

GOOGLE = "https://accounts.google.com"


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
    except (OSError, ValueError) as e:  # no answer, an HTTP error status, or not JSON
        raise LoginFailed(f"{request.full_url}: {e}") from e


class Provider(Protocol):
    async def authorize_url(self, redirect_uri: str, flow: Flow) -> str: ...
    async def identity(self, code: str, redirect_uri: str, flow: Flow) -> Identity: ...


@dataclass(frozen=True, slots=True)
class Issuer:
    """One OIDC issuer: Google, or any issuer with discovery. It reads discovery at
    the first sign-in."""

    url: str
    client_id: str
    client_secret: str = field(repr=False)
    http: Http = field(default_factory=Http)
    _meta: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    async def authorize_url(self, redirect_uri: str, flow: Flow) -> str:
        meta = await self._metadata()
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": flow.state,
            "nonce": flow.nonce,
            "code_challenge": flow.challenge,
            "code_challenge_method": "S256",
        }
        return f"{meta['authorization_endpoint']}?{urllib.parse.urlencode(query)}"

    async def identity(self, code: str, redirect_uri: str, flow: Flow) -> Identity:
        meta = await self._metadata()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": flow.verifier,
        }
        headers: dict[str, str] = {}
        methods = meta.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
        if "client_secret_basic" in methods:
            pair = f"{urllib.parse.quote(self.client_id)}:{urllib.parse.quote(self.client_secret)}"
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
        else:
            form |= {"client_id": self.client_id, "client_secret": self.client_secret}
        tokens = await self.http.post_form(meta["token_endpoint"], form, headers)
        claims = _claims(tokens.get("id_token") if isinstance(tokens, dict) else None)
        # Google also writes its issuer without the scheme.
        issuers = {meta["issuer"]} | ({"accounts.google.com"} if self.url == GOOGLE else set())
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        expires = claims.get("exp")
        subject = claims.get("sub")
        if claims.get("iss") not in issuers:
            raise LoginFailed(f"iss is {claims.get('iss')!r}")
        if self.client_id not in audiences:
            raise LoginFailed(f"aud is {audience!r}")
        if len(audiences) > 1 and claims.get("azp") != self.client_id:
            raise LoginFailed(f"azp is {claims.get('azp')!r}")
        if not isinstance(expires, int | float) or expires < time.time():
            raise LoginFailed("the ID token expired")
        if claims.get("nonce") != flow.nonce:
            raise LoginFailed("the nonce does not match")
        if not isinstance(subject, str) or not subject:
            raise LoginFailed("the ID token has no sub")
        return Identity(
            issuer=meta["issuer"],
            subject=subject,
            email=str(claims.get("email") or "").strip().lower(),
            email_verified=claims.get("email_verified") in (True, "true"),
            name=str(claims.get("name") or ""),
        )

    async def _metadata(self) -> dict[str, Any]:
        if not self._meta:
            meta = await self.http.get_json(
                f"{self.url.rstrip('/')}/.well-known/openid-configuration"
            )
            if not isinstance(meta, dict):
                raise LoginFailed(f"discovery at {self.url} is not an object")
            for key in ("issuer", "authorization_endpoint", "token_endpoint"):
                if not isinstance(meta.get(key), str):
                    raise LoginFailed(f"discovery at {self.url} has no {key}")
            self._meta.update(meta)
        return self._meta


@dataclass(frozen=True, slots=True)
class GitHub:
    """GitHub sign-in: plain OAuth 2. The key is the numeric user id, which never
    changes; the email is the primary verified one."""

    client_id: str
    client_secret: str = field(repr=False)
    http: Http = field(default_factory=Http)

    async def authorize_url(self, redirect_uri: str, flow: Flow) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "read:user user:email",
            "state": flow.state,
            "code_challenge": flow.challenge,
            "code_challenge_method": "S256",
        }
        return f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(query)}"

    async def identity(self, code: str, redirect_uri: str, flow: Flow) -> Identity:
        form = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": flow.verifier,
        }
        tokens = await self.http.post_form("https://github.com/login/oauth/access_token", form, {})
        # GitHub answers 200 with {"error": ...} when it refuses the code.
        token = tokens.get("access_token") if isinstance(tokens, dict) else None
        if not isinstance(token, str):
            raise LoginFailed(f"GitHub gave no token: {tokens!r}")
        headers = {"Authorization": f"Bearer {token}"}
        user = await self.http.get_json("https://api.github.com/user", headers)
        emails = await self.http.get_json("https://api.github.com/user/emails", headers)
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise LoginFailed("GitHub sent no user id")
        primary = (
            next(
                (
                    e
                    for e in emails
                    if isinstance(e, dict) and e.get("primary") and e.get("verified")
                ),
                None,
            )
            if isinstance(emails, list)
            else None
        )
        return Identity(
            issuer="https://github.com",
            subject=str(user["id"]),
            email=str(primary["email"]).strip().lower() if primary else "",
            email_verified=primary is not None,
            name=str(user.get("name") or user.get("login") or ""),
        )


def _claims(id_token: object) -> dict[str, Any]:
    try:
        payload = str(id_token).split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as e:
        raise LoginFailed("the answer has no readable id_token") from e
    if not isinstance(claims, dict):
        raise LoginFailed("the id_token claims are not an object")
    return claims
