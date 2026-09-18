# Routes

The app is a single-page vanilla JavaScript application without a client router.

## Dashboard / paper editor

- Entry: `frontend/app.js`
- Layout: Paper Studio shell (`header()` and `layout()`).
- State: `state.paper === null` renders the dashboard; a selected paper renders the paper editor.
- Key render switch:

```js
function render() { if (state.paper) renderPaper(); else renderWelcome(); }
```
