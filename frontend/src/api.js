const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";
const PUBLIC_API_PREFIX = "/api/v1";
const JOB_POLL_INTERVAL_MS = 2000;
const JOB_POLL_TIMEOUT_MS = 60 * 60 * 1000;
const SESSION_JOB_EVENT = "tcga-trace:job-update";

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
      if (payload.error?.message) {
        message = payload.error.message;
        code = payload.error.code || code;
      } else if (typeof payload.detail === "string") {
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
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function randomRunEventId() {
  const token =
    globalThis.crypto?.randomUUID?.().replaceAll("-", "") ||
    `${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
  return `event-${token}`;
}

function summarizeComputeRequest(path, payload) {
  if (path === "/analyses/combined") {
    const signatureA = payload.signature_a?.name || payload.signature_a?.gene_symbol || "Signature A";
    const signatureB = payload.signature_b?.name || payload.signature_b?.gene_symbol || "Signature B";
    return {
      label: `${signatureA} x ${signatureB}`,
      source_view: "analysis",
      design_summary: [
        payload.cohort,
        payload.endpoint,
        payload.combination_method,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/analyses/batch") {
    const analyses = payload.analyses || [];
    const genes = [...new Set(analyses.map((item) => item.gene_symbol).filter(Boolean))];
    return {
      label: `${genes.slice(0, 3).join(", ")}${genes.length > 3 ? ` +${genes.length - 3}` : ""}`,
      source_view: "compare",
      design_summary: [
        analyses[0]?.cohort,
        analyses[0]?.endpoint,
        `${analyses.length} analyses`,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/analyses/multiverse") {
    const genes = (payload.genes || []).map((item) => item.gene_symbol).filter(Boolean);
    return {
      label: payload.session_label || genes.join(", ") || "Prespecified multiverse",
      source_view: "multiverse",
      design_summary: [
        payload.cohort,
        `${payload.endpoints?.length || 0} endpoints`,
        `${payload.cutpoint_methods?.length || 0} cutpoints`,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/pancancer/survival") {
    return {
      label: payload.gene_symbol || "Pan-cancer scan",
      source_view: "pancancer",
      design_summary: [
        payload.endpoint_mode || payload.endpoint,
        `${payload.cohorts?.length || 33} cohorts`,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/analyses/sessions/export") {
    return {
      label: payload.session_label || "Exploratory session export",
      source_view: "session",
      design_summary: `${payload.entries?.length || 0} selected events`,
    };
  }
  const signatureGenes = (payload.signature_genes || [])
    .map((item) => item.gene_symbol)
    .filter(Boolean);
  return {
    label: payload.signature_method === "single"
      ? payload.gene_symbol || "Survival analysis"
      : `${payload.signature_method}: ${signatureGenes.join(", ")}`,
    source_view: "analysis",
    design_summary: [
      payload.cohort,
      payload.endpoint,
      payload.cutpoint_method,
    ].filter(Boolean).join(" · "),
  };
}

function publishJobUpdate(context, job) {
  if (typeof window === "undefined" || context.summary.source_view === "session") return;
  window.dispatchEvent(new CustomEvent(SESSION_JOB_EVENT, {
    detail: {
      event_id: context.eventId,
      recorded_at: context.recordedAt,
      summary: context.summary,
      job,
    },
  }));
}

async function submitAndWait(path, payload) {
  const context = {
    eventId: randomRunEventId(),
    recordedAt: new Date().toISOString(),
    summary: summarizeComputeRequest(path, payload),
  };
  let job = await request(`${PUBLIC_API_PREFIX}${path}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  publishJobUpdate(context, job);
  const deadline = Date.now() + JOB_POLL_TIMEOUT_MS;

  while (job.status === "queued" || job.status === "running") {
    if (Date.now() >= deadline) {
      const error = new Error(
        `The analysis is still running. Its job ID is ${job.id}; it can be retrieved from the public API.`,
      );
      error.code = "JOB_POLL_TIMEOUT";
      error.jobId = job.id;
      throw error;
    }
    await wait(JOB_POLL_INTERVAL_MS);
    job = await request(`${PUBLIC_API_PREFIX}/jobs/${job.id}`);
    publishJobUpdate(context, job);
  }

  if (job.status !== "completed" || !job.result) {
    const error = new Error(job.error?.message || `Analysis job ended with status ${job.status}.`);
    error.code = job.error?.code || "COMPUTE_FAILED";
    error.jobId = job.id;
    throw error;
  }
  return job.result;
}

export function apiUrl(path) {
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export function getHealth() {
  return request(`${PUBLIC_API_PREFIX}/health`);
}

export function getCohorts() {
  return request(`${PUBLIC_API_PREFIX}/cohorts`);
}

export function getCancerRepositoryCoverage() {
  return request(`${PUBLIC_API_PREFIX}/cancer-types`);
}

export function getRepositoryDatasets(cancerCode = "") {
  const params = cancerCode
    ? `?${new URLSearchParams({ cancer_code: cancerCode }).toString()}`
    : "";
  return request(`${PUBLIC_API_PREFIX}/datasets${params}`);
}

export function getRepositoryDataset(datasetId) {
  return request(`${PUBLIC_API_PREFIX}/datasets/${encodeURIComponent(datasetId)}`);
}

export function getRepositoryDatasetEndpoints(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${PUBLIC_API_PREFIX}/datasets/${encodeURIComponent(datasetId)}/endpoints${params}`,
  );
}

export function getRepositoryExpressionLayers(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${PUBLIC_API_PREFIX}/datasets/${encodeURIComponent(datasetId)}/expression-layers${params}`,
  );
}

export function getRepositoryFilterOptions(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${PUBLIC_API_PREFIX}/datasets/${encodeURIComponent(datasetId)}/filters${params}`,
  );
}

export function getDatasetSummary(cohort = "") {
  const params = cohort ? `?${new URLSearchParams({ cohort }).toString()}` : "";
  return request(`${PUBLIC_API_PREFIX}/dataset/summary${params}`);
}

export function getDataSources() {
  return request(`${PUBLIC_API_PREFIX}/data-sources`);
}

export function getPaperExamples() {
  return request(`${PUBLIC_API_PREFIX}/examples/paper`, { cache: "no-store" });
}

export function getCohortEndpoints(cohort) {
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/endpoints`);
}

export function getExpressionScales() {
  return request(`${PUBLIC_API_PREFIX}/expression-scales`);
}

export function getFilterOptions(cohort) {
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/filters`);
}

export function searchGenes(cohort, query) {
  const params = new URLSearchParams({ query, limit: "20" });
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/genes?${params.toString()}`);
}

export function searchRepositoryGenes(
  datasetId,
  query,
  releaseId = "",
  expressionLayerId = "",
) {
  const params = new URLSearchParams({ query, limit: "20" });
  if (releaseId) params.set("release_id", releaseId);
  if (expressionLayerId) params.set("expression_layer_id", expressionLayerId);
  return request(
    `${PUBLIC_API_PREFIX}/datasets/${encodeURIComponent(datasetId)}/genes?${params.toString()}`,
  );
}

export function resolveGene(cohort, query) {
  const params = new URLSearchParams({ query });
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/genes/resolve?${params.toString()}`);
}

export function createAnalysis(payload) {
  return submitAndWait("/analyses", payload);
}

export function createCombinedAnalysis(payload) {
  return submitAndWait("/analyses/combined", payload);
}

export function createAnalysesBatch(analyses, maxConcurrency = 3) {
  return submitAndWait("/analyses/batch", { analyses, max_concurrency: maxConcurrency });
}

export function createMultiverseAnalysis(payload) {
  return submitAndWait("/analyses/multiverse", payload);
}

export function createPanCancerSurvival(payload) {
  return submitAndWait("/pancancer/survival", payload);
}

export function createExploratorySession(payload) {
  return submitAndWait("/analyses/sessions/export", payload);
}

export function getImmunePanCancerScreen(screenId = "immune_os_immport_all_v2_1") {
  return request(`${PUBLIC_API_PREFIX}/pancancer/immune-screens/${screenId}`);
}
