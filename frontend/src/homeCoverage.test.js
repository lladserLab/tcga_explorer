import { describe, expect, test } from "vitest";
import {
  aggregateCohortCoverage,
  aggregatePublicCatalogCoverage,
  publicCoverageState,
} from "./homeCoverage";

describe("Home cohort coverage", () => {
  test("derives application totals from the lightweight cohort catalog", () => {
    expect(aggregateCohortCoverage([
      { n_patients_paired: 79, n_samples_paired: 81 },
      { n_patients_paired: 120, n_samples_paired: 132 },
    ])).toEqual({
      cohorts: 2,
      patients: 199,
      samples: 213,
    });
  });

  test("uses detailed-summary totals only until the catalog is available", () => {
    expect(aggregateCohortCoverage([], {
      cohorts: 33,
      patients: 10517,
      samples: 11505,
    })).toEqual({
      cohorts: 33,
      patients: 10517,
      samples: 11505,
    });
  });

  test("does not add external-only disease contexts to TCGA coverage", () => {
    expect(aggregateCohortCoverage([
      {
        id: "TCGA-BRCA",
        n_patients_paired: 1095,
        n_samples_paired: 1100,
      },
      {
        id: "EXT-GBC",
        status: "external_only",
        n_patients_paired: 88,
        n_samples_paired: 88,
      },
    ])).toEqual({
      cohorts: 1,
      patients: 1095,
      samples: 1100,
    });
  });
});

describe("Home coverage loading state", () => {
  const complete = { cancerTypes: 38, cohortReleases: 181, patientRecords: 28410, rnaProfiles: 29743 };

  test.each(["loading", "ready", "degraded", "unavailable"])(
    "keeps complete coverage visible while service status is %s",
    (status) => expect(publicCoverageState(complete, status)).toBe("ready"),
  );

  test("waits for all counts rather than showing a partial population", () => {
    expect(publicCoverageState({ ...complete, patientRecords: undefined }, "loading")).toBe("loading");
    expect(publicCoverageState({})).toBe("loading");
  });

  test.each(["ready", "degraded", "unavailable"])(
    "ends the loading state when requests settled as %s without complete coverage",
    (status) => {
      expect(publicCoverageState({ ...complete, rnaProfiles: undefined }, status)).toBe("unavailable");
      expect(publicCoverageState({}, status)).toBe("unavailable");
    },
  );

  test("accepts a complete empty catalog, but not non-finite values", () => {
    expect(publicCoverageState({ cancerTypes: 0, cohortReleases: 0, patientRecords: 0, rnaProfiles: 0 }, "ready")).toBe("ready");
    expect(publicCoverageState({ ...complete, patientRecords: NaN }, "ready")).toBe("unavailable");
  });
});

describe("Home public catalog coverage", () => {
  test("combines TCGA and external release counts without relabeling them as unique people", () => {
    expect(aggregatePublicCatalogCoverage(
      { cohorts: 33, patients: 10517, samples: 11505 },
      {
        datasets: 148,
        represented_cancer_types: 38,
        patient_records_across_active_releases: 17893,
        rna_samples_across_active_releases: 18238,
      },
    )).toEqual({
      cancerTypes: 38,
      cohortReleases: 181,
      patientRecords: 28410,
      rnaProfiles: 29743,
    });
  });

  test("does not flash partial TCGA-only totals while repository coverage is loading", () => {
    expect(aggregatePublicCatalogCoverage(
      { cohorts: 33, patients: 10517, samples: 11505 },
      {},
    )).toEqual({
      cancerTypes: undefined,
      cohortReleases: undefined,
      patientRecords: undefined,
      rnaProfiles: undefined,
    });
  });
});
