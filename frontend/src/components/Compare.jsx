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

function formatValue(benchmark, value) {
  if (!benchmark) return String(value);
  if (benchmark.metric?.includes("Tokens/sec")) return `${value} t/s`;
  if (benchmark.metric?.includes("$/")) return `$${value}`;
  if (benchmark.metric?.includes("%") || benchmark.metric?.includes("Accuracy")) return `${value}%`;
  return String(value);
}

function sourceIndicator(score) {
  const sourceType = score?.source_type || "primary";
  if (sourceType === "secondary") return { icon: "~", className: "text-amber-600" };
  if (sourceType === "manual") return { icon: "✎", className: "text-gray-600" };
  return score?.verified ? { icon: "✓", className: "text-green-700" } : { icon: "✓", className: "text-gray-500" };
}

function ProviderBadge({ provider }) {
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${providerColor(provider)}`}>
      {provider}
    </span>
  );
}

function winnerForBenchmark(models, benchmark) {
  const withData = models.filter((model) => model.scores?.[benchmark.id]?.value != null);
  if (withData.length < 2) return null;

  return withData.reduce((best, model) => {
    const currentScore = model.scores[benchmark.id].value;
    const bestScore = best.scores[benchmark.id].value;
    const better = benchmark.higher_is_better ? currentScore > bestScore : currentScore < bestScore;
    return better ? model : best;
  });
}

export default function Compare({
  models = [],
  benchmarks = [],
  compareIds = [],
  onToggleCompare,
}) {
  const [addQuery, setAddQuery] = useState("");

  const selectedModels = useMemo(() => models.filter((model) => compareIds.includes(model.id)), [models, compareIds]);
  const suggestions = useMemo(() => {
    const search = addQuery.toLowerCase();
    return models
      .filter((model) => !compareIds.includes(model.id))
      .filter((model) => model.name.toLowerCase().includes(search) || model.provider.toLowerCase().includes(search))
      .slice(0, 5);
  }, [models, compareIds, addQuery]);

  const benchmarksWithAnyData = useMemo(
    () => benchmarks.filter((benchmark) => selectedModels.some((model) => model.scores?.[benchmark.id]?.value != null)),
    [benchmarks, selectedModels]
  );

  const winCounts = useMemo(() => {
    const counts = Object.fromEntries(selectedModels.map((model) => [model.id, 0]));
    benchmarksWithAnyData.forEach((benchmark) => {
      const winner = winnerForBenchmark(selectedModels, benchmark);
      if (winner) counts[winner.id] = (counts[winner.id] || 0) + 1;
    });
    return counts;
  }, [selectedModels, benchmarksWithAnyData]);

  return (
    <div className="fade-in">
      <div className="mb-5">
        <h2 className="mb-1 text-xl font-semibold text-gray-800">Compare Models</h2>
        <p className="text-sm text-gray-500">Side-by-side benchmark comparison. Add models from the Model Browser or search below.</p>
      </div>

      <div className="mb-5 rounded-xl border border-gray-200 bg-white p-4">
        <div className="mb-3 text-sm font-medium text-gray-700">
          {selectedModels.length === 0 ? "Add models to compare" : `Comparing ${selectedModels.length} model${selectedModels.length > 1 ? "s" : ""}`}
        </div>
        <div className="mb-3 flex flex-wrap gap-2">
          {selectedModels.map((model) => (
            <span key={model.id} className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm">
              <span className="font-medium text-indigo-800">{model.name}</span>
              <button
                type="button"
                onClick={() => onToggleCompare?.(model.id)}
                className="text-base font-bold leading-none text-indigo-400 hover:text-indigo-700"
              >
                ×
              </button>
            </span>
          ))}
          {selectedModels.length === 0 ? <span className="text-sm text-gray-400">No models selected yet</span> : null}
        </div>
        <input
          type="text"
          placeholder="Search to add a model..."
          value={addQuery}
          onChange={(event) => setAddQuery(event.target.value)}
          className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        {addQuery && suggestions.length > 0 ? (
          <div className="mt-2 overflow-hidden rounded-lg border border-gray-100 shadow-sm">
            {suggestions.map((model) => (
              <button
                key={model.id}
                type="button"
                onClick={() => {
                  onToggleCompare?.(model.id);
                  setAddQuery("");
                }}
                className="flex w-full items-center gap-2 border-b border-gray-100 px-3 py-2 text-left text-sm last:border-0 hover:bg-indigo-50"
              >
                <span>{model.name}</span>
                <ProviderBadge provider={model.provider} />
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {selectedModels.length >= 2 && benchmarksWithAnyData.length > 0 ? (
        <>
          <div className="mb-5 grid gap-3" style={{ gridTemplateColumns: `repeat(${selectedModels.length}, 1fr)` }}>
            {selectedModels.map((model) => {
              const wins = winCounts[model.id] || 0;
              const leading = Math.max(...Object.values(winCounts)) === wins && wins > 0;
              return (
                <div key={model.id} className={`rounded-xl border p-4 text-center ${leading ? "border-indigo-300 shadow-sm" : "border-gray-200"} bg-white`}>
                  <div className="mb-1 truncate text-sm font-semibold text-gray-800">{model.name}</div>
                  <ProviderBadge provider={model.provider} />
                  <div className="mt-3">
                    <span className="text-3xl font-bold text-indigo-600">{wins}</span>
                    <span className="text-sm text-gray-400"> wins</span>
                  </div>
                  <div className="mt-0.5 text-xs text-gray-400">of {benchmarksWithAnyData.length} benchmarks</div>
                </div>
              );
            })}
          </div>

          <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
            <div className="grid border-b border-gray-100 bg-gray-50 px-4 py-3" style={{ gridTemplateColumns: `180px repeat(${selectedModels.length}, 1fr)` }}>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Benchmark</div>
              {selectedModels.map((model) => (
                <div key={model.id} className="truncate px-2 text-xs font-semibold text-gray-700">
                  {model.name}
                </div>
              ))}
            </div>

            {benchmarksWithAnyData.map((benchmark) => {
              const winner = winnerForBenchmark(selectedModels, benchmark);
              return (
                <div
                  key={benchmark.id}
                  className="grid border-b border-gray-50 px-4 py-3 last:border-0 hover:bg-gray-50"
                  style={{ gridTemplateColumns: `180px repeat(${selectedModels.length}, 1fr)` }}
                >
                  <div>
                    <a href={benchmark.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-gray-700 hover:text-indigo-600">
                      {benchmark.short}
                    </a>
                    <div className="text-xs text-gray-400">{benchmark.metric}</div>
                  </div>
                  {selectedModels.map((model) => {
                    const score = model.scores?.[benchmark.id];
                    const isWinner = winner?.id === model.id;
                    const indicator = sourceIndicator(score);
                    return (
                      <div key={model.id} className={`flex items-center gap-2 px-2 ${isWinner ? "font-semibold" : ""}`}>
                        {score?.value != null ? (
                          <>
                            <span className={`text-[10px] font-bold ${indicator.className}`}>{indicator.icon}</span>
                            <span className={`text-sm ${isWinner ? "text-green-700" : "text-gray-600"}`}>
                              {isWinner ? "★ " : ""}
                              {formatValue(benchmark, score.value)}
                            </span>
                          </>
                        ) : (
                          <span className="text-sm text-gray-300">—</span>
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
        <div className="rounded-xl border border-dashed border-gray-200 bg-white py-16 text-center text-gray-400">
          <div className="mb-3 text-4xl">⚖️</div>
          <div className="font-medium">Add at least 2 models to compare</div>
          <div className="mt-1 text-sm">Use the search above or the Model Browser tab to add models</div>
        </div>
      )}
    </div>
  );
}
