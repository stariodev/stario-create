---
name: stario-datastar
description: Every Stario page-side option - h.* tags and helper types, data.* attributes and modifiers, at.* actions, SSE options, morph rules. Use when AGENTS.md lacks an h.*, data.* or at.* option. Not for server code.
---

# The page side: h, data, at, SSE

Verified against stario 5.8 and the free `datastar.js`. The imports are in AGENTS.md; also `from stario.markup import Attrs, SafeString, baked, render, svg`.

## HTML: `h.*`

Every tag is `h.` plus its name with a capital letter: `h.Div`, `h.Textarea`, `h.Dialog`, `h.Thead`, `h.HtmlDocument` (the `<html>` with its doctype).

- Attributes first, then children. A dict, `classes(...)`, and each `data.*` are attributes. The other order raises "HTML attributes must be passed before children" when the `h.*` call runs; the check's lint reports it first.
- `classes("btn", {"active": is_on})` is an attribute of its own, never inside a dict.
- A dict value is `str | int | float | bool | None | SafeString`. `True` writes a bare attribute; `None` or `False` leaves it out.
- A child is a string (escaped), a number, a node, a list of nodes, or `None` (skipped). `h.Div(*items)` spreads a list.
- Trusted HTML (rendered Markdown): `SafeString(html)`. Never wrap user text in it.
- `@baked` caches a function whose output depends only on its arguments. `render(node)` returns the HTML string.
- A `<select>`: `h.Option({"value": v, "selected": v == current}, label)`.

Types for helpers, so pyrefly agrees:

```python
def on_submit(url: str) -> list[Attrs]:  # data.* and classes() return Attrs
    return [data.on("submit", at.post(url), prevent=True), data.indicator("_saving")]


def nav_link(href: str, active: bool, *children: HtmlElement | str) -> HtmlElement:
    return h.A(classes("nav-link", {"active": active}), {"href": href}, *children)


def tag_items(tags: list[str]) -> list[HtmlElement]:
    return [h.Li(tag) for tag in tags]
```

A list of nodes kept in a variable needs its type: `items: list[HtmlElement] = [h.Li(t) for t in tags]` (`h.Li` returns `Element`, and a list does not widen). A list in `data.signals` is a literal: `{"tags": [*tags]}`; a `list[str]` variable is refused.

## Expressions

- `$title` reads or writes the signal `title`; `$form.title` is nested. `el` is the element; `evt` is the event inside `data.on`.
- A leading `_` keeps a signal in the tab: `$_open`.
- Statements join with `;`. More than two statements: a function in `static/js/` (skill `stario-client`).
- User text inside an expression goes through `string_literal(text)`.

## Attributes: `data.*`

```text
data.signals({...}, if_missing=False)   # if_missing=True keeps what the user typed
data.signal(name, expr)   data.computed(key, expr)
data.bind(name, prop=None, event=None)   # bind("done", prop="checked", event="change")
data.text(expr)   data.show(expr)   data.effect(expr)
data.attr(key, expr)   data.attrs({key: expr})   data.class_(name, expr)   data.classes({...})
data.style(prop, expr)   data.styles({prop: expr})
data.ref(name)   data.indicator(name)   data.init(expr, delay=None)
data.on(event, expr, once=, passive=, capture=, delay=, debounce=, throttle=,
        target=None,                     # "window" | "document" | "outside"
        prevent=False, stop=False)
data.on_intersect(expr, threshold=, once=, exit=, delay=, debounce=, throttle=)
data.on_interval(expr, duration="1s", leading=False)
data.on_signal_patch(expr, delay=, debounce=, throttle=, include=, exclude=)
data.preserve_attr("open")  data.preserve_attr(["open", "class"])
data.ignore_morph()   data.ignore(self_only=False)
```

A time is `"200ms"`, `0.2` (a float: seconds), or `2` (an int: whole seconds); a bare `200` is 200 seconds. `include` and `exclude` take a regex or a list of names. `data.indicator` goes on the element whose `data.on` sends the request (the `<form>` for a submit).

Datastar Pro only, so they do nothing with the free `datastar.js`: `persist`, `query_string`, `replace_url`, `scroll_into_view`, `match_media`, `on_resize`, `on_raf`, `animate`, `custom_validity`, and the actions `clipboard`, `intl`, `fit`.

## Actions: `at.*`

```text
at.get(url, queries=None, *, content_type=, include=, exclude=, selector=, headers=,
       open_when_hidden=, payload=, retry=, retry_max_count=, request_cancellation=)
at.post / at.put / at.patch / at.delete      # the same arguments
at.peek(expr)   at.set_all(value)   at.toggle_all()
```

- `retry`: `"auto"`, `"error"`, `"always"`, `"never"`. A live stream uses `retry="always"`.
- `content_type`: `"json"` (the default, sends the signals) or `"form"`.
- `queries` values are literals, URL-encoded: `at.get("/x", {"q": "$q"})` sends `?q=%24q`. The signals travel by themselves; build the URL with `ROUTE.href(query=...)`.

## Server side: `SSE`

```text
sse.patch_elements(part, mode=None, selector=None, namespace=None)
sse.patch_signals({...}, only_if_missing=False)
sse.navigate(url)   sse.execute_script(code)   sse.remove(selector)
```

`mode`: `"outer"` (the default), `"inner"`, `"replace"`, `"prepend"`, `"append"`, `"before"`, `"after"`. A signal read back is JSON: a list arrives as `list`, a number as `int` or `float`; convert and check each one. `read_signals(c.req, max_size=...)`.

## How a morph treats the page

`patch_elements` finds each top element by `id` and morphs it in place. The element with `data.init` and `data.signals(..., if_missing=True)` keeps its tag, `id`, and attributes in every render, so its signals survive. A subtree the client owns gets `data.ignore_morph()`. When the stream test shows the new HTML, Datastar puts it on the page (skill `stario-browser-check`).
