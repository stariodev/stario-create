"""GitHub sign-in: plain OAuth 2, not OpenID Connect. The user comes from the
GitHub API, and state plus PKCE tie the callback to this browser."""

import urllib.parse

from app.common.providers import Flow, Http, Identity, LoginFailed, plain_email

GITHUB = "https://github.com"


class GitHub:
    """The key is the numeric user id, which never changes. The email is the
    primary verified one."""

    def __init__(self, client_id: str, client_secret: str, http: Http) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.http = http

    async def authorize_url(self, redirect_uri: str, flow: Flow) -> str:
        query = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": "user:email",  # /user needs no scope; /user/emails needs this one
            "state": flow.state,
            "code_challenge": flow.challenge,
            "code_challenge_method": "S256",
        }
        return f"{GITHUB}/login/oauth/authorize?{urllib.parse.urlencode(query)}"

    async def identity(self, code: str, redirect_uri: str, flow: Flow) -> Identity:
        form = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": flow.verifier,
        }
        tokens = await self.http.post_form(f"{GITHUB}/login/oauth/access_token", form, {})
        # GitHub answers 200 with {"error": ...} when it refuses the code.
        token = tokens.get("access_token") if isinstance(tokens, dict) else None
        if not isinstance(token, str):
            error = tokens.get("error") if isinstance(tokens, dict) else None
            raise LoginFailed(f"GitHub gave no token: {error!r}")
        headers = {"Authorization": f"Bearer {token}"}
        user = await self.http.get_json("https://api.github.com/user", headers)
        emails = await self.http.get_json("https://api.github.com/user/emails", headers)
        if not isinstance(user, dict) or not isinstance(user.get("id"), int):
            raise LoginFailed("GitHub sent no user id")
        emails = emails if isinstance(emails, list) else []
        verified = [e for e in emails if isinstance(e, dict) and e.get("verified")]
        primary = next((e for e in verified if e.get("primary")), None)
        return Identity(
            issuer=GITHUB,
            subject=str(user["id"]),
            email=plain_email(primary["email"]) if primary else "",
            email_verified=primary is not None,
            name=str(user.get("name") or user.get("login") or ""),
        )
