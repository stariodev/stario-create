---
name: stario-datastar
description: The page side of Stario, every signature - h.* tags and their attribute rule, classes, SafeString, data.* attributes, at.* actions, Datastar expressions and signals, read_signals, SSE (patch_elements, patch_signals, navigate), and how a morph treats the page. Read it with stario-api before you write views.
---

# The page side: h, data, at, SSE

Verified against stario 5.8 and the free `datastar.js`.

```python
from stario import classes, h
from stario.datastar import SSE, at, data, read_signals
from stario.datastar.format import string_literal  # user text inside an expression
from stario.markup import HtmlElement, SafeString, baked, render
```

## HTML: `h.*`

Every tag is `h.` plus the tag name with a capital letter: `h.Div`, `h.Textarea`, `h.Dialog`, `h.HtmlDocument` (the `<html>` with its doctype).

- Attributes first, children after: `h.A({"href": HOME.href()}, data.show("$x"), "Home")`. A dict and each `data.*` result is an attribute. A dict after a child raises "HTML attributes must be passed before children" when the page renders.
- `True` writes a bare attribute. `None` or `False` leaves it out. `classes("btn", {"active": is_on})` builds `class`.
- A child is a string (escaped), a number, a node, a list of nodes, or `None` (skipped). `h.Div(*items)` spreads a list.
- Trusted HTML (rendered Markdown): `SafeString(html)`. Never wrap user text in it unescaped.
- `render(node)` returns the HTML string. `@baked` caches a function whose output depends only on its arguments. SVG: `from stario.markup import svg`.
- A `<select>`: `h.Option({"value": v, "selected": v == current}, label)`.


## Expressions

- `$title` reads or writes the signal `title`. `$form.title` is a nested signal. `el` is the element. `evt` is the event inside `data.on`.
- A leading `_` makes a signal local: `$_open`. Datastar does not send it to the server.
- Statements join with `;`. More than two statements: a function in `static/js/` (skill `stario-client`).
- User text inside an expression goes through `string_literal(text)`.

## Attributes: `data.*`

```text
data.signals({...}, if_missing=False)   # if_missing=True keeps typed values
data.signal(name, expr)   data.computed(key, expr)
data.bind(name, prop=None, event=None)   # bind("done", prop="checked", event="change")
data.text(expr)   data.show(expr)   data.effect(expr)
data.attr(key, expr)   data.attrs({key: expr})
data.class_(name, expr)   data.classes({name: expr})
data.style(prop, expr)   data.styles({prop: expr})
data.ref(name)                           # $name is this element
data.indicator(name)                     # $name is true while this element's request runs
data.init(expr, delay=None)
data.on(event, expr, once=, passive=, capture=, delay=, debounce=, throttle=,
        target=None,                     # "window" | "document" | "outside"
        prevent=False, stop=False)
data.on_intersect(expr, threshold=, once=, exit=, delay=, debounce=, throttle=)
data.on_interval(expr, duration="1s", leading=False)
data.on_signal_patch(expr, delay=, debounce=, throttle=, include=, exclude=)
data.preserve_attr("open")  data.preserve_attr(["open", "class"])
data.ignore_morph()                      # server patches skip this subtree
data.ignore(self_only=False)             # Datastar skips this subtree
```

A time is `200`, `0.2`, or `"200ms"`. `include` and `exclude` take a regex or a list of names.

Datastar Pro only, so they do nothing with the free `datastar.js`: `persist`, `query_string`, `replace_url`, `scroll_into_view`, `match_media`, `on_resize`, `on_raf`, `animate`, `custom_validity`, and the actions `clipboard`, `intl`, `fit`.

## Actions: `at.*`

```text
at.get(url, *, content_type=, include=, exclude=, selector=, headers=,
       open_when_hidden=, payload=, retry=, retry_interval_ms=, retry_max_count=,
       request_cancellation=)              # every keyword defaults to None
at.post / at.put / at.patch / at.delete / at.query   # same arguments as at.get
at.peek(expr)   at.set_all(value)   at.toggle_all()
```

- `retry`: `"auto"`, `"error"`, `"always"`, `"never"`. A live stream uses `retry="always"`.
- `content_type`: `"json"` (the default, sends the signals) or `"form"`. `include` / `exclude` choose the signals.
- Build the URL with `ROUTE.href(...)`. A plain `fetch` ignores the SSE answer.

## Server side: `read_signals` and `SSE`

```text
signals = await read_signals(c.req)      # dict; a GET sends them in ?datastar=; max_size=
sse = SSE(w)
sse.patch_elements(part, mode=None, selector=None, namespace=None)
sse.patch_signals({...}, only_if_missing=False)
sse.navigate(url)                        # a 303 does not change the URL of a Datastar request
sse.execute_script(code)                 # trusted code only
sse.remove(selector)
```

A signal value read back is JSON: a list arrives as `list`, a number as `int` or `float`. Convert and check each one. `mode`: `"outer"` (the default), `"inner"`, `"replace"`, `"prepend"`, `"append"`, `"before"`, `"after"`. A file input bound with `data.bind` arrives as a `FileSignal` dict: `name`, `contents` (base64), `mime`.

## How a morph treats the page

`patch_elements` finds each top element by `id` and morphs it in place. The element with `data.init` and `data.signals(..., if_missing=True)` keeps its tag, `id`, and attributes in every render, so its signals survive. A subtree the client owns needs `data.ignore_morph()`. Trust the morph: when the stream test shows the new HTML, Datastar puts it on the page (skill `stario-browser-check`).
