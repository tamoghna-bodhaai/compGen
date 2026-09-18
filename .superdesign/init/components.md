# Shared components

This is a framework-free frontend. It has no standalone component directory: reusable UI primitives are CSS classes and template helpers in `frontend/app.js`.

## Button and card primitives

- Source: `frontend/styles.css`
- Description: Vanilla CSS classes power buttons (`.btn`, `.btn-primary`, `.btn-outline`) and cards (`.card`).
- Props: Not applicable; markup is emitted by template helpers.

```css
.card { background: var(--paper); border: 1px solid var(--line); border-radius: 13px; box-shadow: 0 3px 12px rgba(16, 24, 40, .03); }
.btn { border: 1px solid transparent; background: #fff; color: #344054; border-radius: 8px; padding: 8px 11px; font-size: 12px; font-weight: 700; white-space: nowrap; }
.btn-primary { background: var(--blue); color: #fff; }
.btn-outline { border-color: #cbd5e1; }
```
