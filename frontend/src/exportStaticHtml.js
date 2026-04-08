const PORTABLE_SNAPSHOT_STYLE = `
  :root {
    color-scheme: light;
    --bg: #f4f7fb;
    --panel: rgba(255, 255, 255, 0.92);
    --panel-strong: #ffffff;
    --border: rgba(148, 163, 184, 0.26);
    --text: #0f172a;
    --muted: #526075;
    --soft: #6b7a90;
    --accent: #0f766e;
    --accent-soft: rgba(15, 118, 110, 0.12);
    --blue: #1d4ed8;
    --blue-soft: rgba(29, 78, 216, 0.12);
    --green: #166534;
    --green-soft: rgba(22, 101, 52, 0.12);
    --amber: #b45309;
    --amber-soft: rgba(180, 83, 9, 0.12);
    --red: #b91c1c;
    --red-soft: rgba(185, 28, 28, 0.12);
    --shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
    --radius-lg: 22px;
    --radius-md: 16px;
    --radius-sm: 12px;
  }

  * {
    box-sizing: border-box;
  }

  html {
    scroll-behavior: smooth;
  }

  body {
    margin: 0;
    background:
      radial-gradient(circle at top left, rgba(14, 165, 233, 0.08), transparent 28%),
      radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 26%),
      linear-gradient(180deg, #f8fafc 0%, var(--bg) 46%, #eef3f8 100%);
    color: var(--text);
    font: 500 15px/1.55 Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }

  a {
    color: inherit;
  }

  button,
  input,
  select {
    font: inherit;
  }

  [hidden] {
    display: none !important;
  }

  .snapshot-shell {
    width: min(1280px, calc(100vw - 32px));
    margin: 0 auto;
    padding: 28px 0 56px;
  }

  .snapshot-hero {
    position: relative;
    overflow: hidden;
    padding: 28px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 28px;
    background:
      linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(241, 245, 249, 0.94) 100%);
    box-shadow: var(--shadow);
  }

  .snapshot-hero::after {
    content: "";
    position: absolute;
    inset: auto -8% -36% auto;
    width: 280px;
    height: 280px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(29, 78, 216, 0.1), rgba(29, 78, 216, 0));
    pointer-events: none;
  }

  .snapshot-kicker {
    margin: 0 0 8px;
    color: var(--accent);
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  .snapshot-hero h1 {
    margin: 0;
    font-size: clamp(2.1rem, 4vw, 3.4rem);
    line-height: 0.96;
    letter-spacing: -0.05em;
  }

  .snapshot-hero-copy {
    max-width: 860px;
    margin: 14px 0 0;
    color: var(--muted);
    font-size: 1rem;
  }

  .snapshot-meta-row,
  .snapshot-hero-actions,
  .snapshot-tab-row,
  .snapshot-mode-toggle,
  .snapshot-filter-grid,
  .snapshot-inline-row,
  .snapshot-footer-row,
  .snapshot-card-actions,
  .snapshot-card-meta,
  .snapshot-pill-list,
  .snapshot-hero-metrics,
  .snapshot-subtle-grid,
  .usecase-chip-list,
  .usecase-status-row {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    align-items: center;
  }

  .snapshot-meta-row {
    margin-top: 18px;
  }

  .snapshot-meta-pill,
  .snapshot-pill,
  .tag,
  .usecase-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    background: rgba(248, 250, 252, 0.86);
    color: var(--muted);
    font-size: 0.84rem;
    line-height: 1.2;
  }

  .snapshot-pill-strong,
  .tag-ready,
  .pill-good {
    border-color: rgba(34, 197, 94, 0.18);
    background: var(--green-soft);
    color: var(--green);
  }

  .snapshot-pill-accent,
  .tag-approval,
  .pill {
    border-color: rgba(14, 165, 233, 0.18);
    background: var(--blue-soft);
    color: var(--blue);
  }

  .snapshot-pill-warn,
  .tag-warning,
  .tag-preview,
  .pill-bad {
    border-color: rgba(245, 158, 11, 0.2);
    background: var(--amber-soft);
    color: var(--amber);
  }

  .snapshot-pill-muted,
  .tag-approval-partial,
  .pill-muted {
    border-color: rgba(148, 163, 184, 0.2);
    background: rgba(241, 245, 249, 0.92);
    color: var(--soft);
  }

  .tag-provisional {
    border-color: rgba(124, 58, 237, 0.18);
    background: rgba(124, 58, 237, 0.1);
    color: #6d28d9;
  }

  .snapshot-hero-actions {
    justify-content: space-between;
    margin-top: 18px;
  }

  .snapshot-mode-toggle {
    padding: 6px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: rgba(248, 250, 252, 0.84);
  }

  .snapshot-mode-button,
  .snapshot-tab,
  .snapshot-button,
  .snapshot-link-button {
    appearance: none;
    border: 0;
    border-radius: 999px;
    padding: 10px 14px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
    transition: background-color 120ms ease, color 120ms ease, transform 120ms ease;
    text-decoration: none;
  }

  .snapshot-mode-button:hover,
  .snapshot-tab:hover,
  .snapshot-button:hover,
  .snapshot-link-button:hover {
    transform: translateY(-1px);
  }

  .snapshot-mode-button-active,
  .snapshot-tab-active {
    background: #0f172a;
    color: #ffffff;
  }

  .snapshot-link {
    color: var(--blue);
    font-weight: 700;
    text-decoration: none;
  }

  .snapshot-link:hover {
    text-decoration: underline;
  }

  .snapshot-tab-row {
    margin-top: 18px;
    padding: 8px;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.74);
    backdrop-filter: blur(14px);
    box-shadow: 0 14px 36px rgba(15, 23, 42, 0.06);
  }

  .snapshot-hero-metrics {
    margin-top: 18px;
  }

  .snapshot-metric-card,
  .snapshot-summary-card,
  .panel {
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: var(--panel);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
    backdrop-filter: blur(12px);
  }

  .snapshot-metric-grid,
  .snapshot-summary-grid,
  .snapshot-card-grid,
  .snapshot-compare-grid,
  .method-grid,
  .methodology-usecases,
  .methodology-benchmarks,
  .static-export-market-grid {
    display: grid;
    gap: 16px;
  }

  .snapshot-metric-grid,
  .snapshot-summary-grid {
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  }

  .snapshot-card-grid {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .snapshot-compare-grid {
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }

  .snapshot-metric-card span,
  .snapshot-summary-card span,
  .snapshot-stat span,
  .detail-label,
  .panel-copy,
  .method-subtle,
  .static-export-subtle,
  .history-source-meta,
  .snapshot-detail-label {
    display: block;
    color: var(--soft);
    font-size: 0.82rem;
  }

  .snapshot-metric-card strong,
  .snapshot-summary-card strong,
  .snapshot-stat strong,
  .title {
    display: block;
    margin-top: 6px;
    font-size: 1.28rem;
    line-height: 1.08;
    letter-spacing: -0.03em;
  }

  .snapshot-panel {
    margin-top: 18px;
  }

  .snapshot-section-head,
  .section-head {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-end;
    margin-bottom: 16px;
  }

  .snapshot-section-head h2,
  .snapshot-section-head h3,
  .section-head h2,
  .section-head h3 {
    margin: 0;
    font-size: 1.2rem;
    letter-spacing: -0.03em;
  }

  .snapshot-section-head p,
  .snapshot-inline-note,
  .static-export-section-copy,
  .method-copy,
  .method-list,
  .history-note,
  .history-source-summary,
  .history-errors,
  .history-source-error,
  .snapshot-card-copy,
  .snapshot-card-line,
  .snapshot-empty-copy,
  .empty {
    margin: 0;
    color: var(--muted);
  }

  .snapshot-filter-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 12px;
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.7);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
  }

  .snapshot-filter-field {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .snapshot-filter-field label,
  .snapshot-checkbox {
    color: var(--muted);
    font-size: 0.84rem;
    font-weight: 700;
  }

  .snapshot-input,
  .snapshot-select {
    width: 100%;
    min-height: 44px;
    padding: 11px 13px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.92);
    color: var(--text);
  }

  .snapshot-input:focus,
  .snapshot-select:focus {
    outline: 2px solid rgba(29, 78, 216, 0.16);
    border-color: rgba(29, 78, 216, 0.4);
  }

  .snapshot-checkbox {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding-top: 10px;
  }

  .snapshot-button,
  .snapshot-link-button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 16px;
    border: 1px solid rgba(148, 163, 184, 0.28);
    background: rgba(255, 255, 255, 0.9);
    color: var(--text);
    font-weight: 700;
  }

  .snapshot-button-primary {
    border-color: rgba(15, 118, 110, 0.22);
    background: linear-gradient(180deg, rgba(15, 118, 110, 0.12), rgba(15, 118, 110, 0.18));
    color: var(--accent);
  }

  .snapshot-button-secondary {
    color: var(--muted);
  }

  .snapshot-button-active {
    border-color: rgba(29, 78, 216, 0.26);
    background: var(--blue-soft);
    color: var(--blue);
  }

  .snapshot-footer-row {
    justify-content: center;
    margin-top: 16px;
  }

  .snapshot-card {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 18px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.88);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  }

  .snapshot-card-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 14px;
  }

  .snapshot-card-title {
    margin: 0;
    font-size: 1.12rem;
    line-height: 1.1;
    letter-spacing: -0.03em;
  }

  .snapshot-card-subtitle {
    margin-top: 6px;
    color: var(--muted);
    font-size: 0.9rem;
  }

  .snapshot-card-meta {
    gap: 8px;
  }

  .snapshot-card-actions {
    justify-content: flex-end;
  }

  .snapshot-card-stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
  }

  .snapshot-stat {
    padding: 12px;
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, 0.16);
    background: rgba(248, 250, 252, 0.86);
  }

  .snapshot-stat strong {
    margin-top: 8px;
    font-size: 1.04rem;
  }

  .snapshot-progress {
    display: grid;
    gap: 8px;
  }

  .snapshot-progress-row {
    display: grid;
    gap: 6px;
  }

  .snapshot-progress-label {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    color: var(--muted);
    font-size: 0.82rem;
  }

  .snapshot-progress-track {
    height: 8px;
    overflow: hidden;
    border-radius: 999px;
    background: rgba(226, 232, 240, 0.9);
  }

  .snapshot-progress-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, #0f766e, #0ea5e9);
  }

  .snapshot-card-copy {
    display: grid;
    gap: 8px;
    font-size: 0.9rem;
  }

  .snapshot-family-section {
    display: grid;
    gap: 12px;
    padding-top: 12px;
    border-top: 1px solid rgba(226, 232, 240, 0.9);
  }

  .snapshot-family-section-head {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }

  .snapshot-family-variant-list {
    display: grid;
    gap: 10px;
  }

  .snapshot-family-variant {
    padding: 12px 14px;
    border: 1px solid rgba(148, 163, 184, 0.18);
    border-radius: 14px;
    background: rgba(248, 250, 252, 0.84);
  }

  .snapshot-family-variant-head,
  .snapshot-family-variant-meta {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .snapshot-family-variant-name {
    font-weight: 700;
  }

  .snapshot-family-variant-rank,
  .snapshot-family-variant-line {
    color: var(--muted);
    font-size: 0.86rem;
  }

  .snapshot-family-variant-meta {
    margin-top: 8px;
    color: var(--soft);
    font-size: 0.82rem;
  }

  .snapshot-family-variant-line {
    margin-top: 8px;
  }

  .snapshot-compare-table-wrap {
    overflow-x: auto;
    padding: 4px;
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.84);
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.04);
  }

  .snapshot-compare-table {
    width: 100%;
    border-collapse: collapse;
    min-width: 720px;
  }

  .snapshot-compare-table th,
  .snapshot-compare-table td {
    padding: 14px 12px;
    border-top: 1px solid rgba(226, 232, 240, 0.9);
    text-align: left;
    vertical-align: top;
  }

  .snapshot-compare-table thead th {
    border-top: 0;
    color: var(--soft);
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .snapshot-compare-table tbody th {
    min-width: 220px;
  }

  .snapshot-compare-win {
    background: rgba(15, 118, 110, 0.08);
    color: var(--accent);
    font-weight: 700;
  }

  .snapshot-table-meta {
    display: block;
    margin-top: 6px;
    color: var(--soft);
    font-size: 0.8rem;
  }

  .stack {
    display: grid;
    gap: 16px;
  }

  .panel-head {
    color: var(--soft);
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .method-grid,
  .methodology-usecases,
  .methodology-benchmarks,
  .static-export-market-grid {
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }

  .method-list,
  .weight-list,
  .history-sources,
  .static-export-source-list,
  .static-export-history-list,
  .usecase-notes {
    display: grid;
    gap: 10px;
  }

  .weight-row,
  .history-source-row,
  .static-export-source-row,
  .method-focus-head,
  .method-focus-title {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }

  .history-source-row,
  .static-export-source-row {
    padding-top: 10px;
    border-top: 1px solid rgba(226, 232, 240, 0.82);
  }

  .history-source-row:first-child,
  .static-export-source-row:first-child {
    border-top: 0;
    padding-top: 0;
  }

  .usecase-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 14px;
    background: rgba(15, 118, 110, 0.1);
    color: var(--accent);
    font-size: 1.1rem;
  }

  .bench-source {
    color: var(--blue);
    font-weight: 700;
    text-decoration: none;
  }

  .bench-source:hover {
    text-decoration: underline;
  }

  .snapshot-empty {
    padding: 22px;
    border-radius: var(--radius-md);
    border: 1px dashed rgba(148, 163, 184, 0.42);
    background: rgba(255, 255, 255, 0.64);
  }

  @media (max-width: 900px) {
    .snapshot-shell {
      width: min(100vw - 20px, 1280px);
      padding-top: 20px;
    }

    .snapshot-hero {
      padding: 22px;
      border-radius: 24px;
    }

    .snapshot-card-header {
      flex-direction: column;
    }
  }
`;

export function exportDashboardHtmlSnapshot(options = {}) {
  if (typeof document === "undefined" || typeof window === "undefined") {
    throw new Error("HTML export is only available in the browser.");
  }

  const exportedAt = new Date();
  const snapshot = buildSnapshotPayload(options, exportedAt);
  const methodologyMarkup = buildMethodologyAppendixMarkup({
    benchmarks: snapshot.benchmarks,
    catalogMode: snapshot.initialState.catalogMode,
    selectedUseCaseId: snapshot.selectedUseCaseId,
    useCases: snapshot.useCases,
  });
  const historyMarkup = buildHistoryAppendixMarkup({
    history: snapshot.history,
    marketSnapshots: snapshot.marketSnapshots,
    sourceRunsByLogId: snapshot.sourceRunsByLogId,
  });
  const html = buildPortableSnapshotHtml({ snapshot, methodologyMarkup, historyMarkup });
  downloadHtmlFile(
    buildSnapshotFileName({
      activeTab: snapshot.meta.activeTab,
      selectedUseCaseLabel: snapshot.selectedUseCaseLabel,
    }),
    html,
  );
}

function buildSnapshotPayload(
  {
    activeTab,
    approvedOnly = false,
    benchmarks = [],
    browserOnlyCompared = false,
    browserSort = "smart",
    catalogMode = "family",
    compareIds = [],
    exactModels = [],
    familyModels = [],
    history = [],
    inferenceLocationFilter = "All",
    marketSnapshots = [],
    providerFilter = "All",
    query = "",
    rankingEntries = [],
    recommendationFilter = "all",
    selectedUseCaseId = "",
    selectedUseCaseLabel = "",
    sourceRunsByLogId = {},
    typeFilter = "All",
    useCases = [],
  } = {},
  exportedAt = new Date(),
) {
  const normalizedActiveTab = normalizePortableTab(activeTab);
  return {
    version: 2,
    exportedAt: exportedAt.toISOString(),
    selectedUseCaseId: String(selectedUseCaseId || ""),
    selectedUseCaseLabel: String(selectedUseCaseLabel || ""),
    benchmarks,
    exactModels,
    familyModels,
    history,
    marketSnapshots,
    rankingRows: serializeRankingRows(rankingEntries),
    sourceRunsByLogId,
    useCases,
    initialState: {
      activeTab: normalizedActiveTab,
      approvedOnly: Boolean(approvedOnly),
      browserOnlyCompared: Boolean(browserOnlyCompared),
      browserSort: String(browserSort || "smart"),
      catalogMode: catalogMode === "exact" ? "exact" : "family",
      compareIds: Array.isArray(compareIds) ? compareIds : [],
      inferenceLocationFilter: String(inferenceLocationFilter || "All"),
      providerFilter: String(providerFilter || "All"),
      query: String(query || ""),
      recommendationFilter: String(recommendationFilter || "all"),
      typeFilter: String(typeFilter || "All"),
    },
    meta: {
      activeTab: normalizedActiveTab,
      sourceUrl: window.location.href,
      title: buildExportTitle({
        activeTab: normalizedActiveTab,
        selectedUseCaseLabel,
      }),
    },
  };
}

function serializeRankingRows(entries) {
  return (Array.isArray(entries) ? entries : [])
    .map((entry) => {
      const modelId = entry?.model?.id;
      if (!modelId) {
        return null;
      }
      return {
        coverage: Number(entry.coverage ?? 0),
        model_id: modelId,
        rank: Number(entry.rank ?? 0),
        rationale: entry.rationale || "",
        score: Number(entry.score ?? 0),
        via_model_name: entry.via_model_name || "",
      };
    })
    .filter(Boolean);
}

function buildPortableSnapshotHtml({ snapshot, methodologyMarkup, historyMarkup }) {
  const title = snapshot.meta?.title || "LLM Intelligence Dashboard - Portable snapshot";
  const serializedSnapshot = serializeForScript(snapshot);
  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="generator" content="LLM Intelligence Dashboard portable snapshot" />
    <title>${escapeHtml(title)}</title>
    <style>${PORTABLE_SNAPSHOT_STYLE}</style>
  </head>
  <body>
    ${buildPortableShellMarkup({ snapshot, methodologyMarkup, historyMarkup })}
    <script id="snapshot-data" type="application/json">${serializedSnapshot}</script>
    <script>(${portableSnapshotRuntime.toString()})();</script>
  </body>
</html>`;
}

function buildPortableShellMarkup({ snapshot, methodologyMarkup, historyMarkup }) {
  const selectedLensLabel = snapshot.selectedUseCaseLabel || "No ranking lens selected";
  const sourceLinkMarkup = snapshot.meta?.sourceUrl
    ? `<a class="snapshot-link" href="${escapeAttribute(snapshot.meta.sourceUrl)}" rel="noreferrer" target="_blank">Open source app</a>`
    : "";

  return `
    <div class="snapshot-shell">
      <header class="snapshot-hero">
        <div class="snapshot-kicker">Portable snapshot</div>
        <h1>LLM Intelligence Dashboard</h1>
        <p class="snapshot-hero-copy">
          Single-file offline export with embedded data. Search, filters, sorting, and compare run locally in this document.
          Admin editing, live updates, and backend calls are intentionally removed.
        </p>
        <div class="snapshot-meta-row">
          <span class="snapshot-meta-pill">Lens: ${escapeHtml(selectedLensLabel)}</span>
          <span class="snapshot-meta-pill">Opened from: ${escapeHtml(humanizeSlug(snapshot.meta?.activeTab || "summary"))}</span>
          <span class="snapshot-meta-pill">Exported: ${escapeHtml(formatExportDate(snapshot.exportedAt))}</span>
          <span class="snapshot-meta-pill">Individual models: ${escapeHtml(snapshot.exactModels?.length ?? 0)}</span>
          <span class="snapshot-meta-pill">Families: ${escapeHtml(snapshot.familyModels?.length ?? 0)}</span>
        </div>
        <div class="snapshot-hero-actions">
          <div class="snapshot-mode-toggle" role="group" aria-label="Catalog mode">
            <button class="snapshot-mode-button" data-mode="family" type="button">Families</button>
            <button class="snapshot-mode-button" data-mode="exact" type="button">Individual models</button>
          </div>
          ${sourceLinkMarkup}
        </div>
      </header>

      <nav class="snapshot-tab-row" aria-label="Portable snapshot navigation">
        <button class="snapshot-tab" data-tab-target="summary" type="button">Summary</button>
        <button class="snapshot-tab" data-tab-target="browser" type="button">Model browser</button>
        <button class="snapshot-tab" data-tab-target="compare" type="button">Compare</button>
        <button class="snapshot-tab" data-tab-target="methodology" type="button">Methodology</button>
        <button class="snapshot-tab" data-tab-target="history" type="button">History</button>
      </nav>

      <div class="snapshot-hero-metrics" id="hero-metrics"></div>

      <main>
        <section class="snapshot-panel" data-tab-panel="summary">
          <div class="snapshot-section-head">
            <div>
              <h2>Summary</h2>
              <p class="panel-copy">A live shortlist over the embedded catalog and current browser state.</p>
            </div>
          </div>
          <div id="summary-overview"></div>
          <div id="summary-ranking"></div>
        </section>

        <section class="snapshot-panel" data-tab-panel="browser">
          <div class="snapshot-section-head">
            <div>
              <h2>Model Browser</h2>
              <p class="panel-copy">All controls below work locally against the embedded snapshot data.</p>
            </div>
          </div>
          <div class="snapshot-filter-grid">
            <div class="snapshot-filter-field">
              <label for="snapshot-query">Search</label>
              <input class="snapshot-input" id="snapshot-query" placeholder="Search name, provider, regions, family…" type="search" />
            </div>
            <div class="snapshot-filter-field">
              <label for="snapshot-provider-filter">Provider</label>
              <select class="snapshot-select" id="snapshot-provider-filter"></select>
            </div>
            <div class="snapshot-filter-field">
              <label for="snapshot-inference-filter">Inference location</label>
              <select class="snapshot-select" id="snapshot-inference-filter"></select>
            </div>
            <div class="snapshot-filter-field">
              <label for="snapshot-type-filter">Type</label>
              <select class="snapshot-select" id="snapshot-type-filter">
                <option value="All">All model types</option>
                <option value="proprietary">Proprietary</option>
                <option value="open_weights">Open weights</option>
              </select>
            </div>
            <div class="snapshot-filter-field">
              <label for="snapshot-sort-filter">Sort</label>
              <select class="snapshot-select" id="snapshot-sort-filter"></select>
            </div>
            <div class="snapshot-filter-field">
              <label for="snapshot-recommendation-filter">Recommendation</label>
              <select class="snapshot-select" id="snapshot-recommendation-filter"></select>
            </div>
            <label class="snapshot-checkbox" for="snapshot-approved-only">
              <input id="snapshot-approved-only" type="checkbox" />
              Approved only
            </label>
            <label class="snapshot-checkbox" for="snapshot-only-compared">
              <input id="snapshot-only-compared" type="checkbox" />
              Compared only
            </label>
            <div class="snapshot-filter-field">
              <label>&nbsp;</label>
              <button class="snapshot-button snapshot-button-secondary" id="snapshot-clear-filters" type="button">Clear filters</button>
            </div>
          </div>
          <div class="snapshot-inline-row" id="browser-status"></div>
          <div class="snapshot-card-grid" id="browser-results"></div>
          <div class="snapshot-footer-row">
            <button class="snapshot-button snapshot-button-secondary" id="browser-load-more" type="button">Load more</button>
          </div>
        </section>

        <section class="snapshot-panel" data-tab-panel="compare">
          <div class="snapshot-section-head">
            <div>
              <h2>Compare</h2>
              <p class="panel-copy">Use compare buttons in Summary or Model Browser to build an offline side-by-side view.</p>
            </div>
          </div>
          <div id="compare-overview"></div>
          <div id="compare-table"></div>
        </section>

        <section class="snapshot-panel" data-tab-panel="methodology">
          ${methodologyMarkup}
        </section>

        <section class="snapshot-panel" data-tab-panel="history">
          ${historyMarkup}
        </section>
      </main>
    </div>
  `;
}

function portableSnapshotRuntime() {
  const DEFAULT_INFERENCE_LOCATION_FILTER = "All";
  const DEFAULT_RECOMMENDATION_FILTER = "all";
  const BROWSER_SORT_OPTIONS = [
    { id: "smart", label: "Smart order" },
    { id: "popularity", label: "OpenRouter popularity" },
    { id: "coverage", label: "Coverage" },
    { id: "release", label: "Newest release" },
    { id: "name", label: "Name A-Z" },
  ];
  const RECOMMENDATION_FILTER_OPTIONS = [
    { id: DEFAULT_RECOMMENDATION_FILTER, label: "All recommendation states" },
    { id: "recommended", label: "Recommended" },
    { id: "not_recommended", label: "Not recommended" },
    { id: "discouraged", label: "Discouraged" },
    { id: "unrated", label: "Unrated" },
  ];

  const snapshotNode = document.getElementById("snapshot-data");
  if (!snapshotNode) {
    return;
  }

  const snapshot = JSON.parse(snapshotNode.textContent || "{}");
  const exactModels = Array.isArray(snapshot.exactModels) ? snapshot.exactModels : [];
  const familyModels = Array.isArray(snapshot.familyModels) ? snapshot.familyModels : [];
  const benchmarks = Array.isArray(snapshot.benchmarks) ? snapshot.benchmarks : [];
  const useCases = Array.isArray(snapshot.useCases) ? snapshot.useCases : [];
  const selectedUseCase = useCases.find((useCase) => useCase.id === snapshot.selectedUseCaseId) || null;
  const benchmarksById = Object.fromEntries(benchmarks.map((benchmark) => [benchmark.id, benchmark]));
  const exactModelsById = Object.fromEntries(exactModels.map((model) => [model.id, model]));
  const familyLookup = buildFamilyLookup(familyModels);
  const exactRankingById = buildRankingIndex(snapshot.rankingRows, exactModelsById);
  const familyRankingById = mapRankingRowsToFamilies(snapshot.rankingRows, familyModels, exactRankingById);

  const state = {
    activeTab: normalizePortableTab(snapshot?.initialState?.activeTab || snapshot?.meta?.activeTab),
    approvedOnly: Boolean(snapshot?.initialState?.approvedOnly),
    browserOnlyCompared: Boolean(snapshot?.initialState?.browserOnlyCompared),
    browserSort: sanitizeBrowserSort(snapshot?.initialState?.browserSort),
    catalogMode: snapshot?.initialState?.catalogMode === "exact" ? "exact" : "family",
    compareIds: Array.isArray(snapshot?.initialState?.compareIds) ? [...snapshot.initialState.compareIds] : [],
    expandedFamilyIds: [],
    inferenceLocationFilter: String(snapshot?.initialState?.inferenceLocationFilter || DEFAULT_INFERENCE_LOCATION_FILTER),
    providerFilter: String(snapshot?.initialState?.providerFilter || "All"),
    query: String(snapshot?.initialState?.query || ""),
    recommendationFilter: sanitizeRecommendationFilter(snapshot?.initialState?.recommendationFilter),
    typeFilter: sanitizeTypeFilter(snapshot?.initialState?.typeFilter),
    visibleBrowserCount: 24,
  };

  const elements = {
    browserLoadMore: document.getElementById("browser-load-more"),
    browserOnlyCompared: document.getElementById("snapshot-only-compared"),
    browserResults: document.getElementById("browser-results"),
    browserStatus: document.getElementById("browser-status"),
    clearFilters: document.getElementById("snapshot-clear-filters"),
    compareOverview: document.getElementById("compare-overview"),
    compareTable: document.getElementById("compare-table"),
    heroMetrics: document.getElementById("hero-metrics"),
    inferenceFilter: document.getElementById("snapshot-inference-filter"),
    modeButtons: Array.from(document.querySelectorAll("[data-mode]")),
    panelNodes: Array.from(document.querySelectorAll("[data-tab-panel]")),
    providerFilter: document.getElementById("snapshot-provider-filter"),
    queryInput: document.getElementById("snapshot-query"),
    recommendationFilter: document.getElementById("snapshot-recommendation-filter"),
    sortFilter: document.getElementById("snapshot-sort-filter"),
    summaryOverview: document.getElementById("summary-overview"),
    summaryRanking: document.getElementById("summary-ranking"),
    tabButtons: Array.from(document.querySelectorAll("[data-tab-target]")),
    typeFilter: document.getElementById("snapshot-type-filter"),
    approvedOnly: document.getElementById("snapshot-approved-only"),
  };

  bindEvents();
  render();

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const tabButton = event.target.closest("[data-tab-target]");
      if (tabButton) {
        state.activeTab = normalizePortableTab(tabButton.dataset.tabTarget);
        render();
        return;
      }

      const modeButton = event.target.closest("[data-mode]");
      if (modeButton) {
        setCatalogMode(modeButton.dataset.mode);
        return;
      }

      const compareButton = event.target.closest("[data-compare-toggle]");
      if (compareButton) {
        toggleCompare(compareButton.dataset.compareToggle);
        return;
      }

      const familyToggleButton = event.target.closest("[data-family-toggle]");
      if (familyToggleButton) {
        toggleFamilyVariants(familyToggleButton.dataset.familyToggle);
        return;
      }

      const jumpButton = event.target.closest("[data-jump-tab]");
      if (jumpButton) {
        state.activeTab = normalizePortableTab(jumpButton.dataset.jumpTab);
        render();
      }
    });

    elements.queryInput?.addEventListener("input", () => {
      state.query = elements.queryInput.value;
      state.visibleBrowserCount = 24;
      render();
    });

    elements.providerFilter?.addEventListener("change", () => {
      state.providerFilter = elements.providerFilter.value;
      state.visibleBrowserCount = 24;
      render();
    });

    elements.inferenceFilter?.addEventListener("change", () => {
      state.inferenceLocationFilter = elements.inferenceFilter.value;
      state.visibleBrowserCount = 24;
      render();
    });

    elements.typeFilter?.addEventListener("change", () => {
      state.typeFilter = sanitizeTypeFilter(elements.typeFilter.value);
      state.visibleBrowserCount = 24;
      render();
    });

    elements.sortFilter?.addEventListener("change", () => {
      state.browserSort = sanitizeBrowserSort(elements.sortFilter.value);
      state.visibleBrowserCount = 24;
      render();
    });

    elements.recommendationFilter?.addEventListener("change", () => {
      state.recommendationFilter = sanitizeRecommendationFilter(elements.recommendationFilter.value);
      state.visibleBrowserCount = 24;
      render();
    });

    elements.approvedOnly?.addEventListener("change", () => {
      state.approvedOnly = Boolean(elements.approvedOnly.checked);
      state.visibleBrowserCount = 24;
      render();
    });

    elements.browserOnlyCompared?.addEventListener("change", () => {
      state.browserOnlyCompared = Boolean(elements.browserOnlyCompared.checked);
      state.visibleBrowserCount = 24;
      render();
    });

    elements.clearFilters?.addEventListener("click", () => {
      state.query = "";
      state.providerFilter = "All";
      state.inferenceLocationFilter = DEFAULT_INFERENCE_LOCATION_FILTER;
      state.typeFilter = "All";
      state.browserSort = "smart";
      state.recommendationFilter = DEFAULT_RECOMMENDATION_FILTER;
      state.approvedOnly = false;
      state.browserOnlyCompared = false;
      state.visibleBrowserCount = 24;
      render();
    });

    elements.browserLoadMore?.addEventListener("click", () => {
      state.visibleBrowserCount += 24;
      renderBrowserResults();
    });
  }

  function render() {
    sanitizeState();
    renderTabs();
    renderModeButtons();
    renderHeroMetrics();
    renderSummary();
    renderBrowserControls();
    renderBrowserResults();
    renderCompare();
  }

  function sanitizeState() {
    const models = getCatalogModels();
    const modelIds = new Set(models.map((model) => model.id));
    state.compareIds = state.compareIds.filter((id) => modelIds.has(id));
    const familyModelIds = new Set(familyModels.map((model) => model.id));
    state.expandedFamilyIds = state.expandedFamilyIds.filter((id) => familyModelIds.has(id));

    const providers = getProviderOptions();
    if (!providers.includes(state.providerFilter)) {
      state.providerFilter = "All";
    }

    const inferenceLocations = getInferenceLocationOptions();
    if (!inferenceLocations.includes(state.inferenceLocationFilter)) {
      state.inferenceLocationFilter = DEFAULT_INFERENCE_LOCATION_FILTER;
    }

    state.typeFilter = sanitizeTypeFilter(state.typeFilter);
    state.browserSort = sanitizeBrowserSort(state.browserSort);
    if (!selectedUseCase) {
      state.recommendationFilter = DEFAULT_RECOMMENDATION_FILTER;
    } else {
      state.recommendationFilter = sanitizeRecommendationFilter(state.recommendationFilter);
    }
  }

  function renderTabs() {
    elements.tabButtons.forEach((button) => {
      const isActive = button.dataset.tabTarget === state.activeTab;
      button.classList.toggle("snapshot-tab-active", isActive);
    });
    elements.panelNodes.forEach((panel) => {
      panel.hidden = panel.dataset.tabPanel !== state.activeTab;
    });
  }

  function renderModeButtons() {
    elements.modeButtons.forEach((button) => {
      button.classList.toggle("snapshot-mode-button-active", button.dataset.mode === state.catalogMode);
    });
  }

  function renderHeroMetrics() {
    const models = getCatalogModels();
    const filtered = getFilteredModels();
    const rankingIndex = getRankingByCatalogId();
    const activeFilterPills = buildActiveFilterPills();
    elements.heroMetrics.innerHTML = `
      <div class="snapshot-metric-grid">
        <article class="snapshot-metric-card">
          <span>Current lens</span>
          <strong>${escapeHtml(selectedUseCase?.label || "No ranking lens")}</strong>
        </article>
        <article class="snapshot-metric-card">
          <span>${state.catalogMode === "family" ? "Families in snapshot" : "Individual models in snapshot"}</span>
          <strong>${formatInteger(models.length)}</strong>
        </article>
        <article class="snapshot-metric-card">
          <span>Filtered results</span>
          <strong>${formatInteger(filtered.length)}</strong>
        </article>
        <article class="snapshot-metric-card">
          <span>${selectedUseCase ? "Ranked rows" : "Models with OpenRouter signal"}</span>
          <strong>${formatInteger(selectedUseCase ? Object.keys(rankingIndex).length : models.filter(hasOpenRouterSignal).length)}</strong>
        </article>
        <article class="snapshot-metric-card">
          <span>Compared</span>
          <strong>${formatInteger(state.compareIds.length)}</strong>
        </article>
      </div>
      <div class="snapshot-inline-row">
        ${activeFilterPills || `<span class="snapshot-pill snapshot-pill-muted">No browser filters applied</span>`}
      </div>
    `;
  }

  function renderSummary() {
    const models = getCatalogModels();
    const filtered = getSortedModels();
    const topModels = filtered.slice(0, 8);
    const approvedCount = selectedUseCase
      ? models.filter((model) => isModelApprovedForUseCase(model, selectedUseCase.id)).length
      : models.filter((model) => model.approved_for_use).length;
    const recommendationCount = selectedUseCase
      ? models.filter((model) => matchesRecommendationFilter(model, selectedUseCase.id, "recommended")).length
      : 0;

    elements.summaryOverview.innerHTML = `
      <div class="snapshot-summary-grid">
        <article class="snapshot-summary-card">
          <span>Snapshot scope</span>
          <strong>${escapeHtml(snapshot.meta?.title || "Portable snapshot")}</strong>
          <p class="panel-copy">
            This file embeds ${formatInteger(exactModels.length)} individual models, ${formatInteger(familyModels.length)} family cards,
            ${formatInteger(benchmarks.length)} benchmarks, and ${formatInteger((snapshot.history || []).length)} update logs.
          </p>
        </article>
        <article class="snapshot-summary-card">
          <span>Current browser state</span>
          <strong>${formatInteger(filtered.length)} visible</strong>
          <p class="panel-copy">
            ${formatInteger(filtered.length)} of ${formatInteger(models.length)} ${state.catalogMode === "family" ? "families" : "individual models"} match the current search and filters.
            Sort is <strong>${escapeHtml(getSortLabel(state.browserSort))}</strong>.
          </p>
          <div class="snapshot-inline-row">
            <button class="snapshot-link-button" data-jump-tab="browser" type="button">Open browser</button>
          </div>
        </article>
        <article class="snapshot-summary-card">
          <span>${selectedUseCase ? "Governance state" : "Catalog state"}</span>
          <strong>${formatInteger(approvedCount)} approved</strong>
          <p class="panel-copy">
            ${
              selectedUseCase
                ? `${formatInteger(recommendationCount)} recommended for ${escapeHtml(selectedUseCase.label)}.`
                : "Approval and recommendation breakdowns become lens-specific when a ranking lens is selected."
            }
          </p>
        </article>
      </div>
    `;

    elements.summaryRanking.innerHTML = topModels.length
      ? `
        <div class="snapshot-section-head">
          <div>
            <h3>Current shortlist</h3>
            <p class="panel-copy">These cards reflect the same search, filter, and sort state as the browser below.</p>
          </div>
        </div>
        <div class="snapshot-card-grid">
          ${topModels.map((model) => buildModelCardMarkup(model, getRankingByCatalogId()[model.id], { compact: true })).join("")}
        </div>
      `
      : `<div class="snapshot-empty"><p class="snapshot-empty-copy">No models match the current snapshot filters.</p></div>`;
  }

  function renderBrowserControls() {
    elements.queryInput.value = state.query;
    elements.approvedOnly.checked = state.approvedOnly;
    elements.browserOnlyCompared.checked = state.browserOnlyCompared;
    populateSelect(
      elements.providerFilter,
      getProviderOptions().map((value) => ({ value, label: value === "All" ? "All providers" : value })),
      state.providerFilter,
    );
    populateSelect(
      elements.inferenceFilter,
      getInferenceLocationOptions().map((value) => ({
        value,
        label: value === DEFAULT_INFERENCE_LOCATION_FILTER ? "All locations" : value,
      })),
      state.inferenceLocationFilter,
    );
    populateSelect(
      elements.sortFilter,
      BROWSER_SORT_OPTIONS.map((option) => ({ value: option.id, label: option.label })),
      state.browserSort,
    );
    populateSelect(
      elements.recommendationFilter,
      RECOMMENDATION_FILTER_OPTIONS.map((option) => ({ value: option.id, label: option.label })),
      state.recommendationFilter,
    );
    elements.recommendationFilter.disabled = !selectedUseCase;
    elements.typeFilter.value = state.typeFilter;
  }

  function renderBrowserResults() {
    const models = getCatalogModels();
    const sorted = getSortedModels();
    const visible = sorted.slice(0, state.visibleBrowserCount);
    elements.browserStatus.innerHTML = `
      <span class="snapshot-pill snapshot-pill-muted">Showing ${formatInteger(visible.length)} of ${formatInteger(sorted.length)} results</span>
      <span class="snapshot-pill snapshot-pill-muted">Scope: ${state.catalogMode === "family" ? "Families" : "Individual models"}</span>
      ${
        selectedUseCase
          ? `<span class="snapshot-pill snapshot-pill-muted">Lens: ${escapeHtml(selectedUseCase.label)}</span>`
          : `<span class="snapshot-pill snapshot-pill-muted">No ranking lens selected</span>`
      }
      ${
        !selectedUseCase
          ? ""
          : `<span class="snapshot-pill snapshot-pill-muted">Recommendation filter works against ${escapeHtml(selectedUseCase.label)}</span>`
      }
    `;
    elements.browserResults.innerHTML = visible.length
      ? visible.map((model) => buildModelCardMarkup(model, getRankingByCatalogId()[model.id])).join("")
      : `<div class="snapshot-empty"><p class="snapshot-empty-copy">No models match the current search and filters.</p></div>`;
    const remaining = Math.max(0, sorted.length - visible.length);
    elements.browserLoadMore.hidden = remaining <= 0;
    elements.browserLoadMore.textContent = `Load ${Math.min(24, remaining)} more`;
  }

  function renderCompare() {
    const compareModels = getCatalogModels().filter((model) => state.compareIds.includes(model.id));
    const suggestions = getSortedModels()
      .filter((model) => !state.compareIds.includes(model.id))
      .slice(0, 4);

    if (!compareModels.length) {
      elements.compareOverview.innerHTML = `
        <div class="snapshot-empty">
          <p class="snapshot-empty-copy">Nothing is in the compare tray yet. Add models from Summary or Model Browser.</p>
        </div>
        ${
          suggestions.length
            ? `
              <div class="snapshot-section-head">
                <div>
                  <h3>Suggested starting points</h3>
                  <p class="panel-copy">Based on the current snapshot filters and sort.</p>
                </div>
              </div>
              <div class="snapshot-card-grid">
                ${suggestions.map((model) => buildModelCardMarkup(model, getRankingByCatalogId()[model.id], { compact: true })).join("")}
              </div>
            `
            : ""
        }
      `;
      elements.compareTable.innerHTML = "";
      return;
    }

    const orderedBenchmarks = benchmarks
      .filter((benchmark) => compareModels.some((model) => model?.scores?.[benchmark.id]?.value != null))
      .sort((left, right) => compareBenchmarkSort(left, right, selectedUseCase));

    elements.compareOverview.innerHTML = `
      <div class="snapshot-section-head">
        <div>
          <h3>Selected models</h3>
          <p class="panel-copy">${
            compareModels.length >= 2
              ? "Use this table to compare overlapping benchmark evidence and governance status."
              : "Add at least one more model to get a more useful side-by-side comparison."
          }</p>
        </div>
      </div>
      <div class="snapshot-compare-grid">
        ${compareModels.map((model) => buildModelCardMarkup(model, getRankingByCatalogId()[model.id], { compact: true })).join("")}
      </div>
    `;
    elements.compareTable.innerHTML = orderedBenchmarks.length
      ? buildCompareTableMarkup(compareModels, orderedBenchmarks)
      : `<div class="snapshot-empty"><p class="snapshot-empty-copy">These selected models do not share benchmark rows in this snapshot.</p></div>`;
  }

  function setCatalogMode(nextMode) {
    const normalizedMode = nextMode === "exact" ? "exact" : "family";
    if (normalizedMode === state.catalogMode) {
      return;
    }
    state.compareIds = remapIdsForCatalogMode(state.compareIds, state.catalogMode, normalizedMode, familyLookup);
    state.catalogMode = normalizedMode;
    state.visibleBrowserCount = 24;
    render();
  }

  function toggleCompare(modelId) {
    if (!modelId) {
      return;
    }
    state.compareIds = state.compareIds.includes(modelId)
      ? state.compareIds.filter((id) => id !== modelId)
      : [...state.compareIds, modelId];
    render();
  }

  function toggleFamilyVariants(modelId) {
    if (!modelId) {
      return;
    }
    state.expandedFamilyIds = state.expandedFamilyIds.includes(modelId)
      ? state.expandedFamilyIds.filter((id) => id !== modelId)
      : [...state.expandedFamilyIds, modelId];
    render();
  }

  function getCatalogModels() {
    return state.catalogMode === "family" ? familyModels : exactModels;
  }

  function getFamilyMemberModels(model) {
    return (model?.family?.member_ids || [])
      .map((memberId) => exactModelsById[memberId])
      .filter(Boolean);
  }

  function getRankingByCatalogId() {
    return state.catalogMode === "family" ? familyRankingById : exactRankingById;
  }

  function getFilteredModels() {
    const search = state.query.trim().toLowerCase();
    return getCatalogModels().filter((model) => {
      const matchQuery = !search || buildModelSearchText(model).includes(search);
      const matchProvider = state.providerFilter === "All" || model.provider === state.providerFilter;
      const matchInferenceLocation =
        state.inferenceLocationFilter === DEFAULT_INFERENCE_LOCATION_FILTER ||
        getModelInferenceCountries(model).includes(state.inferenceLocationFilter);
      const matchType = state.typeFilter === "All" || model.type === state.typeFilter;
      const matchApproval = !state.approvedOnly || isModelApprovedForUseCase(model, selectedUseCase?.id);
      const matchRecommendation =
        !selectedUseCase ||
        state.recommendationFilter === DEFAULT_RECOMMENDATION_FILTER ||
        matchesRecommendationFilter(model, selectedUseCase.id, state.recommendationFilter);
      const matchCompared = !state.browserOnlyCompared || state.compareIds.includes(model.id);
      return matchQuery && matchProvider && matchInferenceLocation && matchType && matchApproval && matchRecommendation && matchCompared;
    });
  }

  function getSortedModels() {
    return sortCatalogModels(getFilteredModels(), {
      rankingByCatalogId: getRankingByCatalogId(),
      selectedUseCase,
      sortKey: state.browserSort,
    });
  }

  function getProviderOptions() {
    return ["All", ...new Set(getCatalogModels().map((model) => model.provider).filter(Boolean))].sort((left, right) =>
      String(left).localeCompare(String(right)),
    );
  }

  function getInferenceLocationOptions() {
    return [
      DEFAULT_INFERENCE_LOCATION_FILTER,
      ...sortInferenceCountries(getCatalogModels().flatMap((model) => getModelInferenceCountries(model))),
    ];
  }

  function populateSelect(selectNode, options, selectedValue) {
    if (!selectNode) {
      return;
    }
    selectNode.innerHTML = options
      .map((option) => `<option value="${escapeAttribute(option.value)}">${escapeHtml(option.label)}</option>`)
      .join("");
    selectNode.value = options.some((option) => option.value === selectedValue) ? selectedValue : options[0]?.value || "";
  }

  function buildActiveFilterPills() {
    const pills = [];
    if (state.query.trim()) {
      pills.push(`Search: ${state.query.trim()}`);
    }
    if (state.providerFilter !== "All") {
      pills.push(`Provider: ${state.providerFilter}`);
    }
    if (state.inferenceLocationFilter !== DEFAULT_INFERENCE_LOCATION_FILTER) {
      pills.push(`Inference: ${state.inferenceLocationFilter}`);
    }
    if (state.typeFilter !== "All") {
      pills.push(`Type: ${state.typeFilter === "open_weights" ? "Open weights" : "Proprietary"}`);
    }
    if (state.approvedOnly) {
      pills.push("Approved only");
    }
    if (state.browserOnlyCompared) {
      pills.push("Compared only");
    }
    if (selectedUseCase && state.recommendationFilter !== DEFAULT_RECOMMENDATION_FILTER) {
      pills.push(`Recommendation: ${getRecommendationFilterLabel(state.recommendationFilter)}`);
    }
    if (state.browserSort !== "smart") {
      pills.push(`Sort: ${getSortLabel(state.browserSort)}`);
    }
    return pills.map((label) => `<span class="snapshot-pill snapshot-pill-muted">${escapeHtml(label)}</span>`).join("");
  }

  function buildModelCardMarkup(model, rankingEntry, { compact = false } = {}) {
    const approvalSummary = getApprovalSummary(model, selectedUseCase?.id);
    const recommendationSummary = getRecommendationSummary(model, selectedUseCase?.id);
    const compareActive = state.compareIds.includes(model.id);
    const coverage = getModelCoveragePercent(model);
    const ageMeta = getModelAgeMeta(model);
    const inferenceLocations = getModelInferenceCountries(model);
    const originCountries = getModelOriginCountries(model);
    const primaryOrigin = getPrimaryOriginCountry(model);
    const popularityLabel = getPreferredOpenRouterLabel(model, selectedUseCase);
    const popularityDetail = getOpenRouterPopularityDetail(model, selectedUseCase);
    const openRouterLine = popularityLabel
      ? `${popularityLabel}${popularityDetail ? ` · ${popularityDetail}` : ""}`
      : "";
    const familyMemberModels = getFamilyMemberModels(model);
    const canExpandFamily = state.catalogMode === "family" && familyMemberModels.length > 0;
    const familyExpanded = canExpandFamily && state.expandedFamilyIds.includes(model.id);

    return `
      <article class="snapshot-card">
        <div class="snapshot-card-header">
          <div>
            <h3 class="snapshot-card-title">${escapeHtml(model.name || model.id)}</h3>
            <div class="snapshot-card-subtitle">${escapeHtml(buildProviderLine(model, primaryOrigin))}</div>
          </div>
          <div class="snapshot-card-actions">
            ${
              canExpandFamily
                ? `<button class="snapshot-button snapshot-button-secondary" data-family-toggle="${escapeAttribute(model.id)}" type="button">
                    ${familyExpanded ? "Hide individual models" : `Show ${familyMemberModels.length} individual model${familyMemberModels.length === 1 ? "" : "s"}`}
                  </button>`
                : ""
            }
            <button class="snapshot-button ${compareActive ? "snapshot-button-active" : "snapshot-button-secondary"}" data-compare-toggle="${escapeAttribute(model.id)}" type="button">
              ${compareActive ? "In compare" : "Add to compare"}
            </button>
          </div>
        </div>
        <div class="snapshot-pill-list">
          ${primaryOrigin ? `<span class="snapshot-pill snapshot-pill-accent">${escapeHtml(primaryOrigin.flag)} ${escapeHtml(model.provider || "Provider")}</span>` : ""}
          <span class="snapshot-pill snapshot-pill-muted">${escapeHtml(model.type === "open_weights" ? "Open weights" : "Proprietary")}</span>
          ${canExpandFamily ? `<span class="snapshot-pill snapshot-pill-muted">${escapeHtml(`${familyMemberModels.length} individual model${familyMemberModels.length === 1 ? "" : "s"}`)}</span>` : ""}
          ${String(model.catalog_status || "") === "provisional" ? `<span class="snapshot-pill snapshot-pill-warn">OpenRouter provisional</span>` : ""}
          ${approvalSummary ? `<span class="snapshot-pill ${approvalSummary.toneClass}">${escapeHtml(approvalSummary.label)}</span>` : ""}
          ${recommendationSummary ? `<span class="snapshot-pill ${recommendationSummary.toneClass}" title="${escapeAttribute(recommendationSummary.title)}">${escapeHtml(recommendationSummary.label)}</span>` : ""}
        </div>
        <div class="snapshot-card-stats">
          <div class="snapshot-stat">
            <span>${escapeHtml(selectedUseCase ? "Lens rank" : "Popularity")}</span>
            <strong>${escapeHtml(rankingEntry?.rank ? `#${rankingEntry.rank}` : (popularityLabel || "—"))}</strong>
          </div>
          <div class="snapshot-stat">
            <span>${escapeHtml(selectedUseCase ? "Composite score" : "Coverage")}</span>
            <strong>${escapeHtml(rankingEntry ? formatNumericValue(rankingEntry.score) : `${coverage}%`)}</strong>
          </div>
          <div class="snapshot-stat">
            <span>Coverage</span>
            <strong>${escapeHtml(`${coverage}%`)}</strong>
          </div>
          <div class="snapshot-stat">
            <span>${escapeHtml(ageMeta?.source === "release" ? "Model age" : "Freshness")}</span>
            <strong>${escapeHtml(ageMeta?.label || "—")}</strong>
          </div>
        </div>
        ${
          compact
            ? ""
            : `
              <div class="snapshot-progress">
                ${rankingEntry ? buildProgressRow("Composite score", clampPercent(rankingEntry.score)) : ""}
                ${buildProgressRow("Evidence coverage", coverage)}
              </div>
            `
        }
        <div class="snapshot-card-copy">
          ${
            selectedUseCase
              ? rankingEntry
                ? `<div class="snapshot-card-line"><strong>${escapeHtml(selectedUseCase.label)}:</strong> Ranked #${escapeHtml(rankingEntry.rank)} in this snapshot.</div>`
                : `<div class="snapshot-card-line"><strong>${escapeHtml(selectedUseCase.label)}:</strong> Not currently surfaced in the ranked snapshot for this lens.</div>`
              : ""
          }
          <div class="snapshot-card-line"><strong>Inference:</strong> ${escapeHtml(inferenceLocations.join(", ") || "Not specified")}</div>
          <div class="snapshot-card-line"><strong>Origin:</strong> ${escapeHtml(originCountries.join(", ") || "Not specified")}</div>
          ${
            openRouterLine
              ? `<div class="snapshot-card-line"><strong>OpenRouter:</strong> ${escapeHtml(openRouterLine)}</div>`
              : ""
          }
        </div>
        ${familyExpanded ? buildFamilyVariantsMarkup(familyMemberModels) : ""}
      </article>
    `;
  }

  function buildFamilyVariantsMarkup(members) {
    const sortedMembers = [...members].sort(compareFamilyMemberModels);
    return `
      <div class="snapshot-family-section">
        <div class="snapshot-family-section-head">
          <div>
            <div class="detail-label">Individual models in this family</div>
            <div class="panel-copy">These are the exact model cards you get when you switch the export to Individual models.</div>
          </div>
        </div>
        <div class="snapshot-family-variant-list">
          ${sortedMembers.map((member) => buildFamilyVariantMarkup(member)).join("")}
        </div>
      </div>
    `;
  }

  function buildFamilyVariantMarkup(member) {
    const memberRanking = exactRankingById[member.id];
    const memberCoverage = getModelCoveragePercent(member);
    const memberAge = getModelAgeMeta(member);
    const memberInference = getModelInferenceCountries(member).join(", ") || "Not specified";
    const memberOpenRouterLabel = getPreferredOpenRouterLabel(member, selectedUseCase);
    const memberOpenRouterDetail = getOpenRouterPopularityDetail(member, selectedUseCase);
    const memberOpenRouterLine = memberOpenRouterLabel
      ? `${memberOpenRouterLabel}${memberOpenRouterDetail ? ` · ${memberOpenRouterDetail}` : ""}`
      : "";
    const metaBits = [
      memberRanking ? `#${memberRanking.rank}${selectedUseCase ? ` in ${selectedUseCase.label}` : ""}` : "",
      `${memberCoverage}% coverage`,
      member.context_window || "",
      memberAge?.label || "",
    ].filter(Boolean);

    return `
      <article class="snapshot-family-variant">
        <div class="snapshot-family-variant-head">
          <span class="snapshot-family-variant-name">${escapeHtml(member.name || member.id)}</span>
          <span class="snapshot-family-variant-rank">${escapeHtml(memberRanking ? `#${memberRanking.rank}` : "Unranked")}</span>
        </div>
        <div class="snapshot-family-variant-meta">
          <span>${escapeHtml(metaBits.join(" · ") || "No additional metadata")}</span>
          <span>${escapeHtml(member.type === "open_weights" ? "Open weights" : "Proprietary")}</span>
        </div>
        <div class="snapshot-family-variant-line"><strong>Inference:</strong> ${escapeHtml(memberInference)}</div>
        ${
          memberOpenRouterLine
            ? `<div class="snapshot-family-variant-line"><strong>OpenRouter:</strong> ${escapeHtml(memberOpenRouterLine)}</div>`
            : ""
        }
      </article>
    `;
  }

  function compareFamilyMemberModels(left, right) {
    const leftRanking = exactRankingById[left.id];
    const rightRanking = exactRankingById[right.id];
    if (leftRanking && rightRanking && leftRanking.rank !== rightRanking.rank) {
      return leftRanking.rank - rightRanking.rank;
    }
    if (leftRanking && !rightRanking) {
      return -1;
    }
    if (!leftRanking && rightRanking) {
      return 1;
    }
    const leftPopularityRank = getOpenRouterPopularityRank(left, selectedUseCase);
    const rightPopularityRank = getOpenRouterPopularityRank(right, selectedUseCase);
    if (leftPopularityRank !== rightPopularityRank) {
      return leftPopularityRank - rightPopularityRank;
    }
    return String(left.name || "").localeCompare(String(right.name || ""));
  }

  function buildCompareTableMarkup(models, orderedBenchmarks) {
    return `
      <div class="snapshot-section-head">
        <div>
          <h3>Benchmark table</h3>
          <p class="panel-copy">Higher or lower is better depending on the benchmark definition. Winning cells are highlighted.</p>
        </div>
      </div>
      <div class="snapshot-compare-table-wrap">
        <table class="snapshot-compare-table">
          <thead>
            <tr>
              <th>Benchmark</th>
              ${models
                .map((model) => {
                  const rankingEntry = getRankingByCatalogId()[model.id];
                  return `
                    <th>
                      ${escapeHtml(model.name)}
                      <span class="snapshot-table-meta">${
                        rankingEntry
                          ? escapeHtml(`#${rankingEntry.rank}${selectedUseCase ? ` in ${selectedUseCase.label}` : ""}`)
                          : escapeHtml("No ranking row")
                      }</span>
                    </th>
                  `;
                })
                .join("")}
            </tr>
          </thead>
          <tbody>
            ${orderedBenchmarks
              .map((benchmark) => {
                const winner = getWinningModelForBenchmark(models, benchmark);
                const weight = selectedUseCase?.weights?.[benchmark.id];
                return `
                  <tr>
                    <th>
                      ${escapeHtml(benchmark.short || benchmark.name || benchmark.id)}
                      <span class="snapshot-table-meta">
                        ${escapeHtml(benchmark.metric || benchmark.category || "Benchmark")}
                        ${weight ? ` · ${escapeHtml(`${Math.round(Number(weight) * 100)}% weight`)}` : ""}
                      </span>
                    </th>
                    ${models
                      .map((model) => {
                        const score = model?.scores?.[benchmark.id];
                        const cellClass = winner?.id === model.id ? "snapshot-compare-win" : "";
                        return `
                          <td class="${cellClass}">
                            ${score?.value != null ? escapeHtml(formatNumericValue(score.value)) : "—"}
                          </td>
                        `;
                      })
                      .join("")}
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function buildProgressRow(label, value) {
    return `
      <div class="snapshot-progress-row">
        <div class="snapshot-progress-label">
          <span>${escapeHtml(label)}</span>
          <span>${escapeHtml(`${Math.round(value)}%`)}</span>
        </div>
        <div class="snapshot-progress-track">
          <div class="snapshot-progress-fill" style="width: ${clampPercent(value)}%"></div>
        </div>
      </div>
    `;
  }

  function getWinningModelForBenchmark(models, benchmark) {
    const withScores = models.filter((model) => model?.scores?.[benchmark.id]?.value != null);
    if (withScores.length < 2) {
      return null;
    }
    return withScores.reduce((best, model) => {
      if (!best) {
        return model;
      }
      const currentValue = Number(model.scores[benchmark.id].value);
      const bestValue = Number(best.scores[benchmark.id].value);
      return benchmark.higher_is_better ? (currentValue > bestValue ? model : best) : currentValue < bestValue ? model : best;
    }, null);
  }

  function buildRankingIndex(rows, modelsById) {
    return Object.fromEntries(
      (Array.isArray(rows) ? rows : [])
        .map((row) => {
          const model = modelsById[row.model_id];
          if (!model) {
            return null;
          }
          return [row.model_id, { ...row, model }];
        })
        .filter(Boolean),
    );
  }

  function buildFamilyLookup(models) {
    const familyIdByMemberId = {};
    const representativeByFamilyId = {};
    (Array.isArray(models) ? models : []).forEach((model) => {
      representativeByFamilyId[model.id] = model.family?.representative_id || model.id;
      (model.family?.member_ids || []).forEach((memberId) => {
        familyIdByMemberId[memberId] = model.id;
      });
    });
    return { familyIdByMemberId, representativeByFamilyId };
  }

  function mapRankingRowsToFamilies(rows, models, rankingIndexByModelId) {
    return Object.fromEntries(
      (Array.isArray(models) ? models : [])
        .map((model) => {
          const familyEntries = (model.family?.member_ids || [])
            .map((memberId) => rankingIndexByModelId[memberId])
            .filter(Boolean)
            .sort((left, right) => left.rank - right.rank || right.score - left.score);
          if (!familyEntries.length) {
            return null;
          }
          const bestEntry = familyEntries[0];
          return [
            model.id,
            {
              ...bestEntry,
              model,
              via_model_name: bestEntry.model?.name || bestEntry.via_model_name || "",
            },
          ];
        })
        .filter(Boolean),
    );
  }

  function remapIdsForCatalogMode(ids, currentMode, nextMode, lookup) {
    return Array.from(
      new Set(
        (Array.isArray(ids) ? ids : [])
          .map((id) => remapIdForCatalogMode(id, currentMode, nextMode, lookup))
          .filter(Boolean),
      ),
    );
  }

  function remapIdForCatalogMode(id, currentMode, nextMode, lookup) {
    if (!id || currentMode === nextMode) {
      return id;
    }
    if (currentMode === "family" && nextMode === "exact") {
      return lookup.representativeByFamilyId[id] || id;
    }
    if (currentMode === "exact" && nextMode === "family") {
      return lookup.familyIdByMemberId[id] || id;
    }
    return id;
  }

  function buildModelSearchText(model) {
    const parts = [
      model.name,
      model.provider,
      model.provider_country_name,
      model.provider_country_code,
      model.type,
      model.release_date,
      model.context_window,
      model.family_name,
      model.canonical_model_name,
      ...(model.inference_countries || []),
    ];
    if (model.family?.member_names?.length) {
      parts.push(...model.family.member_names);
    }
    if (model.canonical?.member_names?.length) {
      parts.push(...model.canonical.member_names);
    }
    if (model.inference_destinations?.length) {
      model.inference_destinations.forEach((destination) => {
        parts.push(
          destination.name,
          destination.hyperscaler,
          destination.availability_scope,
          destination.location_scope,
          destination.pricing_label,
          ...(destination.deployment_modes || []),
          ...(destination.regions || []),
        );
      });
    }
    return parts.filter(Boolean).join(" ").toLowerCase();
  }

  function sortCatalogModels(models, { rankingByCatalogId, selectedUseCase: activeUseCase, sortKey }) {
    return [...models].sort((left, right) => {
      if (sortKey === "name") {
        return String(left.name || "").localeCompare(String(right.name || ""));
      }

      if (sortKey === "release") {
        const releaseDiff = getReleaseTimestamp(right.release_date) - getReleaseTimestamp(left.release_date);
        if (releaseDiff !== 0) {
          return releaseDiff;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
      }

      const leftCoverage = getModelCoveragePercent(left);
      const rightCoverage = getModelCoveragePercent(right);

      if (sortKey === "coverage") {
        if (leftCoverage !== rightCoverage) {
          return rightCoverage - leftCoverage;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
      }

      if (sortKey === "popularity") {
        const leftPopularityRank = getOpenRouterPopularityRank(left, activeUseCase);
        const rightPopularityRank = getOpenRouterPopularityRank(right, activeUseCase);
        if (leftPopularityRank !== rightPopularityRank) {
          return leftPopularityRank - rightPopularityRank;
        }
        const leftPopularityTokens = getOpenRouterPopularityTokens(left, activeUseCase);
        const rightPopularityTokens = getOpenRouterPopularityTokens(right, activeUseCase);
        if (leftPopularityTokens !== rightPopularityTokens) {
          return rightPopularityTokens - leftPopularityTokens;
        }
        return String(left.name || "").localeCompare(String(right.name || ""));
      }

      if (activeUseCase) {
        const leftRanking = rankingByCatalogId[left.id];
        const rightRanking = rankingByCatalogId[right.id];
        if (leftRanking && rightRanking && leftRanking.rank !== rightRanking.rank) {
          return leftRanking.rank - rightRanking.rank;
        }
        if (leftRanking && !rightRanking) {
          return -1;
        }
        if (!leftRanking && rightRanking) {
          return 1;
        }
        if (leftRanking && rightRanking && leftRanking.score !== rightRanking.score) {
          return rightRanking.score - leftRanking.score;
        }
      }

      if (leftCoverage !== rightCoverage) {
        return rightCoverage - leftCoverage;
      }

      return String(left.name || "").localeCompare(String(right.name || ""));
    });
  }

  function compareBenchmarkSort(left, right, activeUseCase) {
    const leftWeight = Number(activeUseCase?.weights?.[left.id] || 0);
    const rightWeight = Number(activeUseCase?.weights?.[right.id] || 0);
    if (leftWeight !== rightWeight) {
      return rightWeight - leftWeight;
    }
    const leftTier = Number(left.tier ?? 999);
    const rightTier = Number(right.tier ?? 999);
    if (leftTier !== rightTier) {
      return leftTier - rightTier;
    }
    return String(left.short || left.name || left.id).localeCompare(String(right.short || right.name || right.id));
  }

  function getModelApprovalRecord(model, useCaseId) {
    if (!useCaseId) {
      return null;
    }
    return model?.use_case_approvals?.[useCaseId] || null;
  }

  function normalizeRecommendationStatus(value, { allowMixed = false } = {}) {
    const normalized = String(value || "").trim().toLowerCase();
    if (["recommended", "not_recommended", "discouraged", "unrated"].includes(normalized)) {
      return normalized;
    }
    if (allowMixed && normalized === "mixed") {
      return normalized;
    }
    return "unrated";
  }

  function isModelApprovedForUseCase(model, useCaseId) {
    if (useCaseId) {
      return Boolean(getModelApprovalRecord(model, useCaseId)?.approved_for_use);
    }
    return Boolean(model?.approved_for_use);
  }

  function matchesRecommendationFilter(model, useCaseId, filterValue) {
    if (!useCaseId || filterValue === DEFAULT_RECOMMENDATION_FILTER) {
      return true;
    }

    const approval = getModelApprovalRecord(model, useCaseId);
    const recommendationStatus = normalizeRecommendationStatus(approval?.recommendation_status, { allowMixed: true });
    const recommendedCount = Number(approval?.recommended_member_count ?? (recommendationStatus === "recommended" ? 1 : 0));
    const notRecommendedCount = Number(approval?.not_recommended_member_count ?? (recommendationStatus === "not_recommended" ? 1 : 0));
    const discouragedCount = Number(approval?.discouraged_member_count ?? (recommendationStatus === "discouraged" ? 1 : 0));

    if (filterValue === "recommended") {
      return recommendedCount > 0;
    }
    if (filterValue === "not_recommended") {
      return notRecommendedCount > 0;
    }
    if (filterValue === "discouraged") {
      return discouragedCount > 0;
    }
    return recommendedCount === 0 && notRecommendedCount === 0 && discouragedCount === 0;
  }

  function getApprovalSummary(model, useCaseId) {
    if (useCaseId) {
      const approval = getModelApprovalRecord(model, useCaseId);
      const approvedCount = Number(approval?.approval_member_count ?? (approval?.approved_for_use ? 1 : 0));
      const totalCount = Number(approval?.approval_total_count ?? 1);
      if (!approvedCount) {
        return null;
      }
      if (totalCount > 1 && approvedCount < totalCount) {
        return {
          label: `${approvedCount}/${totalCount} approved`,
          toneClass: "snapshot-pill-muted",
        };
      }
      return {
        label: totalCount > 1 ? `${approvedCount}/${totalCount} approved` : "Approved",
        toneClass: "snapshot-pill-accent",
      };
    }

    const useCaseCount = Number(model?.approval_use_case_count ?? (model?.approved_for_use ? 1 : 0));
    if (!useCaseCount) {
      return null;
    }
    return {
      label: useCaseCount > 1 ? `Approved in ${useCaseCount} lenses` : "Approved",
      toneClass: "snapshot-pill-accent",
    };
  }

  function getRecommendationSummary(model, useCaseId) {
    if (!useCaseId) {
      return null;
    }
    const approval = getModelApprovalRecord(model, useCaseId);
    if (!approval) {
      return null;
    }
    const status = normalizeRecommendationStatus(approval.recommendation_status, { allowMixed: true });
    const totalCount = Math.max(1, Number(approval.approval_total_count ?? 1));
    const recommendedCount = Number(approval.recommended_member_count ?? (status === "recommended" ? 1 : 0));
    const notRecommendedCount = Number(approval.not_recommended_member_count ?? (status === "not_recommended" ? 1 : 0));
    const discouragedCount = Number(approval.discouraged_member_count ?? (status === "discouraged" ? 1 : 0));

    if (status === "mixed") {
      const details = [
        recommendedCount ? `${recommendedCount} recommended` : "",
        notRecommendedCount ? `${notRecommendedCount} not recommended` : "",
        discouragedCount ? `${discouragedCount} discouraged` : "",
      ]
        .filter(Boolean)
        .join(" · ");
      return {
        label: "Mixed recommendation",
        title: details || "Mixed recommendation",
        toneClass: "snapshot-pill-muted",
      };
    }
    if (status === "recommended") {
      return {
        label: totalCount > 1 && recommendedCount < totalCount ? `${recommendedCount}/${totalCount} recommended` : "Recommended",
        title: approval.recommendation_notes || "Recommended for this lens",
        toneClass: "snapshot-pill-strong",
      };
    }
    if (status === "not_recommended") {
      return {
        label: totalCount > 1 && notRecommendedCount < totalCount ? `${notRecommendedCount}/${totalCount} not recommended` : "Not recommended",
        title: approval.recommendation_notes || "Approved but not a default recommendation",
        toneClass: "snapshot-pill-muted",
      };
    }
    if (status === "discouraged") {
      return {
        label: totalCount > 1 && discouragedCount < totalCount ? `${discouragedCount}/${totalCount} discouraged` : "Discouraged",
        title: approval.recommendation_notes || "Discouraged for this lens",
        toneClass: "snapshot-pill-warn",
      };
    }
    return null;
  }

  function getModelCoveragePercent(model) {
    const scoreEntries = Object.values(model?.scores || {});
    const availableCount = scoreEntries.filter((score) => score?.value != null).length;
    return Math.round((availableCount / Math.max(scoreEntries.length, 1)) * 100);
  }

  function getReleaseTimestamp(value) {
    const parsed = Date.parse(String(value || ""));
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function getModelAgeMeta(model) {
    const releaseTimestamp = getPreciseReleaseTimestamp(model?.release_date);
    if (releaseTimestamp) {
      return { label: formatAgeDays(releaseTimestamp), source: "release" };
    }
    const openRouterAddedTimestamp = getTimestampOrZero(model?.openrouter_added_at);
    if (openRouterAddedTimestamp) {
      return { label: `${formatAgeDays(openRouterAddedTimestamp)} via OpenRouter`, source: "openrouter" };
    }
    return null;
  }

  function getPreciseReleaseTimestamp(value) {
    const text = String(value || "").trim();
    if (!text || !/^\d{4}-\d{2}-\d{2}(?:[T ].*)?$/.test(text)) {
      return 0;
    }
    return getTimestampOrZero(text);
  }

  function getTimestampOrZero(value) {
    const parsed = Date.parse(String(value || ""));
    return Number.isNaN(parsed) ? 0 : parsed;
  }

  function formatAgeDays(timestamp) {
    const diffMs = Date.now() - timestamp;
    if (!Number.isFinite(diffMs)) {
      return "Unknown";
    }
    const days = Math.max(0, Math.floor(diffMs / 86400000));
    return `${days}d`;
  }

  function hasOpenRouterSignal(model) {
    return Boolean(
      Number.isFinite(Number(model?.openrouter_global_rank)) ||
      Number.isFinite(Number(model?.openrouter_global_total_tokens)) ||
      Number.isFinite(Number(model?.openrouter_programming_rank)) ||
      Number.isFinite(Number(model?.openrouter_programming_total_tokens)),
    );
  }

  function getOpenRouterPopularityRank(model, activeUseCase) {
    const wantsProgramming = activeUseCase?.id === "coding";
    const programmingRank = Number(model.openrouter_programming_rank);
    const globalRank = Number(model.openrouter_global_rank);
    if (wantsProgramming && Number.isFinite(programmingRank) && programmingRank > 0) {
      return programmingRank;
    }
    if (Number.isFinite(globalRank) && globalRank > 0) {
      return globalRank;
    }
    if (Number.isFinite(programmingRank) && programmingRank > 0) {
      return programmingRank;
    }
    return Number.POSITIVE_INFINITY;
  }

  function getOpenRouterPopularityTokens(model, activeUseCase) {
    const wantsProgramming = activeUseCase?.id === "coding";
    const programmingTokens = Number(model.openrouter_programming_total_tokens);
    const globalTokens = Number(model.openrouter_global_total_tokens);
    if (wantsProgramming && Number.isFinite(programmingTokens)) {
      return programmingTokens;
    }
    if (Number.isFinite(globalTokens)) {
      return globalTokens;
    }
    if (Number.isFinite(programmingTokens)) {
      return programmingTokens;
    }
    return 0;
  }

  function getPreferredOpenRouterLabel(model, activeUseCase) {
    const programmingRank = Number(model.openrouter_programming_rank);
    if (activeUseCase?.id === "coding" && Number.isFinite(programmingRank) && programmingRank > 0) {
      return `#${programmingRank} on OpenRouter Coding`;
    }
    const globalRank = Number(model.openrouter_global_rank);
    if (Number.isFinite(globalRank) && globalRank > 0) {
      return `#${globalRank} on OpenRouter`;
    }
    if (Number.isFinite(programmingRank) && programmingRank > 0) {
      return `#${programmingRank} on OpenRouter Coding`;
    }
    return "";
  }

  function getOpenRouterPopularityDetail(model, activeUseCase) {
    if (activeUseCase?.id === "coding") {
      const programmingTokens = Number(model.openrouter_programming_total_tokens);
      if (Number.isFinite(programmingTokens) && programmingTokens > 0) {
        return `${formatTokenVolume(programmingTokens)} programming tokens`;
      }
    }
    const globalShare = Number(model.openrouter_global_share);
    const globalTokens = Number(model.openrouter_global_total_tokens);
    if (Number.isFinite(globalShare) && globalShare > 0) {
      return `${(globalShare * 100).toFixed(globalShare >= 0.1 ? 1 : 2).replace(/\.0$/, "")}% weekly share`;
    }
    if (Number.isFinite(globalTokens) && globalTokens > 0) {
      return `${formatTokenVolume(globalTokens)} weekly tokens`;
    }
    return "";
  }

  function getModelInferenceCountries(model) {
    return sortInferenceCountries(model?.inference_countries || []);
  }

  function getPrimaryOriginCountry(model) {
    const normalized = normalizeOriginCountries(model?.provider_origin_countries);
    if (normalized.length === 1) {
      return {
        code: normalized[0].code || "",
        flag: countryFlagFromCode(normalized[0].code || model?.provider_country_code || ""),
      };
    }
    if (model?.provider_country_code) {
      return {
        code: model.provider_country_code,
        flag: countryFlagFromCode(model.provider_country_code),
      };
    }
    return null;
  }

  function getModelOriginCountries(model) {
    const normalized = normalizeOriginCountries(model?.provider_origin_countries);
    if (normalized.length) {
      return normalized.map((country) => country.name).sort((left, right) => String(left).localeCompare(String(right)));
    }
    const fallback = String(model?.provider_country_name || "").trim();
    return fallback ? [fallback] : [];
  }

  function normalizeOriginCountries(countries) {
    const normalized = [];
    const seen = new Set();
    (Array.isArray(countries) ? countries : []).forEach((country) => {
      const code = String(country?.code || "").trim().toUpperCase();
      const name = String(country?.name || "").trim();
      if (!code && !name) {
        return;
      }
      const key = `${code}|${name.toLowerCase()}`;
      if (seen.has(key)) {
        return;
      }
      seen.add(key);
      normalized.push({ code: code || null, name: name || code });
    });
    return normalized;
  }

  function sortInferenceCountries(countries) {
    return Array.from(new Set((countries || []).map((country) => String(country || "").trim()).filter(Boolean))).sort(compareInferenceLocationLabels);
  }

  function compareInferenceLocationLabels(leftValue, rightValue) {
    const left = String(leftValue || "");
    const right = String(rightValue || "");
    if (left === right) {
      return 0;
    }
    const leftRank = getInferenceLocationRank(left);
    const rightRank = getInferenceLocationRank(right);
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }
    return left.localeCompare(right);
  }

  function getInferenceLocationRank(location) {
    if (!location) {
      return 3;
    }
    if (location === "Australia") {
      return 0;
    }
    if (location === "Global") {
      return 2;
    }
    return 1;
  }

  function buildProviderLine(model, primaryOrigin) {
    if (primaryOrigin?.flag) {
      return `${primaryOrigin.flag} ${model.provider || "Unknown provider"}`;
    }
    return String(model.provider || "Unknown provider");
  }

  function sanitizeBrowserSort(value) {
    return BROWSER_SORT_OPTIONS.some((option) => option.id === value) ? value : "smart";
  }

  function sanitizeRecommendationFilter(value) {
    return RECOMMENDATION_FILTER_OPTIONS.some((option) => option.id === value)
      ? value
      : DEFAULT_RECOMMENDATION_FILTER;
  }

  function sanitizeTypeFilter(value) {
    return ["All", "proprietary", "open_weights"].includes(value) ? value : "All";
  }

  function normalizePortableTab(tab) {
    if (tab === "browser" || tab === "compare" || tab === "methodology" || tab === "history") {
      return tab;
    }
    return "summary";
  }

  function getRecommendationFilterLabel(value) {
    return RECOMMENDATION_FILTER_OPTIONS.find((option) => option.id === value)?.label || "All recommendation states";
  }

  function getSortLabel(value) {
    return BROWSER_SORT_OPTIONS.find((option) => option.id === value)?.label || "Smart order";
  }

  function clampPercent(value) {
    return Math.max(0, Math.min(100, Number(value || 0)));
  }

  function formatInteger(value) {
    return Number(value || 0).toLocaleString();
  }

  function formatNumericValue(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return "—";
    }
    if (Math.abs(numeric) >= 100) {
      return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
    }
    if (Math.abs(numeric) >= 10) {
      return numeric.toLocaleString(undefined, { maximumFractionDigits: 1 });
    }
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  function formatTokenVolume(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return "—";
    }
    if (numeric >= 1_000_000_000_000) {
      return `${(numeric / 1_000_000_000_000).toFixed(2).replace(/\.00$/, "").replace(/(\.\d)0$/, "$1")}T`;
    }
    if (numeric >= 1_000_000_000) {
      return `${(numeric / 1_000_000_000).toFixed(1).replace(/\.0$/, "")}B`;
    }
    if (numeric >= 1_000_000) {
      return `${(numeric / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
    }
    if (numeric >= 1_000) {
      return `${(numeric / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
    }
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }

  function countryFlagFromCode(countryCode) {
    if (!countryCode || String(countryCode).length !== 2) {
      return "";
    }
    return String(countryCode)
      .toUpperCase()
      .split("")
      .map((char) => String.fromCodePoint(127397 + char.charCodeAt(0)))
      .join("");
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeAttribute(value) {
    return escapeHtml(value).replaceAll("`", "&#96;");
  }
}

function buildMethodologyAppendixMarkup({ benchmarks, catalogMode, selectedUseCaseId, useCases }) {
  const benchmarksById = Object.fromEntries((benchmarks || []).map((benchmark) => [benchmark.id, benchmark]));
  const orderedUseCases = [...(useCases || [])].sort((left, right) => {
    const leftSegment = String(left.segment || "core");
    const rightSegment = String(right.segment || "core");
    if (leftSegment !== rightSegment) {
      return leftSegment.localeCompare(rightSegment);
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
  const selectedUseCase = orderedUseCases.find((useCase) => useCase.id === selectedUseCaseId) || null;
  const benchmarkLibrary = [...(benchmarks || [])]
    .map((benchmark) => ({
      ...benchmark,
      usedBy: orderedUseCases.filter((useCase) => Object.prototype.hasOwnProperty.call(useCase.weights || {}, benchmark.id)),
    }))
    .sort((left, right) => {
      const leftTier = Number(left.tier || 0);
      const rightTier = Number(right.tier || 0);
      if (leftTier !== rightTier) {
        return leftTier - rightTier;
      }
      return String(left.name || "").localeCompare(String(right.name || ""));
    });

  return `
    <section class="stack" aria-label="Methodology appendix">
      <div class="section-head">
        <div>
          <h2>Methodology</h2>
          <p class="static-export-section-copy">This portable export carries its scoring logic, benchmark library, and lens definitions with it.</p>
        </div>
      </div>

      <div class="method-grid">
        <article class="panel method-card">
          <div class="panel-head">What this snapshot is doing</div>
          <div class="method-copy">
            This is a weighted decision system over benchmark evidence. It does not claim one universal best model.
            Each use case defines its own evidence mix, minimum coverage threshold, and required benchmarks.
          </div>
          <div class="method-list">
            <div><strong>Score:</strong> weighted normalized composite over the configured evidence stack.</div>
            <div><strong>Coverage:</strong> how much of the evidence stack a model actually covers.</div>
            <div><strong>Required evidence:</strong> models missing any required benchmark are excluded from that lens.</div>
            <div><strong>Portable view modes:</strong> this snapshot includes both family and exact views and opens in ${escapeHtml(
              catalogMode === "family" ? "family mode" : "exact mode",
            )}.</div>
          </div>
        </article>
        ${selectedUseCase ? buildMethodologyFocusMarkup(selectedUseCase, benchmarksById) : ""}
      </div>

      <section class="stack">
        <div class="section-head">
          <div>
            <h3>Use-case lenses</h3>
            <p class="static-export-section-copy">These are the actual scoring recipes included in this snapshot.</p>
          </div>
        </div>
        <div class="methodology-usecases">
          ${orderedUseCases.map((useCase) => buildUseCaseMethodCardMarkup(useCase, benchmarksById)).join("")}
        </div>
      </section>

      <section class="stack">
        <div class="section-head">
          <div>
            <h3>Benchmark source library</h3>
            <p class="static-export-section-copy">What each benchmark measures and where it is used.</p>
          </div>
        </div>
        <div class="methodology-benchmarks">
          ${benchmarkLibrary.map((benchmark) => buildBenchmarkLibraryCardMarkup(benchmark)).join("")}
        </div>
      </section>
    </section>
  `;
}

function buildMethodologyFocusMarkup(selectedUseCase, benchmarksById) {
  const requiredBenchmarks = (selectedUseCase.required_benchmarks || [])
    .map((benchmarkId) => buildUseCaseChipMarkup(benchmarksById[benchmarkId]?.short || benchmarkId))
    .join("");
  const weightRows = Object.entries(selectedUseCase.weights || {})
    .sort((left, right) => right[1] - left[1])
    .map(
      ([benchmarkId, weight]) => `
        <div class="weight-row">
          <span>${escapeHtml(benchmarksById[benchmarkId]?.short || benchmarkId)}</span>
          <span>${Math.round(Number(weight || 0) * 100)}%</span>
        </div>
      `,
    )
    .join("");
  const notes = Object.entries(selectedUseCase.benchmark_notes || {})
    .map(
      ([benchmarkId, note]) => `
        <div class="usecase-note-item">
          <strong>${escapeHtml(benchmarksById[benchmarkId]?.short || benchmarkId)}:</strong>
          <span>${escapeHtml(note)}</span>
        </div>
      `,
    )
    .join("");

  return `
    <article class="panel methodology-focus">
      <div class="panel-head">Current lens in this export</div>
      <div class="method-focus-head">
        <div class="method-focus-title">
          <span class="usecase-icon">${escapeHtml(selectedUseCase.icon || "•")}</span>
          <div>
            <div class="title">${escapeHtml(selectedUseCase.label || selectedUseCase.id)}</div>
            <div class="method-subtle">${escapeHtml(selectedUseCase.description || "")}</div>
          </div>
        </div>
        <div class="usecase-status-row">
          <span class="${selectedUseCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}">${escapeHtml(
            selectedUseCase.status === "preview" ? "Preview lens" : "Ready lens",
          )}</span>
          <span class="tag">${Math.round((Number(selectedUseCase.min_coverage || 0.5)) * 100)}% minimum coverage</span>
        </div>
      </div>
      <div class="method-grid">
        <div class="panel">
          <div class="detail-label">Weights</div>
          <div class="weight-list">${weightRows}</div>
        </div>
        <div class="panel">
          <div class="detail-label">Required evidence</div>
          <div class="usecase-chip-list">${requiredBenchmarks || '<span class="static-export-subtle">No hard requirements.</span>'}</div>
        </div>
      </div>
      ${notes ? `<div class="usecase-notes">${notes}</div>` : ""}
    </article>
  `;
}

function buildUseCaseMethodCardMarkup(useCase, benchmarksById) {
  const requiredBenchmarks = (useCase.required_benchmarks || [])
    .map((benchmarkId) => buildUseCaseChipMarkup(benchmarksById[benchmarkId]?.short || benchmarkId))
    .join("");
  const weights = Object.entries(useCase.weights || {})
    .sort((left, right) => right[1] - left[1])
    .map(
      ([benchmarkId, weight]) => `
        <div class="weight-row">
          <span>${escapeHtml(benchmarksById[benchmarkId]?.short || benchmarkId)}</span>
          <span>${Math.round(Number(weight || 0) * 100)}%</span>
        </div>
      `,
    )
    .join("");

  return `
    <article class="panel method-card">
      <div class="method-focus-head">
        <div class="method-focus-title">
          <span class="usecase-icon">${escapeHtml(useCase.icon || "•")}</span>
          <div>
            <div class="title">${escapeHtml(useCase.label || useCase.id)}</div>
            <div class="method-subtle">${escapeHtml(useCase.description || "")}</div>
          </div>
        </div>
        <div class="usecase-status-row">
          <span class="${useCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}">${escapeHtml(
            useCase.status === "preview" ? "Preview" : "Ready",
          )}</span>
          <span class="tag">${Math.round((Number(useCase.min_coverage || 0.5)) * 100)}% min coverage</span>
        </div>
      </div>
      <div class="usecase-chip-list">${requiredBenchmarks || '<span class="static-export-subtle">No required benchmarks.</span>'}</div>
      <div class="weight-list">${weights}</div>
    </article>
  `;
}

function buildBenchmarkLibraryCardMarkup(benchmark) {
  const usedBy = (benchmark.usedBy || []).map((useCase) => useCase.label).join(", ");
  return `
    <article class="panel method-card">
      <div class="method-focus-head">
        <div>
          <div class="title">${escapeHtml(benchmark.name || benchmark.id)}</div>
          <div class="method-subtle">${escapeHtml(benchmark.short || benchmark.id)} · ${escapeHtml(benchmark.category || "")}</div>
        </div>
        <div class="usecase-status-row">
          <span class="tag">Tier ${escapeHtml(benchmark.tier ?? "")}</span>
          <span class="tag">${escapeHtml(benchmark.higher_is_better ? "Higher is better" : "Lower is better")}</span>
        </div>
      </div>
      <div class="method-list">
        <div><strong>Metric:</strong> ${escapeHtml(benchmark.metric || "")}</div>
        <div><strong>Source:</strong> ${escapeHtml(benchmark.source || "")}</div>
        ${benchmark.description ? `<div><strong>What it measures:</strong> ${escapeHtml(benchmark.description)}</div>` : ""}
        <div><strong>Used in:</strong> ${escapeHtml(usedBy || "Not currently used in a ranking lens.")}</div>
      </div>
      ${benchmark.url ? `<a class="bench-source" href="${escapeAttribute(benchmark.url)}" target="_blank" rel="noreferrer">Open source leaderboard</a>` : ""}
    </article>
  `;
}

function buildHistoryAppendixMarkup({ history, marketSnapshots, sourceRunsByLogId }) {
  const sortedHistory = [...(history || [])].sort((left, right) =>
    String(right.started_at || "").localeCompare(String(left.started_at || "")),
  );
  const marketSections = buildMarketSnapshotSectionsMarkup(marketSnapshots);

  return `
    <section class="stack" aria-label="History appendix">
      <div class="section-head">
        <div>
          <h2>History</h2>
          <p class="static-export-section-copy">Update provenance and recent market snapshots remain embedded in this portable export.</p>
        </div>
      </div>

      ${marketSections}

      <div class="static-export-history-list">
        ${sortedHistory.length
          ? sortedHistory.map((entry) => buildHistoryEntryMarkup(entry, sourceRunsByLogId)).join("")
          : '<div class="snapshot-empty"><p class="snapshot-empty-copy">No update logs yet.</p></div>'}
      </div>
    </section>
  `;
}

function buildMarketSnapshotSectionsMarkup(marketSnapshots) {
  const sections = [
    { id: "global", label: "Global weekly rankings", rows: (marketSnapshots || []).filter((row) => row.scope === "global") },
    {
      id: "programming",
      label: "Programming usage",
      rows: (marketSnapshots || []).filter((row) => row.scope === "category" && row.category_slug === "programming"),
    },
  ]
    .map((section) => {
      const latestDate = [...new Set(section.rows.map((row) => row.snapshot_date))].sort((left, right) => String(right).localeCompare(String(left)))[0];
      const latestRows = section.rows
        .filter((row) => row.snapshot_date === latestDate)
        .sort((left, right) => Number(left.rank || 0) - Number(right.rank || 0))
        .slice(0, 5);
      return { ...section, latestDate, latestRows };
    })
    .filter((section) => section.latestRows.length);

  if (!sections.length) {
    return "";
  }

  return `
    <div class="static-export-market-grid">
      ${sections
        .map(
          (section) => `
            <article class="panel method-card">
              <div class="panel-head">${escapeHtml(section.label)}</div>
              <div class="static-export-subtle">${escapeHtml(formatExportDate(section.latestDate))}</div>
              <div class="static-export-source-list">
                ${section.latestRows
                  .map(
                    (row) => `
                      <div class="static-export-source-row">
                        <div>
                          <div class="history-source-name">${escapeHtml(row.model_name || row.model_id)}</div>
                          <div class="static-export-subtle">${escapeHtml(row.provider || "Unknown provider")}</div>
                        </div>
                        <div class="static-export-subtle">#${escapeHtml(row.rank ?? "—")}</div>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function buildHistoryEntryMarkup(entry, sourceRunsByLogId) {
  const sourceRuns = sourceRunsByLogId?.[entry.id] || sourceRunsByLogId?.[String(entry.id)] || entry.source_runs || [];
  const failedSources = sourceRuns.filter((sourceRun) => sourceRun.status === "failed").length;
  const totalRawRecords = sourceRuns.reduce((sum, sourceRun) => sum + Number(sourceRun.records_found || 0), 0);

  return `
    <article class="panel history-entry">
      <div class="history-date">${escapeHtml(formatExportDate(entry.started_at))}</div>
      <div class="history-note">
        Status: ${escapeHtml(entry.status || "unknown")} · ${escapeHtml(entry.scores_added ?? 0)} scores added · ${escapeHtml(entry.scores_updated ?? 0)} scores updated
      </div>
      <div class="history-source-summary">
        ${escapeHtml(sourceRuns.length)} source runs · ${escapeHtml(failedSources)} failed · ${escapeHtml(totalRawRecords)} raw records
      </div>
      ${Array.isArray(entry.errors) && entry.errors.length
        ? `<div class="history-errors">${escapeHtml(entry.errors.map((error) => error.error_message || "Unknown error").join("; "))}</div>`
        : ""}
      ${
        sourceRuns.length
          ? `<div class="history-sources">
              ${sourceRuns
                .map(
                  (sourceRun) => `
                    <div class="panel">
                      <div class="history-source-row">
                        <div>
                          <div class="history-source-name">${escapeHtml(sourceRun.source_name || "unknown_source")}</div>
                          <div class="history-source-meta">${escapeHtml(sourceRun.benchmark_id || "n/a")} · ${escapeHtml(sourceRun.records_found ?? 0)} raw records</div>
                        </div>
                        <div class="history-source-status">
                          <span class="${
                            sourceRun.status === "completed"
                              ? "tag tag-ready"
                              : sourceRun.status === "failed"
                                ? "tag tag-warning"
                                : "tag"
                          }">${escapeHtml(sourceRun.status || "pending")}</span>
                        </div>
                      </div>
                      ${sourceRun.error_message ? `<div class="history-source-error">${escapeHtml(sourceRun.error_message)}</div>` : ""}
                    </div>
                  `,
                )
                .join("")}
            </div>`
          : ""
      }
    </article>
  `;
}

function buildUseCaseChipMarkup(label) {
  return `<span class="usecase-chip">${escapeHtml(label)}</span>`;
}

function normalizePortableTab(activeTab) {
  if (activeTab === "browser" || activeTab === "compare" || activeTab === "methodology" || activeTab === "history") {
    return activeTab;
  }
  return "summary";
}

function buildExportTitle({ activeTab, selectedUseCaseLabel }) {
  const viewLabel = buildViewLabel({ activeTab, selectedUseCaseLabel });
  return `LLM Intelligence Dashboard - ${viewLabel} portable snapshot`;
}

function buildViewLabel({ activeTab, selectedUseCaseLabel }) {
  const tabLabel = activeTab ? `${humanizeSlug(activeTab)} view` : "Dashboard view";
  if (selectedUseCaseLabel) {
    return `${tabLabel} · ${selectedUseCaseLabel}`;
  }
  return tabLabel;
}

function buildSnapshotFileName({ activeTab, selectedUseCaseLabel }) {
  const parts = ["llm-dashboard", "portable"];
  if (activeTab) {
    parts.push(slugify(activeTab));
  }
  if (selectedUseCaseLabel) {
    parts.push(slugify(selectedUseCaseLabel));
  }
  parts.push(new Date().toISOString().slice(0, 10));
  return `${parts.filter(Boolean).join("-")}.html`;
}

function downloadHtmlFile(fileName, html) {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function serializeForScript(value) {
  return JSON.stringify(value)
    .replaceAll("<", "\\u003c")
    .replaceAll(">", "\\u003e")
    .replaceAll("&", "\\u0026")
    .replaceAll("\u2028", "\\u2028")
    .replaceAll("\u2029", "\\u2029");
}

function humanizeSlug(value) {
  return String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase())
    .trim() || "Dashboard";
}

function slugify(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

function formatExportDate(value) {
  if (!value) {
    return "Unknown";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return String(value);
  }
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
