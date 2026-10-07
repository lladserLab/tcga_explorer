import { expect, test } from "vitest";
import { adjustCompareResults, compareRequestContext, comparisonFamilySummary, compareSummaryCsv, groupedInference, requestedAdjustedModel } from "./resultContract";
import { survivalResultsAreStale } from "../survival/setupState";

const row = (method, metrics) => ({ gene: "CA9", method, result: { id: "test-result", metrics } });

test("maxstat correction precedes BH; missing corrections do not use naive log-rank", () => {
  const rows = adjustCompareResults([
    row("maxstat", { logrank_p_value: 0.001, cutpoint_details: { corrected_p_value: 0.3, corrected_p_status: "completed" } }),
    row("median", { logrank_p_value: 0.02 }),
    { gene: "CA9", method: "percentile", error: "Failed" },
    row("maxstat", { logrank_p_value: 0.0001 }),
  ]);
  expect(rows[0]).toMatchObject({ p: 0.3, bh: 0.3, bonferroni: 0.6, test: "maxstat_lau94_corrected" });
  expect(rows[1].bh).toBe(0.04);
  expect(rows[3].p).toBeNull();
  expect(rows[3].bh).toBeUndefined();
  expect(comparisonFamilySummary(rows)).toEqual({ requested: 4, completed: 3, failed: 1, evaluable: 2, unavailable: 2 });
});

test.each([undefined, null, NaN, Infinity, -1, 2, true])("rejects invalid p %s", (p) => {
  expect(groupedInference(row("median", { logrank_p_value: p })).p).toBeNull();
});

test("new batch inference comes from the server, without raw-p fallback", () => {
  expect(adjustCompareResults([row("maxstat", { logrank_p_value: 0.001 })], {
    contract: "compare-grouped-family-v1", tests: [{ index: 0, p_value: 0.3, test: "maxstat_lau94_corrected", bh_q_value: 0.4, bonferroni_p_value: 0.6 }],
  })[0]).toMatchObject({ p: 0.3, bh: 0.4, bonferroni: 0.6 });
});

test.each(["endpoint", "gene_symbol", "cutpoint_method", "cohort", "dataset_release_id", "expression_layer_id", "filters", "adjustment_covariates", "plot_style"])("records changes to %s", (field) => {
  const request = { cohort: "TCGA-KIRC", gene_symbol: "CA9", endpoint: "OS", cutpoint_method: "median" };
  const before = compareRequestContext([request]);
  const after = compareRequestContext([{ ...request, [field]: "changed" }]);
  expect(survivalResultsAreStale(before.fingerprint, after.fingerprint)).toBe(true);
  expect(before.genes).toEqual(["CA9"]);
});

test("unknown recovered context is never asserted to match current controls", () => {
  expect(survivalResultsAreStale(null, "current")).toBe(true);
});

test("requested adjustment is never replaced with an automatic model", () => {
  const skipped = { model: "user_adjusted", status: "skipped", reason: "Too few cases" };
  const stage = { model: "stage_adjusted", status: "completed", hazard_ratio: 1.5 };
  expect(requestedAdjustedModel([skipped, stage])).toBe(skipped);
  expect(requestedAdjustedModel([skipped, stage], "", false)).toBeNull();
  expect(requestedAdjustedModel([stage])).toBeNull();
  expect(requestedAdjustedModel([stage], "", true).status).toBe("unavailable");
  expect(requestedAdjustedModel(null, "continuous_", true).model).toBe("continuous_user_adjusted");
});

test("summary export preserves counts and tests, not private request contents", () => {
  const rows = adjustCompareResults([row("median", { logrank_p_value: 0.02 }), { gene: "=PRIVATE()", method: "maxstat", error: 'Missing "p"' }]);
  const csv = compareSummaryCsv(rows, { cohort: "TCGA-KIRC", endpoint: "OS", fingerprint: "private-patient-rows" });
  expect(csv).toContain("bonferroni_p_value");
  expect(csv).toContain("valid_grouped_tests_in_submitted_batch");
  expect(csv).toContain("'=PRIVATE()");
  expect(csv).not.toContain("private-patient-rows");
});
