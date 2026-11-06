from stario import h
from stario.markup import HtmlElement

from app.common.providers import Provider
from app.common.shell import page
from app.features.login.urls import LOGIN_START

ERRORS = {
    "denied": "The sign-in was cancelled.",
    "expired": "The sign-in took too long. Try again.",
    "failed": "The sign-in did not work. Try again.",
    "not_allowed": "This account has no access.",
}


def render(providers: list[Provider], next_url: str, error: str) -> HtmlElement:
    message = ERRORS.get(error)
    return page(
        "Sign in",
        h.Main(
            {"id": "login"},
            h.H1("Sign in"),
            h.P({"role": "alert"}, message) if message else None,
            # Plain forms: the answer is a redirect to the provider.
            [
                h.Form(
                    {"method": "post", "action": LOGIN_START.href(p.name)},
                    h.Input({"type": "hidden", "name": "next", "value": next_url}),
                    h.Button({"type": "submit"}, f"Continue with {p.label}"),
                )
                for p in providers
            ],
        ),
    )
