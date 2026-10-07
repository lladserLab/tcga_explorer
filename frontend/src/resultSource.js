// The cohort shown in a result header. `analysis.cohort` is the TCGA cancer context of the request; when the
// analysis ran on an external study or a private upload, the result's dataset descriptor names the real source.
export function resultSourceLabel(dataset, cohort, cohortName) {
  if (dataset && (dataset.kind === "external" || dataset.kind === "user") && dataset.name) {
    return dataset.kind === "user" ? `${dataset.name} (private upload)` : `${dataset.name} (external cohort)`;
  }
  const name = cohortName ? cohortName(cohort) : "";
  return name && name !== cohort ? `${name} (${cohort})` : String(cohort || "");
}
