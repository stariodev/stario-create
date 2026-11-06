from stario import h
from stario.datastar import at, data
from stario.markup import HtmlElement

from app.common.shell import page
from app.features.login.urls import LOGIN_POST


def render() -> HtmlElement:
    return page(
        "Sign in",
        h.Main(
            {"id": "login"},
            data.signals({"email": "", "password": "", "_error": ""}, if_missing=True),
            h.H1("Sign in"),
            h.Form(
                data.on("submit", at.post(LOGIN_POST.href()), prevent=True),
                data.indicator("_sending"),
                h.Label(
                    "Email",
                    h.Input(
                        {"type": "email", "required": True, "autocomplete": "username"},
                        data.bind("email"),
                    ),
                ),
                h.Label(
                    "Password",
                    h.Input(
                        {"type": "password", "required": True, "autocomplete": "current-password"},
                        data.bind("password"),
                    ),
                ),
                h.P({"role": "alert"}, data.show("$_error"), data.text("$_error")),
                h.Button({"type": "submit"}, data.attr("disabled", "$_sending"), "Sign in"),
            ),
        ),
    )
