import { survivalRequestFingerprint } from "../survival/setupState";

const validP = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;

export function groupedInference(row) {
  const metrics = row.result?.metrics || {};
  const cutpoint = metrics.cutpoint_details || {};
  if (row.method === "maxstat" || cutpoint.method === "maxstat" || metrics.cutpoint_method === "maxstat") {
    return cutpoint.corrected_p_status === "completed" && validP(cutpoint.corrected_p_value)
      ? { p: cutpoint.corrected_p_value, test: "maxstat_lau94_corrected" }
      : { p: null, test: "maxstat_corrected_unavailable" };
  }
  return { p: validP(metrics.logrank_p_value) ? metrics.logrank_p_value : null, test: "logrank" };
}

export function adjustCompareResults(rows, family) {
  const withP = rows.map((row, index) => ({ ...row, index: row.index ?? index, ...groupedInference(row) }));
  // The server is authoritative for new batches. Legacy results are recomputed
  // with the same selection-aware rule, never their old naive grouped q-values.
  if (family?.contract === "compare-grouped-family-v1") {
    return withP.map((row) => {
      const inference = family.tests?.find((item) => item.index === row.index);
      return { ...row, p: inference?.p_value ?? null, test: inference?.test || row.test,
        bh: inference?.bh_q_value ?? null, bonferroni: inference?.bonferroni_p_value ?? null };
    });
  }
  const valid = withP.filter((row) => validP(row.p)).sort((a, b) => a.p - b.p);
  let running = 1;
  for (let i = valid.length - 1; i >= 0; i -= 1) {
    running = Math.min(running, valid[i].p * valid.length / (i + 1));
    valid[i].bh = running;
    valid[i].bonferroni = Math.min(1, valid[i].p * valid.length);
  }
  return withP;
}

export function compareRequestContext(requests) {
  if (!requests?.length) return null;
  const first = requests[0];
  return {
    // In-memory only: a full request can include private clinical covariates.
    fingerprint: survivalRequestFingerprint(requests),
    cohort: first.cohort, endpoint: first.endpoint,
    dataset_id: first.dataset_id, dataset_release_id: first.dataset_release_id,
    expression_layer_id: first.expression_layer_id, expression_scale: first.expression_scale,
    filters: structuredClone(first.filters || {}),
    adjustment_covariates: [...(first.adjustment_covariates || [])],
    external_adjustment_covariates: [...(first.external_adjustment_covariates || [])],
    custom_percentile: requests.find((request) => request.cutpoint_method === "percentile")?.custom_percentile ?? null,
    genes: [...new Set(requests.map((request) => request.gene_symbol))],
    methods: [...new Set(requests.map((request) => request.cutpoint_method))],
    adjustment_requested: requests.some((request) => request.adjustment_covariates?.length || request.external_adjustment_covariates?.length),
  };
}

export function comparisonFamilySummary(rows) {
  const completed = rows.filter((row) => row.result).length;
  const evaluable = rows.filter((row) => validP(row.p)).length;
  return { requested: rows.length, completed, failed: rows.length - completed, evaluable, unavailable: rows.length - evaluable };
}

export function requestedAdjustedModel(models = [], prefix = "", requested) {
  if (requested === false) return null;
  const model = (models || []).find((item) => item.model === `${prefix}user_adjusted`);
  // Never replace an unavailable requested model with an automatic stage/grade fit.
  return model || (requested ? { model: `${prefix}user_adjusted`, status: "unavailable", reason: "Requested model was not returned." } : null);
}

export function compareSummaryCsv(rows, context) {
  const counts = comparisonFamilySummary(rows);
  const fields = ["cohort", "endpoint", "dataset_id", "dataset_release_id", "expression_layer_id", "expression_scale",
    "gene", "method", "custom_percentile", "filters", "adjustment_covariates", "external_adjustment_covariates",
    "analysis_id", "status", "error", "test", "p_value", "bh_q_value", "bonferroni_p_value",
    "requested", "completed", "failed", "evaluable", "unavailable", "correction_scope"];
  const escape = (value) => {
    let text = String(value ?? "");
    // Spreadsheet formula injection protection for user-controlled identifiers.
    if (/^[\s]*[=+@-]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  };
  return [fields.join(","), ...rows.map((row) => {
    const record = { ...context, ...counts, gene: row.gene, method: row.method, analysis_id: row.result?.id,
      custom_percentile: row.method === "percentile" ? context?.custom_percentile : null,
      filters: context?.filters ? JSON.stringify(context.filters) : null,
      adjustment_covariates: context?.adjustment_covariates?.join("; "),
      external_adjustment_covariates: context?.external_adjustment_covariates?.join("; "),
      status: row.result ? "completed" : "failed", error: row.error, test: row.test, p_value: row.p,
      bh_q_value: row.bh, bonferroni_p_value: row.bonferroni,
      correction_scope: "valid_grouped_tests_in_submitted_batch" };
    return fields.map((field) => escape(record[field])).join(",");
  })].join("\r\n");
}
