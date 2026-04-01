import { useDeferredValue, useMemo, useState, useTransition } from "react";

import { useDashboardData } from "./useDashboardData";

const PROVIDER_COLORS = {
  Anthropic: { tone: "orange" },
  OpenAI: { tone: "green" },
  Google: { tone: "blue" },
  "Zhipu AI": { tone: "violet" },
  "Inception Labs": { tone: "pink" },
  default: { tone: "slate" },
};

function App() {
  const data = useDashboardData();
  const [activeTab, setActiveTab] = useState("finder");
  const [catalogMode, setCatalogMode] = useState("family");
  const [compareIds, setCompareIds] = useState([]);
  const [query, setQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [expandedId, setExpandedId] = useState(null);
  const [compareQuery, setCompareQuery] = useState("");
  const [expandedHistoryId, setExpandedHistoryId] = useState(null);
  const [isPending, startTransition] = useTransition();

  const deferredQuery = useDeferredValue(query);
  const deferredCompareQuery = useDeferredValue(compareQuery);

  const benchmarksById = useMemo(
    () => Object.fromEntries(data.benchmarks.map((benchmark) => [benchmark.id, benchmark])),
    [data.benchmarks],
  );
  const catalogModels = useMemo(
    () => (catalogMode === "family" ? buildFamilyModels(data.models, benchmarksById) : data.models),
    [benchmarksById, catalogMode, data.models],
  );
  const visibleModelCount = catalogModels.length;

  const filteredModels = useMemo(() => {
    const search = deferredQuery.toLowerCase();
    return catalogModels.filter((model) => {
      const matchQuery = buildModelSearchText(model).includes(search);
      const matchProvider = providerFilter === "All" || model.provider === providerFilter;
      const matchType = typeFilter === "All" || model.type === typeFilter;
      return matchQuery && matchProvider && matchType;
    });
  }, [catalogModels, deferredQuery, providerFilter, typeFilter]);

  const compareSuggestions = useMemo(() => {
    const search = deferredCompareQuery.toLowerCase();
    return catalogModels
      .filter((model) => !compareIds.includes(model.id))
      .filter((model) => buildModelSearchText(model).includes(search))
      .slice(0, 5);
  }, [catalogModels, compareIds, deferredCompareQuery]);

  const providers = useMemo(
    () => ["All", ...new Set(catalogModels.map((model) => model.provider).filter(Boolean))].sort(),
    [catalogModels],
  );

  function handleSelectUseCase(useCaseId) {
    startTransition(() => {
      const nextUseCaseId = useCaseId === data.selectedUseCaseId ? "" : useCaseId;
      data.loadRankings(nextUseCaseId);
    });
  }

  function toggleCompare(modelId) {
    setCompareIds((current) =>
      current.includes(modelId) ? current.filter((id) => id !== modelId) : [...current, modelId],
    );
  }

  function handleCatalogModeChange(nextMode) {
    if (nextMode === catalogMode) {
      return;
    }
    startTransition(() => {
      setCatalogMode(nextMode);
      setCompareIds([]);
      setExpandedId(null);
      setCompareQuery("");
    });
  }

  function toggleHistoryEntry(logId) {
    setExpandedHistoryId((current) => {
      const nextLogId = current === logId ? null : logId;
      if (nextLogId && !data.sourceRunsByLogId[nextLogId]?.length) {
        data.loadSourceRuns(nextLogId);
      }
      return nextLogId;
    });
  }

  function renderContent() {
    if (activeTab === "finder") {
      return (
        <UseCaseFinder
          benchmarksById={benchmarksById}
          isPending={isPending}
          rankings={data.rankings}
          rankingsError={data.rankingsError}
          rankingsLoading={data.rankingsLoading}
          selectedUseCaseId={data.selectedUseCaseId}
          useCases={data.useCases}
          onSelectUseCase={handleSelectUseCase}
        />
      );
    }

    if (activeTab === "browser") {
      return (
        <ModelBrowser
          compareIds={compareIds}
          catalogMode={catalogMode}
          filteredModels={filteredModels}
          expandedId={expandedId}
          benchmarksById={benchmarksById}
          onAddToCompare={toggleCompare}
          onCatalogModeChange={handleCatalogModeChange}
          onExpandedIdChange={setExpandedId}
          onProviderFilterChange={setProviderFilter}
          onQueryChange={setQuery}
          onTypeFilterChange={setTypeFilter}
          providerFilter={providerFilter}
          providers={providers}
          query={query}
          typeFilter={typeFilter}
        />
      );
    }

    if (activeTab === "compare") {
      return (
        <Compare
          benchmarks={data.benchmarks}
          benchmarksById={benchmarksById}
          catalogMode={catalogMode}
          compareIds={compareIds}
          compareSuggestions={compareSuggestions}
          compareQuery={compareQuery}
          models={catalogModels}
          onAddToCompare={toggleCompare}
          onCatalogModeChange={handleCatalogModeChange}
          onCompareQueryChange={setCompareQuery}
        />
      );
    }

    if (activeTab === "methodology") {
      return (
        <Methodology
          benchmarks={data.benchmarks}
          benchmarksById={benchmarksById}
          catalogMode={catalogMode}
          selectedUseCaseId={data.selectedUseCaseId}
          useCases={data.useCases}
        />
      );
    }

    return (
      <History
        expandedHistoryId={expandedHistoryId}
        history={data.history}
        loadRawSourceRecords={data.loadRawSourceRecords}
        onToggleEntry={toggleHistoryEntry}
        rawRecordsBySourceRunId={data.rawRecordsBySourceRunId}
        rawRecordsLoadingBySourceRunId={data.rawRecordsLoadingBySourceRunId}
        sourceRunsByLogId={data.sourceRunsByLogId}
        sourceRunsLoadingByLogId={data.sourceRunsLoadingByLogId}
        updateState={data.updateState}
      />
    );
  }

  return (
    <div className="shell">
      <style>{styles}</style>
      <Header
        benchmarkCount={data.benchmarks.length}
        isUpdating={data.updateState.status === "running"}
        lastUpdated={data.history[0]?.completed_at || data.history[0]?.started_at || "Not updated yet"}
        message={data.updateState.message}
        modelCount={visibleModelCount}
        onUpdate={() => data.triggerUpdate()}
      />
      <TabNav activeTab={activeTab} onTabChange={(tab) => startTransition(() => setActiveTab(tab))} />
      <main className="page">
        {data.error ? <Banner tone="error" title="Data load failed" message={data.error} /> : null}
        {data.updateState.message ? (
          <Banner
            tone={data.updateState.status === "failed" ? "error" : "info"}
            title="Update status"
            message={data.updateState.message}
          />
        ) : null}
        {data.loading ? <LoadingState /> : renderContent()}
      </main>
      {data.updateState.status === "running" ? (
        <div className="toast">{data.updateState.message || "Update running..."}</div>
      ) : null}
    </div>
  );
}

function Header({ benchmarkCount, isUpdating, lastUpdated, message, modelCount, onUpdate }) {
  return (
    <header className="topbar">
      <div>
        <div className="eyebrow">Internal research tool</div>
        <h1>LLM Intelligence Dashboard</h1>
        <p className="meta">
          Last updated {formatDate(lastUpdated)} · {modelCount} models · {benchmarkCount} benchmarks
        </p>
      </div>
      <div className="topbar-actions">
        <div className="version">v1.0</div>
        <button className="btn btn-primary" disabled={isUpdating} onClick={onUpdate} type="button">
          {isUpdating ? "Updating..." : "Update Now"}
        </button>
        {message ? <div className="message">{message}</div> : null}
      </div>
    </header>
  );
}

function TabNav({ activeTab, onTabChange }) {
  const tabs = [
    { id: "finder", label: "Use Case Finder", icon: "🔍" },
    { id: "browser", label: "Model Browser", icon: "📊" },
    { id: "compare", label: "Compare", icon: "⚖️" },
    { id: "methodology", label: "Methodology", icon: "🧭" },
    { id: "history", label: "History", icon: "🕐" },
  ];

  return (
    <nav className="tabs">
      <div className="tabs-inner">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={activeTab === tab.id ? "tab tab-active" : "tab"}
            onClick={() => onTabChange(tab.id)}
            type="button"
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>
    </nav>
  );
}

function ViewModeToggle({ mode, onChange }) {
  return (
    <div className="toggle-group" role="tablist" aria-label="Catalog mode">
      <button
        className={mode === "family" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
        onClick={() => onChange("family")}
        type="button"
      >
        Families
      </button>
      <button
        className={mode === "exact" ? "toggle-btn toggle-btn-active" : "toggle-btn"}
        onClick={() => onChange("exact")}
        type="button"
      >
        Exact variants
      </button>
    </div>
  );
}

function UseCaseFinder({
  benchmarksById,
  isPending,
  onSelectUseCase,
  rankings,
  rankingsError,
  rankingsLoading,
  selectedUseCaseId,
  useCases,
}) {
  const selected = useCases.find((useCase) => useCase.id === selectedUseCaseId) || null;
  const groupedUseCases = groupUseCasesBySegment(useCases);
  const selectedRequired = selected?.required_benchmarks || [];
  const selectedNotes = selected?.benchmark_notes || {};
  const selectedMinCoverage = selected?.min_coverage ?? 0.5;

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Which model for my use case?</h2>
          <p>Select a use case to see models ranked by evidence from our benchmark sources.</p>
        </div>
        {isPending || rankingsLoading ? <div className="pill">Loading rankings...</div> : null}
      </div>

      <div className="usecase-sections">
        {groupedUseCases.map((group) => (
          <section key={group.id} className="usecase-section">
            <div className="usecase-section-head">
              <div className="eyebrow">{group.title}</div>
              <div className="usecase-section-copy">{group.description}</div>
            </div>
            <div className="usecase-grid">
              {group.items.map((useCase) => (
                <button
                  key={useCase.id}
                  className={selected?.id === useCase.id ? "usecase usecase-active" : "usecase"}
                  onClick={() => onSelectUseCase(useCase.id)}
                  type="button"
                >
                  <div className="usecase-topline">
                    <div className="usecase-icon">{useCase.icon}</div>
                    <span className={useCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                      {useCase.status === "preview" ? "Preview" : "Ready"}
                    </span>
                  </div>
                  <div className="usecase-label">{useCase.label}</div>
                  <div className="usecase-desc">{useCase.description}</div>
                  <div className="usecase-meta">
                    <span>{Math.round((useCase.min_coverage ?? 0.5) * 100)}% min coverage</span>
                    {useCase.segment === "enterprise" ? <span className="tag tag-enterprise">Enterprise</span> : null}
                  </div>
                  {useCase.required_benchmarks?.length ? (
                    <div className="usecase-chip-list">
                      {useCase.required_benchmarks.slice(0, 3).map((benchmarkId) => (
                        <span key={benchmarkId} className="usecase-chip">
                          {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      {rankingsError ? <Banner tone="error" title="Rankings failed" message={rankingsError} /> : null}

      {selected ? (
        <section className="stack">
          <div className="section-head">
            <h3>
              {selected.icon} Best models for <span className="accent">{selected.label}</span>
            </h3>
            <div className="hint">Ranked by weighted benchmark score</div>
          </div>

          <div className="usecase-status-row">
            <span className={selected.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
              {selected.status === "preview" ? "Preview lens" : "Ready lens"}
            </span>
            <span className="tag">{Math.round(selectedMinCoverage * 100)}% minimum coverage</span>
          </div>
          {selected.status === "preview" ? (
            <div className="preview-note">
              Preview lenses are useful for exploration, but they still rely on thinner or more uneven benchmark coverage
              than the ready lenses.
            </div>
          ) : null}

          {!rankings || !rankings.rankings || rankings.rankings.length === 0 ? (
            <EmptyState message="No models have data for this use case yet. Trigger an update to populate scores." />
          ) : (
            <div className="stack">
              {rankings.rankings.map((entry) => (
                <RankedModelCard key={`${entry.model.id}-${entry.rank}`} benchmarksById={benchmarksById} entry={entry} />
              ))}
            </div>
          )}

          <div className="note">
            <strong>Note:</strong> Rankings are weighted averages of available benchmark data. Models must cover at
            least {Math.round(selectedMinCoverage * 100)}% of the benchmark weight for this use case to be ranked.
            <span className="note-list">
              Evidence mix: {formatUseCaseWeights(selected, benchmarksById)}
              .
            </span>
            {Object.prototype.hasOwnProperty.call(selected.weights, "terminal_bench") ? (
              <span className="note-list">
                Terminal-Bench contributes agent-derived workflow evidence from verified single-model public submissions.
              </span>
            ) : null}
          </div>

          {selectedRequired.length ? (
            <div className="panel">
              <div className="panel-head">Required evidence</div>
              <div className="usecase-chip-list">
                {selectedRequired.map((benchmarkId) => (
                  <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                    {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
              <div className="usecase-note-caption">
                Models missing any required benchmark stay visible if they clear the coverage threshold, but they are
                flagged with critical gaps and sorted below more complete evidence.
              </div>
              {Object.keys(selectedNotes).length ? (
                <div className="usecase-notes">
                  {Object.entries(selectedNotes).map(([benchmarkId, note]) => (
                    <div key={benchmarkId} className="usecase-note-item">
                      <strong>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}:</strong>
                      <span>{note}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}

function Methodology({ benchmarks, benchmarksById, catalogMode, selectedUseCaseId, useCases }) {
  const groupedUseCases = groupUseCasesBySegment(useCases);
  const selectedLens = useCases.find((useCase) => useCase.id === selectedUseCaseId) || useCases.find((useCase) => useCase.id === "coding") || useCases[0] || null;
  const benchmarksWithUsage = [...benchmarks]
    .map((benchmark) => ({
      ...benchmark,
      usedBy: useCases.filter((useCase) => Object.prototype.hasOwnProperty.call(useCase.weights || {}, benchmark.id)),
    }))
    .sort((left, right) => {
      if (left.tier !== right.tier) {
        return left.tier - right.tier;
      }
      return left.name.localeCompare(right.name);
    });

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Methodology</h2>
          <p>How this app ranks models, what each source measures, and how to interpret the outputs responsibly.</p>
        </div>
        <div className="hint">This is the decision logic behind every use-case ranking.</div>
      </div>

      <div className="method-grid">
        <article className="panel method-card">
          <div className="panel-head">What this app is doing</div>
          <div className="method-copy">
            This is a weighted decision system over benchmark evidence. It is not claiming one universal “best model”.
            Each use case defines its own evidence mix, minimum coverage threshold, and required benchmarks.
          </div>
          <div className="method-list">
            <div><strong>Score:</strong> weighted normalized composite, not a raw percentage.</div>
            <div><strong>Coverage:</strong> how much of the use-case evidence stack a model actually covers.</div>
            <div><strong>Critical gaps:</strong> missing required benchmarks that make a ranking less trustworthy.</div>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How ranking works</div>
          <div className="method-steps">
            <div className="method-step"><strong>1.</strong> Pick the benchmarks that belong to the selected lens.</div>
            <div className="method-step"><strong>2.</strong> Normalize each benchmark against the current model pool, including inverting lower-is-better metrics like cost or hallucination rate.</div>
            <div className="method-step"><strong>3.</strong> Apply the lens weights and compute a weighted average over the benchmarks the model actually has.</div>
            <div className="method-step"><strong>4.</strong> Drop any model below the lens minimum coverage threshold.</div>
            <div className="method-step"><strong>5.</strong> Sort models with fewer critical gaps first, then higher weighted score, then higher coverage.</div>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How to read results</div>
          <div className="method-list">
            <div><strong>#1 rank:</strong> strongest evidence mix for that lens in the current dataset.</div>
            <div><strong>High score, low trust:</strong> possible when a model is strong on partial evidence but misses required benchmarks.</div>
            <div><strong>Preview lens:</strong> useful for exploration, but still thinner or more uneven than ready lenses.</div>
            <div><strong>{catalogMode === "family" ? "Families mode" : "Exact variants mode"}:</strong> {catalogMode === "family" ? "variant scores are rolled into a family card using the best available benchmark evidence per family." : "you are looking at exact model/variant cards with no family aggregation."}</div>
          </div>
          <div className="method-badges">
            <span className="method-badge"><SourceBadge score={{ source_type: "primary", verified: true }} /> direct primary row</span>
            <span className="method-badge"><SourceBadge score={{ source_type: "secondary", verified: false }} /> lower-trust / derived / self-reported</span>
            <span className="method-badge"><SourceBadge score={{ source_type: "manual", verified: false }} /> manual entry</span>
          </div>
        </article>

        <article className="panel method-card">
          <div className="panel-head">How to use this tool</div>
          <div className="method-list">
            <div><strong>Start with a use case lens:</strong> that gives you the right weighting for the task you actually care about.</div>
            <div><strong>Use family view first:</strong> it is the best default for procurement and shortlist decisions.</div>
            <div><strong>Switch to exact variants second:</strong> use it when you need to choose between reasoning, max, mini, or context-window variants.</div>
            <div><strong>Open the benchmark rows:</strong> check source, caveat, and missing evidence before trusting a high rank.</div>
          </div>
        </article>
      </div>

      {selectedLens ? (
        <section className="panel methodology-focus">
          <div className="panel-head">How to read the current lens</div>
          <div className="method-focus-head">
            <div className="method-focus-title">
              <span className="usecase-icon">{selectedLens.icon}</span>
              <div>
                <div className="title">{selectedLens.label}</div>
                <div className="method-subtle">{selectedLens.description}</div>
              </div>
            </div>
            <div className="usecase-status-row">
              <span className={selectedLens.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                {selectedLens.status === "preview" ? "Preview lens" : "Ready lens"}
              </span>
              <span className="tag">{Math.round((selectedLens.min_coverage ?? 0.5) * 100)}% minimum coverage</span>
            </div>
          </div>
          <div className="method-grid">
            <div className="method-card method-card-soft">
              <div className="detail-label">Weights</div>
              <div className="weight-list">
                {Object.entries(selectedLens.weights || {})
                  .sort((left, right) => right[1] - left[1])
                  .map(([benchmarkId, weight]) => (
                    <div key={benchmarkId} className="weight-row">
                      <span>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}</span>
                      <span>{Math.round(weight * 100)}%</span>
                    </div>
                  ))}
              </div>
            </div>
            <div className="method-card method-card-soft">
              <div className="detail-label">Required evidence</div>
              <div className="usecase-chip-list">
                {(selectedLens.required_benchmarks || []).map((benchmarkId) => (
                  <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                    {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                  </span>
                ))}
              </div>
              <div className="method-subtle">
                Models missing these benchmarks can still appear if they clear the coverage gate, but they rank below more complete evidence.
              </div>
            </div>
          </div>
          <div className="usecase-notes">
            {Object.entries(selectedLens.benchmark_notes || {}).map(([benchmarkId, note]) => (
              <div key={benchmarkId} className="usecase-note-item">
                <strong>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}:</strong>
                <span>{note}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="stack">
        <div className="section-head">
          <div>
            <h3>Use-case lenses</h3>
            <p>Every lens is a different ranking recipe. The weights below are the actual scoring logic.</p>
          </div>
        </div>
        {groupedUseCases.map((group) => (
          <section key={group.id} className="stack stack-tight">
            <div className="usecase-section-head">
              <div className="eyebrow">{group.title}</div>
              <div className="usecase-section-copy">{group.description}</div>
            </div>
            <div className="methodology-usecases">
              {group.items.map((useCase) => (
                <article key={useCase.id} className="panel method-card">
                  <div className="method-focus-head">
                    <div className="method-focus-title">
                      <span className="usecase-icon">{useCase.icon}</span>
                      <div>
                        <div className="title">{useCase.label}</div>
                        <div className="method-subtle">{useCase.description}</div>
                      </div>
                    </div>
                    <div className="usecase-status-row">
                      <span className={useCase.status === "preview" ? "tag tag-preview" : "tag tag-ready"}>
                        {useCase.status === "preview" ? "Preview" : "Ready"}
                      </span>
                      <span className="tag">{Math.round((useCase.min_coverage ?? 0.5) * 100)}% min coverage</span>
                    </div>
                  </div>
                  <div className="usecase-chip-list">
                    {(useCase.required_benchmarks || []).map((benchmarkId) => (
                      <span key={benchmarkId} className="usecase-chip usecase-chip-required">
                        {benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}
                      </span>
                    ))}
                  </div>
                  <div className="weight-list">
                    {Object.entries(useCase.weights || {})
                      .sort((left, right) => right[1] - left[1])
                      .map(([benchmarkId, weight]) => (
                        <div key={benchmarkId} className="weight-row">
                          <span>{benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ")}</span>
                          <span>{Math.round(weight * 100)}%</span>
                        </div>
                      ))}
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </section>

      <section className="stack">
        <div className="section-head">
          <div>
            <h3>Benchmark source library</h3>
            <p>What each benchmark is, who publishes it, why it matters, and where it is used.</p>
          </div>
        </div>
        <div className="methodology-benchmarks">
          {benchmarksWithUsage.map((benchmark) => {
            const context = getBenchmarkContext(benchmark);
            return (
              <article key={benchmark.id} className="panel method-card">
                <div className="method-focus-head">
                  <div>
                    <div className="title">{benchmark.name}</div>
                    <div className="method-subtle">{benchmark.short} · {benchmark.category}</div>
                  </div>
                  <div className="usecase-status-row">
                    <span className="tag">Tier {benchmark.tier}</span>
                    <span className="tag">{benchmark.higher_is_better ? "Higher is better" : "Lower is better"}</span>
                  </div>
                </div>
                <div className="method-list">
                  <div><strong>Metric:</strong> {benchmark.metric}</div>
                  <div><strong>Source:</strong> {context.source}</div>
                  <div><strong>Why it matters:</strong> {context.why}</div>
                  {context.caveat ? <div><strong>Caveat:</strong> {context.caveat}</div> : null}
                  <div><strong>Used in:</strong> {benchmark.usedBy.length ? benchmark.usedBy.map((useCase) => useCase.label).join(", ") : "Not currently used in a ranking lens."}</div>
                </div>
                {benchmark.url ? (
                  <a className="bench-source" href={benchmark.url} rel="noreferrer" target="_blank">
                    Open source leaderboard
                  </a>
                ) : null}
              </article>
            );
          })}
        </div>
      </section>
    </section>
  );
}

function RankedModelCard({ benchmarksById, entry }) {
  const [expanded, setExpanded] = useState(false);
  const isTop = entry.rank === 1;
  const criticalMissing = entry.critical_missing_benchmarks || [];

  return (
    <article className={isTop ? "card card-top" : "card"}>
      <div className="card-body">
        <div className="rank-pill">{entry.rank}</div>
        <div className="card-main">
          <div className="card-headline">
            <span className="title">{entry.model.name}</span>
            <ProviderBadge provider={entry.model.provider} />
            <TypeBadge type={entry.model.type} />
            {isTop ? <span className="tag tag-top">Top pick</span> : null}
            {criticalMissing.length ? (
              <span className="tag tag-warning">Critical gaps: {criticalMissing.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}</span>
            ) : null}
          </div>
          <ScoreBar score={entry.score} />
          <CoverageIndicator coverage={entry.coverage} />
        </div>
        <button className="link-btn" onClick={() => setExpanded((value) => !value)} type="button">
          {expanded ? "▲ Less" : "▼ Detail"}
        </button>
      </div>

      {expanded ? (
        <div className="card-details">
          <div className="detail-label">Benchmark breakdown</div>
          {criticalMissing.length ? (
            <div className="critical-gaps">
              <strong>Critical evidence missing:</strong>{" "}
              {criticalMissing.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}
            </div>
          ) : null}
          <div className="detail-list">
            {entry.breakdown.map((item) => (
              <div key={item.benchmark_id} className="detail-row">
                <span className="detail-short">{benchmarksById[item.benchmark_id]?.short || item.benchmark_id.replaceAll("_", " ")}</span>
                <div className="mini-bar">
                  <div className="mini-fill" style={{ width: `${item.normalised}%` }} />
                </div>
                <span className="detail-value">
                  <SourceBadge score={{ source_type: item.source_type, verified: item.verified }} />
                  {formatBenchmarkValue(benchmarksById[item.benchmark_id], item.raw_value)}
                </span>
                <span className="detail-weight">{Math.round(item.weight * 100)}% weight</span>
                {item.notes ? <span className="detail-note">{item.notes}</span> : null}
              </div>
            ))}
            {entry.missing_benchmarks.length ? (
              <div className="missing">
                Missing data: {entry.missing_benchmarks.map((id) => benchmarksById[id]?.short || id.replaceAll("_", " ")).join(", ")}
              </div>
            ) : null}
          </div>
          <div className="small-meta">
            Context: {entry.model.context_window || "Unknown"} · Released: {entry.model.release_date || "Unknown"}
          </div>
        </div>
      ) : null}
    </article>
  );
}

function ModelBrowser({
  benchmarksById,
  catalogMode,
  compareIds,
  expandedId,
  filteredModels,
  onAddToCompare,
  onCatalogModeChange,
  onExpandedIdChange,
  onProviderFilterChange,
  onQueryChange,
  onTypeFilterChange,
  providerFilter,
  providers,
  query,
  typeFilter,
}) {
  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Model Browser</h2>
          <p>
            Search and explore all tracked models with their full benchmark profiles.
            {catalogMode === "family" ? " Family view combines variants into a best-available family card." : ""}
          </p>
        </div>
        <ViewModeToggle mode={catalogMode} onChange={onCatalogModeChange} />
      </div>

      <div className="toolbar">
        <input
          className="input"
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search models..."
          type="text"
          value={query}
        />
        <select className="input select" onChange={(event) => onProviderFilterChange(event.target.value)} value={providerFilter}>
          {providers.map((provider) => (
            <option key={provider} value={provider}>
              {provider}
            </option>
          ))}
        </select>
        <select className="input select" onChange={(event) => onTypeFilterChange(event.target.value)} value={typeFilter}>
          <option value="All">All types</option>
          <option value="proprietary">Proprietary</option>
          <option value="open_weights">Open weights</option>
        </select>
      </div>

      <div className="stack">
        {!filteredModels.length ? <EmptyState message="No models match your search." /> : null}
        {filteredModels.map((model) => (
          <ModelBrowserCard
            benchmarksById={benchmarksById}
            key={model.id}
            compareIds={compareIds}
            expanded={expandedId === model.id}
            model={model}
            onAddToCompare={onAddToCompare}
            onToggle={() => onExpandedIdChange(expandedId === model.id ? null : model.id)}
          />
        ))}
      </div>
    </section>
  );
}

function ModelBrowserCard({ benchmarksById, compareIds, expanded, model, onAddToCompare, onToggle }) {
  const scoredBenchmarks = Object.entries(model.scores).filter(([, score]) => score?.value != null);
  const coverage = Math.round((scoredBenchmarks.length / Math.max(1, Object.keys(model.scores).length)) * 100);
  const isFamily = Boolean(model.family && model.family.member_count > 1);

  return (
    <article className="card">
      <div className="card-body card-clickable" onClick={onToggle}>
        <div className="card-main">
          <div className="card-headline">
            <span className="title">{model.name}</span>
            <ProviderBadge provider={model.provider} />
            <TypeBadge type={model.type} />
            {isFamily ? <span className="tag tag-family">{model.family.member_count} variants</span> : null}
          </div>
          <div className="submeta">
            <span>Context: {model.context_window || "Unknown"}</span>
            <span>Released: {model.release_date || "Unknown"}</span>
            <span className={coverage >= 50 ? "coverage coverage-good" : "coverage coverage-warn"}>
              {coverage}% benchmark coverage
            </span>
          </div>
        </div>
        <div className="card-actions">
          <button
            className={compareIds.includes(model.id) ? "btn btn-secondary btn-active" : "btn btn-secondary"}
            onClick={(event) => {
              event.stopPropagation();
              onAddToCompare(model.id);
            }}
            type="button"
          >
            {compareIds.includes(model.id) ? "✓ In compare" : "+ Compare"}
          </button>
          <span className="chev">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded ? (
        <div className="card-details">
          {isFamily ? (
            <div className="stack stack-tight">
              <div className="detail-label">Family members</div>
              <div className="member-chips">
                {model.family.member_names.map((memberName) => (
                  <span key={memberName} className="member-chip">
                    {memberName}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
          <div className="bench-grid">
            {Object.entries(model.scores).map(([benchmarkId, score]) => {
              const benchmark = benchmarksById[benchmarkId];
              const label = benchmark?.short || benchmarkId.replaceAll("_", " ");
              const variantName = score?.family_variant_name;
              const provenance = benchmarkId === "terminal_bench" ? score?.notes : "";
              const benchmarkContext = getBenchmarkContext(benchmark);
              return (
                <div key={benchmarkId} className="bench-row">
                  {benchmark?.url ? (
                    <a className="bench-short bench-link" href={benchmark.url} rel="noreferrer" target="_blank">
                      {label}
                    </a>
                  ) : (
                    <span className="bench-short">{label}</span>
                  )}
                  {score?.value != null ? (
                    <>
                      <div className="mini-bar">
                        <div
                          className="mini-fill"
                          style={{ width: `${normalizeBenchmarkValue(benchmark, score.value)}%` }}
                        />
                      </div>
                      <span className="bench-score">
                        <SourceBadge score={score} />
                        {formatBenchmarkValue(benchmark, score.value)}
                      </span>
                      {variantName ? <span className="bench-variant">via {variantName}</span> : null}
                      {provenance ? <span className="bench-provenance">{provenance}</span> : null}
                      <span className="bench-date">{formatDate(score.collected_at)}</span>
                    </>
                  ) : (
                    <span className="bench-empty">— no data</span>
                  )}
                  {benchmark?.url ? (
                    <a className="bench-source" href={benchmark.url} rel="noreferrer" target="_blank">
                      Source: {benchmarkContext.source}
                    </a>
                  ) : (
                    <span className="bench-source">Source: {benchmarkContext.source}</span>
                  )}
                  <span className="bench-context">Why it matters: {benchmarkContext.why}</span>
                  {benchmarkContext.caveat ? <span className="bench-caveat">Caveat: {benchmarkContext.caveat}</span> : null}
                </div>
              );
            })}
          </div>
          <div className="tip">Tip: Click any benchmark name to view source leaderboard. Missing scores can be populated by running an update.</div>
        </div>
      ) : null}
    </article>
  );
}

function Compare({
  benchmarks,
  benchmarksById,
  catalogMode,
  compareIds,
  compareQuery,
  compareSuggestions,
  models,
  onAddToCompare,
  onCatalogModeChange,
  onCompareQueryChange,
}) {
  const selectedModels = models.filter((model) => compareIds.includes(model.id));
  const benchmarksWithData = benchmarks.filter((benchmark) =>
    selectedModels.some((model) => model.scores[benchmark.id]?.value != null),
  );

  function winnerForBenchmark(benchmark) {
    const withData = selectedModels.filter((model) => model.scores[benchmark.id]?.value != null);
    if (withData.length < 2) {
      return null;
    }

    return withData.reduce((best, model) => {
      const current = model.scores[benchmark.id].value;
      const bestValue = best.scores[benchmark.id].value;
      return benchmark.higher_is_better ? (current > bestValue ? model : best) : current < bestValue ? model : best;
    });
  }

  const winCounts = selectedModels.reduce((acc, model) => ({ ...acc, [model.id]: 0 }), {});
  benchmarksWithData.forEach((benchmark) => {
    const winner = winnerForBenchmark(benchmark);
    if (winner) {
      winCounts[winner.id] += 1;
    }
  });

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Compare Models</h2>
          <p>
            Side-by-side benchmark comparison. Add models from the Model Browser or search below.
            {catalogMode === "family" ? " Family mode uses the best available variant per benchmark." : ""}
          </p>
        </div>
        <ViewModeToggle mode={catalogMode} onChange={onCatalogModeChange} />
      </div>

      <div className="panel">
        <div className="panel-head">
          {selectedModels.length === 0 ? "Add models to compare" : `Comparing ${selectedModels.length} model${selectedModels.length > 1 ? "s" : ""}`}
        </div>
        <div className="compare-pills">
          {selectedModels.length ? (
            selectedModels.map((model) => (
              <span key={model.id} className="compare-pill">
                <span>{model.name}</span>
                <button onClick={() => onAddToCompare(model.id)} type="button">
                  ×
                </button>
              </span>
            ))
          ) : (
            <span className="hint">No models selected yet</span>
          )}
        </div>
        <input
          className="input"
          onChange={(event) => onCompareQueryChange(event.target.value)}
          placeholder="Search to add a model..."
          type="text"
          value={compareQuery}
        />
        {compareQuery && compareSuggestions.length ? (
          <div className="suggestions">
            {compareSuggestions.map((model) => (
              <button
                key={model.id}
                className="suggestion"
                onClick={() => {
                  onAddToCompare(model.id);
                  onCompareQueryChange("");
                }}
                type="button"
              >
                <span>{model.name}</span>
                <ProviderBadge provider={model.provider} />
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {selectedModels.length >= 2 && benchmarksWithData.length ? (
        <>
          <div className="compare-summary" style={{ gridTemplateColumns: `repeat(${selectedModels.length}, minmax(0, 1fr))` }}>
            {selectedModels.map((model) => (
              <div key={model.id} className={hasWinners(winCounts) && isWinner(winCounts, selectedModels, model.id) ? "summary summary-top" : "summary"}>
                <div className="summary-title">{model.name}</div>
                <ProviderBadge provider={model.provider} />
                {model.family && model.family.member_count > 1 ? <div className="summary-foot">{model.family.member_count} variants</div> : null}
                <div className="summary-score">
                  <span>{winCounts[model.id]}</span>
                  <small>wins</small>
                </div>
                <div className="summary-foot">of {benchmarksWithData.length} benchmarks</div>
              </div>
            ))}
          </div>

          <div className="table">
            <div className="table-head" style={{ gridTemplateColumns: `180px repeat(${selectedModels.length}, minmax(0, 1fr))` }}>
              <div>Benchmark</div>
              {selectedModels.map((model) => (
                <div key={model.id}>{model.name}</div>
              ))}
            </div>

            {benchmarksWithData.map((benchmark) => {
              const winner = winnerForBenchmark(benchmark);
              return (
                <div key={benchmark.id} className="table-row" style={{ gridTemplateColumns: `180px repeat(${selectedModels.length}, minmax(0, 1fr))` }}>
                  <div>
                    <a href={benchmark.url} rel="noreferrer" target="_blank">
                      {benchmark.short}
                    </a>
                    <div className="metric">{benchmark.metric}</div>
                  </div>
                  {selectedModels.map((model) => {
                    const score = model.scores[benchmark.id];
                    const isWinnerModel = winner?.id === model.id;
                    return (
                      <div key={model.id} className={isWinnerModel ? "cell cell-winner" : "cell"}>
                        {score?.value != null ? (
                          <div className="cell-score">
                            <span className={isWinnerModel ? "score score-winner" : "score"}>
                              <SourceBadge score={score} />
                              {isWinnerModel ? "★ " : ""}
                              {formatBenchmarkValue(benchmarksById[benchmark.id], score.value)}
                            </span>
                            {score.family_variant_name ? <span className="cell-variant">via {score.family_variant_name}</span> : null}
                            {benchmark.id === "terminal_bench" && score.notes ? <span className="cell-variant">{score.notes}</span> : null}
                          </div>
                        ) : (
                          <span className="cell-empty">—</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <EmptyState message="Add at least 2 models to compare." />
      )}
    </section>
  );
}

function History({
  expandedHistoryId,
  history,
  loadRawSourceRecords,
  onToggleEntry,
  rawRecordsBySourceRunId,
  rawRecordsLoadingBySourceRunId,
  sourceRunsByLogId,
  sourceRunsLoadingByLogId,
  updateState,
}) {
  const [expandedSourceRunIds, setExpandedSourceRunIds] = useState({});
  const entries = [...history].sort((left, right) => String(right.started_at).localeCompare(String(left.started_at)));

  function toggleSourceRun(sourceRunId) {
    setExpandedSourceRunIds((current) => {
      const isExpanded = Boolean(current[sourceRunId]);
      if (!isExpanded && !rawRecordsBySourceRunId[sourceRunId]?.length) {
        loadRawSourceRecords(sourceRunId);
      }
      return { ...current, [sourceRunId]: !isExpanded };
    });
  }

  return (
    <section className="stack">
      <div className="section-head">
        <div>
          <h2>Update History</h2>
          <p>A log of each time this dashboard&apos;s data was refreshed.</p>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">How to trigger an update</div>
        <p className="panel-copy">
          Click <strong>Update Now</strong> in the header. The frontend will trigger the backend update job, poll for
          completion, and refresh the loaded models and benchmarks.
        </p>
      </div>

      <div className="history-list">
        {entries.length ? (
          entries.map((entry) => {
            const sourceRuns = sourceRunsByLogId[entry.id] || [];
            const failedSources = sourceRuns.filter((sourceRun) => sourceRun.status === "failed").length;

            return (
              <article key={entry.id} className="history-item history-entry">
                <button className="history-toggle" onClick={() => onToggleEntry(entry.id)} type="button">
                  <div className="history-dot" />
                  <div className="history-main">
                    <div className="history-date">{formatDate(entry.started_at)}</div>
                    <div className="history-note">
                      Status: {entry.status} · {entry.scores_added} scores added · {entry.scores_updated} scores updated
                    </div>
                    {sourceRuns.length ? (
                      <div className="history-source-summary">
                        {sourceRuns.length} source runs · {failedSources} failed ·{" "}
                        {sourceRuns.reduce((total, sourceRun) => total + (sourceRun.records_found || 0), 0)} raw records
                      </div>
                    ) : null}
                    {Array.isArray(entry.errors) && entry.errors.length ? (
                      <div className="history-errors">{entry.errors.map((error) => error.error_message || "Unknown error").join("; ")}</div>
                    ) : null}
                  </div>
                  <span className="history-chevron">{expandedHistoryId === entry.id ? "▲" : "▼"}</span>
                </button>
                {expandedHistoryId === entry.id ? (
                  <div className="history-sources">
                    {sourceRunsLoadingByLogId[entry.id] ? (
                      <div className="history-sources-empty">Loading source runs...</div>
                    ) : sourceRuns.length ? (
                      sourceRuns.map((sourceRun) => (
                        <div key={sourceRun.id} className="history-source-card">
                          <button className="history-source-row" onClick={() => toggleSourceRun(sourceRun.id)} type="button">
                            <div>
                              <div className="history-source-name">{sourceRun.source_name}</div>
                              <div className="history-source-meta">
                                {sourceRun.benchmark_id || "n/a"} · {sourceRun.records_found} raw records
                              </div>
                            </div>
                            <div className="history-source-status">
                              <span className={sourceRun.status === "completed" ? "pill pill-good" : sourceRun.status === "failed" ? "pill pill-bad" : "pill"}>
                                {sourceRun.status}
                              </span>
                              <span className="history-source-chevron">{expandedSourceRunIds[sourceRun.id] ? "▲" : "▼"}</span>
                              {sourceRun.error_message ? <div className="history-source-error">{sourceRun.error_message}</div> : null}
                            </div>
                          </button>
                          {expandedSourceRunIds[sourceRun.id] ? (
                            <HistorySourceRunDetails
                              rawRecords={rawRecordsBySourceRunId[sourceRun.id] || []}
                              rawRecordsLoading={rawRecordsLoadingBySourceRunId[sourceRun.id]}
                              sourceRun={sourceRun}
                            />
                          ) : null}
                        </div>
                      ))
                    ) : (
                      <div className="history-sources-empty">No source-run detail stored for this update.</div>
                    )}
                  </div>
                ) : null}
              </article>
            );
          })
        ) : (
          <EmptyState message="No update logs yet. Trigger an update to populate history." />
        )}
      </div>

      <div className="note">
        <strong>Why manual updates?</strong> Automatic scraping of benchmark leaderboards is unreliable, so the backend
        keeps a human-triggered update flow and stores every run in the database.
      </div>

      {updateState.errors?.length ? (
        <div className="panel">
          <div className="panel-head">Latest update errors</div>
          <div className="history-errors">
            {updateState.errors.map((error) => error.error_message || "Unknown error").join("; ")}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function HistorySourceRunDetails({ rawRecords, rawRecordsLoading, sourceRun }) {
  if (rawRecordsLoading) {
    return <div className="history-raw-empty">Loading raw-record detail...</div>;
  }

  if (!rawRecords.length) {
    return <div className="history-raw-empty">No raw-record detail stored for this source run.</div>;
  }

  const resolutionCounts = rawRecords.reduce((acc, row) => {
    const key = row.resolution_status || "unresolved";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const skippedAggregate = rawRecords.filter((row) => row.resolution_status === "skipped_aggregate").slice(0, 5);
  const unresolved = rawRecords.filter((row) => row.resolution_status === "unresolved").slice(0, 5);

  return (
    <div className="history-raw-panel">
      <div className="history-raw-summary">
        <span className="pill">resolved {resolutionCounts.resolved || 0}</span>
        <span className="pill">skipped aggregate {resolutionCounts.skipped_aggregate || 0}</span>
        <span className="pill">unresolved {resolutionCounts.unresolved || 0}</span>
      </div>
      {sourceRun.source_name === "terminal_bench" ? (
        <div className="history-raw-note">
          Terminal-Bench keeps multi-model aggregate submissions as raw provenance and excludes them from the model catalog.
        </div>
      ) : null}
      {skippedAggregate.length ? (
        <div className="history-raw-list">
          <div className="detail-label">Aggregate provenance kept raw</div>
          {skippedAggregate.map((row) => (
            <div key={row.id} className="history-raw-row">
              <span className="history-raw-name">{row.raw_model_name}</span>
              <span className="history-raw-meta">{row.raw_value || "n/a"}</span>
            </div>
          ))}
        </div>
      ) : null}
      {unresolved.length ? (
        <div className="history-raw-list">
          <div className="detail-label">Still unresolved</div>
          {unresolved.map((row) => (
            <div key={row.id} className="history-raw-row">
              <span className="history-raw-name">{row.raw_model_name}</span>
              <span className="history-raw-meta">{row.raw_value || "n/a"}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function ProviderBadge({ provider }) {
  const tone = PROVIDER_COLORS[provider]?.tone || PROVIDER_COLORS.default.tone;
  return <span className={`badge badge-${tone}`}>{provider}</span>;
}

function SourceBadge({ score }) {
  if (!score) {
    return null;
  }

  if (score.source_type === "manual") {
    return <span className="source-badge source-badge-manual">MANUAL</span>;
  }

  if (score.source_type === "secondary") {
    return <span className="source-badge source-badge-secondary">SECONDARY</span>;
  }

  return score.verified ? <span className="source-badge source-badge-verified">VERIFIED</span> : null;
}

function TypeBadge({ type }) {
  return type === "open_weights" ? <span className="badge badge-indigo">Open weights</span> : <span className="badge badge-slate">Proprietary</span>;
}

function CoverageIndicator({ coverage }) {
  const safeCoverage = Math.max(0, Math.min(100, Math.round(coverage * 100)));
  const tone = safeCoverage >= 70 ? "good" : safeCoverage >= 40 ? "warn" : "muted";
  return (
    <div className="coverage-row">
      <div className="coverage-track">
        <div className={`coverage-fill coverage-${tone}`} style={{ width: `${safeCoverage}%` }} />
      </div>
      <span className="coverage-label">{safeCoverage}% data</span>
    </div>
  );
}

function ScoreBar({ score }) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const tone = value >= 75 ? "good" : value >= 50 ? "warn" : "bad";
  return (
    <div className="score-row">
      <div className="score-track">
        <div className={`score-fill score-${tone}`} style={{ width: `${value}%` }} />
      </div>
      <span className={`score-value score-${tone}`}>{value}</span>
    </div>
  );
}

function Banner({ message, tone, title }) {
  return (
    <div className={tone === "error" ? "banner banner-error" : "banner banner-info"}>
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading">
      <div className="loading-card" />
      <div className="loading-card" />
      <div className="loading-card" />
    </div>
  );
}

function EmptyState({ message }) {
  return <div className="empty">{message}</div>;
}

function hasWinners(winCounts) {
  return Math.max(...Object.values(winCounts)) > 0;
}

function isWinner(winCounts, models, modelId) {
  const top = Math.max(...Object.values(winCounts));
  return winCounts[modelId] === top && top > 0;
}

function groupUseCasesBySegment(useCases) {
  const orderedSegments = [
    {
      id: "core",
      title: "Core evaluation lenses",
      description: "General-purpose benchmark views for model selection and frontier tracking.",
    },
    {
      id: "enterprise",
      title: "Enterprise workflows",
      description: "Operational lenses tuned for internal copilots, support, and document-heavy business work.",
    },
  ];

  return orderedSegments
    .map((segment) => ({
      ...segment,
      items: useCases.filter((useCase) => (useCase.segment || "core") === segment.id),
    }))
    .filter((segment) => segment.items.length);
}

function formatUseCaseWeights(useCase, benchmarksById) {
  return Object.entries(useCase.weights || {})
    .sort((left, right) => right[1] - left[1])
    .map(([benchmarkId, weight]) => {
      const label = benchmarksById[benchmarkId]?.short || benchmarkId.replaceAll("_", " ");
      return `${label} ${Math.round(weight * 100)}%`;
    })
    .join(", ");
}

function buildFamilyModels(models, benchmarksById) {
  const groups = new Map();

  models.forEach((model) => {
    const familyName = extractFamilyName(model.name);
    const familyKey = `${model.provider}::${slugifyText(familyName)}`;
    const current = groups.get(familyKey) || {
      familyKey,
      familyName,
      provider: model.provider,
      members: [],
    };
    current.members.push(model);
    groups.set(familyKey, current);
  });

  return Array.from(groups.values())
    .map((group) => buildFamilyModel(group, benchmarksById))
    .sort((left, right) => {
      const providerComparison = String(left.provider).localeCompare(String(right.provider));
      if (providerComparison !== 0) {
        return providerComparison;
      }
      return String(left.name).localeCompare(String(right.name));
    });
}

function buildFamilyModel(group, benchmarksById) {
  const { familyKey, familyName, members, provider } = group;
  const representative = chooseRepresentativeModel(members, familyName);
  const benchmarkIds = new Set(members.flatMap((member) => Object.keys(member.scores || {})));
  const scores = {};

  benchmarkIds.forEach((benchmarkId) => {
    const benchmark = benchmarksById[benchmarkId];
    const bestEntry = members.reduce((best, member) => {
      const score = member.scores?.[benchmarkId];
      if (!score?.value && score?.value !== 0) {
        return best;
      }
      if (!best) {
        return { member, score };
      }
      if (isBetterBenchmarkScore(score, best.score, benchmark)) {
        return { member, score };
      }
      return best;
    }, null);

    scores[benchmarkId] = bestEntry
      ? {
          ...bestEntry.score,
          family_variant_id: bestEntry.member.id,
          family_variant_name: bestEntry.member.name,
        }
      : null;
  });

  return {
    ...representative,
    id: `family:${slugifyText(provider)}:${slugifyText(familyName || representative.name)}`,
    name: familyName || representative.name,
    context_window: mergeFamilyValue(members, "context_window", representative.context_window),
    release_date: mergeFamilyValue(members, "release_date", representative.release_date),
    scores,
    family: {
      key: familyKey,
      member_count: members.length,
      member_ids: members.map((member) => member.id),
      member_names: members.map((member) => member.name).sort((left, right) => left.localeCompare(right)),
      representative_id: representative.id,
    },
  };
}

function buildModelSearchText(model) {
  const parts = [model.name, model.provider, model.type, model.release_date, model.context_window];
  if (model.family?.member_names?.length) {
    parts.push(...model.family.member_names);
  }
  return parts
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function chooseRepresentativeModel(members, familyName) {
  return [...members].sort((left, right) => {
    const leftScore = representativeSortScore(left, familyName);
    const rightScore = representativeSortScore(right, familyName);
    if (leftScore !== rightScore) {
      return leftScore - rightScore;
    }

    const leftCoverage = countAvailableScores(left);
    const rightCoverage = countAvailableScores(right);
    if (leftCoverage !== rightCoverage) {
      return rightCoverage - leftCoverage;
    }

    return left.name.localeCompare(right.name);
  })[0];
}

function representativeSortScore(model, familyName) {
  let score = 0;
  const baseName = extractFamilyName(model.name);
  if (model.name === familyName) {
    score -= 50;
  }
  if (baseName === familyName) {
    score -= 10;
  }
  if (isSlugLike(model.name)) {
    score += 10;
  }
  if (hasVariantSuffix(model.name)) {
    score += 20;
  }
  score += model.name.length / 100;
  return score;
}

function countAvailableScores(model) {
  return Object.values(model.scores || {}).filter((score) => score?.value != null).length;
}

function mergeFamilyValue(members, key, fallback) {
  const values = Array.from(new Set(members.map((member) => member[key]).filter(Boolean)));
  if (values.length === 1) {
    return values[0];
  }
  if (values.length > 1) {
    return "Mixed";
  }
  return fallback || null;
}

function isBetterBenchmarkScore(candidate, currentBest, benchmark) {
  const candidateValue = Number(candidate?.value);
  const bestValue = Number(currentBest?.value);
  if (Number.isNaN(candidateValue)) {
    return false;
  }
  if (Number.isNaN(bestValue)) {
    return true;
  }

  const higherIsBetter = benchmark?.higher_is_better !== false;
  if (candidateValue !== bestValue) {
    return higherIsBetter ? candidateValue > bestValue : candidateValue < bestValue;
  }

  return String(candidate?.collected_at || "") > String(currentBest?.collected_at || "");
}

function extractFamilyName(name) {
  if (!name) {
    return "";
  }

  if (isSlugLike(name)) {
    return stripSlugVariantSuffix(name);
  }

  return stripFriendlyVariantSuffix(name);
}

function stripFriendlyVariantSuffix(name) {
  let next = String(name).trim();
  next = next.replace(/\s+20\d{6}$/i, "");
  next = next.replace(/\s*\(([^)]*)\)\s*$/i, "");
  return next.trim();
}

function stripSlugVariantSuffix(name) {
  let next = String(name).trim();
  let previous;

  do {
    previous = next;
    next = next.replace(/-20\d{6}$/i, "");
    next = next.replace(/-(?:\d+k-)?thinking(?:-\d+k)?$/i, "");
    next = next.replace(/-thinking(?:-\d+k)?$/i, "");
    next = next.replace(/-(?:no-thinking|max|adaptive)$/i, "");
    next = next.replace(/-non-reasoning(?:-low-effort)?$/i, "");
  } while (next !== previous);

  return next;
}

function hasVariantSuffix(name) {
  return /\([^)]*\)\s*$/i.test(name) || /-(?:20\d{6}|thinking(?:-\d+k)?|no-thinking|max|adaptive|non-reasoning(?:-low-effort)?)$/i.test(name);
}

function isSlugLike(name) {
  return /^[a-z0-9-]+$/i.test(String(name).trim());
}

function slugifyText(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeBenchmarkValue(benchmark, value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return 50;
  }

  const rangeMin = Number(benchmark?.range_min);
  const rangeMax = Number(benchmark?.range_max);
  if (Number.isFinite(rangeMin) && Number.isFinite(rangeMax) && rangeMax > rangeMin) {
    const scaled = ((numeric - rangeMin) / (rangeMax - rangeMin)) * 100;
    const normalized = benchmark?.higher_is_better === false ? 100 - scaled : scaled;
    return Math.max(0, Math.min(100, normalized));
  }

  if (rangeMax === rangeMin && Number.isFinite(rangeMin)) {
    return 75;
  }

  return Math.max(0, Math.min(100, numeric <= 1.5 ? numeric * 100 : numeric));
}

function formatScore(value) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  if (Math.abs(numeric) >= 1000) {
    return numeric.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (Number.isInteger(numeric)) {
    return String(numeric);
  }
  return numeric.toFixed(1).replace(/\.0$/, "");
}

function formatBenchmarkValue(benchmark, value) {
  if (!benchmark) {
    return formatScore(value);
  }

  const metric = String(benchmark.metric || "");
  if (metric.includes("Tokens/sec")) {
    return `${formatScore(value)} t/s`;
  }
  if (metric.includes("$/")) {
    return `$${formatScore(value)}`;
  }
  if (metric.includes("%") || metric.includes("Accuracy") || metric.includes("Grade")) {
    return `${formatScore(value)}%`;
  }
  return formatScore(value);
}

function formatDate(value) {
  if (!value) {
    return "Not updated yet";
  }
  const text = String(value);
  if (text.includes("T")) {
    const date = new Date(text);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }
  }
  return text;
}

function formatSourceHost(url) {
  if (!url) {
    return "";
  }

  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return String(url);
  }
}

function getBenchmarkContext(benchmark) {
  const sourceHost = formatSourceHost(benchmark?.url);
  const fallbackSource = benchmark?.source ? `${benchmark.source}${sourceHost ? ` · ${sourceHost}` : ""}` : sourceHost || "benchmark source";

  const contextByBenchmarkId = {
    aa_intelligence: {
      source: "Artificial Analysis · independent frontier model leaderboard",
      why: "best single-number snapshot here for broad model capability when you need an overall quality signal.",
    },
    aa_speed: {
      source: "Artificial Analysis · throughput leaderboard",
      why: "strongest quick signal here for real-time UX, concurrency, and queue-processing latency.",
    },
    aa_cost: {
      source: "Artificial Analysis · normalized model pricing data",
      why: "best quick read on whether a model is financially viable at production volume.",
    },
    chatbot_arena: {
      source: "Arena.ai / LMSYS lineage · blind human preference votes",
      why: "strong proxy for chat quality, helpfulness, and which answers people actually prefer.",
    },
    gpqa_diamond: {
      source: "Epoch AI · contamination-resistant reasoning benchmark",
      why: "one of the better signals here for hard reasoning beyond memorized benchmark performance.",
    },
    mmmu: {
      source: "MMMU benchmark team · multimodal academic benchmark",
      why: "best current signal here for document, chart, screenshot, and image reasoning.",
    },
    swebench_verified: {
      source: "SWE-bench team · verified GitHub issue benchmark",
      why: "best signal here for repo-level bug fixing and code-change execution.",
      caveat: "still a benchmark, not a complete substitute for your own engineering evals.",
    },
    terminal_bench: {
      source: "tbench.ai · public verified leaderboard for agent submissions",
      why: "strongest signal here for real tool use and terminal workflows, so it matters heavily for enterprise agents.",
      caveat: "scores are agent-derived from verified single-model submissions, not a pure model-only benchmark.",
    },
    ifeval: {
      source: "llm-stats / ZeroEval feed · instruction-following leaderboard",
      why: "useful proxy for instruction obedience, formatting reliability, and workflow discipline in enterprise prompts.",
      caveat: "we treat this as lower-trust than fully primary benchmark publishers.",
    },
    ailuminate: {
      source: "MLCommons AILuminate · public named safety results",
      why: "best current signal here for deployment risk, refusal quality, and enterprise guardrails.",
    },
    rag_groundedness: {
      source: "Vectara hallucination leaderboard · factual consistency evaluation",
      why: "useful groundedness signal for whether answers stay faithful to supplied source text.",
      caveat: "measures faithfulness to provided context, not retrieval relevance on your private corpus.",
    },
    rag_task_faithfulness: {
      source: "Vectara FaithJudge leaderboard · RAG task hallucination benchmark",
      why: "more direct signal for hallucination across RAG-style tasks than generic chat benchmarks.",
      caveat: "still measures faithfulness on supplied context, not end-to-end retrieval quality.",
    },
  };

  return contextByBenchmarkId[benchmark?.id] || {
    source: fallbackSource,
    why: benchmark?.description || "useful benchmark evidence for this model decision.",
    caveat: "",
  };
}

const styles = `
  :root {
    color-scheme: light;
    --bg: #f8fafc;
    --panel: rgba(255, 255, 255, 0.9);
    --panel-strong: #ffffff;
    --line: rgba(148, 163, 184, 0.22);
    --text: #0f172a;
    --muted: #64748b;
    --accent: #4f46e5;
    --accent-soft: rgba(79, 70, 229, 0.08);
    --good: #16a34a;
    --warn: #f59e0b;
    --bad: #ef4444;
    --shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
  }

  * { box-sizing: border-box; }
  html, body, #root { min-height: 100%; }
  body {
    margin: 0;
    font-family: Inter, system-ui, sans-serif;
    color: var(--text);
    background:
      radial-gradient(circle at top left, rgba(79, 70, 229, 0.12), transparent 28%),
      radial-gradient(circle at top right, rgba(245, 158, 11, 0.11), transparent 24%),
      linear-gradient(180deg, #f8fafc 0%, #eef2ff 100%);
  }
  button, input, select { font: inherit; }
  a { color: inherit; text-decoration: none; }
  .shell {
    min-height: 100vh;
  }
  .topbar {
    max-width: 1160px;
    margin: 0 auto;
    padding: 24px 20px 18px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
  }
  h1, h2, h3 {
    margin: 0;
    font-family: "Space Grotesk", Inter, system-ui, sans-serif;
    letter-spacing: -0.02em;
  }
  h1 { font-size: clamp(1.45rem, 2vw, 2rem); }
  h2 { font-size: clamp(1.1rem, 1.6vw, 1.3rem); }
  h3 { font-size: 1rem; }
  .eyebrow, .meta, .version, .hint, .submeta, .tip, .small-meta, .panel-copy, .note, .coverage-label, .history-note, .history-errors, .detail-label, .bench-date, .metric, .message {
    color: var(--muted);
  }
  .eyebrow {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.18em;
    margin-bottom: 8px;
  }
  .meta {
    margin-top: 6px;
    font-size: 0.88rem;
  }
  .topbar-actions {
    display: flex;
    align-items: flex-end;
    justify-content: flex-end;
    gap: 10px;
    flex-wrap: wrap;
  }
  .version {
    border: 1px solid var(--line);
    background: var(--panel);
    padding: 8px 12px;
    border-radius: 999px;
    box-shadow: var(--shadow);
  }
  .btn {
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 10px 14px;
    cursor: pointer;
    background: var(--panel-strong);
    color: var(--text);
    transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
  }
  .btn:hover { transform: translateY(-1px); }
  .btn:disabled { cursor: not-allowed; opacity: .7; transform: none; }
  .btn-primary {
    background: linear-gradient(135deg, #4f46e5, #4338ca);
    color: white;
    border-color: rgba(67, 56, 202, .35);
  }
  .btn-secondary {
    background: #fff;
  }
  .btn-active {
    background: #4f46e5;
    color: #fff;
    border-color: #4f46e5;
  }
  .tabs {
    position: sticky;
    top: 0;
    z-index: 20;
    backdrop-filter: blur(16px);
    background: rgba(255, 255, 255, 0.72);
    border-top: 1px solid rgba(255,255,255,.5);
    border-bottom: 1px solid var(--line);
  }
  .tabs-inner {
    max-width: 1160px;
    margin: 0 auto;
    padding: 0 20px;
    display: flex;
    overflow-x: auto;
    gap: 0;
  }
  .tab {
    border: 0;
    background: transparent;
    padding: 14px 16px;
    border-bottom: 2px solid transparent;
    color: var(--muted);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    white-space: nowrap;
  }
  .tab-active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }
  .page {
    max-width: 1160px;
    margin: 0 auto;
    padding: 28px 20px 44px;
  }
  .stack { display: grid; gap: 14px; }
  .stack-tight { display: grid; gap: 8px; }
  .section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }
  .toggle-group {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px;
    border: 1px solid var(--line);
    border-radius: 999px;
    background: rgba(255,255,255,.92);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  }
  .toggle-btn {
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 8px 12px;
    border-radius: 999px;
    font-weight: 700;
    cursor: pointer;
  }
  .toggle-btn-active {
    background: rgba(79, 70, 229, .10);
    color: var(--accent);
  }
  .pill, .badge, .tag, .compare-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 999px;
    padding: 6px 10px;
    font-size: 0.77rem;
    border: 1px solid var(--line);
    background: rgba(255,255,255,.92);
  }
  .pill-good {
    color: #166534;
    background: rgba(220, 252, 231, .95);
    border-color: rgba(34, 197, 94, .22);
  }
  .pill-bad {
    color: #991b1b;
    background: rgba(254, 242, 242, .95);
    border-color: rgba(248, 113, 113, .22);
  }
  .badge-slate { background: rgba(148, 163, 184, .14); color: #334155; }
  .badge-indigo, .tag-top {
    background: rgba(79, 70, 229, .10);
    color: var(--accent);
    border-color: rgba(79, 70, 229, .18);
  }
  .tag-ready {
    background: rgba(34, 197, 94, .10);
    color: #166534;
    border-color: rgba(34, 197, 94, .22);
  }
  .tag-preview {
    background: rgba(245, 158, 11, .12);
    color: #92400e;
    border-color: rgba(245, 158, 11, .22);
  }
  .tag-warning {
    background: rgba(251, 146, 60, .12);
    color: #9a3412;
    border-color: rgba(251, 146, 60, .22);
  }
  .badge-orange { background: rgba(249, 115, 22, .10); color: #9a3412; }
  .badge-green { background: rgba(34, 197, 94, .10); color: #166534; }
  .badge-blue { background: rgba(59, 130, 246, .10); color: #1d4ed8; }
  .badge-violet { background: rgba(139, 92, 246, .10); color: #6d28d9; }
  .badge-pink { background: rgba(236, 72, 153, .10); color: #be185d; }
  .tag-family {
    background: rgba(14, 165, 233, .10);
    color: #0f766e;
    border-color: rgba(14, 165, 233, .18);
  }
  .badge-slate, .badge-indigo, .badge-orange, .badge-green, .badge-blue, .badge-violet, .badge-pink {
    font-weight: 600;
  }
  .usecase-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .usecase-sections, .usecase-section {
    display: grid;
    gap: 14px;
  }
  .usecase-section-head {
    display: grid;
    gap: 4px;
  }
  .usecase-section-copy {
    color: var(--muted);
    font-size: .83rem;
    max-width: 720px;
  }
  @media (min-width: 760px) {
    .usecase-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  }
  .usecase, .card, .panel, .summary, .table, .banner, .empty, .loading-card {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--panel);
    box-shadow: var(--shadow);
  }
  .usecase {
    text-align: left;
    padding: 16px;
    cursor: pointer;
    transition: transform .15s ease, border-color .15s ease, background .15s ease;
  }
  .usecase:hover, .card-clickable:hover { transform: translateY(-1px); }
  .usecase-active {
    border-color: rgba(79, 70, 229, .4);
    background: rgba(239, 246, 255, .95);
  }
  .usecase-topline {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 12px;
  }
  .usecase-icon { font-size: 1.45rem; }
  .usecase-label { font-weight: 700; font-size: .92rem; color: #111827; }
  .usecase-desc { margin-top: 6px; font-size: .77rem; line-height: 1.3; color: var(--muted); }
  .usecase-meta {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 10px;
    font-size: .74rem;
    color: var(--muted);
  }
  .usecase-chip-list {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
  }
  .usecase-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 4px 8px;
    font-size: .72rem;
    color: #334155;
    background: rgba(255,255,255,.92);
    border: 1px solid rgba(148, 163, 184, .18);
  }
  .usecase-chip-required {
    background: rgba(239, 246, 255, .95);
    border-color: rgba(59, 130, 246, .16);
  }
  .usecase-status-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }
  .preview-note, .usecase-note-caption {
    font-size: .78rem;
    line-height: 1.45;
    color: var(--muted);
  }
  .preview-note {
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid rgba(245, 158, 11, .18);
    background: rgba(255, 251, 235, .88);
  }
  .usecase-notes {
    display: grid;
    gap: 8px;
    margin-top: 12px;
  }
  .usecase-note-item {
    display: grid;
    gap: 2px;
    font-size: .78rem;
    line-height: 1.4;
    color: var(--muted);
  }
  .tag-enterprise {
    background: rgba(2, 132, 199, .10);
    color: #0f766e;
    border-color: rgba(14, 165, 233, .22);
  }
  .card, .panel, .banner, .summary, .table, .empty { overflow: hidden; }
  .card-body {
    padding: 16px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .card-clickable { cursor: pointer; }
  .rank-pill {
    width: 32px;
    height: 32px;
    border-radius: 999px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    background: rgba(148, 163, 184, .12);
    color: #334155;
    font-weight: 800;
  }
  .card-top .rank-pill {
    background: rgba(79, 70, 229, .92);
    color: white;
  }
  .card-main { flex: 1; min-width: 0; }
  .card-headline {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }
  .title { font-weight: 700; color: #0f172a; }
  .submeta {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    font-size: .78rem;
  }
  .coverage-good { color: #16a34a; }
  .coverage-warn { color: #d97706; }
  .card-actions {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .chev, .link-btn {
    color: var(--accent);
    background: transparent;
    border: 0;
    cursor: pointer;
    font-weight: 700;
  }
  .card-details {
    border-top: 1px solid rgba(148, 163, 184, .16);
    background: rgba(248, 250, 252, .8);
    padding: 14px 16px;
  }
  .critical-gaps {
    margin-bottom: 10px;
    padding: 10px 12px;
    border-radius: 12px;
    background: rgba(255, 247, 237, .9);
    border: 1px solid rgba(251, 146, 60, .22);
    color: #9a3412;
    font-size: .78rem;
    line-height: 1.45;
  }
  .detail-label { font-size: .76rem; font-weight: 700; margin-bottom: 10px; }
  .detail-list, .bench-grid, .history-list { display: grid; gap: 8px; }
  .member-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .member-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    padding: 6px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255,255,255,.94);
    color: #334155;
    font-size: .76rem;
  }
  .detail-row {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr) auto auto;
    gap: 8px;
    align-items: center;
  }
  .bench-row {
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr) auto auto;
    gap: 8px;
    align-items: center;
  }
  .detail-short, .bench-short {
    font-size: .75rem;
    color: #475569;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .bench-link {
    color: var(--accent);
  }
  .bench-score, .score {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .detail-value {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .detail-weight {
    font-size: .72rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .detail-note {
    grid-column: 2 / 5;
    font-size: .76rem;
    color: var(--muted);
    line-height: 1.45;
  }
  .bench-variant, .cell-variant, .bench-provenance {
    color: var(--muted);
    font-size: .76rem;
  }
  .bench-source, .bench-context, .bench-caveat {
    grid-column: 2 / 5;
    font-size: .76rem;
    line-height: 1.45;
  }
  .bench-source {
    color: var(--accent);
  }
  .bench-provenance {
    grid-column: 2 / 4;
    line-height: 1.45;
  }
  .bench-context {
    color: var(--muted);
  }
  .bench-caveat {
    color: #92400e;
  }
  .source-badge {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 999px;
    padding: 2px 6px;
    font-size: .62rem;
    font-weight: 800;
    letter-spacing: .04em;
    border: 1px solid transparent;
  }
  .source-badge-verified {
    color: #166534;
    background: rgba(220, 252, 231, .95);
    border-color: rgba(34, 197, 94, .22);
  }
  .source-badge-secondary {
    color: #92400e;
    background: rgba(254, 243, 199, .95);
    border-color: rgba(245, 158, 11, .22);
  }
  .source-badge-manual {
    color: #334155;
    background: rgba(226, 232, 240, .9);
    border-color: rgba(148, 163, 184, .25);
  }
  .mini-bar, .score-track, .coverage-track {
    width: 100%;
    height: 8px;
    background: rgba(226, 232, 240, 0.9);
    border-radius: 999px;
    overflow: hidden;
  }
  .score-track { height: 10px; }
  .mini-fill, .score-fill, .coverage-fill {
    height: 100%;
    border-radius: inherit;
  }
  .score-row, .coverage-row {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .score-row { margin-bottom: 8px; }
  .score-value {
    width: 42px;
    text-align: right;
    font-weight: 800;
  }
  .score-good, .coverage-good { background: linear-gradient(90deg, #22c55e, #16a34a); color: #166534; }
  .score-warn, .coverage-warn { background: linear-gradient(90deg, #f59e0b, #d97706); color: #92400e; }
  .score-bad, .coverage-muted { background: linear-gradient(90deg, #f87171, #ef4444); color: #b91c1c; }
  .coverage-label { width: 60px; text-align: right; font-size: .78rem; }
  .small-meta, .tip { margin-top: 10px; font-size: .78rem; }
  .note {
    padding: 12px 14px;
    border: 1px solid rgba(245, 158, 11, .2);
    border-radius: 14px;
    background: rgba(255, 251, 235, .85);
    font-size: .8rem;
    line-height: 1.45;
  }
  .note-list { display: inline; margin-left: 4px; }
  .panel {
    padding: 16px;
    display: grid;
    gap: 12px;
  }
  .panel-head { font-weight: 700; }
  .panel-copy { margin: 0; line-height: 1.5; }
  .method-grid, .methodology-usecases, .methodology-benchmarks {
    display: grid;
    gap: 12px;
  }
  .method-card {
    align-content: start;
  }
  .method-card-soft {
    padding: 14px;
    border-radius: 14px;
    border: 1px solid rgba(148, 163, 184, .14);
    background: rgba(248, 250, 252, .8);
  }
  .method-copy, .method-subtle {
    font-size: .82rem;
    line-height: 1.5;
    color: var(--muted);
  }
  .method-list, .method-steps, .weight-list {
    display: grid;
    gap: 8px;
  }
  .method-list > div, .method-step {
    font-size: .8rem;
    line-height: 1.45;
    color: #334155;
  }
  .method-step strong {
    display: inline-block;
    width: 18px;
    color: var(--accent);
  }
  .method-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .method-badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: 999px;
    padding: 8px 10px;
    border: 1px solid rgba(148, 163, 184, .18);
    background: rgba(255,255,255,.94);
    font-size: .75rem;
    color: #334155;
  }
  .method-focus-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }
  .method-focus-title {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }
  .weight-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: .78rem;
    color: #334155;
    border-bottom: 1px solid rgba(148, 163, 184, .12);
    padding-bottom: 6px;
  }
  .weight-row:last-child {
    border-bottom: 0;
    padding-bottom: 0;
  }
  .toolbar {
    display: grid;
    grid-template-columns: 1fr;
    gap: 10px;
    margin-bottom: 10px;
  }
  @media (min-width: 860px) {
    .toolbar { grid-template-columns: minmax(0, 1fr) 220px 220px; }
    .method-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .methodology-usecases { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .methodology-benchmarks { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  .input, .select {
    width: 100%;
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 12px 14px;
    background: rgba(255,255,255,.95);
    color: var(--text);
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.04);
  }
  .stack > .panel, .stack > .card, .stack > .table, .stack > .banner, .stack > .empty {
    margin-top: 2px;
  }
  .table { display: grid; }
  .table-head, .table-row {
    display: grid;
    gap: 0;
  }
  .table-head {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(148, 163, 184, .16);
    background: rgba(248, 250, 252, .9);
    font-size: .75rem;
    font-weight: 800;
    letter-spacing: .04em;
    text-transform: uppercase;
    color: #64748b;
  }
  .table-row {
    padding: 14px 16px;
    border-bottom: 1px solid rgba(241, 245, 249, .85);
    align-items: center;
  }
  .table-row:last-child { border-bottom: 0; }
  .metric { font-size: .76rem; margin-top: 4px; }
  .cell, .cell-winner { padding: 0 8px; }
  .cell-score {
    display: grid;
    gap: 4px;
  }
  .cell-winner { font-weight: 700; }
  .score-winner { color: #166534; }
  .cell-empty { color: #cbd5e1; }
  .compare-summary {
    display: grid;
    gap: 12px;
  }
  .summary {
    padding: 16px;
    text-align: center;
  }
  .summary-top { border-color: rgba(79, 70, 229, .3); }
  .summary-title { font-weight: 700; margin-bottom: 8px; }
  .summary-score { margin-top: 14px; }
  .summary-score span { font-size: 2rem; font-weight: 800; color: var(--accent); display: block; line-height: 1; }
  .summary-score small, .summary-foot { color: var(--muted); }
  .summary-foot { margin-top: 6px; font-size: .78rem; }
  .compare-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 10px;
  }
  .compare-pill button {
    border: 0;
    background: transparent;
    color: var(--accent);
    cursor: pointer;
    font-weight: 800;
  }
  .suggestions {
    margin-top: 10px;
    border: 1px solid rgba(226, 232, 240, .9);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: var(--shadow);
  }
  .suggestion {
    width: 100%;
    padding: 12px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border: 0;
    background: #fff;
    border-bottom: 1px solid rgba(241, 245, 249, .9);
    cursor: pointer;
  }
  .suggestion:last-child { border-bottom: 0; }
  .history-list { gap: 12px; }
  .history-item {
    display: flex;
    gap: 14px;
    align-items: flex-start;
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 16px;
    background: rgba(255,255,255,.9);
    box-shadow: var(--shadow);
  }
  .history-entry {
    display: grid;
    gap: 12px;
  }
  .history-toggle {
    border: 0;
    background: transparent;
    padding: 0;
    width: 100%;
    display: flex;
    align-items: flex-start;
    gap: 14px;
    text-align: left;
    cursor: pointer;
  }
  .history-main {
    min-width: 0;
    flex: 1 1 auto;
  }
  .history-chevron {
    color: var(--accent);
    font-weight: 800;
  }
  .history-dot {
    width: 10px;
    height: 10px;
    margin-top: 6px;
    border-radius: 999px;
    background: #818cf8;
    flex: 0 0 auto;
  }
  .history-date { font-weight: 700; margin-bottom: 4px; }
  .history-note, .history-errors { font-size: .82rem; line-height: 1.5; }
  .history-errors { color: #b91c1c; margin-top: 4px; }
  .history-sources {
    display: grid;
    gap: 10px;
    border-top: 1px solid rgba(148, 163, 184, .16);
    padding-top: 12px;
  }
  .history-source-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    border: 0;
    background: transparent;
    width: 100%;
    padding: 0;
    text-align: left;
    cursor: pointer;
  }
  .history-source-card {
    display: grid;
    gap: 8px;
    padding: 10px 0;
    border-top: 1px solid rgba(148, 163, 184, .12);
  }
  .history-source-card:first-child { border-top: 0; padding-top: 0; }
  .history-source-name {
    font-weight: 700;
    color: var(--text);
  }
  .history-source-meta, .history-sources-empty {
    font-size: .78rem;
    color: var(--muted);
  }
  .history-source-status {
    display: grid;
    justify-items: end;
    gap: 6px;
  }
  .history-source-chevron {
    color: var(--accent);
    font-size: .8rem;
    font-weight: 800;
  }
  .history-source-error {
    font-size: .76rem;
    color: #b91c1c;
    text-align: right;
    max-width: 280px;
  }
  .history-raw-panel {
    display: grid;
    gap: 8px;
    margin-left: 0;
    padding: 10px 12px;
    border: 1px solid rgba(148, 163, 184, .16);
    border-radius: 12px;
    background: rgba(248, 250, 252, .88);
  }
  .history-raw-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .history-raw-note, .history-raw-empty, .history-raw-meta {
    font-size: .76rem;
    color: var(--muted);
  }
  .history-raw-list {
    display: grid;
    gap: 6px;
  }
  .history-raw-row {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: baseline;
  }
  .history-raw-name {
    font-size: .8rem;
    color: var(--text);
  }
  .banner {
    padding: 14px 16px;
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .banner-error {
    background: rgba(254, 242, 242, .95);
    border-color: rgba(248, 113, 113, .22);
    color: #991b1b;
  }
  .banner-info {
    background: rgba(239, 246, 255, .95);
    border-color: rgba(96, 165, 250, .22);
    color: #1e3a8a;
  }
  .empty {
    padding: 22px;
    text-align: center;
    color: var(--muted);
    background: rgba(255,255,255,.9);
  }
  .loading {
    display: grid;
    gap: 14px;
  }
  .loading-card {
    height: 110px;
    background: linear-gradient(90deg, rgba(226, 232, 240, .6), rgba(241, 245, 249, .95), rgba(226, 232, 240, .6));
    background-size: 200% 100%;
    animation: shimmer 1.4s infinite linear;
  }
  .toast {
    position: fixed;
    right: 18px;
    bottom: 18px;
    max-width: min(420px, calc(100vw - 36px));
    padding: 14px 16px;
    border-radius: 14px;
    background: rgba(15, 23, 42, .94);
    color: white;
    box-shadow: 0 18px 60px rgba(15, 23, 42, .24);
  }
  @keyframes shimmer {
    0% { background-position: 0 0; }
    100% { background-position: -200% 0; }
  }
  @media (max-width: 860px) {
    .topbar { flex-direction: column; }
    .section-head { flex-direction: column; align-items: flex-start; }
    .card-body { flex-direction: column; }
    .card-actions { width: 100%; justify-content: space-between; }
    .compare-summary { grid-template-columns: 1fr !important; }
    .table-head, .table-row { grid-template-columns: 1fr !important; }
    .table-row > div { margin-bottom: 8px; }
    .detail-row, .bench-row { grid-template-columns: 82px minmax(0, 1fr); }
    .detail-weight { grid-column: 2; }
    .detail-note, .bench-provenance, .bench-source, .bench-context, .bench-caveat { grid-column: 2; }
    .history-source-row { flex-direction: column; }
    .history-source-status { justify-items: start; }
    .history-source-error { max-width: none; text-align: left; }
  }
`;

export default App;
