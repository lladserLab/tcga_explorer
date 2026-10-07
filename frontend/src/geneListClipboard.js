function cleanClipboardToken(rawToken, allowWeights) {
  const token = String(rawToken || "")
    .trim()
    .replace(/^["'`]+|["'`]+$/g, "");
  if (!token) return "";
  const colonIndex = token.indexOf(":");
  const rawSymbol = colonIndex >= 0 ? token.slice(0, colonIndex) : token;
  const symbol = rawSymbol.trim().toUpperCase();
  if (!symbol) return "";
  if (!allowWeights || colonIndex < 0) return symbol;
  const weight = token.slice(colonIndex + 1).trim();
  return weight ? `${symbol}:${weight}` : symbol;
}

export function parseClipboardGeneList(rawValue, { allowWeights = true } = {}) {
  const seen = new Set();
  return String(rawValue || "")
    .split(/[\s,;+]+/)
    .map((token) => cleanClipboardToken(token, allowWeights))
    .filter((token) => {
      const symbol = token.split(":")[0];
      if (!symbol || seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

export function normalizeClipboardGeneList(rawValue, options) {
  return parseClipboardGeneList(rawValue, options).join(", ");
}

export function mergeClipboardGeneList(
  currentValue,
  clipboardValue,
  { allowWeights = true, maximum = Number.POSITIVE_INFINITY } = {},
) {
  const current = parseClipboardGeneList(currentValue, { allowWeights });
  const incoming = parseClipboardGeneList(clipboardValue, { allowWeights });
  const bySymbol = new Map(
    current.map((token) => [token.split(":")[0], token]),
  );
  incoming.forEach((token) => {
    bySymbol.set(token.split(":")[0], token);
  });
  return [...bySymbol.values()].slice(0, maximum).join(", ");
}

export function isGeneListClipboardValue(rawValue) {
  return /[\s,;+]/.test(String(rawValue || "").trim());
}
