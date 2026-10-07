import {
  clearActiveJob,
  recordActiveJobUpdate,
} from "./activeJobs";
import { loadUserDatasetAccessToken } from "./userDataset";

// Production builds inherit their deployment path when no API override is set.
// Development and unit tests keep the root API proxy.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL
  || (import.meta.env.PROD ? import.meta.env.BASE_URL.replace(/\/$/, "") : "");
const PUBLIC_API_PREFIX = "/api/v1";
const JOB_POLL_INTERVAL_MS = 2000;
const JOB_POLL_TIMEOUT_MS = 60 * 60 * 1000;
const SESSION_JOB_EVENT = "tcga-trace:job-update";

export function formatRetryDuration(retryAfter = "") {
  const seconds = Number.parseInt(String(retryAfter || "").trim(), 10);
  if (!Number.isFinite(seconds) || seconds <= 0) return "a moment";
  if (seconds < 60) return seconds === 1 ? "1 second" : `${seconds} seconds`;
  if (seconds < 3600) {
    const minutes = Math.max(1, Math.ceil(seconds / 60));
    return minutes === 1 ? "about 1 minute" : `about ${minutes} minutes`;
  }
  const hours = Math.ceil(seconds / 3600);
  return hours === 1 ? "about 1 hour" : `about ${hours} hours`;
}

export function formatRateLimitMessage(options = {}) {
  const normalized = typeof options === "object" && options !== null
    ? options
    : { retryAfter: options };
  const {
    code = "HTTP_429",
    retryAfter = "",
    details = {},
    message = "",
  } = normalized;
  const wait = formatRetryDuration(retryAfter);
  const preserved = "Results already generated remain available.";
  if (code === "USER_DATASET_LIMIT") {
    const count = Number(details.maximum_active);
    const limit = Number.isInteger(count) && count > 0
      ? `${count} active private datasets`
      : "the maximum number of active private datasets";
    return `This network has reached its limit of ${limit}. Delete a private dataset you can access, or wait until an existing upload expires, before uploading another. This is an upload limit, not an analysis limit.`;
  }
  if (code === "CLIENT_ACTIVE_LIMIT") {
    const count = Number(details.limit);
    const active = Number.isFinite(count) && count > 0
      ? `${count} analyses`
      : "the maximum number of analyses";
    return `This network already has ${active} queued or running. Wait for one to finish, then try again. ${preserved}`;
  }
  if (code === "HOURLY_LIMIT") {
    const count = Number(details.limit);
    const family = String(details.kind_label || "this type of analysis");
    const limit = Number.isFinite(count) && count > 0
      ? ` (${count} submissions per hour)`
      : "";
    return `This network has reached the hourly limit for ${family}${limit}. Try again in ${wait}. ${preserved}`;
  }
  return message || `Too many compute requests were submitted from this network. Try again in ${wait}. ${preserved}`;
}

async function request(path, options = {}) {
  const isFormData =
    typeof FormData !== "undefined" && options.body instanceof FormData;
  const response = await authorizedFetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let message = response.statusText;
    let code = `HTTP_${response.status}`;
    let details = {};
    let requestId = "";
    try {
      const payload = await response.json();
      if (payload.error?.message) {
        message = payload.error.message;
        code = payload.error.code || code;
        details = payload.error.details || {};
        requestId = payload.error.request_id || "";
      } else if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail?.message) {
        message = payload.detail.message;
        code = payload.detail.code || code;
        details = payload.detail.details || {};
        requestId = payload.detail.request_id || "";
      }
    } catch {
      // Keep status text when response is not JSON.
    }
    const retryAfter = response.headers?.get?.("Retry-After") || "";
    if (response.status === 429) {
      message = formatRateLimitMessage({ code, retryAfter, details, message });
    }
    const error = new Error(message);
    error.code = code;
    error.status = response.status;
    error.details = details;
    error.requestId = requestId;
    error.retryAfter = retryAfter;
    throw error;
  }
  return response.json();
}

export function authorizedFetch(url, options = {}) {
  const datasetToken = loadUserDatasetAccessToken();
  return fetch(url, {
    ...options,
    headers: {
      ...(datasetToken
        ? { "X-TRACE-Dataset-Token": datasetToken }
        : {}),
      ...(options.headers || {}),
    },
  });
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

export function summarizeComputeRequest(path, payload) {
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
  if (path === "/analyses/signature-panel") {
    const signatures = payload.signatures || [];
    return {
      label:
        payload.panel_name ||
        `${signatures.length} signature panel`,
      source_view: "analysis",
      design_summary: [
        payload.cohort,
        payload.endpoint,
        `${signatures.length} continuous scores`,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/analyses/gsea") {
    const grouping = payload.grouping || {};
    return {
      label: `${grouping.group_b_label || "Group B"} vs ${grouping.group_a_label || "Group A"}`,
      source_view: "gsea",
      design_summary: [
        payload.cohort,
        grouping.source,
        payload.gene_set_collection,
      ].filter(Boolean).join(" · "),
    };
  }
  if (path === "/analyses/expression-comparisons") {
    const grouping = payload.grouping || {};
    const genes = payload.genes || [];
    return {
      label: `${genes.slice(0, 3).join(", ")}${genes.length > 3 ? ` +${genes.length - 3}` : ""}`,
      source_view: "expression",
      design_summary: [
        payload.cohort,
        `${grouping.group_b_label || "Group B"} vs ${grouping.group_a_label || "Group A"}`,
        grouping.source,
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
      recovery_context: analyses.map((analysis) => ({
        gene: analysis.gene_symbol,
        method: analysis.cutpoint_method,
        plot_style: analysis.plot_style,
        cohort: analysis.cohort,
        endpoint: analysis.endpoint,
        dataset_id: analysis.dataset_id,
        dataset_release_id: analysis.dataset_release_id,
        expression_layer_id: analysis.expression_layer_id,
        expression_scale: analysis.expression_scale,
        adjustment_requested: Boolean(analysis.adjustment_covariates?.length || analysis.external_adjustment_covariates?.length),
      })),
    };
  }
  if (path === "/analyses/multiverse") {
    const genes = (payload.genes || []).map((item) => item.gene_symbol).filter(Boolean);
    return {
      label: payload.session_label || genes.join(", ") || "Robustness",
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
  if (path === "/pancancer/hierarchical-survival") {
    return {
      label: payload.gene_symbol || "Hierarchical pan-cancer scan",
      source_view: "pancancer",
      design_summary: [
        "study → cancer → global",
        payload.clinical_context,
        payload.scope,
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
  recordActiveJobUpdate({
    event_id: context.eventId,
    recorded_at: context.recordedAt,
    summary: context.summary,
    job,
  });
  window.dispatchEvent(new CustomEvent(SESSION_JOB_EVENT, {
    detail: {
      event_id: context.eventId,
      recorded_at: context.recordedAt,
      summary: context.summary,
      job,
    },
  }));
}

async function submitAndWait(path, payload, { retainCompletedForRecovery = false } = {}) {
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
    clearActiveJob(context.eventId);
    const error = new Error(job.error?.message || `Analysis job ended with status ${job.status}.`);
    error.code = job.error?.code || "COMPUTE_FAILED";
    error.jobId = job.id;
    throw error;
  }
  if (retainCompletedForRecovery) return { ...job.result, recovery_event_id: context.eventId };
  clearActiveJob(context.eventId);
  return job.result;
}

export function apiUrl(path) {
  if (/^https?:\/\//i.test(String(path || ""))) {
    return path;
  }
  if (!API_BASE_URL) {
    return path;
  }
  return `${API_BASE_URL}${path}`;
}

export function getHealth() {
  return request(`${PUBLIC_API_PREFIX}/health`);
}

export function getComputeJob(jobId) {
  return request(
    `${PUBLIC_API_PREFIX}/jobs/${encodeURIComponent(String(jobId || ""))}`,
    { cache: "no-store" },
  );
}

export function getCohorts() {
  return request(`${PUBLIC_API_PREFIX}/cohorts`);
}

export function getCancerRepositoryCoverage({ includeSearch = true } = {}) {
  const params = includeSearch ? "" : "?include_search=false";
  return request(`${PUBLIC_API_PREFIX}/cancer-types${params}`);
}

export function getRepositoryDatasets(cancerCode = "", { includeMetadata = true } = {}) {
  const query = new URLSearchParams();
  if (cancerCode) query.set("cancer_code", cancerCode);
  if (!includeMetadata) query.set("include_metadata", "false");
  const params = query.size ? `?${query.toString()}` : "";
  return request(`${PUBLIC_API_PREFIX}/datasets${params}`);
}

export function getRepositoryDatasetCandidates({
  diseaseId = "",
  status = "",
  analysisType = "",
  query: searchQuery = "",
} = {}) {
  const query = new URLSearchParams();
  if (diseaseId) query.set("disease_id", diseaseId);
  if (status) query.set("status", status);
  if (analysisType) query.set("analysis_type", analysisType);
  if (searchQuery) query.set("query", searchQuery);
  const params = query.size ? `?${query.toString()}` : "";
  return request(`${PUBLIC_API_PREFIX}/dataset-candidates${params}`, {
    cache: "no-store",
  });
}

function datasetApiPath(datasetId) {
  const collection = String(datasetId || "").startsWith("user-")
    ? "user-datasets"
    : "datasets";
  return `${PUBLIC_API_PREFIX}/${collection}/${encodeURIComponent(datasetId)}`;
}

export function getRepositoryDataset(datasetId) {
  return request(datasetApiPath(datasetId));
}

export function getRepositoryDatasetEndpoints(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${datasetApiPath(datasetId)}/endpoints${params}`,
  );
}

export function getRepositoryExpressionLayers(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${datasetApiPath(datasetId)}/expression-layers${params}`,
  );
}

export function getRepositoryFilterOptions(datasetId, releaseId = "") {
  const params = releaseId
    ? `?${new URLSearchParams({ release_id: releaseId }).toString()}`
    : "";
  return request(
    `${datasetApiPath(datasetId)}/filters${params}`,
  );
}

export function getDatasetSummary(
  cohort = "",
  { includeDataSources = true, includeDataSync = true } = {},
) {
  const query = new URLSearchParams();
  if (cohort) query.set("cohort", cohort);
  if (!includeDataSources) query.set("include_data_sources", "false");
  if (!includeDataSync) query.set("include_data_sync", "false");
  const params = query.size ? `?${query.toString()}` : "";
  return request(`${PUBLIC_API_PREFIX}/dataset/summary${params}`);
}

export function getDataSources() {
  return request(`${PUBLIC_API_PREFIX}/data-sources`);
}

export function getCohortEndpoints(cohort) {
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/endpoints`);
}

export function getExpressionScales() {
  return request(`${PUBLIC_API_PREFIX}/expression-scales`);
}

export function getFilterOptions(cohort, samplePopulation = "") {
  const params = new URLSearchParams();
  if (samplePopulation) params.set("sample_population", samplePopulation);
  const query = params.size ? `?${params.toString()}` : "";
  return request(`${PUBLIC_API_PREFIX}/cohorts/${cohort}/filters${query}`);
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
    `${datasetApiPath(datasetId)}/genes?${params.toString()}`,
  );
}

export function createUserDataset(expressionFile, clinicalFile, mapping) {
  const payload = new FormData();
  payload.append("expression_file", expressionFile);
  payload.append("clinical_file", clinicalFile);
  payload.append("mapping", JSON.stringify(mapping));
  return request(`${PUBLIC_API_PREFIX}/user-datasets`, {
    method: "POST",
    body: payload,
  });
}

export function getUserDataset(datasetId) {
  return request(
    `${PUBLIC_API_PREFIX}/user-datasets/${encodeURIComponent(datasetId)}`,
    { cache: "no-store" },
  );
}

export function deleteUserDataset(datasetId) {
  return request(
    `${PUBLIC_API_PREFIX}/user-datasets/${encodeURIComponent(datasetId)}`,
    { method: "DELETE" },
  );
}

export function getUserDatasetTemplateUrl() {
  return apiUrl(`${PUBLIC_API_PREFIX}/user-datasets/template`);
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

export function createSignaturePanelAnalysis(payload) {
  return submitAndWait("/analyses/signature-panel", payload);
}

export function getGseaCollections() {
  return request(`${PUBLIC_API_PREFIX}/gsea/collections`);
}

export function createGseaAnalysis(payload) {
  return submitAndWait("/analyses/gsea", payload);
}

export function createExpressionComparisonAnalysis(payload) {
  return submitAndWait("/analyses/expression-comparisons", payload);
}

export function createAnalysesBatch(analyses, maxConcurrency = 3, options = {}) {
  return submitAndWait("/analyses/batch", { analyses, max_concurrency: maxConcurrency }, options);
}

export function createMultiverseAnalysis(payload) {
  return submitAndWait("/analyses/multiverse", payload);
}

export function createPanCancerSurvival(payload) {
  return submitAndWait("/pancancer/survival", payload);
}

export function getHierarchicalPanCancerPreflight(payload) {
  return request(`${PUBLIC_API_PREFIX}/pancancer/hierarchical/preflight`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createHierarchicalPanCancerSurvival(payload) {
  return submitAndWait("/pancancer/hierarchical-survival", payload);
}

export function createExploratorySession(payload) {
  return submitAndWait("/analyses/sessions/export", payload);
}

export function getImmunePanCancerScreen(screenId = "immune_os_immport_all_v2_2") {
  return request(`${PUBLIC_API_PREFIX}/pancancer/immune-screens/${screenId}`);
}
