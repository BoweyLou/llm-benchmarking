import React, { useMemo, useState } from "react";

function providerColor(provider) {
  const map = {
    Anthropic: "border-orange-200 bg-orange-100 text-orange-800",
    OpenAI: "border-green-200 bg-green-100 text-green-800",
    Google: "border-blue-200 bg-blue-100 text-blue-800",
    "Zhipu AI": "border-purple-200 bg-purple-100 text-purple-800",
    "Inception Labs": "border-pink-200 bg-pink-100 text-pink-800",
    default: "border-gray-200 bg-gray-100 text-gray-700",
  };
  return map[provider] || map.default;
}

function normalizeValue(benchmark, value) {
  if (!benchmark || value == null) return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;

  const range = benchmark.range || {};
  const min = Number.isFinite(range.min) ? range.min : null;
  const max = Number.isFinite(range.max) ? range.max : null;
  if (min === null || max === null || max === min) return 50;

  let normalized = ((numeric - min) / (max - min)) * 100;
  if (!benchmark.higher_is_better) normalized = 100 - normalized;
  return Math.max(0, Math.min(100, normalized));
}

function scoreColor(score) {
  if (score >= 75) return "text-green-700";
  if (score >= 50) return "text-yellow-700";
  return "text-red-600";
}

function scoreBg(score) {
  if (score >= 75) return "bg-green-500";
  if (score >= 50) return "bg-yellow-400";
  return "bg-red-400";
}

function formatValue(benchmark, value) {
  if (!benchmark) return String(value);
  if (benchmark.metric?.includes("Tokens/sec")) return `${value} t/s`;
  if (benchmark.metric?.includes("$/")) return `$${value}`;
  if (benchmark.metric?.includes("%") || benchmark.metric?.includes("Accuracy")) return `${value}%`;
  return String(value);
}

function providerBadge(provider) {
  return `inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${providerColor(provider)}`;
}

function sourceIndicator(score) {
  const sourceType = score?.source_type || "primary";
  if (sourceType === "secondary") return { icon: "~", className: "text-amber-600 bg-amber-50 border-amber-200" };
  if (sourceType === "manual") return { icon: "✎", className: "text-gray-600 bg-gray-100 border-gray-200" };
  return score?.verified ? { icon: "✓", className: "text-green-700 bg-green-50 border-green-200" } : { icon: "✓", className: "text-gray-500 bg-gray-100 border-gray-200" };
}

function SourceBadge({ score }) {
  if (!score) return null;
  const indicator = sourceIndicator(score);
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] font-bold ${indicator.className}`} title={score.source_type}>
      {indicator.icon}
    </span>
  );
}

function ModelBrowserCard({ model, expanded, onToggle, onToggleCompare, inCompare, benchmarks }) {
  const scoredBenchmarks = benchmarks.filter((benchmark) => model.scores?.[benchmark.id]?.value != null);
  const dataPct = Math.round((scoredBenchmarks.length / Math.max(benchmarks.length, 1)) * 100);

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
      <div className="flex cursor-pointer items-center gap-3 p-4" onClick={onToggle}>
        <div className="flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="font-semibold text-gray-900">{model.name}</span>
            <span className={providerBadge(model.provider)}>{model.provider}</span>
            <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${model.type === "open_weights" ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-gray-200 bg-gray-100 text-gray-600"}`}>
              {model.type === "open_weights" ? "Open weights" : "Proprietary"}
            </span>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-gray-400">
            <span>Context: {model.context_window || "Unknown"}</span>
            <span>Released: {model.release_date || "Unknown"}</span>
            <span className={dataPct >= 50 ? "text-green-600" : "text-amber-500"}>{dataPct}% benchmark coverage</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onToggleCompare?.(model.id);
            }}
            className={`rounded border px-2.5 py-1 text-xs font-medium transition-all ${
              inCompare
                ? "border-indigo-600 bg-indigo-600 text-white"
                : "border-gray-300 text-gray-600 hover:border-indigo-400 hover:text-indigo-600"
            }`}
          >
            {inCompare ? "✓ In compare" : "+ Compare"}
          </button>
          <span className="text-sm text-gray-300">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {expanded ? (
        <div className="fade-in border-t border-gray-100 bg-gray-50 px-4 py-4">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {benchmarks.map((benchmark) => {
              const score = model.scores?.[benchmark.id];
              const hasData = score?.value != null;
              const normalized = hasData ? normalizeValue(benchmark, score.value) : null;

              return (
                <div key={benchmark.id} className="flex items-center gap-2">
                  <a
                    href={benchmark.url}
                    target="_blank"
                    rel="noreferrer"
                    className="w-20 flex-shrink-0 truncate text-xs text-indigo-500 hover:text-indigo-700"
                    title={benchmark.name}
                  >
                    {benchmark.short}
                  </a>
                  {hasData ? (
                    <>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200">
                        <div className={`h-full rounded-full ${scoreBg(normalized ?? 50)}`} style={{ width: `${normalized ?? 50}%` }} />
                      </div>
                      <div className="flex w-24 items-center justify-end gap-1.5">
                        <SourceBadge score={score} />
                        <span className="text-xs font-medium text-gray-700">{formatValue(benchmark, score.value)}</span>
                      </div>
                      <span className="w-12 text-right text-xs text-gray-300">{score.collected_at?.slice(0, 10)}</span>
                    </>
                  ) : (
                    <span className="flex-1 text-xs text-gray-300">— no data</span>
                  )}
                </div>
              );
            })}
          </div>
          <div className="mt-3 text-xs text-gray-400">Tip: Click any benchmark name to view the source leaderboard. Missing scores can be populated by running an update.</div>
        </div>
      ) : null}
    </div>
  );
}

export default function ModelBrowser({
  models = [],
  benchmarks = [],
  compareIds = [],
  onToggleCompare,
}) {
  const [query, setQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState("All");
  const [typeFilter, setTypeFilter] = useState("All");
  const [expandedId, setExpandedId] = useState(null);

  const providers = useMemo(() => ["All", ...Array.from(new Set(models.map((model) => model.provider))).sort()], [models]);

  const filtered = useMemo(() => {
    const search = query.toLowerCase();
    return models.filter((model) => {
      const matchQuery = model.name.toLowerCase().includes(search) || model.provider.toLowerCase().includes(search);
      const matchProvider = providerFilter === "All" || model.provider === providerFilter;
      const matchType = typeFilter === "All" || model.type === typeFilter;
      return matchQuery && matchProvider && matchType;
    });
  }, [models, query, providerFilter, typeFilter]);

  return (
    <div className="fade-in">
      <div className="mb-5">
        <h2 className="mb-1 text-xl font-semibold text-gray-800">Model Browser</h2>
        <p className="text-sm text-gray-500">Search and explore all tracked models with their full benchmark profiles.</p>
      </div>

      <div className="mb-5 flex flex-wrap gap-3">
        <input
          type="text"
          placeholder="Search models..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className="min-w-48 flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <select
          value={providerFilter}
          onChange={(event) => setProviderFilter(event.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          {providers.map((provider) => (
            <option key={provider} value={provider}>{provider}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(event) => setTypeFilter(event.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="All">All types</option>
          <option value="proprietary">Proprietary</option>
          <option value="open_weights">Open weights</option>
        </select>
      </div>

      <div className="space-y-2">
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-gray-200 bg-white py-12 text-center text-gray-400">No models match your search.</div>
        ) : null}
        {filtered.map((model) => (
          <ModelBrowserCard
            key={model.id}
            model={model}
            expanded={expandedId === model.id}
            onToggle={() => setExpandedId((current) => (current === model.id ? null : model.id))}
            onToggleCompare={onToggleCompare}
            inCompare={compareIds.includes(model.id)}
            benchmarks={benchmarks}
          />
        ))}
      </div>
    </div>
  );
}
