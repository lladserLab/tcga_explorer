// Missing scientific estimates must never become measured zeroes.
export function scientificNumber(value) {
  if (typeof value !== "number" && typeof value !== "string") return null;
  if (typeof value === "string" && !value.trim()) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function scientificEstimate(estimate, low, high, missing = "...") {
  const values = [estimate, low, high].map(scientificNumber);
  if (values.some((value) => value === null)) return missing;
  const [center, lower, upper] = values.map((value) => value.toFixed(2));
  return `${center} (${lower}-${upper})`;
}
