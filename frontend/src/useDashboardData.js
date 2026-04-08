import { useEffect, useRef, useState } from "react";

import {
  applyModelFamilyApprovalBulk,
  applyModelFamilyApprovalDelta,
  getBenchmarks,
  getMarketSnapshots,
  getModels,
  getProviders,
  getRankings,
  getSourceRunRawRecords,
  getUpdateHistory,
  getUpdateHistorySources,
  getUpdateStatus,
  getUseCases,
  startUpdate,
  updateManualBenchmarkScore,
  updateModelApproval,
  updateModelUseCaseApproval,
  updateProvider,
  updateUseCaseInternalWeight,
} from "./api";

function buildUpdateMessage(status) {
  if (!status) {
    return "";
  }

  const totalSteps = Number(status.total_steps || status.progress_steps?.length || 0);
  const finishedSteps = Number(status.finished_steps || 0);
  const currentStepLabel = String(status.current_step_label || "").trim();

  if (status.status === "running") {
    if (totalSteps > 0 && currentStepLabel) {
      return `Update running · ${finishedSteps}/${totalSteps} steps finished · ${currentStepLabel}`;
    }
    if (totalSteps > 0) {
      return `Update running · ${finishedSteps}/${totalSteps} steps finished`;
    }
    return currentStepLabel ? `Update running · ${currentStepLabel}` : "Update running…";
  }

  const errorCount = Array.isArray(status.errors) ? status.errors.length : 0;
  const summaryPrefix = status.status === "completed" ? "Update complete" : "Update finished with issues";
  return `${summaryPrefix} · ${status.scores_added} scores refreshed · ${errorCount} errors`;
}

function buildUpdateStateFromLog(status) {
  return {
    status: status?.status || "idle",
    message: buildUpdateMessage(status),
    logId: status?.id ?? null,
    errors: Array.isArray(status?.errors) ? status.errors : [],
    startedAt: status?.started_at || "",
    completedAt: status?.completed_at || "",
    currentStepKey: status?.current_step_key || "",
    currentStepLabel: status?.current_step_label || "",
    currentStepIndex: Number(status?.current_step_index || 0),
    totalSteps: Number(status?.total_steps || status?.progress_steps?.length || 0),
    finishedSteps: Number(status?.finished_steps || 0),
    progressPercent: Number(status?.progress_percent || 0),
    progressSteps: Array.isArray(status?.progress_steps) ? status.progress_steps : [],
  };
}

export function useDashboardData() {
  const [benchmarks, setBenchmarks] = useState([]);
  const [useCases, setUseCases] = useState([]);
  const [models, setModels] = useState([]);
  const [providers, setProviders] = useState([]);
  const [history, setHistory] = useState([]);
  const [marketSnapshots, setMarketSnapshots] = useState([]);
  const [rankings, setRankings] = useState(null);
  const [selectedUseCaseId, setSelectedUseCaseId] = useState("");
  const [sourceRunsByLogId, setSourceRunsByLogId] = useState({});
  const [sourceRunsLoadingByLogId, setSourceRunsLoadingByLogId] = useState({});
  const [rawRecordsBySourceRunId, setRawRecordsBySourceRunId] = useState({});
  const [rawRecordsLoadingBySourceRunId, setRawRecordsLoadingBySourceRunId] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rankingsLoading, setRankingsLoading] = useState(false);
  const [rankingsError, setRankingsError] = useState("");
  const [marketSnapshotsLoading, setMarketSnapshotsLoading] = useState(false);
  const [marketSnapshotsError, setMarketSnapshotsError] = useState("");
  const [updateState, setUpdateState] = useState({
    status: "idle",
    message: "",
    logId: null,
    errors: [],
    startedAt: "",
    completedAt: "",
    currentStepKey: "",
    currentStepLabel: "",
    currentStepIndex: 0,
    totalSteps: 0,
    finishedSteps: 0,
    progressPercent: 0,
    progressSteps: [],
  });
  const activePollLogIdRef = useRef(null);

  async function refreshData() {
    setLoading(true);
    setError("");
    setMarketSnapshotsLoading(true);
    setMarketSnapshotsError("");
    try {
      const [nextBenchmarks, nextUseCases, nextModels, nextProviders, nextHistory] = await Promise.all([
        getBenchmarks(),
        getUseCases(),
        getModels(),
        getProviders(),
        getUpdateHistory(),
      ]);
      setBenchmarks(nextBenchmarks);
      setUseCases(nextUseCases);
      setModels(nextModels);
      setProviders(nextProviders);
      setHistory(nextHistory);
      const runningLog = nextHistory.find((entry) => entry.status === "running");
      if (runningLog) {
        setUpdateState(buildUpdateStateFromLog(runningLog));
        void pollUpdate(runningLog.id);
      }
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to load dashboard data.");
    }

    try {
      const nextMarketSnapshots = await getMarketSnapshots();
      setMarketSnapshots(nextMarketSnapshots);
      setMarketSnapshotsError("");
    } catch (exception) {
      setMarketSnapshotsError(exception instanceof Error ? exception.message : "Failed to load market snapshots.");
    } finally {
      setMarketSnapshotsLoading(false);
      setLoading(false);
    }
  }

  async function refreshHistory() {
    setMarketSnapshotsLoading(true);
    try {
      const [nextHistory, nextMarketSnapshots] = await Promise.all([getUpdateHistory(), getMarketSnapshots()]);
      setHistory(nextHistory);
      setMarketSnapshots(nextMarketSnapshots);
      setMarketSnapshotsError("");
      const runningLog = nextHistory.find((entry) => entry.status === "running");
      if (runningLog) {
        setUpdateState(buildUpdateStateFromLog(runningLog));
        void pollUpdate(runningLog.id);
      }
    } catch (exception) {
      const message = exception instanceof Error ? exception.message : "Failed to load update history.";
      setError(message);
      setMarketSnapshotsError(message);
    } finally {
      setMarketSnapshotsLoading(false);
    }
  }

  async function pollUpdate(logId) {
    if (!logId || activePollLogIdRef.current === logId) {
      return;
    }

    activePollLogIdRef.current = logId;
    let settledStatus = null;

    try {
      while (activePollLogIdRef.current === logId) {
        const status = await getUpdateStatus(logId);
        setUpdateState(buildUpdateStateFromLog(status));
        if (Array.isArray(status.source_runs)) {
          setSourceRunsByLogId((current) => ({ ...current, [logId]: status.source_runs }));
        }

        if (status.status !== "running") {
          settledStatus = status;
          activePollLogIdRef.current = null;
          break;
        }

        await new Promise((resolve) => setTimeout(resolve, 3000));
      }

      if (settledStatus) {
        await Promise.all([refreshData(), refreshHistory()]);
        if (selectedUseCaseId) {
          await loadRankings(selectedUseCaseId);
        }
      }
    } catch (exception) {
      activePollLogIdRef.current = null;
      setUpdateState({
        status: "failed",
        message: exception instanceof Error ? exception.message : "Update failed.",
        logId,
        errors: [],
        startedAt: "",
        completedAt: "",
        currentStepKey: "",
        currentStepLabel: "",
        currentStepIndex: 0,
        totalSteps: 0,
        finishedSteps: 0,
        progressPercent: 0,
        progressSteps: [],
      });
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
    activePollLogIdRef.current = null;
    setUpdateState({
      status: "running",
      message: "Update running…",
      logId: null,
      errors: [],
      startedAt: "",
      completedAt: "",
      currentStepKey: "",
      currentStepLabel: "",
      currentStepIndex: 0,
      totalSteps: 0,
      finishedSteps: 0,
      progressPercent: 0,
      progressSteps: [],
    });

    try {
      const started = await startUpdate(benchmarksToRefresh ? { benchmarks: benchmarksToRefresh } : {});
      const logId = started.log_id;
      setUpdateState((current) => ({ ...current, logId }));
      await pollUpdate(logId);
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
        startedAt: "",
        completedAt: "",
        currentStepKey: "",
        currentStepLabel: "",
        currentStepIndex: 0,
        totalSteps: 0,
        finishedSteps: 0,
        progressPercent: 0,
        progressSteps: [],
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

  async function loadRawSourceRecords(sourceRunId) {
    if (!sourceRunId) {
      return [];
    }

    if (Object.prototype.hasOwnProperty.call(rawRecordsBySourceRunId, sourceRunId)) {
      return rawRecordsBySourceRunId[sourceRunId];
    }

    setRawRecordsLoadingBySourceRunId((current) => ({ ...current, [sourceRunId]: true }));
    try {
      const records = await getSourceRunRawRecords(sourceRunId);
      setRawRecordsBySourceRunId((current) => ({ ...current, [sourceRunId]: records }));
      return records;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to load raw source records.");
      return [];
    } finally {
      setRawRecordsLoadingBySourceRunId((current) => ({ ...current, [sourceRunId]: false }));
    }
  }

  useEffect(() => {
    refreshData();
  }, []);

  useEffect(() => () => {
    activePollLogIdRef.current = null;
  }, []);

  async function saveProvider(providerId, payload) {
    try {
      await updateProvider(providerId, payload);
      await refreshData();
      return true;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to update provider.");
      return false;
    }
  }

  async function saveModelApproval(modelId, payload) {
    try {
      if (payload?.use_case_id) {
        await updateModelUseCaseApproval(modelId, payload.use_case_id, payload);
      } else {
        await updateModelApproval(modelId, payload);
      }
      await refreshData();
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
      return true;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to update model approval.");
      return false;
    }
  }

  async function applyFamilyApprovalDelta(familyId, useCaseId, payload) {
    try {
      const result = await applyModelFamilyApprovalDelta(familyId, useCaseId, payload);
      await refreshData();
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
      return result;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to apply family approval delta.");
      return null;
    }
  }

  async function applyFamilyApprovalBulk(familyId, payload) {
    try {
      const result = await applyModelFamilyApprovalBulk(familyId, payload);
      await refreshData();
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
      return result;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to apply bulk family approval.");
      return null;
    }
  }

  async function saveUseCaseInternalWeight(useCaseId, payload) {
    try {
      await updateUseCaseInternalWeight(useCaseId, payload);
      await refreshData();
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
      return true;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to update internal view weight.");
      return false;
    }
  }

  async function saveManualBenchmarkScore(modelId, benchmarkId, payload) {
    try {
      await updateManualBenchmarkScore(modelId, benchmarkId, payload);
      await refreshData();
      if (selectedUseCaseId) {
        await loadRankings(selectedUseCaseId);
      }
      return true;
    } catch (exception) {
      setError(exception instanceof Error ? exception.message : "Failed to update internal benchmark score.");
      return false;
    }
  }

  return {
    benchmarks,
    error,
    history,
    applyFamilyApprovalDelta,
    applyFamilyApprovalBulk,
    marketSnapshots,
    marketSnapshotsError,
    marketSnapshotsLoading,
    loadRankings,
    loadSourceRuns,
    loading,
    models,
    providers,
    rankings,
    rankingsError,
    rankingsLoading,
    refreshData,
    refreshHistory,
    selectedUseCaseId,
    setSelectedUseCaseId,
    sourceRunsByLogId,
    sourceRunsLoadingByLogId,
    rawRecordsBySourceRunId,
    rawRecordsLoadingBySourceRunId,
    loadRawSourceRecords,
    saveManualBenchmarkScore,
    saveModelApproval,
    saveProvider,
    saveUseCaseInternalWeight,
    triggerUpdate,
    updateState,
    useCases,
  };
}
