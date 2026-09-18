# Extractable components

## AppShell

- Source: `frontend/app.js`
- Category: layout
- Description: Desktop sidebar, topbar, and central workspace shell.
- Extractable props: `title`, `subtitle`, `activeItem`.
- Hardcoded: Paper Studio brand, current navy/blue CSS token system.

## GenerationProgress

- Source: `frontend/app.js`
- Category: basic
- Description: Generation state, message, counter, and optional progress bar.
- Extractable props: `state`, `completed`, `total`, `message`.
- Hardcoded: status colors and progress styling.
