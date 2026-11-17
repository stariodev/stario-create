---
name: stario-client
description: JavaScript in a Stario app - where it goes and how Python calls it. Use before any script, addEventListener, long data.on expression, drag, picker, or clipboard. Not for what a GET or a data.* attribute does.
---

# Client behaviour

The server renders the state. JavaScript is for what HTML and Datastar cannot express. It lives in `static/js/<name>.js`, and Python calls it from Datastar attributes; it never lives in a Python string. Every `data.*` and `at.*` signature is in skill `stario-datastar`.

## Pick the first layer that does the job

1. **The server.** A search, a filter, or a list is a `GET` that patches its part, not JavaScript over a JSON copy of the data.
2. **HTML and CSS.** `<dialog>`, `<details>`, `popover`, `:has()`, scroll-snap.
3. **A Datastar attribute** with a short expression: one or two statements over signals, `el`, `evt`, and `app.*` calls. `data.bind` on `<input type="file">` already gives `[{name, contents, mime}]`; `@post` already follows `navigate`.
4. **A function in `static/js/<name>.js`**, called from an attribute: math, measuring, pointer physics, browser APIs (`visualViewport`, clipboard, `SpeechRecognition`).

## A file

Each file is a classic script (not a module) that defines one namespace named after the file, and nothing else at the top level. A namespace is a plain object literal; methods call each other with `this`, and state is a property.

```js
// static/js/share.js
window.app ??= {};
app.share = {
  copy(url, done) {
    navigator.clipboard.writeText(url).then(() => {
      done(true);
      setTimeout(() => done(false), 1600);
    });
  },
};
```

```python
h.Button(
    {"type": "button", "data-url": share_url},
    data.on("click", "app.share.copy(el.dataset.url, v => $_copied = v)"),
    h.Span(data.text("$_copied ? 'Copied' : 'Copy'")),
)
```

`SCRIPTS` in `app/layout.py` lists the files, and `page()` loads them before Datastar, so `app` exists at the first `data-init`: `SCRIPTS = tuple(ASSETS.href(f"js/{name}.js") for name in ("share",))`. An element that needs its own state (a ruler, a drag): a factory, `references/factories.md`.

## Rules

- **Datastar adds the listeners**: `data.on("click", ...)`, and `target="window"`, `"document"`, or `"outside"` for a page-wide event, on the shell element (`h.Body`) in one place. A file never calls `addEventListener` on `window` or `document`.
- **Signals carry state between JavaScript and HTML.** A function returns a value (`$t = app.clock.now()`) or calls a callback the expression gives it (`v => $weight_kg = v`); HTML shows it with `data.show`, `data.class_`, `data.attr`, `data.text`.
- **JavaScript does not build HTML.** A repaint removes what the server did not render. Render the markup on the server and toggle it with signals.
- **UI state a click toggles is a local signal**: `$_qr = !$_qr` with `data.show("$_qr")`, not `el.hidden = ...` in a file.
- **A repaint copies every attribute from the server HTML.** An element whose `style` or `class` JavaScript writes gets `data.preserve_attr("style class")`.
- **Another element is a ref**, not an id lookup: `data.ref("_edit")` on the dialog, `$_edit.showModal()` on the button.
- **Server values reach JavaScript as signals or `data-*` attributes.** A literal in an expression goes through `string_literal`; never build JavaScript with an f-string.
- **Guard an index read with the length**: `$files.length > 2 && $files[2].name`; a read past the end creates the entry.
- **A checkbox group bound to one signal is positional**: predefine `"scope": []`; the server drops the empty strings.
- **`sse.execute_script(...)` is for an action** (`app.list.focus()`), not for text: text goes in a signal (`_toast`, `_error`).
- **The only inline `<script>` is the theme restore in `<head>`** (skill `stario-tailwind-daisyui`). `security_headers()` sets no CSP.
- **Write the logic, not the defence**: no fallback for a value the server always renders, no `try` around an API the browsers have.

## The check

`tests/test_js.py` collects every `app.<name>.<method>` in the strings of `app/**/*.py` and asserts that `static/js/<name>.js` defines it, so a rename or a typo fails the check. A file that holds state (a drag, a ruler) is the one case for a browser (skill `stario-browser-check`): check that one interaction, then stop.
