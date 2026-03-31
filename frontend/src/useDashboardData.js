import { useEffect, useState } from "react";

import {
  getBenchmarks,
  getModels,
  getRankings,
  getUpdateHistory,
  getUpdateHistorySources,
  getUpdateStatus,
  getUseCases,
  startUpdate,
} from "./api";

export function useDashboardData() {
  const [benchmarks, setBenchmarks] = useState([]);
  const [useCases, setUseCases] = useState([]);
  const [models, setModels] = useState([]);
  const [history, setHistory] = useState([]);
  const [rankings, setRankings] = useState(null);
  const [selectedUseCaseId, setSelectedUseCaseId] = useState("");
  const [sourceRunsByLogId, setSourceRunsByLogId] = useState({});
  const [sourceRunsLoadingByLogId, setSourceRunsLoadingByLogId] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rankingsLoading, setRankingsLoading] = useState(false);
  const [rankingsError, setRankingsError] = useState("");
  const [updateState, setUpdateState] = useState({
    status: "idle",
    message: "",
    logId: null,
    errors: [],
  });

  async function refreshData() {
    setLoading(true);
    setError("");
    try {
      const [nextBenchmarks, nextUseCases, nextModels, nextHistory] = await Promise.all([
        getBenchmarks(),
        getUseCases(),
        getModels(),
        getUpdateHistory(),
      ]);
      setBenchmarks(nextBenchmarks);
      setUseCases(nextUseCases);
      setModels(nextModels);
      setHistory(nextHistory);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  async function refreshHistory() {
    try {
      const nextHistory = await getUpdateHistory();
      setHistory(nextHistory);
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to load update history.");
    }
  }

  async function loadRankings(useCaseId) {
    if (!useCaseId) {
      setSelectedUseCaseId("");
      setRankings(null);
      setRankingsError("");
      return;
    }

    setSelectedUseCaseId(useCaseId);
    setRankingsLoading(true);
    setRankingsError("");
    try {
      const nextRankings = await getRankings(useCaseId);
      setRankings(nextRankings);
    } catch (exception) {
      setRankingsError(exception instanceof Error ? exception.message : "Failed to load rankings.");
      setRankings(null);
    } finally {
      setRankingsLoading(false);
    }
  }

  async function triggerUpdate(benchmarksToRefresh = null) {
    setUpdateState({
      status: "running",
      message: "Update running...",
      logId: null,
      errors: [],
    });

    try {
      const started = await startUpdate(benchmarksToRefresh ? { benchmarks: benchmarksToRefresh } : {});
      const logId = started.log_id;
      setUpdateState((current) => ({ ...current, logId, message: "Update running..." }));

      while (true) {
        const status = await getUpdateStatus(logId);
        if (status.status !== "running") {
          const summary = `${status.status === "completed" ? "Update complete" : "Update finished with issues"} - ${status.scores_added} scores refreshed, ${Array.isArray(status.errors) ? status.errors.length : 0} errors`;
          setUpdateState({
            status: status.status,
            message: summary,
            logId,
            errors: Array.isArray(status.errors) ? status.errors : [],
          });
          break;
        }

        await new Promise((resolve) => setTimeout(resolve, 3000));
      }

      await Promise.all([refreshData(), refreshHistory()]);
      if (logId) {
        await loadSourceRuns(logId);
      }
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
    } catch (exception) {
      setUpdateState({
        status: "failed",
        message: exception instanceof Error ? exception.message : "Update failed.",
        logId: null,
        errors: [],
      });
    }
  }

  async function loadSourceRuns(logId) {
    if (!logId) {
      return [];
    }

    if (Object.prototype.hasOwnProperty.call(sourceRunsByLogId, logId)) {
      return sourceRunsByLogId[logId];
    }

    setSourceRunsLoadingByLogId((current) => ({ ...current, [logId]: true }));
    try {
      const sourceRuns = await getUpdateHistorySources(logId);
      setSourceRunsByLogId((current) => ({ ...current, [logId]: sourceRuns }));
      return sourceRuns;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to load source runs.");
      return [];
    } finally {
      setSourceRunsLoadingByLogId((current) => ({ ...current, [logId]: false }));
    }
  }

  useEffect(() => {
    refreshData();
  }, []);

  return {
    benchmarks,
    error,
    history,
    loadRankings,
    loadSourceRuns,
    loading,
    models,
    rankings,
    rankingsError,
    rankingsLoading,
    refreshData,
    refreshHistory,
    selectedUseCaseId,
    setSelectedUseCaseId,
    sourceRunsByLogId,
    sourceRunsLoadingByLogId,
    triggerUpdate,
    updateState,
    useCases,
  };
}
