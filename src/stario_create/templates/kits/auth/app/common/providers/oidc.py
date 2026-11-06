"""An OpenID Connect issuer with discovery. `Google` is one. Another issuer is a
subclass in its own file that passes its URL, like `google.py`.

The ID token comes straight from the token endpoint over TLS, so its signature
needs no check (OpenID Connect Core 3.1.3.7). Its claims do: iss, aud, azp,
exp, and nonce.
"""

import base64
import time
import urllib.parse
from typing import Any

from stario import json

from app.common.providers import Flow, Http, Identity, LoginFailed, is_secure, plain_email


class OidcIssuer:
    """One issuer at `url`. It reads discovery at the first sign-in."""

    # Other spellings of the issuer that its ID tokens may carry.
    other_issuers: frozenset[str] = frozenset()

    def __init__(self, url: str, client_id: str, client_secret: str, http: Http) -> None:
        # Discovery names the token endpoint, so it must come over TLS too.
        if not is_secure(url):
            raise ValueError(f"the issuer must be an https:// URL: {url}")
        self.url = url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http
        self._meta: dict[str, Any] = {}

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
            quote = urllib.parse.quote  # RFC 6749 2.3.1: encode both parts, "/" too
            pair = f"{quote(self.client_id, safe='')}:{quote(self.client_secret, safe='')}"
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode()
        else:
            form |= {"client_id": self.client_id, "client_secret": self.client_secret}
        tokens = await self.http.post_form(meta["token_endpoint"], form, headers)
        try:
            payload = str(tokens.get("id_token")).split(".")[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        except (AttributeError, IndexError, ValueError) as e:
            # The key names only: the answer holds tokens, and the reason goes to the log.
            keys = sorted(tokens) if isinstance(tokens, dict) else type(tokens).__name__
            raise LoginFailed(f"the answer has no readable id_token: {keys}") from e
        if not isinstance(claims, dict):
            raise LoginFailed("the id_token claims are not an object")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, list) else [audience]
        expires = claims.get("exp")
        subject = claims.get("sub")
        issuer = claims.get("iss")
        if not isinstance(issuer, str) or issuer not in {meta["issuer"], *self.other_issuers}:
            raise LoginFailed(f"iss is {issuer!r}")
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
            email=plain_email(claims.get("email")),
            email_verified=claims.get("email_verified") in (True, "true"),
            name=str(claims.get("name") or ""),
        )

    async def _metadata(self) -> dict[str, Any]:
        if self._meta:
            return self._meta
        meta = await self.http.get_json(f"{self.url}/.well-known/openid-configuration")
        if not isinstance(meta, dict):
            raise LoginFailed(f"discovery at {self.url} is not an object")
        for key in ("issuer", "authorization_endpoint", "token_endpoint"):
            if not isinstance(meta.get(key), str):
                raise LoginFailed(f"discovery at {self.url} has no {key}")
        # OIDC Discovery 4.3: the issuer in the document is the URL we asked.
        if meta["issuer"].rstrip("/") != self.url:
            raise LoginFailed(f"discovery says issuer {meta['issuer']!r}, not {self.url!r}")
        # The skipped signature check rests on TLS to the token endpoint.
        for key in ("authorization_endpoint", "token_endpoint"):
            if not is_secure(meta[key]):
                raise LoginFailed(f"{key} is not HTTPS: {meta[key]}")
        self._meta.update(meta)
        return self._meta
