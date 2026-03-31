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
    const message = typeof body === "string" ? body : body?.detail || response.statusText;
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

export function getRankings(useCaseId) {
  return request(`/rankings?use_case=${encodeURIComponent(useCaseId)}`);
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

export function getUpdateHistorySources(logId) {
  return request(`/update/history/${logId}/sources`);
}
