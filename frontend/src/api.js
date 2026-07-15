const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let message = response.statusText;
    let code = `HTTP_${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail?.message) {
        message = payload.detail.message;
        code = payload.detail.code || code;
      }
    } catch {
      // Keep status text when response is not JSON.
    }
    const error = new Error(message);
    error.code = code;
    throw error;
  }
  return response.json();
}

export function apiUrl(path) {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export function getHealth() {
  return request("/api/health");
}

export function getCohorts() {
  return request("/api/cohorts");
}

export function getDatasetSummary(cohort = "") {
  const params = cohort ? `?${new URLSearchParams({ cohort }).toString()}` : "";
  return request(`/api/dataset/summary${params}`);
}

export function getDataSources() {
  return request("/api/data-sources");
}

export function getCohortEndpoints(cohort) {
  return request(`/api/cohorts/${cohort}/endpoints`);
}

export function getExpressionScales() {
  return request("/api/expression-scales");
}

export function getFilterOptions(cohort) {
  return request(`/api/cohorts/${cohort}/filters`);
}

export function searchGenes(cohort, query) {
  const params = new URLSearchParams({ query, limit: "20" });
  return request(`/api/cohorts/${cohort}/genes?${params.toString()}`);
}

export function resolveGene(cohort, query) {
  const params = new URLSearchParams({ query });
  return request(`/api/cohorts/${cohort}/genes/resolve?${params.toString()}`);
}

export function createAnalysis(payload) {
  return request("/api/analyses", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createCombinedAnalysis(payload) {
  return request("/api/analyses/combined", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createAnalysesBatch(analyses, maxConcurrency = 3) {
  return request("/api/analyses/batch", {
    method: "POST",
    body: JSON.stringify({ analyses, max_concurrency: maxConcurrency }),
  });
}

export function createPanCancerSurvival(payload) {
  return request("/api/pancancer/survival", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getImmunePanCancerScreen(screenId = "immune_os_immport_all_v1") {
  return request(`/api/pancancer/immune-screens/${screenId}`);
}
