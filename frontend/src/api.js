const API_PREFIX = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const isBlankStringBody = typeof body === "string" && !body.trim();
    const message = (
      isBlankStringBody && import.meta.env.DEV && response.status === 500
        ? "Backend API unavailable. Start `uvicorn backend.main:app --reload --port 8000` and retry."
        : typeof body === "string"
          ? body
          : body?.detail || response.statusText
    );
    throw new Error(message || `Request failed with status ${response.status}`);
  }

  return body;
}

export function getBenchmarks() {
  return request("/benchmarks");
}

export function getUseCases() {
  return request("/use-cases");
}

export function getModels() {
  return request("/models");
}

export function getProviders() {
  return request("/providers");
}

export function getRankings(useCaseId) {
  return request(`/rankings?use_case=${encodeURIComponent(useCaseId)}`);
}

export function updateProvider(providerId, payload) {
  return request(`/providers/${encodeURIComponent(providerId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateModelApproval(modelId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/approval`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateModelUseCaseApproval(modelId, useCaseId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/approvals/${encodeURIComponent(useCaseId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateModelUseCaseInferenceApproval(modelId, useCaseId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/approvals/${encodeURIComponent(useCaseId)}/inference-route`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function curateModelIdentity(modelId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/curation/identity`, {
    method: "PUT",
    body: JSON.stringify(payload || {}),
  });
}

export function mergeModelDuplicate(modelId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/curation/duplicate`, {
    method: "PUT",
    body: JSON.stringify(payload || {}),
  });
}

export function applyModelUseCaseInferenceApprovalBulk(useCaseId, payload) {
  return request(`/models/approvals/${encodeURIComponent(useCaseId)}/inference-route/bulk`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export function applyModelFamilyApprovalDelta(familyId, useCaseId, payload) {
  return request(`/model-families/${encodeURIComponent(familyId)}/approvals/${encodeURIComponent(useCaseId)}/apply-delta`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export function applyModelFamilyApprovalBulk(familyId, payload) {
  return request(`/model-families/${encodeURIComponent(familyId)}/approvals/bulk`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export function updateUseCaseInternalWeight(useCaseId, payload) {
  return request(`/use-cases/${encodeURIComponent(useCaseId)}/internal-weight`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateManualBenchmarkScore(modelId, benchmarkId, payload) {
  return request(`/models/${encodeURIComponent(modelId)}/benchmarks/${encodeURIComponent(benchmarkId)}/manual-score`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function startUpdate(payload = {}) {
  return request("/update", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getUpdateStatus(logId) {
  return request(`/update/status/${logId}`);
}

export function getUpdateHistory() {
  return request("/update/history");
}

export function getMarketSnapshots({ scope = "", category = "", limit = 300 } = {}) {
  const params = new URLSearchParams();
  if (scope) params.set("scope", scope);
  if (category) params.set("category", category);
  if (limit) params.set("limit", String(limit));
  const query = params.toString();
  return request(`/market-snapshots${query ? `?${query}` : ""}`);
}

export function getUpdateHistorySources(logId) {
  return request(`/update/history/${logId}/sources`);
}

export function getSourceRunRawRecords(sourceRunId) {
  return request(`/update/source-runs/${sourceRunId}/raw-records`);
}
