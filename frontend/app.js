const api = "/api";
const state = {
  papers: [], paper: null, selectedQuestionId: null, questionDraft: null, sourceQuestions: [], paperView: "questions", brandingProfiles: null,
  ingestionJobs: [], activeIngestionJobId: null, completedIngestionJobId: null,
  dashboardFilter: "all", dashboardSearch: "", catalog: [], catalogLoaded: false, bankSelection: {}, bankQuestions: [], bankQuestionTotal: 0, bankQuestionOffset: 0,
  creation: {
    title: "Definite Integrals Practice Paper", exam: "JEE", subject: "Mathematics", chapters: [], subtopicKeys: [], plans: {},
    questionCounts: { single_correct_mcq: 10, numerical: 0, multiple_correct_mcq: 0 },
    difficultyCounts: { easy: 0, medium: 10, hard: 0 }, generation_mode: "structural_variation", variation_strength: "balanced",
  },
};
let generationPollTimer = null;
const app = document.querySelector("#app");
const modal = document.querySelector("#modal");

const esc = (value = "") => String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const letters = ["A", "B", "C", "D", "E", "F"];
const origin = (question) => question.generation_metadata?.origin || "manual";

function normaliseLatex(value = "") {
  return String(value)
    .replaceAll("\\\\", "\\")
    // Some legacy model responses contained JSON escape characters where a
    // LaTeX command backslash should have been. Repair only unambiguous
    // command fragments so KaTeX can render those stored solutions as well.
    .replace(/\f(?=rac\b)/g, String.raw`\f`)
    .replace(/\t(?=(?:an|ext)\b)/g, String.raw`\t`)
    .replace(/\u0008(?=(?:egin|ox)\b)/g, String.raw`\b`)
    .replace(/\r(?=ight\b)/g, String.raw`\r`)
    .replace(/\u0007(?=sqrt(?:\b|\d))/g, "\\");
}

function readableMath(value = "") {
  let text = normaliseLatex(value).replaceAll("$", "").replace(/\\,/g, " ").replace(/\\!/g, "");
  for (let i = 0; i < 3; i += 1) text = text.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1)/($2)");
  return text
    .replace(/\\int/g, "∫").replace(/\\sum/g, "Σ").replace(/\\lim/g, "lim")
    .replace(/\\infty/g, "∞").replace(/\\pi/g, "π").replace(/\\leq/g, "≤")
    .replace(/\\geq/g, "≥").replace(/\\ne/g, "≠").replace(/\\to/g, "→")
    .replace(/\\sqrt\{([^{}]+)\}/g, "√($1)").replace(/\\left|\\right/g, "")
    .replace(/\\([a-zA-Z]+)/g, "$1").replace(/[{}]/g, "");
}

function renderMath(value = "") {
  const source = normaliseLatex(value);
  const delimiters = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g;
  let result = ""; let cursor = 0;
  for (const match of source.matchAll(delimiters)) {
    result += esc(source.slice(cursor, match.index)).replaceAll("\n", "<br>");
    const token = match[0]; let tex = token; let displayMode = false;
    if (token.startsWith("$$")) { tex = token.slice(2, -2); displayMode = true; }
    else if (token.startsWith("\\[")) { tex = token.slice(2, -2); displayMode = true; }
    else if (token.startsWith("\\(")) tex = token.slice(2, -2);
    else tex = token.slice(1, -1);
    try {
      result += window.katex?.renderToString(tex, { throwOnError: false, displayMode, output: "html" }) || esc(readableMath(token));
    } catch { result += esc(readableMath(token)); }
    cursor = (match.index || 0) + token.length;
  }
  return result + esc(source.slice(cursor)).replaceAll("\n", "<br>");
}

async function request(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const response = await fetch(`${api}${path}`, { headers: { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) }, ...options });
  if (!response.ok) {
    let message = "Something went wrong.";
    try { message = (await response.json()).detail || message; } catch { /* no JSON body */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  return response.json();
}

function toast(message, type = "") {
  const item = document.createElement("div"); item.className = `toast ${type}`; item.textContent = message;
  document.querySelector("#toast-region").append(item); setTimeout(() => item.remove(), 4200);
}

const EXAMS = ["JEE", "NEET"];
const SUBJECTS = ["Mathematics", "Physics", "Chemistry"];
const QUESTION_TYPES = [["single_correct_mcq", "MCQ"], ["numerical", "Numerical"], ["multiple_correct_mcq", "Multiple answer"]];
const DIFFICULTIES = [["easy", "Easy", 1], ["medium", "Medium", 3], ["hard", "Hard", 5]];

const ICON_PATHS = {
  dashboard: '<rect x="3" y="3" width="7" height="7" rx="1.5"></rect><rect x="14" y="3" width="7" height="7" rx="1.5"></rect><rect x="3" y="14" width="7" height="7" rx="1.5"></rect><rect x="14" y="14" width="7" height="7" rx="1.5"></rect>',
  library: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"></path>',
  plus: '<path d="M12 5v14M5 12h14"></path>',
  search: '<circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path>',
  document: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6M8 13h8M8 17h6"></path>',
  sparkle: '<path d="m12 3-1.1 3.1a3 3 0 0 1-1.8 1.8L6 9l3.1 1.1a3 3 0 0 1 1.8 1.8L12 15l1.1-3.1a3 3 0 0 1 1.8-1.8L18 9l-3.1-1.1a3 3 0 0 1-1.8-1.8L12 3Z"></path><path d="m5 16-.5 1.5A2 2 0 0 1 3 19l1.5.5A2 2 0 0 1 6 21l.5-1.5A2 2 0 0 1 8 18l-1.5-.5A2 2 0 0 1 5 16Z"></path>',
  check: '<path d="M20 6 9 17l-5-5"></path>',
  questions: '<path d="M8 6h13M8 12h13M8 18h13"></path><path d="M3 6h.01M3 12h.01M3 18h.01"></path>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"></path>',
  download: '<path d="M12 3v12m0 0 4-4m-4 4-4-4"></path><path d="M5 21h14"></path>',
};

function icon(name, className = "") {
  return `<svg class="icon ${className}" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON_PATHS[name] || ICON_PATHS.document}</svg>`;
}

function route() {
  const path = window.location.hash.replace(/^#/, "") || "/";
  if (path === "/question-bank") return { name: "question-bank" };
  if (path === "/new-paper") return { name: "new-paper" };
  const paper = path.match(/^\/papers\/([^/]+)$/);
  return paper ? { name: "paper", id: decodeURIComponent(paper[1]) } : { name: "dashboard" };
}

function navigate(path) { window.location.hash = path; }

function catalogRows(filters = {}) {
  return state.catalog.filter((row) => Object.entries(filters).every(([key, values]) => {
    if (!values?.length) return true;
    return values.includes(row[key]);
  }));
}

function availability(rows) { return rows.reduce((total, row) => total + row.count, 0); }

function defaultPlan() {
  return {
    questionCounts: { single_correct_mcq: 5, numerical: 0, multiple_correct_mcq: 0 },
    difficultyCounts: { easy: 0, medium: 5, hard: 0 },
    generation_mode: "structural_variation", variation_strength: "balanced", sectionTitle: "",
  };
}

function hydrateCreation() {
  const creation = state.creation;
  if (!creation.plans) creation.plans = {};
  const subjectRows = catalogRows({ exam: [creation.exam], subject: [creation.subject] });
  if (!creation.chapters.length) {
    const chapter = subjectRows.find((row) => row.chapter)?.chapter;
    if (chapter) creation.chapters = [chapter];
  }
  const topicRows = catalogRows({ exam: [creation.exam], subject: [creation.subject], chapter: creation.chapters });
  if (!creation.subtopicKeys.length) {
    const row = topicRows.find((item) => item.topic);
    if (row) creation.subtopicKeys = [`${row.topic || ""}::${row.subtopic || ""}`];
  }
  // One plan per selected subtopic. New picks inherit the first plan's
  // configuration so mixed papers start consistent but stay independently editable.
  const template = creation.subtopicKeys.map((key) => creation.plans[key]).find(Boolean)
    || { questionCounts: creation.questionCounts, difficultyCounts: creation.difficultyCounts, generation_mode: creation.generation_mode, variation_strength: creation.variation_strength, sectionTitle: "" };
  for (const key of creation.subtopicKeys) {
    if (!creation.plans[key]) {
      creation.plans[key] = {
        questionCounts: { ...defaultPlan().questionCounts, ...(template.questionCounts || {}) },
        difficultyCounts: { ...defaultPlan().difficultyCounts, ...(template.difficultyCounts || {}) },
        generation_mode: template.generation_mode || "structural_variation",
        variation_strength: template.variation_strength || "balanced",
        sectionTitle: "",
      };
    }
  }
  for (const key of Object.keys(creation.plans)) {
    if (!creation.subtopicKeys.includes(key)) delete creation.plans[key];
  }
}

async function loadCatalog() {
  if (state.catalogLoaded) return;
  state.catalog = (await request("/questions/catalog")).items;
  state.catalogLoaded = true;
  hydrateCreation();
}

function creationPayload() {
  const creation = state.creation;
  if (!creation.plans) hydrateCreation();
  const subtopic_plans = creation.subtopicKeys.map((key) => {
    const separator = key.indexOf("::");
    const topic = key.slice(0, separator); const subtopic = key.slice(separator + 2);
    const plan = creation.plans[key] || defaultPlan();
    return {
      topic, subtopic, chapters: creation.chapters,
      section_title: (plan.sectionTitle || "").trim() || `${topic} › ${subtopic}`,
      question_types: QUESTION_TYPES.map(([type]) => ({ type, count: Number(plan.questionCounts?.[type]) || 0 })).filter((item) => item.count > 0),
      difficulty_distribution: DIFFICULTIES.map(([planKey, , difficulty]) => ({ difficulty, count: Number(plan.difficultyCounts?.[planKey]) || 0 })).filter((item) => item.count > 0),
      generation_mode: plan.generation_mode, variation_strength: plan.variation_strength,
    };
  });
  const selectedSubtopics = creation.subtopicKeys.map((key) => {
    const separator = key.indexOf("::");
    return { topic: key.slice(0, separator), subtopic: key.slice(separator + 2) };
  });
  // Aggregated globals keep older backends/clients working; the per-subtopic
  // plans are authoritative when present.
  const aggregate = (pick) => {
    const totals = new Map();
    for (const plan of subtopic_plans) for (const item of pick(plan)) totals.set(JSON.stringify(item.type ?? item.difficulty), (totals.get(JSON.stringify(item.type ?? item.difficulty)) || 0) + item.count);
    return totals;
  };
  const typeTotals = new Map(); const difficultyTotals = new Map();
  for (const plan of subtopic_plans) {
    for (const item of plan.question_types) typeTotals.set(item.type, (typeTotals.get(item.type) || 0) + item.count);
    for (const item of plan.difficulty_distribution) difficultyTotals.set(item.difficulty, (difficultyTotals.get(item.difficulty) || 0) + item.count);
  }
  void aggregate;
  return {
    title: creation.title.trim(), exam: creation.exam, subject: creation.subject, chapters: creation.chapters,
    topics: [...new Set(selectedSubtopics.map((item) => item.topic).filter(Boolean))],
    subtopics: [...new Set(selectedSubtopics.map((item) => item.subtopic).filter(Boolean))], concepts: [],
    question_types: [...typeTotals.entries()].map(([type, count]) => ({ type, count })),
    difficulty_distribution: [...difficultyTotals.entries()].map(([difficulty, count]) => ({ difficulty, count })),
    generation_mode: creation.generation_mode, variation_strength: creation.variation_strength,
    subtopic_plans,
  };
}

async function refreshPapers(selectId = state.paper?.id) {
  state.papers = (await request("/papers")).items;
  await loadIngestionJobs();
  if (selectId) await loadPaper(selectId, false); else render();
  syncGenerationPolling();
}

async function loadPaper(id, shouldRender = true) {
  const previousQuestionId = state.selectedQuestionId;
  state.paper = await request(`/papers/${id}`);
  state.selectedQuestionId = state.paper.questions.some((question) => question.id === previousQuestionId) ? previousQuestionId : state.paper.questions[0]?.id || null;
  if (state.questionDraft?.id !== state.selectedQuestionId) state.questionDraft = null;
  if (shouldRender) render();
}

function generationPaused(job) { return job?.control_state === "paused"; }
function generationCancelled(job) { return job?.control_state === "cancelled"; }
function activeGeneration(paper) { return ["queued", "running"].includes(paper.generation_job?.state) && !generationCancelled(paper.generation_job); }
function activeIngestion(job) { return ["queued", "running"].includes(job?.state); }
async function loadIngestionJobs() {
  state.ingestionJobs = (await request("/questions/ingestion-jobs")).items;
  const tracked = state.ingestionJobs.find((job) => job.id === state.activeIngestionJobId);
  if (tracked?.state === "succeeded" && state.completedIngestionJobId !== tracked.id) {
    state.completedIngestionJobId = tracked.id; state.catalogLoaded = false; state.catalog = []; state.sourceQuestions = []; state.bankSelection = {};
    toast(`${tracked.ingested_questions} question${tracked.ingested_questions === 1 ? "" : "s"} ingested from ${tracked.source_name}. Review labels before relying on them in a paper.`);
  }
  if (modal.querySelector("#ingestion-form") && tracked) ingestionModal();
}

function generationLabel(paper) {
  const job = paper.generation_job;
  if (!job) return `${paper.question_count} questions · ${paper.status}`;
  if (generationCancelled(job)) return `Cancelled · ${job.completed_questions}/${job.total_questions} retained`;
  if (generationPaused(job)) return `Paused · ${job.completed_questions}/${job.total_questions} complete`;
  if (activeGeneration(paper)) return job.operation === "solutions" ? `Solutions · ${job.completed_questions}/${job.total_questions} generated` : `Generating · ${job.completed_questions}/${job.total_questions} validated`;
  if (job.state === "failed") return job.operation === "solutions" ? "Solutions need attention" : "Generation needs attention";
  return `${paper.question_count} questions · ${paper.status}`;
}

function generationProgress(paper, compact = false) {
  const job = paper.generation_job;
  if (!job) return "";
  const active = activeGeneration(paper);
  const paused = generationPaused(job);
  const cancelled = generationCancelled(job);
  const percent = job.total_questions ? Math.round((job.completed_questions / job.total_questions) * 100) : 0;
  const subject = job.operation === "solutions" ? "solution generation" : "paper generation";
  if (compact) return `<span class="generation-state ${job.state}">${esc(generationLabel(paper))}</span>`;
  const controls = active ? `<div class="generation-controls">${paused ? `<button class="btn btn-primary small" data-action="generation-resume">Resume</button>` : `<button class="btn btn-outline small" data-action="generation-pause">Pause</button>`}<button class="btn btn-danger small" data-action="generation-cancel">Cancel</button></div>` : "";
  const title = paused ? `${subject[0].toUpperCase()}${subject.slice(1)} paused` : cancelled ? `${subject[0].toUpperCase()}${subject.slice(1)} cancelled` : active ? `${subject[0].toUpperCase()}${subject.slice(1)} in progress` : job.state === "failed" ? `${subject[0].toUpperCase()}${subject.slice(1)} needs attention` : `Latest ${subject}`;
  return `<div class="generation-progress card ${job.state} ${paused ? "paused" : ""} ${cancelled ? "cancelled" : ""}"><div class="generation-progress-head"><div><span class="live-dot ${active && !paused ? "pulse" : ""}"></span><strong>${title}</strong></div><span>${job.completed_questions}/${job.total_questions}</span></div><p>${esc(job.message || generationLabel(paper))}</p>${active ? `<div class="progress-track" aria-label="${percent}% complete"><span style="width:${percent}%"></span></div>` : ""}${controls}${job.error_message ? `<p class="generation-error">${esc(job.error_message)}</p>` : ""}</div>`;
}

function ingestionProgress(job) {
  const active = activeIngestion(job); const percent = job.total_chunks ? Math.round((job.completed_chunks / job.total_chunks) * 100) : 0;
  const title = active ? "Book ingestion in progress" : job.state === "failed" ? "Book ingestion needs attention" : "Latest book ingestion";
  return `<div class="generation-progress card ${job.state}"><div class="generation-progress-head"><div><span class="live-dot ${active ? "pulse" : ""}"></span><strong>${title}</strong></div><span>${job.total_chunks ? `${job.completed_chunks}/${job.total_chunks}` : ""}</span></div><p>${esc(job.message || job.phase)}</p>${active ? `<div class="progress-track" aria-label="${percent}% complete"><span style="width:${percent}%"></span></div>` : ""}${job.ingested_questions ? `<p class="status">${job.ingested_questions} questions ingested</p>` : ""}${job.error_message ? `<p class="generation-error">${esc(job.error_message)}</p>` : ""}</div>`;
}

function paperDashboardState(paper) {
  if (generationCancelled(paper.generation_job)) return "cancelled";
  if (activeGeneration(paper)) return "generating";
  if (paper.generation_job?.state === "failed") return "attention";
  if (["generated", "final"].includes(paper.status)) return "ready";
  return "draft";
}

function dashboardStateLabel(paper) {
  const status = paperDashboardState(paper);
  if (status === "generating") return "Generating";
  if (status === "cancelled") return "Cancelled";
  if (status === "attention") return "Needs attention";
  if (status === "ready") return paper.status === "final" ? "Final" : "Ready";
  return "Draft";
}

function dashboardMetrics() {
  return state.papers.reduce((metrics, paper) => {
    const status = paperDashboardState(paper);
    metrics.total += 1; metrics.questions += paper.question_count || 0;
    if (status === "generating") metrics.generating += 1;
    if (status === "ready") metrics.ready += 1;
    if (status === "attention") metrics.attention += 1;
    return metrics;
  }, { total: 0, generating: 0, ready: 0, attention: 0, questions: 0 });
}

function matchesDashboardFilter(paper) {
  const query = state.dashboardSearch.trim().toLowerCase();
  const matchesQuery = !query || [paper.title, paper.exam, paper.subject].filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
  return matchesQuery && (state.dashboardFilter === "all" || paperDashboardState(paper) === state.dashboardFilter);
}

function formatUpdatedAt(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "Recently updated";
  return `Updated ${new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date)}`;
}

function paperActionLabel(paper) {
  if (paperDashboardState(paper) === "cancelled") return "Continue generation";
  if (paperDashboardState(paper) === "attention") return "Retry generation";
  if (paperDashboardState(paper) === "draft" && !paper.question_count) return "Generate draft";
  return "Open paper";
}

function syncGenerationPolling() {
  if (generationPollTimer) window.clearTimeout(generationPollTimer);
  if (!state.papers.some(activeGeneration) && !state.ingestionJobs.some(activeIngestion)) return;
  generationPollTimer = window.setTimeout(async () => {
    generationPollTimer = null;
    try { await refreshPapers(state.paper?.id); } catch { syncGenerationPolling(); }
  }, 2500);
}

function header() {
  const current = route();
  return `<aside class="sidebar"><button class="brand" data-action="dashboard" aria-label="Go to Paper Studio dashboard"><span class="brand-mark">${icon("document")}</span><span><h1>Paper Studio</h1><p>JEE workspace</p></span></button><div class="sidebar-section"><span class="sidebar-label">Workspace</span><nav class="primary-nav" aria-label="Workspace navigation"><button class="nav-link ${current.name === "dashboard" ? "active" : ""}" data-action="dashboard">${icon("dashboard", "nav-icon")}<span>Dashboard</span></button><button class="nav-link ${current.name === "question-bank" ? "active" : ""}" data-action="question-bank">${icon("library", "nav-icon")}<span>Question bank</span></button></nav></div><button class="btn btn-primary sidebar-cta" data-action="new-paper">${icon("plus")}<span>New paper</span></button><div class="sidebar-spacer"></div></aside>`;
}

function layout(content, title = "Question paper workspace", subtitle = "Create, curate, and export JEE-ready papers") {
  const current = route();
  app.innerHTML = `<div class="shell">${header()}<main class="workspace"><header class="topbar"><div class="topbar-title"><div class="eyebrow">Paper Studio</div><h2>${esc(title)}</h2></div><div class="top-actions"><button class="btn btn-outline" data-action="question-bank">${icon("library")}<span>Question bank</span></button><button class="btn btn-primary" data-action="new-paper">${icon("plus")}<span>New paper</span></button></div></header><nav class="mobile-nav" aria-label="Workspace navigation"><button class="${current.name === "dashboard" ? "active" : ""}" data-action="dashboard">${icon("dashboard")}<span>Dashboard</span></button><button class="${current.name === "question-bank" ? "active" : ""}" data-action="question-bank">${icon("library")}<span>Question bank</span></button><button data-action="new-paper">${icon("plus")}<span>New paper</span></button></nav>${content}</main></div>`;
}

function dashboardPaperCard(paper) {
  const status = paperDashboardState(paper);
  const requested = paper.requested_question_count || 0;
  const questionCount = requested ? `${paper.question_count}/${requested} questions` : `${paper.question_count} questions`;
  const primaryAction = status === "attention" || status === "cancelled" || (status === "draft" && !paper.question_count)
    ? `<button class="btn btn-outline" data-action="dashboard-retry" data-id="${paper.id}">${paperActionLabel(paper)}</button>`
    : `<button class="btn btn-primary" data-action="open-paper" data-id="${paper.id}">Open paper ${icon("arrow")}</button>`;
  const exportAction = paper.question_count ? `<button class="btn btn-quiet" data-action="dashboard-export" data-id="${paper.id}">${icon("download")}<span>PDF</span></button>` : "";
  return `<article class="paper-library-card"><div class="paper-library-card-head"><span class="paper-card-icon">${icon("document")}</span><span class="dashboard-status ${status}">${dashboardStateLabel(paper)}</span></div><div class="paper-card-body"><h4>${esc(paper.title)}</h4><p>${esc([paper.exam, paper.subject].filter(Boolean).join(" · ") || "Paper workspace")}</p><div class="paper-card-meta"><span>${icon("questions")}${questionCount}</span><span>${formatUpdatedAt(paper.updated_at)}</span>${status === "generating" ? `<span>${esc(generationLabel(paper))}</span>` : ""}</div>${status === "generating" ? `<div class="progress-track" aria-label="Generation progress"><span style="width:${paper.generation_job?.total_questions ? Math.round((paper.generation_job.completed_questions / paper.generation_job.total_questions) * 100) : 0}%"></span></div>` : ""}</div><footer>${primaryAction}${exportAction}</footer></article>`;
}

function renderWelcome() {
  const metrics = dashboardMetrics();
  const tracked = state.papers.filter((paper) => ["generating", "attention", "cancelled"].includes(paperDashboardState(paper)));
  const ingestionTracked = state.ingestionJobs.filter((job) => activeIngestion(job) || job.state === "failed");
  const filtered = state.papers.filter(matchesDashboardFilter);
  const filterOptions = [["all", "All papers"], ["draft", "Drafts"], ["generating", "Generating"], ["ready", "Ready"], ["attention", "Needs attention"], ["cancelled", "Cancelled"]];
  const activity = tracked.length || ingestionTracked.length ? `<section class="dashboard-section dashboard-panel" aria-labelledby="activity-heading"><div class="dashboard-section-head"><div><div class="eyebrow">Live activity</div><h3 id="activity-heading">Generation &amp; ingestion</h3></div><span class="auto-update"><span class="live-dot pulse"></span>Updates automatically</span></div><div class="generation-grid">${tracked.map((paper) => `<article class="generation-card card"><div class="generation-card-head"><div><strong>${esc(paper.title)}</strong><span class="dashboard-status ${paperDashboardState(paper)}">${dashboardStateLabel(paper)}</span></div><button class="btn btn-quiet small" data-action="open-paper" data-id="${paper.id}">Open ${icon("arrow")}</button></div>${generationProgress(paper)}${["attention", "cancelled"].includes(paperDashboardState(paper)) ? `<button class="btn btn-outline small" data-action="dashboard-retry" data-id="${paper.id}">${paperActionLabel(paper)}</button>` : ""}</article>`).join("")}${ingestionTracked.map((job) => `<article class="generation-card card"><div class="generation-card-head"><div><strong>${esc(job.source_name)}</strong><span class="dashboard-status ${job.state === "failed" ? "attention" : "generating"}">${job.state === "failed" ? "Needs attention" : "Ingesting"}</span></div></div>${ingestionProgress(job)}</article>`).join("")}</div></section>` : "";
  const library = filtered.length ? filtered.map(dashboardPaperCard).join("") : `<div class="dashboard-empty card"><span class="empty-icon">${icon(state.papers.length ? "search" : "document")}</span><h4>${state.papers.length ? "No papers match this view" : "Your paper library starts here"}</h4><p>${state.papers.length ? "Try another status or clear your search." : "Create a paper, track its generation, and return here whenever you need it."}</p>${state.papers.length ? `<button class="btn btn-outline" data-action="dashboard-filter" data-filter="all">Show all papers</button>` : `<button class="btn btn-primary" data-action="new-paper">${icon("plus")}Create your first paper</button>`}</div>`;
  layout(`<section class="content dashboard-content"><header class="dashboard-hero"><div><div class="eyebrow">Overview</div><h1>Your paper workspace</h1><p>Create, monitor, curate, and export JEE-ready question papers from one focused workspace.</p></div><div class="dashboard-hero-actions"><button class="btn btn-outline" data-action="question-bank">${icon("library")}<span>Browse question bank</span></button><button class="btn btn-primary" data-action="new-paper">${icon("plus")}<span>Create paper</span></button></div></header><section class="dashboard-metrics" aria-label="Paper overview"><button class="dashboard-metric ${state.dashboardFilter === "all" ? "active" : ""}" data-action="dashboard-filter" data-filter="all"><span class="metric-icon">${icon("document")}</span><span class="metric-copy"><small>Total papers</small><strong>${metrics.total}</strong><span>All workspace papers</span></span></button><button class="dashboard-metric generating ${state.dashboardFilter === "generating" ? "active" : ""}" data-action="dashboard-filter" data-filter="generating"><span class="metric-icon">${icon("sparkle")}</span><span class="metric-copy"><small>Generating</small><strong>${metrics.generating}</strong><span>Live work in progress</span></span></button><button class="dashboard-metric ready ${state.dashboardFilter === "ready" ? "active" : ""}" data-action="dashboard-filter" data-filter="ready"><span class="metric-icon">${icon("check")}</span><span class="metric-copy"><small>Ready to export</small><strong>${metrics.ready}</strong><span>Completed papers</span></span></button><button class="dashboard-metric ${state.dashboardFilter === "all" ? "active" : ""}" data-action="dashboard-filter" data-filter="all"><span class="metric-icon">${icon("questions")}</span><span class="metric-copy"><small>Total questions</small><strong>${metrics.questions}</strong><span>Across all papers</span></span></button></section>${activity}<section class="dashboard-section paper-library dashboard-panel" aria-labelledby="paper-library-heading"><div class="dashboard-section-head library-heading"><div><div class="eyebrow">Library</div><h3 id="paper-library-heading">Your papers <span>${state.papers.length}</span></h3></div><label class="dashboard-search"><span class="sr-only">Search papers</span>${icon("search")}<input id="dashboard-search" value="${esc(state.dashboardSearch)}" placeholder="Search papers, exams, or subjects"></label></div><div class="library-toolbar"><div class="dashboard-filters" role="tablist" aria-label="Filter papers by status">${filterOptions.map(([value, label]) => `<button class="dashboard-filter ${state.dashboardFilter === value ? "active" : ""}" data-action="dashboard-filter" data-filter="${value}" role="tab" aria-selected="${state.dashboardFilter === value}">${label}</button>`).join("")}</div><p class="status">${filtered.length} of ${state.papers.length} shown</p></div><div class="paper-library-results"><div class="paper-library-grid">${library}</div></div></section></section>`, "Dashboard", "Manage your paper workspace in one place");
}

function groupQuestions(paper) {
  const groups = new Map();
  paper.sections.forEach((section) => groups.set(section.id, { title: section.title, items: [] }));
  groups.set("unassigned", { title: "Unsectioned questions", items: [] });
  paper.questions.forEach((question) => (groups.get(question.section_id || "unassigned") || groups.get("unassigned")).items.push(question));
  return [...groups.entries()].filter(([, group]) => group.items.length || group.title !== "Unsectioned questions");
}

function questionCard(question, index) {
  question = effectiveQuestion(question);
  const data = question.question_json || {}; const selected = state.selectedQuestionId === question.id ? "selected" : "";
  const options = (data.options || []).map((option, optionIndex) => `<span>${letters[optionIndex]}. <span class="math-content">${renderMath(option)}</span></span>`).join("");
  return `<button class="question-card ${selected}" data-question-card="true" data-action="select-question" data-id="${question.id}"><div class="q-head"><span class="q-number">Q${index} · ${esc(question.question_type.replaceAll("_", " "))}</span><span class="chips"><span class="chip difficulty-chip">Difficulty ${question.difficulty}/5</span>${question.locked ? "<span class=\"chip locked\">Locked</span>" : ""}${origin(question) === "generated" ? "<span class=\"chip generated\">Generated</span>" : ""}</span></div><p class="q-stem math-content">${renderMath(data.stem)}</p>${options ? `<div class="q-options">${options}</div>` : ""}</button>`;
}

function questionsPane(paper) {
  let index = 0;
  const groups = groupQuestions(paper).map(([, group]) => {
    const cards = group.items.map((question) => questionCard(question, ++index)).join("");
    return `${paper.sections.length ? `<div class="section-label">${esc(group.title)}</div>` : ""}${cards}`;
  }).join("");
  const requested = paper.requested_question_count || 0;
  const countNote = requested ? `${paper.question_count} question${paper.question_count === 1 ? "" : "s"} · requested ${requested}` : `${paper.question_count} question${paper.question_count === 1 ? "" : "s"}`;
  return `<section class="card"><div class="toolbar"><button class="btn btn-outline small" data-action="add-section">＋ Section</button><button class="btn btn-outline small" data-action="add-source-bank">Add from bank</button><button class="btn btn-outline small" data-action="manual-question">＋ Manual</button><span class="spacer"></span><span class="status ${requested && paper.question_count !== requested ? "count-alert" : ""}">${countNote}</span></div><div class="question-stack">${groups || `<div class="empty"><h4>Start curating</h4><p>Add a source question or compose one manually. Generation is available when your model credentials are configured.</p><button class="btn btn-primary" data-action="add-source-bank">Browse the seed bank</button></div>`}</div></section>`;
}

function answerKeyPane(paper) {
  const missing = paper.questions.filter((question) => !question.solution).length;
  const jobRunning = activeGeneration(paper);
  const rows = paper.questions.map((question, index) => {
    const answer = question.answer_json?.correct_answer || "Not set";
    return `<article class="answer-item"><div class="answer-item-head"><strong>Q${index + 1}</strong><span class="answer-badge">Answer: <span class="math-content">${renderMath(answer)}</span></span></div>${question.solution ? `<div class="solution-body math-content">${renderMath(question.solution)}</div>` : `<p class="status">No worked solution yet.</p>`}</article>`;
  }).join("");
  const buttonLabel = jobRunning && paper.generation_job?.operation === "solutions" ? "Generating solutions…" : missing ? `Generate ${missing} missing solution${missing === 1 ? "" : "s"}` : "All solutions available";
  return `<section class="card answer-key-pane"><div class="toolbar"><div><strong>Answer key &amp; worked solutions</strong><span class="status answer-summary">${paper.question_count - missing}/${paper.question_count} solutions available</span></div><span class="spacer"></span><button class="btn btn-primary small" data-action="generate-solutions" ${!missing || jobRunning ? "disabled" : ""}>${buttonLabel}</button></div><div class="answer-list">${rows || `<div class="empty"><h4>No questions yet</h4><p>Generate or add questions before creating an answer key.</p></div>`}</div></section>`;
}

function selectedQuestion() { return state.paper?.questions.find((question) => question.id === state.selectedQuestionId); }
function effectiveQuestion(question) {
  if (!question || state.questionDraft?.id !== question.id) return question;
  const draft = state.questionDraft.values;
  return { ...question, difficulty: draft.difficulty ?? question.difficulty, question_json: { ...question.question_json, stem: draft.stem ?? question.question_json.stem, options: draft.options ?? question.question_json.options, marks: draft.marks ?? question.question_json.marks }, answer_json: { ...question.answer_json, correct_answer: draft.correct_answer ?? question.answer_json?.correct_answer }, solution: draft.solution ?? question.solution };
}

function inspector(paper) {
  const question = selectedQuestion();
  if (!question) return `<aside class="card inspector"><div class="empty"><h4>Question inspector</h4><p>Select a question to edit its content, answer key, marks, and regeneration protection.</p></div></aside>`;
  const preview = effectiveQuestion(question); const data = preview.question_json || {}; const options = data.options || [];
  return `<aside class="card inspector"><div class="inspector-head"><div><h4>Question inspector</h4>${state.questionDraft?.id === question.id ? '<span class="status">Unsaved preview</span>' : ""}</div><button class="btn small ${question.locked ? "btn-outline" : "btn-primary"}" data-action="toggle-lock" data-id="${question.id}">${question.locked ? "Unlock" : "Lock question"}</button></div><form class="card-pad form-grid" id="question-form"><input type="hidden" name="question_id" value="${question.id}"><div class="field"><label>QUESTION STEM</label><textarea name="stem" required>${esc(data.stem || "")}</textarea></div><div class="field"><label>OPTIONS</label>${[0,1,2,3].map((i) => `<div class="option-field"><span class="option-letter">${letters[i]}</span><input name="option${i}" value="${esc(options[i] || "")}" required></div>`).join("")}</div><div class="two-col"><div class="field"><label>CORRECT ANSWER</label><input name="correct_answer" value="${esc(preview.answer_json?.correct_answer || "")}" placeholder="A, B, C, or D"></div><div class="field"><label>SECTION</label><select name="section_id"><option value="">Unsectioned</option>${paper.sections.map((section) => `<option value="${section.id}" ${section.id === question.section_id ? "selected" : ""}>${esc(section.title)}</option>`).join("")}</select></div></div><div class="two-col"><div class="field"><label>DIFFICULTY (1–5)</label><input type="number" min="1" max="5" name="difficulty" value="${preview.difficulty}"></div><div class="field"><label>MARKS</label><input type="number" min="1" max="100" name="marks" value="${data.marks || 4}"></div></div><div class="field"><label>SOLUTION / REVIEW NOTES</label><textarea name="solution" placeholder="Optional; use once verified">${esc(preview.solution || "")}</textarea></div><div class="field"><label>CUSTOM REGENERATION INSTRUCTION (OPTIONAL)</label><textarea name="custom_instruction" maxlength="1200" placeholder="e.g. Use a projectile-motion setup and avoid logarithms."></textarea></div><div class="form-actions"><button class="btn btn-primary" type="submit">Save changes</button><button class="btn btn-outline" type="button" data-action="regenerate-one" data-id="${question.id}" ${question.locked ? "disabled" : ""}>Regenerate</button><button class="btn btn-danger" type="button" data-action="delete-question" data-id="${question.id}">Delete</button></div></form></aside>`;
}

async function brandingModal() {
  if (!state.brandingProfiles) state.brandingProfiles = (await request("/branding-profiles")).items;
  const branding = state.paper?.branding_config || {};
  const logo = branding.logo_data_url ? `<img class="logo-preview" id="branding-logo-preview" src="${esc(branding.logo_data_url)}" alt="Current academy logo">` : `<div class="logo-preview" id="branding-logo-preview"></div>`;
  const profiles = state.brandingProfiles.map((profile) => `<option value="${profile.id}">${esc(profile.name)}</option>`).join("");
  showModal(`${modalHead("Branding, header & footer", "Saved branding is included in DOCX and PDF exports.")}<form id="paper-settings" class="modal-body form-grid"><div class="branding-intro"><div>${logo}<strong>${esc(branding.institution_name || "Paper branding")}</strong><span>Configure your academy identity and document chrome.</span></div></div><div class="two-col"><div class="field"><label>USE A SAVED BRANDING PROFILE</label><select id="branding-profile-select"><option value="">Current paper branding</option>${profiles}</select></div><div class="field"><label>SAVE AS REUSABLE PROFILE</label><input name="profile_name" placeholder="e.g. Apex Academy standard"></div></div><input type="hidden" name="profile_logo_data_url" value="${esc(branding.logo_data_url || "")}"><div class="two-col"><div class="field"><label>ACADEMY / INSTITUTION NAME</label><input name="institution_name" value="${esc(branding.institution_name || "")}" placeholder="Apex Academy"></div><div class="field"><label>LOGO</label><input name="logo_file" type="file" accept="image/png,image/jpeg,image/webp"></div></div><div class="field"><label>ADDRESS</label><textarea name="address" placeholder="Campus address, city, PIN">${esc(branding.address || "")}</textarea></div><div class="two-col"><div class="field"><label>PHONE / EMAIL</label><input name="contact" value="${esc(branding.contact || "")}" placeholder="+91… · hello@academy.in"></div><div class="field"><label>DURATION (MINUTES)</label><input name="duration_minutes" type="number" min="1" value="${esc(branding.duration_minutes || "")}" placeholder="Optional"></div></div><div class="two-col"><div class="field"><label>TOTAL MARKS</label><input name="total_marks" type="number" min="1" value="${esc(branding.total_marks || "")}" placeholder="Optional"></div><div class="field"><label>WATERMARK</label><input name="watermark_text" value="${esc(branding.watermark_text || "")}" placeholder="e.g. Apex Academy · Confidential"></div></div><div class="field"><label>HEADER TEXT</label><input name="header_text" value="${esc(branding.header_text || "")}" placeholder="Defaults to academy name"></div><div class="field"><label>FOOTER TEXT</label><input name="footer_text" value="${esc(branding.footer_text || "")}" placeholder="e.g. Practice paper · Do not reproduce"></div><div class="field"><label>INSTRUCTIONS (ONE PER LINE)</label><textarea name="instructions" placeholder="Attempt all questions">${esc((branding.instructions || []).join("\n"))}</textarea></div><div class="modal-actions"><button class="btn btn-outline" type="button" data-action="close-modal">Cancel</button><button class="btn btn-outline" type="submit" name="save_profile" value="true">Save as profile</button><button class="btn btn-primary" type="submit">Save branding</button></div></form>`);
}

function renderPaper() {
  const paper = state.paper;
  const answers = state.paperView === "answers";
  const variant = answers ? "answer_key" : "question_paper";
  const remaining = Math.max(0, (paper.requested_question_count || 0) - paper.question_count);
  const initialLabel = paper.question_count ? `Generate ${remaining} remaining` : "Generate draft";
  const content = `<section class="content paper-editor-content"><div class="page-head"><div><div class="title-edit"><input id="paper-title" value="${esc(paper.title)}" aria-label="Paper title"><button class="btn btn-quiet small" data-action="save-title">Save title</button></div><p>${esc(paper.exam)} · ${esc(paper.subject)} · ${esc((paper.generation_config.topics || []).join(", ") || "No topic set")} · <strong>${esc(paper.status)}</strong></p></div><div class="top-actions"><button class="btn btn-outline" data-action="branding">Branding &amp; layout</button><button class="btn btn-outline" data-action="generate-initial" ${!remaining || activeGeneration(paper) ? "disabled" : ""}>${initialLabel}</button><button class="btn btn-outline" data-action="regenerate-unlocked" ${!paper.question_count || activeGeneration(paper) ? "disabled" : ""}>Regenerate unlocked</button><button class="btn btn-primary" data-action="export-paper" data-variant="${variant}" data-format="pdf">Export PDF</button><button class="btn btn-outline" data-action="export-paper" data-variant="${variant}" data-format="docx">DOCX</button></div></div><div class="paper-tabs" role="tablist"><button class="paper-tab ${answers ? "" : "active"}" data-action="show-questions">Question paper</button><button class="paper-tab ${answers ? "active" : ""}" data-action="show-answers">Answer key</button></div>${generationProgress(paper)}${answers ? answerKeyPane(paper) : `<div class="editor-grid"><div>${questionsPane(paper)}</div>${inspector(paper)}</div>`}</section>`;
  layout(content, "Paper editor", "Curate questions with locked-item protection");
}

function render() {
  const current = route();
  if (current.name === "paper" && state.paper?.id === current.id) renderPaper();
  else if (current.name === "question-bank") renderQuestionBank();
  else if (current.name === "new-paper") renderNewPaper();
  else renderWelcome();
}

async function syncRoute() {
  const current = route();
  try {
    if (current.name === "paper") {
      await loadPaper(current.id, false);
    } else {
      state.paper = null; state.selectedQuestionId = null;
      if (current.name === "new-paper" || current.name === "question-bank") await loadCatalog();
    }
    render();
  } catch (error) {
    layout(`<section class="content"><div class="card empty"><h4>Couldn’t open this page</h4><p>${esc(error.message)}</p></div></section>`);
  }
}

function showModal(markup) { modal.innerHTML = markup; modal.showModal(); }
function closeModal() { modal.close(); modal.innerHTML = ""; }
function modalHead(title, subtitle = "") { return `<div class="modal-head"><div><h3>${esc(title)}</h3>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div><button class="btn btn-quiet" data-action="close-modal">Close</button></div>`; }

function uniqueRows(rows, key) {
  return [...new Map(rows.map((row) => [key(row), row])).values()];
}

function renderNewPaper() {
  hydrateCreation();
  const creation = state.creation;
  const subjectRows = catalogRows({ exam: [creation.exam], subject: [creation.subject] });
  const chapterRows = uniqueRows(subjectRows.filter((row) => row.chapter), (row) => row.chapter);
  // Chapter-scoped pool: per-subtopic counts must reflect every subtopic under the
  // selected chapters, NOT just the already-selected ones — otherwise unselected
  // subtopics read as "0 seeds", render disabled, and trap the user at one pick.
  const chapterScopedRows = catalogRows({ exam: [creation.exam], subject: [creation.subject], chapter: creation.chapters });
  const topicRows = uniqueRows(
    chapterScopedRows.filter((row) => row.topic),
    (row) => `${row.topic || ""}::${row.subtopic || ""}`,
  );
  const splitKey = (key) => { const separator = key.indexOf("::"); return [key.slice(0, separator), key.slice(separator + 2)]; };
  const payload = creationPayload();
  const typeTotal = payload.question_types.reduce((total, item) => total + item.count, 0);
  const planStates = creation.subtopicKeys.map((key, index) => {
    const [topic, subtopic] = splitKey(key);
    const plan = creation.plans[key] || defaultPlan();
    const rows = catalogRows({ exam: [creation.exam], subject: [creation.subject], chapter: creation.chapters, topic: [topic], subtopic: [subtopic] });
    const typeAvailability = Object.fromEntries(QUESTION_TYPES.map(([type]) => [type, availability(rows.filter((row) => row.question_type === type))]));
    const difficultyAvailability = Object.fromEntries(DIFFICULTIES.map(([planKey, , representative]) => [planKey, availability(rows.filter((row) => representative === 1 ? row.difficulty <= 2 : representative === 3 ? row.difficulty === 3 : row.difficulty >= 4))]));
    const planPayload = payload.subtopic_plans[index] || { question_types: [], difficulty_distribution: [] };
    const planTypeTotal = planPayload.question_types.reduce((total, item) => total + item.count, 0);
    const planDifficultyTotal = planPayload.difficulty_distribution.reduce((total, item) => total + item.count, 0);
    const validTypes = planPayload.question_types.every((item) => (typeAvailability[item.type] || 0) >= 3);
    const validDifficulties = planPayload.difficulty_distribution.every((item) => {
      const planKey = DIFFICULTIES.find(([, , difficulty]) => difficulty === item.difficulty)?.[0];
      return planKey && (difficultyAvailability[planKey] || 0) >= 3;
    });
    return { key, topic, subtopic, plan, rows, typeAvailability, difficultyAvailability, planPayload, planTypeTotal, planDifficultyTotal, validTypes, validDifficulties };
  });
  const ready = Boolean(payload.title) && planStates.length > 0 && planStates.every((item) => item.planTypeTotal > 0 && item.planTypeTotal === item.planDifficultyTotal && item.validTypes && item.validDifficulties);
  const subtopicLabel = (row) => row.subtopic ? `${row.topic} › ${row.subtopic}` : row.topic;
  const option = (value, label, count, selected) => `<option value="${esc(value)}" ${selected ? "selected" : ""} ${count ? "" : "disabled"}>${esc(label)} (${count} seed${count === 1 ? "" : "s"})</option>`;
  const examOptions = EXAMS.map((exam) => option(exam, exam, availability(catalogRows({ exam: [exam] })), creation.exam === exam)).join("");
  const subjectOptions = SUBJECTS.map((subject) => option(subject, subject, availability(catalogRows({ exam: [creation.exam], subject: [subject] })), creation.subject === subject)).join("");
  const chapterOptions = chapterRows.map((row) => option(row.chapter, row.chapter, availability(subjectRows.filter((item) => item.chapter === row.chapter)), creation.chapters.includes(row.chapter))).join("");
  const subtopicOptions = topicRows.map((row) => {
    const key = `${row.topic || ""}::${row.subtopic || ""}`;
    return option(key, subtopicLabel(row), availability(chapterScopedRows.filter((item) => item.topic === row.topic && item.subtopic === row.subtopic)), creation.subtopicKeys.includes(key));
  }).join("");
  const planCards = planStates.map((item) => {
    const typeInputs = QUESTION_TYPES.map(([type, label]) => `<label class="count-picker ${item.typeAvailability[type] ? "" : "unavailable"}"><span>${label}<small>${item.typeAvailability[type]} seed${item.typeAvailability[type] === 1 ? "" : "s"}</small></span><input type="number" min="0" max="100" value="${item.plan.questionCounts[type] ?? 0}" data-plan-count="${esc(item.key)}|${type}" ${item.typeAvailability[type] ? "" : "disabled"}></label>`).join("");
    const difficultyInputs = DIFFICULTIES.map(([planKey, label]) => `<label class="count-picker ${item.difficultyAvailability[planKey] ? "" : "unavailable"}"><span>${label}<small>${item.difficultyAvailability[planKey]} seed${item.difficultyAvailability[planKey] === 1 ? "" : "s"}</small></span><input type="number" min="0" max="100" value="${item.plan.difficultyCounts[planKey] ?? 0}" data-plan-difficulty="${esc(item.key)}|${planKey}" ${item.difficultyAvailability[planKey] ? "" : "disabled"}></label>`).join("");
    const hint = !item.planTypeTotal ? "Set at least one question." : item.planTypeTotal !== item.planDifficultyTotal ? `Type total (${item.planTypeTotal}) must equal difficulty total (${item.planDifficultyTotal}).` : !item.validTypes || !item.validDifficulties ? "Each chosen type/difficulty needs at least three seeds in this subtopic." : `${item.planTypeTotal} questions · one section in the paper.`;
    return `<div class="card card-pad plan-card"><div class="field"><label>SECTION ${planStates.length > 1 ? planStates.indexOf(item) + 1 : ""} · ${esc(item.topic)} › ${esc(item.subtopic)}</label><input value="${esc(item.plan.sectionTitle || "")}" placeholder="${esc(`${item.topic} › ${item.subtopic}`)}" data-plan-field="${esc(item.key)}|sectionTitle" aria-label="Section title"></div><div class="two-col"><div class="field"><label>QUESTIONS BY TYPE</label><div class="count-picker-grid">${typeInputs}</div></div><div class="field"><label>QUESTIONS BY DIFFICULTY</label><div class="count-picker-grid">${difficultyInputs}</div></div></div><div class="two-col"><div class="field"><label>VARIATION MODE</label><select data-plan-field="${esc(item.key)}|generation_mode"><option value="structural_variation" ${item.plan.generation_mode === "structural_variation" ? "selected" : ""}>Structural variation</option><option value="concept_variation" ${item.plan.generation_mode === "concept_variation" ? "selected" : ""}>Concept variation</option></select></div><div class="field"><label>VARIATION STRENGTH</label><select data-plan-field="${esc(item.key)}|variation_strength"><option value="close" ${item.plan.variation_strength === "close" ? "selected" : ""}>Close to source</option><option value="balanced" ${item.plan.variation_strength === "balanced" ? "selected" : ""}>Balanced</option><option value="high" ${item.plan.variation_strength === "high" ? "selected" : ""}>High variation</option></select></div></div><p class="status ${item.planTypeTotal && item.planTypeTotal === item.planDifficultyTotal && item.validTypes && item.validDifficulties ? "" : "count-alert"}">${esc(hint)}</p></div>`;
  }).join("");
  const firstInvalid = planStates.find((item) => !(item.planTypeTotal > 0 && item.planTypeTotal === item.planDifficultyTotal && item.validTypes && item.validDifficulties));
  const validation = !planStates.length ? "Select at least one subtopic." : firstInvalid ? (!firstInvalid.planTypeTotal ? `“${firstInvalid.topic} › ${firstInvalid.subtopic}” needs at least one question.` : firstInvalid.planTypeTotal !== firstInvalid.planDifficultyTotal ? `“${firstInvalid.topic} › ${firstInvalid.subtopic}”: type total (${firstInvalid.planTypeTotal}) must equal difficulty total (${firstInvalid.planDifficultyTotal}).` : `“${firstInvalid.topic} › ${firstInvalid.subtopic}” needs at least three seeds for each chosen type/difficulty.`) : `Mixed paper ready: ${typeTotal} questions across ${planStates.length} section${planStates.length === 1 ? "" : "s"}.`;
  layout(`<section class="content creation-content"><div class="page-head"><div><div class="eyebrow">CREATE PAPER</div><h3>Build a precise paper request</h3><p>Only catalog choices with compatible labeled seed questions can be generated.</p></div></div><form id="new-paper-form" class="card card-pad form-grid"><div class="field"><label>PAPER TITLE</label><input id="new-paper-title" name="title" required value="${esc(creation.title)}"></div><div class="two-col"><div class="field"><label>EXAM</label><select data-creation-field="exam">${examOptions}</select></div><div class="field"><label>SUBJECT</label><select data-creation-field="subject">${subjectOptions}</select></div></div><div class="two-col"><div class="field"><label>CHAPTERS</label><select multiple size="4" data-creation-field="chapters">${chapterOptions || '<option disabled>No chapters available</option>'}</select><span class="status">Ctrl/Cmd+click to pick several chapters.</span></div><div class="field"><label>SUBTOPICS</label><select multiple size="4" data-creation-field="subtopicKeys">${subtopicOptions || '<option disabled>Select a chapter first</option>'}</select><span class="status">Ctrl/Cmd+click to mix several subtopics in one paper.</span></div></div><div class="field"><label>PER-SUBTOPIC PLANS · EACH BECOMES ONE SECTION</label><div class="plan-list">${planCards || '<p class="status">Select subtopics to configure per-section counts.</p>'}</div></div><div class="two-col"><div class="field"><label>DEFAULT VARIATION MODE</label><select data-creation-field="generation_mode"><option value="structural_variation" ${creation.generation_mode === "structural_variation" ? "selected" : ""}>Structural variation</option><option value="concept_variation" ${creation.generation_mode === "concept_variation" ? "selected" : ""}>Concept variation</option></select></div><div class="field"><label>VARIATION STRENGTH</label><select data-creation-field="variation_strength"><option value="close" ${creation.variation_strength === "close" ? "selected" : ""}>Close to source</option><option value="balanced" ${creation.variation_strength === "balanced" ? "selected" : ""}>Balanced</option><option value="high" ${creation.variation_strength === "high" ? "selected" : ""}>High variation</option></select></div></div><p class="status ${ready ? "" : "count-alert"}">${esc(validation)}</p><div class="form-actions"><button class="btn btn-outline" type="button" data-action="dashboard">Cancel</button><button class="btn btn-primary" type="submit" ${ready ? "" : "disabled"}>Create &amp; generate ${typeTotal ? `(${typeTotal})` : ""}</button></div></form></section>`, "Create paper", "Choose the seed taxonomy before generation");
}

function catalogCount(rows) { return availability(rows); }

function bankRows(filters = {}) {
  const selected = { ...state.bankSelection, ...filters };
  return state.catalog.filter((row) => Object.entries(selected).every(([key, value]) => !value || row[key] === value));
}

async function loadBankQuestions(offset = 0) {
  const selection = state.bankSelection;
  if (!Object.keys(selection).length) {
    state.bankQuestions = []; state.bankQuestionTotal = 0; state.bankQuestionOffset = 0; return;
  }
  const parameters = new URLSearchParams({ limit: "50", offset: String(offset) });
  Object.entries(selection).forEach(([key, value]) => { if (value) parameters.set(key, value); });
  const response = await request(`/questions?${parameters.toString()}`);
  state.bankQuestions = response.items;
  state.bankQuestionTotal = response.total;
  state.bankQuestionOffset = response.offset;
}

function selectionButton(label, filters, count, className = "") {
  return `<button class="taxonomy-node ${className}" data-action="bank-select" data-exam="${esc(filters.exam || "")}" data-subject="${esc(filters.subject || "")}" data-chapter="${esc(filters.chapter || "")}" data-topic="${esc(filters.topic || "")}" data-subtopic="${esc(filters.subtopic || "")}"><span>${esc(label)}</span><strong>${count}</strong></button>`;
}

function parentBankSelection(selection = state.bankSelection) {
  const parent = { ...selection };
  // Topics and subtopics are presented as a single leaf in the taxonomy tree,
  // so backing out of either returns to the containing chapter.
  if (parent.topic || parent.subtopic) { delete parent.topic; delete parent.subtopic; }
  else if (parent.chapter) delete parent.chapter;
  else if (parent.subject) delete parent.subject;
  else if (parent.exam) delete parent.exam;
  return parent;
}

function renderQuestionBank() {
  const selection = state.bankSelection;
  const rows = bankRows();
  const total = catalogCount(state.catalog);
  const selectedLabel = [selection.exam, selection.subject, selection.chapter, selection.topic, selection.subtopic].filter(Boolean).join(" › ") || "All classified seed questions";
  const exams = uniqueRows(rows, (row) => row.exam);
  const branches = exams.map((examRow) => {
    const exam = examRow.exam; const examRows = rows.filter((row) => row.exam === exam);
    const subjects = uniqueRows(examRows, (row) => row.subject).map((subjectRow) => {
      const subject = subjectRow.subject; const subjectRows = examRows.filter((row) => row.subject === subject);
      const chapters = uniqueRows(subjectRows, (row) => row.chapter || "Unclassified chapter").map((chapterRow) => {
        const chapter = chapterRow.chapter; const chapterRows = subjectRows.filter((row) => row.chapter === chapter);
        const topics = uniqueRows(chapterRows, (row) => `${row.topic || "Unclassified topic"}::${row.subtopic || ""}`).map((topicRow) => {
          const topic = topicRow.topic; const subtopic = topicRow.subtopic;
          const label = subtopic ? `${topic || "Unclassified topic"} › ${subtopic}` : topic || "Unclassified topic";
          return selectionButton(label, { exam, subject, chapter, topic, subtopic }, catalogCount(chapterRows.filter((row) => row.topic === topic && row.subtopic === subtopic)), "taxonomy-leaf");
        }).join("");
        return `<section class="taxonomy-chapter"><div class="taxonomy-chapter-head">${selectionButton(chapter || "Unclassified chapter", { exam, subject, chapter }, catalogCount(chapterRows))}</div><div class="taxonomy-leaves">${topics}</div></section>`;
      }).join("");
      return `<section class="taxonomy-subject"><div class="taxonomy-subject-head">${selectionButton(subject, { exam, subject }, catalogCount(subjectRows))}</div>${chapters}</section>`;
    }).join("");
    return `<section class="taxonomy-exam"><div class="taxonomy-exam-head">${selectionButton(exam, { exam }, catalogCount(examRows))}</div>${subjects}</section>`;
  }).join("");
  const typeSummary = QUESTION_TYPES.map(([type, label]) => `<span class="chip">${label}: ${catalogCount(rows.filter((row) => row.question_type === type))}</span>`).join("");
  const difficultySummary = DIFFICULTIES.map(([key, label, representative]) => `<span class="chip">${label}: ${catalogCount(rows.filter((row) => representative === 1 ? row.difficulty <= 2 : representative === 3 ? row.difficulty === 3 : row.difficulty >= 4))}</span>`).join("");
  const hasSelection = Object.keys(selection).length > 0;
  const questionCards = state.bankQuestions.map((question, index) => {
    const questionNumber = state.bankQuestionOffset + index + 1;
    const metadata = [question.question_type.replaceAll("_", " "), `Difficulty ${question.difficulty}/5`, question.verification_status.replaceAll("_", " ")].join(" · ");
    return `<button class="bank-question-card" data-action="bank-open-question" data-id="${question.id}"><span class="q-number">Question ${questionNumber}</span><p class="math-content">${renderMath(question.question_json?.stem || "")}</p><span class="status">${esc(metadata)}</span></button>`;
  }).join("");
  const questionList = hasSelection ? `<section class="card bank-question-list"><div class="toolbar"><div><strong>Questions in this selection</strong><span class="status answer-summary">${state.bankQuestionTotal} classified seed question${state.bankQuestionTotal === 1 ? "" : "s"}</span></div><span class="spacer"></span><span class="status">Showing ${state.bankQuestionTotal ? state.bankQuestionOffset + 1 : 0}-${Math.min(state.bankQuestionOffset + state.bankQuestions.length, state.bankQuestionTotal)}</span></div><div class="bank-question-grid">${questionCards || '<div class="empty"><h4>No questions match this branch</h4><p>Choose a different taxonomy branch.</p></div>'}</div>${state.bankQuestionTotal > 50 ? `<footer class="bank-pagination"><button class="btn btn-outline small" data-action="bank-page" data-offset="${Math.max(0, state.bankQuestionOffset - 50)}" ${state.bankQuestionOffset ? "" : "disabled"}>Previous</button><span class="status">Page ${Math.floor(state.bankQuestionOffset / 50) + 1} of ${Math.ceil(state.bankQuestionTotal / 50)}</span><button class="btn btn-outline small" data-action="bank-page" data-offset="${state.bankQuestionOffset + 50}" ${state.bankQuestionOffset + 50 < state.bankQuestionTotal ? "" : "disabled"}>Next</button></footer>` : ""}</section>` : "";
  const empty = `<div class="empty"><h4>No classified seed questions yet</h4><p>Upload a PDF or DOCX, or paste question text. The classifier will turn it into reviewable, taxonomy-labeled seed questions.</p><button class="btn btn-primary" data-action="ingest-questions">Ingest questions</button></div>`;
  const selectionActions = hasSelection ? `<div class="bank-selection-actions"><button class="btn btn-outline" data-action="bank-back" aria-label="Go back to the previous question bank level">← Back</button><button class="btn btn-quiet" data-action="bank-clear">Clear selection</button></div>` : "";
  layout(`<section class="content question-bank-content"><div class="page-head"><div><div class="eyebrow">QUESTION BANK</div><h3>Classified seed library</h3><p>Click a taxonomy branch to open its questions, then select any question to inspect it in full.</p></div><div class="top-actions"><button class="btn btn-outline" data-action="new-paper">Create paper</button><button class="btn btn-primary" data-action="ingest-questions">＋ Ingest questions</button></div></div>${total ? `<section class="bank-summary card card-pad"><div><span class="status">CURRENT COLLECTION</span><h4>${esc(selectedLabel)}</h4><p>${catalogCount(rows)} of ${total} seed questions · imported questions remain pending review until verified.</p></div>${selectionActions}<div class="chips bank-summary-chips">${typeSummary}${difficultySummary}</div></section><section class="taxonomy-tree card card-pad">${branches}</section>${questionList}` : `<section class="card card-pad">${empty}</section>`}</section>`, "Question bank", "Classified seed content for paper generation");
}

function bankQuestionModal(id) {
  const question = state.bankQuestions.find((item) => item.id === id);
  if (!question) return;
  const data = question.question_json || {}; const options = data.options || [];
  const subtitle = `${question.exam} · ${question.subject} · ${question.chapter || "Unclassified"}`;
  const optionList = options.length ? `<ol class="bank-question-options">${options.map((option) => `<li class="math-content">${renderMath(option)}</li>`).join("")}</ol>` : "";
  const answer = question.answer_json?.correct_answer;
  showModal(`${modalHead("Seed question", subtitle)}<div class="modal-body bank-question-detail"><div class="chips"><span class="chip">${esc(question.topic || "No topic")}</span>${question.subtopic ? `<span class="chip">${esc(question.subtopic)}</span>` : ""}<span class="chip">${esc(question.question_type.replaceAll("_", " "))}</span><span class="chip">Difficulty ${question.difficulty}/5</span></div><div class="math-content bank-question-stem">${renderMath(data.stem || "")}</div>${optionList}<div class="rule"></div><p class="status">Source: ${esc(question.source_reference || question.source || "Not stated")}</p><p class="status">Review state: ${esc(question.verification_status.replaceAll("_", " "))}</p>${answer ? `<p class="status">Recorded answer: <strong>${esc(answer)}</strong></p>` : '<p class="status">No recorded answer; verify against the original source.</p>'}</div>`);
}

function ingestionModal() {
  const job = state.ingestionJobs.find((item) => item.id === state.activeIngestionJobId);
  const inFlight = activeIngestion(job);
  const result = job ? `<div class="modal-body">${ingestionProgress(job)}${job.state === "succeeded" ? `<div class="modal-actions"><button class="btn btn-primary" type="button" data-action="close-modal">Done</button></div>` : ""}</div>` : "";
  const form = job ? "" : `<form id="ingestion-form" class="modal-body form-grid"><div class="field"><label>PDF OR DOCX SOURCE (UP TO 35 MB)</label><input name="file" type="file" accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"></div><div class="field"><label>OR PASTE QUESTION TEXT</label><textarea name="source_text" placeholder="Paste one question or a complete question set"></textarea></div><div class="field"><label>ADDITIONAL CLASSIFICATION INSTRUCTION (OPTIONAL)</label><textarea name="conversion_note" placeholder="e.g. Treat this as JEE Mathematics, Class 12; label coordinate geometry questions under Analytic Geometry."></textarea></div><p class="status">The source is treated as reference content, not as instructions. Ambiguous or missing answers are left for review rather than invented.</p><div class="modal-actions"><button class="btn btn-outline" type="button" data-action="close-modal">Cancel</button><button class="btn btn-primary" type="submit">Classify &amp; ingest</button></div></form>`;
  showModal(`${modalHead("Ingest seed questions", job ? "Track extraction, classification, and saving live." : "Upload a text-based PDF or DOCX, or paste questions. OpenRouter will transcribe and classify the source for review.")}${result || form}`);
}

async function sourceBankModal() {
  if (!state.paper) { navigate("/question-bank"); return; }
  if (!state.sourceQuestions.length) state.sourceQuestions = (await request("/questions?limit=100")).items;
  const sourceItems = state.sourceQuestions.map((question) => `<article class="source-item"><div class="chips"><span class="chip">Source Q${question.source_reference?.match(/question (\d+)/i)?.[1] || ""}</span><span class="chip">Difficulty ${question.difficulty}/5</span><span class="chip">${esc(question.primary_concept || "Definite Integrals")}</span></div><p class="math-content">${renderMath(question.question_json.stem)}</p><footer><span class="status">${question.question_json.options?.length || 0} options · answer not verified</span><button class="btn btn-primary small" data-action="add-source" data-id="${question.id}">Add to paper</button></footer></article>`).join("");
  showModal(`${modalHead("Seed question bank", "50 transcribed JEE Definite Integrals questions. Their answers have not been guessed.")}<div class="modal-body"><div class="field"><label>FILTER QUESTIONS</label><input id="source-filter" placeholder="Search a concept or question text"></div><div class="source-list" id="source-list">${sourceItems}</div></div>`);
}

function manualQuestionModal() {
  if (!state.paper) { navigate("/new-paper"); return; }
  showModal(`${modalHead("Add manual question", "Single-correct MCQ with four choices.")}<form id="manual-question-form" class="modal-body form-grid"><div class="field"><label>QUESTION STEM</label><textarea name="stem" required placeholder="Write the question stem"></textarea></div><div class="field"><label>OPTIONS</label>${[0,1,2,3].map((i) => `<div class="option-field"><span class="option-letter">${letters[i]}</span><input name="option${i}" required></div>`).join("")}</div><div class="two-col"><div class="field"><label>CORRECT ANSWER</label><input name="correct_answer" placeholder="A, B, C, or D"></div><div class="field"><label>SECTION</label><select name="section_id"><option value="">Unsectioned</option>${state.paper.sections.map((section) => `<option value="${section.id}">${esc(section.title)}</option>`).join("")}</select></div></div><div class="two-col"><div class="field"><label>DIFFICULTY</label><input type="number" name="difficulty" min="1" max="5" value="3"></div><div class="field"><label>MARKS</label><input type="number" name="marks" min="1" max="100" value="4"></div></div><div class="modal-actions"><button class="btn btn-outline" type="button" data-action="close-modal">Cancel</button><button class="btn btn-primary" type="submit">Add question</button></div></form>`);
}

async function addSourceQuestion(id) {
  const source = state.sourceQuestions.find((item) => item.id === id); if (!source) return;
  const body = { question_type: "single_correct_mcq", stem: source.question_json.stem, options: source.question_json.options, correct_answer: null, solution: null, difficulty: source.difficulty, marks: source.marks || 3, primary_concept: source.primary_concept, secondary_concepts: source.secondary_concepts || [], estimated_time_minutes: source.expected_time_minutes || 3, section_id: null };
  await request(`/papers/${state.paper.id}/questions/manual`, { method: "POST", body: JSON.stringify(body) });
  closeModal(); await refreshPapers(state.paper.id); toast("Source question added. Verify the answer before export.");
}

async function addSection() {
  if (!state.paper) return;
  const title = window.prompt("Section title", `Section ${state.paper.sections.length + 1}`); if (!title?.trim()) return;
  await request(`/papers/${state.paper.id}/sections`, { method: "POST", body: JSON.stringify({ title: title.trim() }) });
  await refreshPapers(state.paper.id); toast("Section added.");
}

async function saveQuestion(form) {
  const values = new FormData(form); const options = [0, 1, 2, 3].map((i) => values.get(`option${i}`).trim());
  const body = { stem: values.get("stem").trim(), options, correct_answer: values.get("correct_answer").trim() || null, solution: values.get("solution").trim() || null, difficulty: Number(values.get("difficulty")), marks: Number(values.get("marks")), section_id: values.get("section_id") || null };
  await request(`/papers/${state.paper.id}/questions/${values.get("question_id")}`, { method: "PUT", body: JSON.stringify(body) });
  state.questionDraft = null;
  await refreshPapers(state.paper.id); toast("Question saved.");
}

async function imageAsDataUrl(file) {
  if (!file || !file.size) return null;
  if (file.size > 750 * 1024) throw new Error("Use a logo smaller than 750 KB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The selected logo could not be read."));
    reader.readAsDataURL(file);
  });
}

async function exportPaper(format, variant = "question_paper", paperId = state.paper?.id) {
  if (!paperId) throw new Error("Choose a paper before exporting.");
  const exportTarget = state.paper?.id === paperId ? state.paper : await request(`/papers/${paperId}`);
  const response = await fetch(`${api}/papers/${paperId}/export`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ format, variant }) });
  if (!response.ok) { let message = "Export failed."; try { message = (await response.json()).detail || message; } catch { /* no JSON */ } throw new Error(message); }
  const blob = await response.blob(); const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${exportTarget.title}.${format}`; anchor.click(); URL.revokeObjectURL(url); toast(`${format.toUpperCase()} download started.`);
}

async function retryPaperGeneration(paperId) {
  const paper = await request(`/papers/${paperId}`);
  const endpoint = paper.generation_job?.state === "failed" && paper.generation_job.operation === "solutions"
    ? `/papers/${paperId}/solutions/generate`
    : `/papers/${paperId}/generate`;
  await request(endpoint, { method: "POST" });
  await refreshPapers();
  toast("Generation queued. Track it in Live activity.");
}

document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action]"); if (!target) return;
  const { action, id, format, variant } = target.dataset;
  try {
    if (action === "new-paper") navigate("/new-paper");
    if (action === "dashboard") navigate("/");
    if (action === "question-bank") navigate("/question-bank");
    if (action === "dashboard-filter") { state.dashboardFilter = target.dataset.filter || "all"; navigate("/"); renderWelcome(); }
    if (action === "close-modal") { closeModal(); if (!activeIngestion(state.ingestionJobs.find((job) => job.id === state.activeIngestionJobId))) state.activeIngestionJobId = null; }
    if (action === "open-paper") navigate(`/papers/${id}`);
    if (action === "dashboard-retry") await retryPaperGeneration(id);
    if (action === "dashboard-export") await exportPaper("pdf", "question_paper", id);
    if (action === "source-bank") navigate("/question-bank");
    if (action === "ingest-questions") ingestionModal();
    if (action === "bank-clear") { state.bankSelection = {}; await loadBankQuestions(); renderQuestionBank(); }
    if (action === "bank-back") { state.bankSelection = parentBankSelection(); await loadBankQuestions(); renderQuestionBank(); }
    if (action === "bank-select") {
      state.bankSelection = Object.fromEntries(Object.entries({
        exam: target.dataset.exam, subject: target.dataset.subject, chapter: target.dataset.chapter,
        topic: target.dataset.topic, subtopic: target.dataset.subtopic,
      }).filter(([, value]) => value));
      await loadBankQuestions(); renderQuestionBank();
    }
    if (action === "bank-page") { await loadBankQuestions(Number(target.dataset.offset) || 0); renderQuestionBank(); }
    if (action === "bank-open-question") bankQuestionModal(id);
    if (action === "add-source-bank") await sourceBankModal();
    if (action === "manual-question") manualQuestionModal();
    if (action === "add-source") await addSourceQuestion(id);
    if (action === "add-section") await addSection();
    if (action === "branding") await brandingModal();
    if (action === "show-questions") { state.paperView = "questions"; render(); }
    if (action === "show-answers") { state.paperView = "answers"; render(); }
    if (action === "select-question") { state.selectedQuestionId = id; state.questionDraft = null; render(); }
    if (action === "save-title") { const title = document.querySelector("#paper-title").value.trim(); if (title) { await request(`/papers/${state.paper.id}`, { method: "PUT", body: JSON.stringify({ title }) }); await refreshPapers(state.paper.id); toast("Paper title saved."); } }
    if (action === "toggle-lock") { await request(`/papers/${state.paper.id}/questions/${id}/lock`, { method: "PUT", body: JSON.stringify({ locked: !selectedQuestion().locked }) }); await refreshPapers(state.paper.id); toast("Question lock updated."); }
    if (action === "delete-question") { if (window.confirm("Delete this question from the paper?")) { await request(`/papers/${state.paper.id}/questions/${id}`, { method: "DELETE" }); await refreshPapers(state.paper.id); toast("Question deleted."); } }
    if (action === "generate-initial") { await request(`/papers/${state.paper.id}/generate`, { method: "POST" }); await refreshPapers(state.paper.id); toast("Generation queued. Progress is now tracked live."); }
    if (action === "generation-pause") { await request(`/papers/${state.paper.id}/generation/pause`, { method: "POST" }); await refreshPapers(state.paper.id); toast("Generation paused. Completed questions remain available to review."); }
    if (action === "generation-resume") { await request(`/papers/${state.paper.id}/generation/resume`, { method: "POST" }); await refreshPapers(state.paper.id); toast("Generation resumed."); }
    if (action === "generation-cancel") {
      if (window.confirm("Cancel this generation? Questions and solutions completed so far will be kept.")) {
        await request(`/papers/${state.paper.id}/generation/cancel`, { method: "POST" });
        await refreshPapers(state.paper.id); toast("Generation cancelled. Partial work is retained.");
      }
    }
    if (action === "generate-solutions") { await request(`/papers/${state.paper.id}/solutions/generate`, { method: "POST" }); await refreshPapers(state.paper.id); toast("Solution generation queued. Track it in the Answer key tab."); }
    if (action === "regenerate-one") { const form = document.querySelector("#question-form"); const custom_instruction = String(new FormData(form).get("custom_instruction") || "").trim() || null; await request(`/papers/${state.paper.id}/regenerate-selected`, { method: "POST", body: JSON.stringify({ question_ids: [id], custom_instruction }) }); state.questionDraft = null; await refreshPapers(state.paper.id); toast("Question regenerated."); }
    if (action === "regenerate-unlocked") { await request(`/papers/${state.paper.id}/regenerate-unlocked`, { method: "POST" }); await refreshPapers(state.paper.id); toast("Unlocked questions regenerated."); }
    if (action === "export-paper") await exportPaper(format, variant);
  } catch (error) { toast(error.message, "error"); }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  try {
    if (form.id === "new-paper-form") {
      event.preventDefault();
      state.creation.title = new FormData(form).get("title").trim();
      hydrateCreation();
      const payload = creationPayload();
      const count = payload.question_types.reduce((total, item) => total + item.count, 0);
      if (!payload.title || !count || !payload.subtopic_plans?.length) throw new Error("Set a title and at least one question in each selected subtopic.");
      for (const plan of payload.subtopic_plans) {
        const typeCount = plan.question_types.reduce((total, item) => total + item.count, 0);
        const difficultyCount = plan.difficulty_distribution.reduce((total, item) => total + item.count, 0);
        if (!typeCount || typeCount !== difficultyCount) throw new Error(`“${plan.topic} › ${plan.subtopic}” needs matching question-type and difficulty totals.`);
      }
      const paper = await request("/papers", { method: "POST", body: JSON.stringify(payload) });
      try {
        await request(`/papers/${paper.id}/generate`, { method: "POST" });
      } catch (error) {
        await refreshPapers();
        throw new Error(`Draft created, but generation failed: ${error.message}. Use Generate draft to retry.`);
      }
      state.paper = null; state.selectedQuestionId = null;
      await refreshPapers(); navigate("/"); toast(`${count}-question generation queued. Track progress on the dashboard.`);
    }
    if (form.id === "ingestion-form") {
      event.preventDefault();
      const values = new FormData(form);
      const file = values.get("file"); const sourceText = String(values.get("source_text") || "").trim();
      if ((!file || !file.size) && !sourceText) throw new Error("Upload a PDF/DOCX or paste question text.");
      const submit = form.querySelector('button[type="submit"]');
      if (submit) { submit.disabled = true; submit.textContent = "Classifying…"; }
      const result = await request("/questions/ingest", { method: "POST", body: values });
      state.activeIngestionJobId = result.job.id;
      state.ingestionJobs = [result.job, ...state.ingestionJobs.filter((job) => job.id !== result.job.id)];
      ingestionModal(); syncGenerationPolling();
    }
    if (form.id === "manual-question-form") { event.preventDefault(); const values = new FormData(form); const body = { question_type: "single_correct_mcq", stem: values.get("stem").trim(), options: [0,1,2,3].map((i) => values.get(`option${i}`).trim()), correct_answer: values.get("correct_answer").trim() || null, solution: null, difficulty: Number(values.get("difficulty")), marks: Number(values.get("marks")), primary_concept: null, secondary_concepts: [], estimated_time_minutes: null, section_id: values.get("section_id") || null }; await request(`/papers/${state.paper.id}/questions/manual`, { method: "POST", body: JSON.stringify(body) }); closeModal(); await refreshPapers(state.paper.id); toast("Manual question added."); }
    if (form.id === "question-form") { event.preventDefault(); await saveQuestion(form); }
    if (form.id === "paper-settings") {
      event.preventDefault();
      const values = new FormData(form); const previous = state.paper.branding_config || {};
      const logo_data_url = await imageAsDataUrl(values.get("logo_file")) || values.get("profile_logo_data_url") || previous.logo_data_url || null;
      const instructions = values.get("instructions").split("\n").map((line) => line.trim()).filter(Boolean);
      const branding_config = {
        institution_name: values.get("institution_name").trim(), address: values.get("address").trim(), contact: values.get("contact").trim(),
        logo_data_url, duration_minutes: Number(values.get("duration_minutes")) || null, total_marks: Number(values.get("total_marks")) || null,
        watermark_text: values.get("watermark_text").trim(), header_text: values.get("header_text").trim(), footer_text: values.get("footer_text").trim(), instructions,
      };
      const profileName = values.get("profile_name").trim();
      if (event.submitter?.value === "true" && !profileName) throw new Error("Enter a profile name before saving reusable branding.");
      await request(`/papers/${state.paper.id}`, { method: "PUT", body: JSON.stringify({ branding_config }) });
      if (event.submitter?.value === "true") {
        const profile = await request("/branding-profiles", { method: "POST", body: JSON.stringify({ name: profileName, branding_config }) });
        const index = state.brandingProfiles.findIndex((item) => item.id === profile.id);
        if (index >= 0) state.brandingProfiles[index] = profile; else state.brandingProfiles.unshift(profile);
      }
      closeModal(); await refreshPapers(state.paper.id); toast("Branding saved for future exports.");
    }
  } catch (error) { toast(error.message, "error"); }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "new-paper-title") { state.creation.title = event.target.value; return; }
  if (event.target.dataset?.planField) {
    const separator = event.target.dataset.planField.indexOf("|");
    const key = event.target.dataset.planField.slice(0, separator);
    const field = event.target.dataset.planField.slice(separator + 1);
    if (field === "sectionTitle") {
      hydrateCreation();
      if (state.creation.plans[key]) state.creation.plans[key].sectionTitle = event.target.value;
      return;
    }
  }
  if (event.target.id === "dashboard-search") {
    const input = event.target; const cursor = input.selectionStart;
    state.dashboardSearch = input.value; renderWelcome();
    const replacement = document.querySelector("#dashboard-search");
    if (replacement) { replacement.focus(); replacement.setSelectionRange(cursor, cursor); }
    return;
  }
  const questionForm = event.target.closest("#question-form");
  if (questionForm && ["stem", "correct_answer", "difficulty", "marks", "solution", "option0", "option1", "option2", "option3"].includes(event.target.name)) {
    const values = new FormData(questionForm); const questionId = String(values.get("question_id"));
    state.questionDraft = { id: questionId, values: {
      stem: String(values.get("stem") || ""), options: [0, 1, 2, 3].map((index) => String(values.get(`option${index}`) || "")),
      correct_answer: String(values.get("correct_answer") || ""), difficulty: Number(values.get("difficulty")) || selectedQuestion()?.difficulty,
      marks: Number(values.get("marks")) || 4, solution: String(values.get("solution") || ""),
    } };
    const card = document.querySelector(`[data-question-card="true"][data-id="${questionId}"]`); const preview = effectiveQuestion(selectedQuestion());
    if (card && preview) {
      card.querySelector(".q-stem").innerHTML = renderMath(preview.question_json.stem || "");
      const options = preview.question_json.options || [];
      const optionMarkup = options.map((option, index) => `<span>${letters[index]}. <span class="math-content">${renderMath(option)}</span></span>`).join("");
      const container = card.querySelector(".q-options"); if (container) container.innerHTML = optionMarkup;
      const difficulty = card.querySelector(".difficulty-chip"); if (difficulty) difficulty.textContent = `Difficulty ${preview.difficulty}/5`;
    }
    const status = questionForm.closest(".inspector")?.querySelector(".inspector-head > div");
    if (status && !status.querySelector(".status")) status.insertAdjacentHTML("beforeend", '<span class="status">Unsaved preview</span>');
    return;
  }
  if (event.target.id !== "source-filter") return;
  const query = event.target.value.toLowerCase();
  document.querySelectorAll(".source-item").forEach((item) => { item.hidden = !item.textContent.toLowerCase().includes(query); });
});

document.addEventListener("change", async (event) => {
  if (event.target.dataset.planCount) {
    const separator = event.target.dataset.planCount.indexOf("|");
    const key = event.target.dataset.planCount.slice(0, separator);
    const type = event.target.dataset.planCount.slice(separator + 1);
    hydrateCreation();
    if (state.creation.plans[key]) state.creation.plans[key].questionCounts[type] = Math.max(0, Number(event.target.value) || 0);
    renderNewPaper(); return;
  }
  if (event.target.dataset.planDifficulty) {
    const separator = event.target.dataset.planDifficulty.indexOf("|");
    const key = event.target.dataset.planDifficulty.slice(0, separator);
    const difficultyKey = event.target.dataset.planDifficulty.slice(separator + 1);
    hydrateCreation();
    if (state.creation.plans[key]) state.creation.plans[key].difficultyCounts[difficultyKey] = Math.max(0, Number(event.target.value) || 0);
    renderNewPaper(); return;
  }
  if (event.target.dataset.planField) {
    const separator = event.target.dataset.planField.indexOf("|");
    const key = event.target.dataset.planField.slice(0, separator);
    const field = event.target.dataset.planField.slice(separator + 1);
    hydrateCreation();
    if (state.creation.plans[key] && field !== "sectionTitle") state.creation.plans[key][field] = event.target.value;
    renderNewPaper(); return;
  }
  if (event.target.dataset.creationCount) {
    state.creation.questionCounts[event.target.dataset.creationCount] = Math.max(0, Number(event.target.value) || 0); renderNewPaper(); return;
  }
  if (event.target.dataset.creationDifficulty) {
    state.creation.difficultyCounts[event.target.dataset.creationDifficulty] = Math.max(0, Number(event.target.value) || 0); renderNewPaper(); return;
  }
  if (event.target.dataset.creationField) {
    const field = event.target.dataset.creationField;
    state.creation[field] = event.target.multiple ? [...event.target.selectedOptions].map((option) => option.value) : event.target.value;
    if (field === "exam" || field === "subject") { state.creation.chapters = []; state.creation.subtopicKeys = []; }
    if (field === "chapters") state.creation.subtopicKeys = [];
    hydrateCreation(); renderNewPaper(); return;
  }
  const questionForm = event.target.closest("#question-form");
  if (questionForm && event.target.name === "section_id") {
    try {
      const questionId = new FormData(questionForm).get("question_id");
      await request(`/papers/${state.paper.id}/questions/${questionId}`, { method: "PUT", body: JSON.stringify({ section_id: event.target.value || null }) });
      await refreshPapers(state.paper.id); toast("Question moved and reordered in its section.");
    } catch (error) { toast(error.message, "error"); }
    return;
  }
  if (event.target.id !== "branding-profile-select") return;
  const profile = state.brandingProfiles?.find((item) => item.id === event.target.value);
  if (!profile) return;
  const form = event.target.closest("form"); const branding = profile.branding_config || {};
  for (const key of ["institution_name", "address", "contact", "duration_minutes", "total_marks", "watermark_text", "header_text", "footer_text"]) {
    const input = form.elements.namedItem(key); if (input) input.value = branding[key] || "";
  }
  form.elements.namedItem("instructions").value = (branding.instructions || []).join("\n");
  form.elements.namedItem("profile_logo_data_url").value = branding.logo_data_url || "";
  const logo = document.querySelector("#branding-logo-preview");
  if (logo && branding.logo_data_url) { logo.outerHTML = `<img class="logo-preview" id="branding-logo-preview" src="${esc(branding.logo_data_url)}" alt="Selected academy logo">`; }
});

window.addEventListener("hashchange", () => { syncRoute(); });
refreshPapers().then(syncRoute).catch((error) => { layout(`<section class="content"><div class="card empty"><h4>Couldn’t reach the API</h4><p>${esc(error.message)} Start the FastAPI server, then refresh this page.</p></div></section>`); });
