function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonicalize(value[key])]),
    );
  }
  return value;
}

export function plotStyleFingerprint(plotStylePayload = {}) {
  return JSON.stringify(canonicalize(plotStylePayload));
}

export function compareResultsRequireRerun({
  resultCount = 0,
  recordedFingerprint = "",
  currentFingerprint = "",
} = {}) {
  return Boolean(
    resultCount > 0
    && recordedFingerprint
    && currentFingerprint
    && recordedFingerprint !== currentFingerprint,
  );
}
