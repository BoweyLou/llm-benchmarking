const EXPORT_NOTE_STYLE = `
  .static-export-page .skip-link {
    display: none !important;
  }
  .static-export-banner {
    max-width: 1160px;
    margin: 16px auto 0;
    padding: 12px 20px;
    border: 1px solid rgba(59, 130, 246, 0.18);
    border-radius: 16px;
    background: rgba(239, 246, 255, 0.94);
    color: #1e3a8a;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    font: 500 0.88rem/1.4 Inter, system-ui, sans-serif;
  }
  .static-export-banner strong {
    font-weight: 700;
  }
  .static-export-banner a {
    color: inherit;
  }
  .static-export-page button,
  .static-export-page input,
  .static-export-page select,
  .static-export-page textarea,
  .static-export-page [data-static-export-link="true"] {
    pointer-events: none !important;
    cursor: default !important;
  }
  .static-export-appendix {
    margin-top: 28px;
    padding-top: 8px;
    border-top: 1px solid rgba(148, 163, 184, 0.18);
  }
  .static-export-section-copy {
    color: #475569;
    line-height: 1.55;
  }
  .static-export-market-grid,
  .static-export-source-list,
  .static-export-history-list {
    display: grid;
    gap: 12px;
  }
  .static-export-market-grid {
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  }
  .static-export-source-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
    padding: 10px 0;
    border-top: 1px solid rgba(226, 232, 240, 0.8);
  }
  .static-export-source-row:first-child {
    border-top: 0;
    padding-top: 0;
  }
  .static-export-subtle {
    font-size: 0.8rem;
    color: #64748b;
  }
`;

export function exportDashboardHtmlSnapshot({
  activeTab,
  benchmarks = [],
  catalogMode = "family",
  history = [],
  marketSnapshots = [],
  selectedUseCaseId = "",
  selectedUseCaseLabel = "",
  sourceRunsByLogId = {},
  useCases = [],
} = {}) {
  if (typeof document === "undefined" || typeof window === "undefined") {
    throw new Error("HTML export is only available in the browser.");
  }

  const snapshotRoot = document.documentElement.cloneNode(true);
  const head = snapshotRoot.querySelector("head");
  const body = snapshotRoot.querySelector("body");

  snapshotRoot.querySelectorAll("script").forEach((node) => node.remove());
  snapshotRoot.querySelectorAll('link[rel="modulepreload"]').forEach((node) => node.remove());

  if (body) {
    body.classList.add("static-export-page");
    body.insertAdjacentHTML(
      "afterbegin",
      buildExportBannerMarkup({
        activeTab,
        selectedUseCaseLabel,
        exportedAt: new Date(),
        sourceUrl: window.location.href,
      }),
    );
  }

  if (head) {
    upsertTitle(head, buildExportTitle({ activeTab, selectedUseCaseLabel }));
    head.insertAdjacentHTML("beforeend", '<meta name="generator" content="LLM Intelligence Dashboard HTML export" />');
    head.insertAdjacentHTML("beforeend", `<style data-static-export="true">${EXPORT_NOTE_STYLE}</style>`);
  }

  const main = snapshotRoot.querySelector("#main-content") || body;
  if (main) {
    const supplementalSectionsMarkup = buildSupplementalSectionsMarkup({
      activeTab,
      benchmarks,
      catalogMode,
      history,
      marketSnapshots,
      selectedUseCaseId,
      sourceRunsByLogId,
      useCases,
    });
    if (supplementalSectionsMarkup) {
      main.insertAdjacentHTML("beforeend", supplementalSectionsMarkup);
    }
  }

  neutralizeInternalLinks(snapshotRoot);

  const html = `<!DOCTYPE html>\n${snapshotRoot.outerHTML}`;
  downloadHtmlFile(buildSnapshotFileName({ activeTab, selectedUseCaseLabel }), html);
}

function buildSupplementalSectionsMarkup({
  activeTab,
  benchmarks,
  catalogMode,
  history,
  marketSnapshots,
  selectedUseCaseId,
  sourceRunsByLogId,
  useCases,
}) {
  const sections = [];
  if (activeTab !== "methodology") {
    sections.push(
      buildMethodologyAppendixMarkup({
        benchmarks,
        catalogMode,
        selectedUseCaseId,
        useCases,
      }),
    );
  }
  if (activeTab !== "history") {
    sections.push(
      buildHistoryAppendixMarkup({
        history,
        marketSnapshots,
        sourceRunsByLogId,
      }),
    );
  }
  return sections.filter(Boolean).join("");
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
    <section class="stack static-export-appendix" aria-label="Methodology appendix">
      <div class="section-head">
        <div>
          <h2>Methodology</h2>
          <p class="static-export-section-copy">Included in this static export so the ranking logic travels with the snapshot.</p>
        </div>
      </div>

      <div class="method-grid">
        <article class="panel method-card">
          <div class="panel-head">What this app is doing</div>
          <div class="method-copy">
            This is a weighted decision system over benchmark evidence. It does not claim one universal best model.
            Each use case defines its own evidence mix, minimum coverage threshold, and required benchmarks.
          </div>
          <div class="method-list">
            <div><strong>Score:</strong> weighted normalized composite over the configured evidence stack.</div>
            <div><strong>Coverage:</strong> how much of the evidence stack a model actually covers.</div>
            <div><strong>Required evidence:</strong> models missing any required benchmark are excluded from that lens.</div>
            <div><strong>${escapeHtml(catalogMode === "family" ? "Families mode" : "Exact variants mode")}:</strong> ${escapeHtml(
              catalogMode === "family"
                ? "cards are aggregated at family/canonical level to support shortlist decisions."
                : "cards show exact variants with no family aggregation.",
            )}</div>
          </div>
        </article>
        ${selectedUseCase ? buildMethodologyFocusMarkup(selectedUseCase, benchmarksById) : ""}
      </div>

      <section class="stack">
        <div class="section-head">
          <div>
            <h3>Use-case lenses</h3>
            <p class="static-export-section-copy">These are the actual scoring recipes used in the app.</p>
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
        <div class="method-card method-card-soft">
          <div class="detail-label">Weights</div>
          <div class="weight-list">${weightRows}</div>
        </div>
        <div class="method-card method-card-soft">
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
    <section class="stack static-export-appendix" aria-label="History appendix">
      <div class="section-head">
        <div>
          <h2>History</h2>
          <p class="static-export-section-copy">Included in this export so update provenance and recent market snapshots are preserved.</p>
        </div>
      </div>

      ${marketSections}

      <div class="history-list static-export-history-list">
        ${sortedHistory.length
          ? sortedHistory.map((entry) => buildHistoryEntryMarkup(entry, sourceRunsByLogId)).join("")
          : '<div class="empty">No update logs yet.</div>'}
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
    <article class="history-item history-entry">
      <div class="panel">
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
                      <div class="history-source-card">
                        <div class="static-export-source-row">
                          <div>
                            <div class="history-source-name">${escapeHtml(sourceRun.source_name || "unknown_source")}</div>
                            <div class="history-source-meta">${escapeHtml(sourceRun.benchmark_id || "n/a")} · ${escapeHtml(sourceRun.records_found ?? 0)} raw records</div>
                          </div>
                          <div class="history-source-status">
                            <span class="${
                              sourceRun.status === "completed"
                                ? "pill pill-good"
                                : sourceRun.status === "failed"
                                  ? "pill pill-bad"
                                  : "pill pill-muted"
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
      </div>
    </article>
  `;
}

function buildUseCaseChipMarkup(label) {
  return `<span class="usecase-chip usecase-chip-required">${escapeHtml(label)}</span>`;
}

function buildExportBannerMarkup({ activeTab, selectedUseCaseLabel, exportedAt, sourceUrl }) {
  const viewLabel = buildViewLabel({ activeTab, selectedUseCaseLabel });
  const exportedLabel = exportedAt.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

  return `
    <div class="static-export-banner" role="note">
      <div><strong>Static snapshot.</strong> ${escapeHtml(viewLabel)} exported ${escapeHtml(exportedLabel)}.</div>
      <div>Interactive controls are frozen in this copy. Source: <a href="${escapeAttribute(sourceUrl)}">${escapeHtml(sourceUrl)}</a></div>
    </div>
  `;
}

function buildExportTitle({ activeTab, selectedUseCaseLabel }) {
  return `LLM Intelligence Dashboard - ${buildViewLabel({ activeTab, selectedUseCaseLabel })}`;
}

function buildViewLabel({ activeTab, selectedUseCaseLabel }) {
  const tabLabel = activeTab ? `${humanizeSlug(activeTab)} view` : "Dashboard view";
  if (selectedUseCaseLabel) {
    return `${tabLabel} · ${selectedUseCaseLabel}`;
  }
  return tabLabel;
}

function buildSnapshotFileName({ activeTab, selectedUseCaseLabel }) {
  const parts = ["llm-dashboard"];
  if (activeTab) {
    parts.push(slugify(activeTab));
  }
  if (selectedUseCaseLabel) {
    parts.push(slugify(selectedUseCaseLabel));
  }
  parts.push(new Date().toISOString().slice(0, 10));
  return `${parts.filter(Boolean).join("-")}.html`;
}

function upsertTitle(head, title) {
  const existing = head.querySelector("title");
  if (existing) {
    existing.textContent = title;
    return;
  }
  head.insertAdjacentHTML("beforeend", `<title>${escapeHtml(title)}</title>`);
}

function neutralizeInternalLinks(root) {
  root.querySelectorAll("a[href]").forEach((anchor) => {
    const rawHref = anchor.getAttribute("href");
    if (!rawHref) {
      return;
    }

    if (/^(https?:|mailto:|tel:)/i.test(rawHref)) {
      return;
    }

    try {
      const target = new URL(rawHref, window.location.href);
      if (target.origin !== window.location.origin) {
        return;
      }
    } catch {
      // Treat unparsable links as internal UI links and neutralize them.
    }

    anchor.setAttribute("href", "#");
    anchor.setAttribute("aria-disabled", "true");
    anchor.setAttribute("data-static-export-link", "true");
  });
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
