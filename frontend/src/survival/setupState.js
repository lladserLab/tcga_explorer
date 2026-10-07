// Keep readiness and result identity tied to the selected data and submitted
// request, not to the currently visible workflow page. Never persist these keys.
export function metadataContextKey(form) {
  return JSON.stringify([
    form.cohort || null,
    form.dataset_id || null,
    form.dataset_release_id || null,
    form.dataset_id ? null : form.filters?.sample_population || null,
  ]);
}

export function metadataReady(state, key) {
  return state.status === "ready" && state.key === key;
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
  }
  return value;
}

export function survivalRequestFingerprint(requests) {
  if (!requests?.length) return null;
  return JSON.stringify(canonical(requests));
}

export function survivalResultsAreStale(resultFingerprint, currentFingerprint) {
  // A recovered result without its complete request must not be presented as
  // matching the current controls merely because its gene and endpoint match.
  return !resultFingerprint || !currentFingerprint || resultFingerprint !== currentFingerprint;
}
