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

function formatValue(benchmarkId, value, benchmarksById = {}) {
  const benchmark = benchmarksById[benchmarkId];
  if (!benchmark) return String(value);

  if (benchmark.metric?.includes("Tokens/sec")) return `${value} t/s`;
  if (benchmark.metric?.includes("$/")) return `$${value}`;
  if (benchmark.metric?.includes("%") || benchmark.metric?.includes("Accuracy")) return `${value}%`;
  if (benchmark.metric?.toLowerCase().includes("elo")) return String(value);
  return String(value);
}

function ProviderBadge({ provider }) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${providerColor(provider)}`}>
      {provider}
    </span>
  );
}

function TypeBadge({ type }) {
  if (type === "open_weights") {
    return <span className="inline-flex items-center rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">Open weights</span>;
  }
  return <span className="inline-flex items-center rounded border border-gray-200 bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">Proprietary</span>;
}

function CoverageIndicator({ coverage }) {
  const pct = Math.round((coverage || 0) * 100);
  const color = pct >= 70 ? "bg-green-400" : pct >= 40 ? "bg-yellow-400" : "bg-gray-300";
  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-gray-200">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{pct}% data</span>
    </div>
  );
}

function ScoreBar({ score }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${scoreBg(score)}`} style={{ width: `${score}%` }} />
      </div>
      <span className={`w-10 text-right text-sm font-bold ${scoreColor(score)}`}>{Math.round(score)}</span>
    </div>
  );
}

function RankedModelCard({ model, result, rank, benchmarksById }) {
  const [expanded, setExpanded] = useState(false);
  const isTop = rank === 1;

  return (
    <div className={`overflow-hidden rounded-xl border ${isTop ? "border-indigo-300 shadow-sm" : "border-gray-200"} bg-white`}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-sm font-bold ${isTop ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500"}`}>
            {rank}
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="font-semibold text-gray-900">{model?.name}</span>
              <ProviderBadge provider={model?.provider || "Unknown"} />
              <TypeBadge type={model?.type || "proprietary"} />
              {isTop ? <span className="rounded border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-600">Top pick</span> : null}
            </div>
            <ScoreBar score={result.score} />
            <div className="mt-1.5">
              <CoverageIndicator coverage={result.coverage} />
            </div>
          </div>
          <button
            type="button"
            onClick={() => setExpanded((current) => !current)}
            className="flex-shrink-0 text-xs font-medium text-indigo-500 hover:text-indigo-700"
          >
            {expanded ? "▲ Less" : "▼ Detail"}
          </button>
        </div>
      </div>

      {expanded ? (
        <div className="fade-in border-t border-gray-100 bg-gray-50 px-4 py-3">
          <div className="mb-2 text-xs font-medium text-gray-500">Benchmark breakdown</div>
          <div className="space-y-1.5">
            {(result.breakdown || []).map(({ benchmark_id, normalised, raw_value }) => {
              const benchmark = benchmarksById[benchmark_id];
              return (
                <div key={benchmark_id} className="flex items-center gap-2">
                  <span className="w-24 truncate text-xs text-gray-500">{benchmark?.short || benchmark_id}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-gray-200">
                    <div className={`h-full rounded-full ${scoreBg(normalised)}`} style={{ width: `${normalised}%` }} />
                  </div>
                  <span className="w-20 text-right text-xs font-medium text-gray-700">{formatValue(benchmark_id, raw_value, benchmarksById)}</span>
                  <a href={benchmark?.url} target="_blank" rel="noreferrer" className="text-xs text-indigo-400 hover:text-indigo-600">↗</a>
                </div>
              );
            })}
            {(result.missing_benchmarks || []).length > 0 ? (
              <div className="pt-1 text-xs text-gray-400">
                Missing data: {(result.missing_benchmarks || []).map((id) => benchmarksById[id]?.short || id).join(", ")}
              </div>
            ) : null}
          </div>
          <div className="mt-2 text-xs text-gray-400">
            Context: {model?.context_window || "Unknown"} · Released: {model?.release_date || "Unknown"}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function UseCaseFinder({
  useCases = [],
  benchmarksById = {},
  selectedUseCaseId = null,
  rankings = [],
  isLoading = false,
  error = null,
  onSelectUseCase,
}) {
  const selected = useMemo(
    () => useCases.find((useCase) => useCase.id === selectedUseCaseId) || null,
    [selectedUseCaseId, useCases]
  );

  const benchmarkShorts = selected
    ? Object.keys(selected.weights || {})
        .map((id) => benchmarksById[id]?.short || id)
        .join(", ")
    : "";

  return (
    <div className="fade-in">
      <div className="mb-6">
        <h2 className="mb-1 text-xl font-semibold text-gray-800">Which model for my use case?</h2>
        <p className="text-sm text-gray-500">Select a use case to see models ranked by evidence from our benchmark sources.</p>
      </div>

      <div className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {useCases.map((useCase) => {
          const active = selected?.id === useCase.id;
          return (
            <button
              key={useCase.id}
              type="button"
              onClick={() => onSelectUseCase?.(active ? null : useCase.id)}
              className={`cursor-pointer rounded-xl border-2 p-4 text-left transition-all ${
                active ? "border-indigo-500 bg-indigo-50 shadow-sm" : "border-gray-200 bg-white hover:border-indigo-300 hover:shadow-sm"
              }`}
            >
              <div className="mb-2 text-2xl">{useCase.icon}</div>
              <div className="text-sm font-medium text-gray-800">{useCase.label}</div>
              <div className="mt-0.5 text-xs leading-tight text-gray-400">{useCase.description}</div>
            </button>
          );
        })}
      </div>

      {selected ? (
        <div className="fade-in">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold text-gray-800">
              {selected.icon} Best models for <span className="text-indigo-600">{selected.label}</span>
            </h3>
            <span className="text-xs text-gray-400">Ranked by weighted benchmark score</span>
          </div>

          {isLoading ? (
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-10 text-center text-gray-400">Loading rankings...</div>
          ) : error ? (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-10 text-center text-sm text-red-700">{error}</div>
          ) : rankings.length === 0 ? (
            <div className="rounded-xl border border-gray-200 bg-white px-4 py-12 text-center text-gray-400">
              No models have data for this use case yet. Trigger an update to populate scores.
            </div>
          ) : (
            <div className="space-y-3">
              {rankings.map(({ model, result, rank }) => (
                <RankedModelCard key={model.id} model={model} result={result} rank={rank} benchmarksById={benchmarksById} />
              ))}
            </div>
          )}

          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-700">
            <strong>Note:</strong> Rankings are weighted averages of available benchmark data.
            Models with low data coverage should be verified before use.
            {benchmarkShorts ? ` Benchmarks used: ${benchmarkShorts}.` : null}
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-200 bg-white px-4 py-12 text-center text-gray-400">
          Select a use case above to see the ranked list.
        </div>
      )}
    </div>
  );
}
