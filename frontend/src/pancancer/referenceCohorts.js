export function tcgaReferenceCohorts(cohorts = []) {
  return cohorts.filter((cohort) => String(cohort.id || "").startsWith("TCGA-"));
}

export function referenceCohortId(cohorts, ...candidates) {
  const reference = tcgaReferenceCohorts(cohorts);
  const ids = new Set(reference.map((cohort) => cohort.id));
  return candidates.find((id) => ids.has(id)) || reference[0]?.id || "";
}
