---
name: stario-js
description: JavaScript in a Stario app - a static/js file per behaviour, app.name functions called from data.on, clipboard, drag, charts, editors, keyboard input; the browser check for JS that holds state. Use before writing any script or addEventListener. Not for what data.* attributes already do.
---

# JavaScript

The server renders the page and Datastar runs the expressions in `data.*` attributes. Most
behaviour needs no file: a signal, `data.on`, `data.show`, `data.class_`, `data.attr`. Write a
file only for what a short expression cannot do: a browser API (clipboard, file reader), a
drag, a chart, a third-party widget, logic over several lines.

## No file needed

An expression sees signals (`$name`), the element (`el`) and the event (`evt`):

```python
h.Input(
    {"placeholder": "Enter tags"},
    data.bind("tag"),
    # Enter adds the tag to the list and does not submit the form.
    data.on(
        "keydown",
        "if (evt.key === 'Enter') { evt.preventDefault();"
        " if ($tag.trim()) $tags = [...$tags, $tag.trim()]; $tag = '' }",
    ),
)
h.Span(data.text("$tags.join(', ')"))
# A plain form sends the list as one field; read it with form.get("tags", "").split(",").
h.Input({"type": "hidden", "name": "tags"}, data.attr("value", "$tags.join(',')"))
```

Declare the signals once on an ancestor: `data.signals({"tag": "", "tags": []})`.

## A file

One file per behaviour, `static/js/<name>.js`, defines `app.<name>`:

```js
// static/js/clipboard.js
window.app ??= {};
app.clipboard = {
  async copy(text) {
    await navigator.clipboard.writeText(text);
  },
};
```

List it in `SCRIPTS` in `app/layout.py`, so every page loads it (deferred, before Datastar):

```python
# app/layout.py (the SCRIPTS line)
SCRIPTS = tuple(ASSETS.href(f"js/{name}.js") for name in ("clipboard",))
```

Call it from an attribute. Pass data through `data-*` attributes or signals, never by putting
user text into the expression:

```python
h.Button(
    {"data-text": "the note text"},
    data.signals({"_copied": False}),
    data.on(
        "click",
        "app.clipboard.copy(el.dataset.text); $_copied = true; setTimeout(() => $_copied = false, 2000)",
    ),
    h.Span(data.show("!$_copied"), "Copy"),
    h.Span(data.show("$_copied"), "Copied"),
)
```

`tests/test_js.py` (generated) fails when Python calls `app.<name>.<method>` that
`static/js/<name>.js` does not define. To send a result to the server, set a signal and call an
action: `$value = app.picker.value(); @post('/save')`.

## Rules

- A script that changes the DOM loses its work when a stream repaints that element. Keep its
  element outside the repainted one, or give it `data.ignore_morph()`.
- A third-party library: download its file into `static/js/vendor/` and list it in `SCRIPTS`
  before the file that uses it. No npm and no bundler.
- No inline `<script>` with user data. `SSE(w).execute_script(code)` runs trusted code only.

## The browser check

Only for JS that holds state (a drag, a gesture, a canvas) or a bug that a test and `request`
both show as correct. Pages, forms, streams and logins need no browser: `request`, the page
check and TestClient tests prove them.

1. `uvx stario-create@latest add browser` writes `scripts/browser.py`.
2. Edit its `steps(actor, viewer)`: the two tabs of one page.
3. `uv run --with playwright playwright install chromium`, then
   `uv run --with playwright python scripts/browser.py /board`. It starts the app on a free port,
   prints console errors, saves a screenshot, and stops the app.

When a person watches the app, they are the browser: make the change and say what to look at.
