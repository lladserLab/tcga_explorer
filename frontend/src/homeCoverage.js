/**
 * Build the lightweight, application-wide coverage shown on Home.
 * The cohort catalog is the authoritative fast source for these three totals;
 * the detailed dataset summary remains available to the Dataset workspace.
 */
export function aggregateCohortCoverage(cohorts, fallback = {}) {
  const tcgaCohorts = Array.isArray(cohorts)
    ? cohorts.filter((cohort) => cohort?.status !== "external_only")
    : [];
  if (tcgaCohorts.length === 0) {
    return {
      cohorts: fallback.cohorts,
      patients: fallback.patients,
      samples: fallback.samples,
    };
  }

  return tcgaCohorts.reduce(
    (totals, cohort) => ({
      cohorts: totals.cohorts + 1,
      patients: totals.patients + finiteCount(cohort?.n_patients_paired),
      samples: totals.samples + finiteCount(cohort?.n_samples_paired),
    }),
    { cohorts: 0, patients: 0, samples: 0 },
  );
}

/**
 * Combine TCGA coverage with the curated external repository without implying
 * that records have been deduplicated across releases.
 */
export function aggregatePublicCatalogCoverage(tcgaCoverage = {}, externalCoverage = {}) {
  return {
    cancerTypes: finiteValue(externalCoverage?.represented_cancer_types),
    cohortReleases: completeSum(
      tcgaCoverage?.cohorts,
      externalCoverage?.datasets,
    ),
    patientRecords: completeSum(
      tcgaCoverage?.patients,
      externalCoverage?.patient_records_across_active_releases,
    ),
    rnaProfiles: completeSum(
      tcgaCoverage?.samples,
      externalCoverage?.rna_samples_across_active_releases,
    ),
  };
}

/** Keep a completed load failure distinct from a pending coverage request. */
export function publicCoverageState(coverage, serviceStatus = "loading") {
  const complete = ["cancerTypes", "cohortReleases", "patientRecords", "rnaProfiles"]
    .every((key) => Number.isFinite(coverage?.[key]));
  if (complete) return "ready";
  return ["ready", "degraded", "unavailable"].includes(serviceStatus)
    ? "unavailable"
    : "loading";
}

function completeSum(...values) {
  const counts = values.map(finiteValue);
  if (counts.some((value) => value === undefined)) return undefined;
  return counts.reduce((total, value) => total + value, 0);
}

function finiteValue(value) {
  if (value === undefined || value === null || value === "") return undefined;
  const number = Number(value);
  return Number.isFinite(number) ? number : undefined;
}

function finiteCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}
