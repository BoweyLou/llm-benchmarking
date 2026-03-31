import React from "react";

export default function History({
  history = [],
  updateInstructions = "Use the Update Now button in the header to refresh benchmark data.",
}) {
  return (
    <div className="fade-in">
      <div className="mb-5">
        <h2 className="mb-1 text-xl font-semibold text-gray-800">Update History</h2>
        <p className="text-sm text-gray-500">A log of each time this dashboard's data was refreshed.</p>
      </div>

      <div className="mb-5 overflow-hidden rounded-xl border border-gray-200 bg-white">
        <div className="border-b border-gray-100 bg-indigo-50 p-4">
          <div className="mb-1 text-sm font-semibold text-indigo-800">How to trigger an update</div>
          <div className="text-sm text-indigo-700">
            Open a Claude session and say: <em>"{updateInstructions}"</em>
          </div>
          <div className="mt-1.5 text-xs text-indigo-500">
            The history log below updates automatically after each refresh.
          </div>
        </div>

        <div className="divide-y divide-gray-100">
          {[...history].reverse().map((entry, index) => (
            <div key={`${entry.date}-${index}`} className="flex items-start gap-4 px-5 py-4">
              <div className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-indigo-400" />
              <div>
                <div className="text-sm font-semibold text-gray-700">{entry.date}</div>
                <div className="mt-0.5 text-sm text-gray-500">{entry.note}</div>
                <div className="mt-1.5 flex gap-4 text-xs text-gray-400">
                  <span>{entry.model_count} models</span>
                  <span>{entry.benchmark_count} benchmarks</span>
                </div>
              </div>
            </div>
          ))}
          {history.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-gray-400">No update history yet.</div>
          ) : null}
        </div>
      </div>

      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
        <strong>Why manual updates?</strong> Automatic scraping of benchmark leaderboards is unreliable when sources change structure or publish contested results.
        A human-in-the-loop update ensures scores are verified before they inform decisions.
      </div>
    </div>
  );
}
