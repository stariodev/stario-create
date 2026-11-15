# A custom DaisyUI theme

A custom theme replaces the `@plugin` block in `input.css`:

```css
@plugin "../daisyui.mjs" {
  themes: false;
}

@plugin "../daisyui-theme.mjs" {
  name: "app";
  default: true;
  color-scheme: light;
  --color-base-100: #f7f6f1;
  --color-base-content: #1a1f24;
  --color-primary: #3d4a6b;
  --color-primary-content: #f7f6f1;
}
```
