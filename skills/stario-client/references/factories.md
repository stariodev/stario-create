# A factory: one element with its own state

A factory exists only when each element needs its own state (a ruler, a wheel, a drag). It listens on its own `el`, so its listeners die with the element:

```js
// static/js/ruler.js
window.app ??= {};
app.ruler = (el, write) => {
  const min = Number(el.dataset.min), max = Number(el.dataset.max), step = Number(el.dataset.step);
  const valueAt = () => min + Math.round(el.scrollLeft / 10) * step;
  let dragging = false;
  el.addEventListener("pointerdown", (evt) => { dragging = true; el.setPointerCapture(evt.pointerId); });
  el.addEventListener("pointerup", () => { dragging = false; });
  el.addEventListener("scroll", () => dragging || write(valueAt()), { passive: true });
  return {
    show(value) { /* return early when value is already shown; else scroll to it */ },
    step(dir) { write(Math.min(max, Math.max(min, valueAt() + dir * step))); },
  };
};
```

```python
h.Div(
    {"data-min": 30, "data-max": 200, "data-step": 0.1},
    data.ref("_weight_ruler"),
    data.init("el.ruler ??= app.ruler(el, v => $weight_kg = v)"),
    data.effect("el.ruler.show($weight_kg)"),
    *ticks,
)
h.Button({"type": "button"}, data.on("click", "$_weight_ruler.ruler.step(1)"), "+")
```

A factory listens on its own `el`, so its listeners die with the element. Keep the `data.init` text constant and write `el.x ??= app.x(el, ...)`, so the factory runs once per element. An element whose `style` or `class` the factory writes during a drag gets `data.preserve_attr("style class")`.

## Common mistakes

| Avoid | Do |
| --- | --- |
| JavaScript in a Python string, `h.Script(SafeString(...))` | a function in `static/js/<name>.js` |
| `window.myThing = ...`, `if (window.x) return` guards | `app.<name>` in its own file |
| `addEventListener` on `window` or `document` | `data.on(..., target="window")` |
| `DOMContentLoaded`, `dataset.bound` guards | `data.init` on the element |
| `document.getElementById(...)` in an expression | `data.ref("_name")` and `$_name` |
| JavaScript that filters a JSON copy of server data | a `GET` that patches its part |
| JavaScript that builds HTML | server HTML plus `data.show` / `data.class_` |
| A five-statement `data.on` expression | an `app.<name>.<method>` call |
| A Python helper that returns a JavaScript string | the expression inline, or a function in the file |
