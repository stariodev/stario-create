from pathlib import Path

from stario import Assets, h
from stario.datastar import ModuleScript, data
from stario.markup import HtmlElement, SafeString, baked, classes

ASSETS = Assets(Path(__file__).resolve().parents[1] / "static", url_prefix="/static")
STYLE_CSS = ASSETS.href("css/output.css")
DATASTAR_JS = ASSETS.href("js/datastar.js")
# Client behaviour lives in static/js/<name>.js — each file defines app.<name>.
SCRIPTS: tuple[str, ...] = tuple(ASSETS.href(f"js/{name}.js") for name in ("theme",))

# The one inline script: it sets the theme before the first paint.
RESTORE_THEME = SafeString(
    "document.documentElement.dataset.theme = localStorage.getItem('theme')"
    " || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')"
)


@baked
def page(title: str, body: HtmlElement) -> HtmlElement:
    return h.HtmlDocument(
        {"lang": "en", "data-theme": "light"},
        data.preserve_attr("data-theme"),
        h.Head(
            h.Meta({"charset": "utf-8"}),
            h.Meta({"name": "viewport", "content": "width=device-width, initial-scale=1"}),
            h.Title(title),
            h.Script(RESTORE_THEME),
            h.Link({"rel": "stylesheet", "href": STYLE_CSS}),
            *[h.Script({"src": src, "defer": True}) for src in SCRIPTS],
            ModuleScript(DATASTAR_JS),
        ),
        h.Body(
            classes("min-h-screen", "bg-base-100", "text-base-content"),
            body,
            h.Div(
                classes("toast", "toast-end"),
                data.show("$_toast"),
                h.Output(
                    classes("alert", "alert-info"),
                    {"id": "toast", "role": "status"},
                    data.signals({"_toast": ""}, if_missing=True),
                    data.text("$_toast"),
                    data.effect("$_toast && setTimeout(() => $_toast = '', 4000)"),
                ),
            ),
        ),
    )


# Markup that several pages share (a nav bar, a card, a date) goes below.
