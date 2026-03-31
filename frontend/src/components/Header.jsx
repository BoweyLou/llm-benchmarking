import React from "react";

function formatLastUpdated(value) {
  if (!value) return "Not updated yet";
  if (typeof value === "string") return value;
  return String(value);
}

function SummaryLine({ updateSummary }) {
  if (!updateSummary) return null;

  if (typeof updateSummary === "string") {
    return <div className="text-xs text-slate-500 mt-1.5">{updateSummary}</div>;
  }

  const parts = [];
  if (updateSummary.status) parts.push(String(updateSummary.status));
  if (typeof updateSummary.scores_added === "number" || typeof updateSummary.scores_updated === "number") {
    parts.push(
      `${updateSummary.scores_added ?? 0} added, ${updateSummary.scores_updated ?? 0} updated`
    );
  }
  if (Array.isArray(updateSummary.errors) && updateSummary.errors.length > 0) {
    parts.push(`${updateSummary.errors.length} errors`);
  }

  return <div className="text-xs text-slate-500 mt-1.5">{parts.join(" · ")}</div>;
}

export default function Header({
  title = "LLM Intelligence Dashboard",
  subtitle = "Internal research tool",
  version,
  lastUpdated,
  modelCount = 0,
  benchmarkCount = 0,
  onUpdateNow,
  isUpdating = false,
  updateSummary = null,
}) {
  return (
    <div className="border-b border-gray-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
        <div>
          <h1 className="text-lg font-bold text-gray-900">{title}</h1>
          <p className="text-xs text-gray-400">
            Last updated {formatLastUpdated(lastUpdated)} · {modelCount} models · {benchmarkCount} benchmarks
          </p>
          <SummaryLine updateSummary={updateSummary} />
        </div>

        <div className="hidden text-right text-xs text-gray-400 sm:block">
          <div>{subtitle}</div>
          <div className="font-medium text-indigo-500">{version ? `v${version}` : "v0.1"}</div>
        </div>

        {onUpdateNow ? (
          <button
            type="button"
            onClick={onUpdateNow}
            disabled={isUpdating}
            className={`ml-4 inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all ${
              isUpdating
                ? "cursor-not-allowed border-indigo-200 bg-indigo-50 text-indigo-400"
                : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:border-indigo-300 hover:bg-indigo-100"
            }`}
          >
            {isUpdating ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-indigo-400 border-t-transparent" /> : null}
            {isUpdating ? "Updating..." : "Update Now"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
