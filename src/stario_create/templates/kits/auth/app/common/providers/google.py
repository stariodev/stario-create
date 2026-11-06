"""Google sign-in: an OpenID Connect issuer at accounts.google.com."""

from app.common.providers import Http
from app.common.providers.oidc import OidcIssuer

GOOGLE = "https://accounts.google.com"


class Google(OidcIssuer):
    # Google also writes its issuer without the scheme.
    other_issuers = frozenset({"accounts.google.com"})

    def __init__(self, client_id: str, client_secret: str, http: Http) -> None:
        super().__init__(GOOGLE, client_id, client_secret, http)
