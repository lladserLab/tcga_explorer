// Search aliases affect discovery only. They never change cohort identity.
const GALLBLADDER_ALIASES = ["gallblader", "gall bladder", "vesicula", "vesicula biliar"];

export function cohortPickerCountLabel(count, query = "") {
  const types = count === 1 ? "cancer type" : "cancer types";
  return query.trim()
    ? `${count} ${types} ${count === 1 ? "matches" : "match"} your search`
    : `${count} ${types} available for this analysis`;
}

function normalize(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function cohortMatchesQuery(cohort, query, displayName = "") {
  const terms = normalize(query).split(/\s+/).filter(Boolean);
  if (!terms.length) return true;
  const aliases = ["FU-GBC", "EXT-GBC"].includes(cohort.id)
    ? GALLBLADDER_ALIASES
    : [];
  const searchable = normalize([
    cohort.id,
    displayName,
    cohort.primary_site,
    cohort.disease_type,
    ...aliases,
  ].filter(Boolean).join(" "));
  return terms.every((term) => searchable.includes(term));
}
