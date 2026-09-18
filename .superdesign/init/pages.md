# Key page dependencies

## Dashboard (single-page state)

Entry: `frontend/app.js`

Dependencies:

- `frontend/app.js`
  - `renderWelcome()` dashboard renderer
  - `header()` and `layout()` shared shell
  - `generationProgress()` live job status renderer
  - `refreshPapers()` API loader
- `frontend/styles.css`
- `frontend/index.html`

## Paper editor (single-page state)

Entry: `frontend/app.js`

Dependencies:

- `frontend/app.js`
  - `renderPaper()`
  - `questionsPane()` / `answerKeyPane()` / `inspector()`
  - `exportPaper()` and generation actions
- `frontend/styles.css`
