# Shared layouts

## Paper Studio shell

- Source: `frontend/app.js`
- Description: A fixed desktop sidebar plus topbar and scrolling workspace content.

```js
function header() {
  return `<aside class="sidebar"><button class="brand" data-action="dashboard" aria-label="Go to Paper Studio dashboard"><span class="brand-mark">Q</span><span><h1>Paper Studio</h1><p>JEE question workspace</p></span></button><button class="btn btn-primary" data-action="new-paper">＋ New paper</button><div><div class="nav-caption">Your papers</div><div class="paper-list">${state.papers.length ? state.papers.map(paperLink).join("") : "<p class=\"api-note\">No papers yet.</p>"}</div></div><div class="sidebar-spacer"></div><p class="api-note">Seed bank: 50 medium JEE questions on Definite Integrals. Answers remain unverified.</p></aside>`;
}

function layout(content, title = "Question paper workspace", subtitle = "Create, curate, and export JEE-ready papers") {
  app.innerHTML = `<div class="shell">${header()}<main class="workspace"><header class="topbar"><div><div class="eyebrow">Question Paper Generator</div><h2>${esc(title)}</h2></div><div class="top-actions"><button class="btn btn-outline" data-action="source-bank">Browse question bank</button><button class="btn btn-primary" data-action="new-paper">New paper</button></div></header>${content}</main></div>`;
}
```

```css
.shell { height: 100vh; min-height: 0; display: grid; grid-template-columns: 270px minmax(0, 1fr); overflow: hidden; }
.sidebar { min-height: 0; overflow-y: auto; background: var(--navy); color: #fff; padding: 24px 16px; display: flex; flex-direction: column; gap: 22px; }
.workspace { min-width: 0; min-height: 0; height: 100vh; display: flex; flex-direction: column; }
.topbar { height: 76px; background: rgba(255,255,255,.92); border-bottom: 1px solid var(--line); padding: 0 34px; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.content { width: 100%; min-height: 0; flex: 1; overflow: auto; padding: 30px 34px 56px; max-width: 1500px; margin: 0 auto; }
```
