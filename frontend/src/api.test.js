import { afterEach, describe, expect, test, vi } from "vitest";
import {
  apiUrl,
  authorizedFetch,
  createUserDataset,
  formatRateLimitMessage,
  formatRetryDuration,
  getRepositoryDatasetCandidates,
  summarizeComputeRequest,
} from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete globalThis.window;
});

describe("API URL handling", () => {
  test("uses the deployment path for production API requests without an override", async () => {
    vi.stubEnv("PROD", true);
    vi.stubEnv("BASE_URL", "/tcga_explorer/");
    vi.stubEnv("VITE_API_BASE_URL", "");
    vi.resetModules();
    try {
      const deployedApi = await import("./api");
      const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
      vi.stubGlobal("fetch", fetchMock);
      await Promise.all([
        deployedApi.getHealth(),
        deployedApi.getCohorts(),
        deployedApi.getExpressionScales(),
      ]);
      expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
        "/tcga_explorer/api/v1/health",
        "/tcga_explorer/api/v1/cohorts",
        "/tcga_explorer/api/v1/expression-scales",
      ]);
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });

  test("does not prefix an already absolute download URL twice", () => {
    const absolute = "https://example.org/api/v1/results/demo";
    expect(apiUrl(absolute)).toBe(absolute);
  });

  test("encodes optional candidate registry filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ candidates: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getRepositoryDatasetCandidates({
      diseaseId: "GBC",
      status: "under_review",
      analysisType: "gsea",
      query: "RNA matrix",
    });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/v1/dataset-candidates?disease_id=GBC&status=under_review&analysis_type=gsea&query=RNA+matrix",
    );
  });

});

describe("public queue rate-limit copy", () => {
  test("explains the private upload limit without inventing a compute wait", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers(),
      json: async () => ({ detail: {
        code: "USER_DATASET_LIMIT",
        message: "Delete an existing private dataset before uploading another.",
        details: { maximum_active: 3 },
      } }),
    }));
    const error = await createUserDataset(new Blob(["expression"]), new Blob(["metadata"]), {}).catch((value) => value);
    expect(error.code).toBe("USER_DATASET_LIMIT");
    expect(error.message).toContain("3 active private datasets");
    expect(error.message).toContain("Delete a private dataset you can access");
    expect(error.message).toContain("until an existing upload expires");
    expect(error.message).not.toContain("compute requests");
    expect(error.message).not.toContain("in a moment");
  });

  test("preserves an unfamiliar rate-limit explanation from the server", () => {
    expect(formatRateLimitMessage({ code: "OTHER_LIMIT", message: "Contact the dataset owner." }))
      .toBe("Contact the dataset owner.");
  });

  test("distinguishes a network hourly quota from a full queue", () => {
    expect(formatRateLimitMessage({
      code: "HOURLY_LIMIT",
      retryAfter: "901",
      details: { limit: 25, kind_label: "expression comparisons" },
    })).toBe(
      "This network has reached the hourly limit for expression comparisons (25 submissions per hour). Try again in about 16 minutes. Results already generated remain available.",
    );
  });

  test("explains an active-job limit separately", () => {
    expect(formatRateLimitMessage({
      code: "CLIENT_ACTIVE_LIMIT",
      retryAfter: "60",
      details: { limit: 5 },
    })).toBe(
      "This network already has 5 analyses queued or running. Wait for one to finish, then try again. Results already generated remain available.",
    );
  });

  test("formats Retry-After as human time", () => {
    expect(formatRetryDuration("12")).toBe("12 seconds");
    expect(formatRetryDuration("3600")).toBe("about 1 hour");
    expect(formatRetryDuration()).toBe("a moment");
  });
});

describe("private dataset authorization", () => {
  test("adds the session token without overwriting caller headers", async () => {
    globalThis.window = {
      sessionStorage: {
        getItem: () => "private-session-token",
      },
    };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true });
    vi.stubGlobal("fetch", fetchMock);

    await authorizedFetch("/api/v1/example", {
      headers: { Accept: "application/json" },
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/example",
      expect.objectContaining({
        headers: {
          Accept: "application/json",
          "X-TRACE-Dataset-Token": "private-session-token",
        },
      }),
    );
  });
});

describe("Compare job recovery", () => {
  test("retains the plot style used by every submitted analysis", () => {
    const plotStyle = {
      cox_forest: {
        multivariable_display: "selected",
        multivariable_model_ids: ["stage_adjusted"],
      },
    };
    const summary = summarizeComputeRequest("/analyses/batch", {
      analyses: [
        {
          cohort: "TCGA-BRCA",
          endpoint: "OS",
          gene_symbol: "ESR1",
          cutpoint_method: "median",
          plot_style: plotStyle,
          external_covariates: { rows: [{ patient_id: "private-id", age: 65 }] },
          external_adjustment_covariates: ["age"],
        },
      ],
    });

    expect(summary.recovery_context).toEqual([
      { gene: "ESR1", method: "median", plot_style: plotStyle, cohort: "TCGA-BRCA", endpoint: "OS",
        dataset_id: undefined, dataset_release_id: undefined, expression_layer_id: undefined, expression_scale: undefined,
        adjustment_requested: true },
    ]);
    expect(JSON.stringify(summary.recovery_context)).not.toContain("private-id");
  });
});
