import { scientificNumber } from "../scientificNumbers";

const GENE_TOKEN_DELIMITERS = new Set([",", ";", "\n", "\r", "\t"]);

export const GSEA_DOTPLOT_LIMIT = 30;
export const GSEA_DOTPLOT_NEG_LOG10_FDR_CAP = 10;
export const GSEA_TABLE_PAGE_SIZE = 50;

const GSEA_NES_NEGATIVE_COLOR = "#00008b";
const GSEA_NES_NEUTRAL_COLOR = "#ffffff";
const GSEA_NES_POSITIVE_COLOR = "#ff0000";

function boundedCursor(value, cursor) {
  const numeric = Number(cursor);
  if (!Number.isFinite(numeric)) return value.length;
  return Math.max(0, Math.min(value.length, Math.trunc(numeric)));
}

export function geneCompletionContext(rawValue, cursor) {
  const value = String(rawValue || "");
  const caret = boundedCursor(value, cursor);
  let start = caret;
  let end = caret;
  while (start > 0 && !GENE_TOKEN_DELIMITERS.has(value[start - 1])) {
    start -= 1;
  }
  while (end < value.length && !GENE_TOKEN_DELIMITERS.has(value[end])) {
    end += 1;
  }

  const token = value.slice(start, end);
  const leadingWhitespace = token.match(/^\s*/)?.[0] || "";
  const trailingWhitespace = token.match(/\s*$/)?.[0] || "";
  const contentStart = leadingWhitespace.length;
  const contentEnd = Math.max(contentStart, token.length - trailingWhitespace.length);
  const content = token.slice(contentStart, contentEnd);
  const colonIndex = content.indexOf(":");
  const rawGene = colonIndex >= 0 ? content.slice(0, colonIndex) : content;
  const weightSuffix = colonIndex >= 0 ? content.slice(colonIndex) : "";

  return {
    start,
    end,
    caret,
    leadingWhitespace,
    trailingWhitespace,
    query: rawGene.trim().toUpperCase(),
    weightSuffix,
  };
}

export function replaceGeneCompletion(rawValue, cursor, selectedGene) {
  const value = String(rawValue || "");
  const context = geneCompletionContext(value, cursor);
  const gene = String(selectedGene || "").trim().toUpperCase();
  if (!gene) {
    return { value, cursor: context.caret };
  }
  const replacement = [
    context.leadingWhitespace,
    gene,
    context.weightSuffix,
    context.trailingWhitespace,
  ].join("");
  const nextValue =
    value.slice(0, context.start) + replacement + value.slice(context.end);
  return {
    value: nextValue,
    cursor:
      context.start +
      context.leadingWhitespace.length +
      gene.length +
      context.weightSuffix.length,
  };
}

export function signatureGeneSymbols(rawValue) {
  const seen = new Set();
  return String(rawValue || "")
    .split(/[\s,;]+/)
    .map((token) => token.split(":")[0].trim().toUpperCase())
    .filter((gene) => {
      if (!gene || seen.has(gene)) return false;
      seen.add(gene);
      return true;
    });
}

export function negativeLog10Fdr(value) {
  const fdr = scientificNumber(value);
  if (fdr === null || fdr < 0 || fdr > 1) return null;
  if (fdr === 0) return 300;
  if (fdr === 1) return 0;
  return -Math.log10(fdr);
}

export function dotPlotSizeValue(value) {
  const significance = negativeLog10Fdr(value);
  return significance === null
    ? null
    : Math.min(significance, GSEA_DOTPLOT_NEG_LOG10_FDR_CAP);
}

export function dotRadiusForSignificance(
  significance,
  maximumSignificance,
  maximumRadius = 14,
) {
  const value = Math.max(0, Number(significance) || 0);
  const maximum = Math.max(0, Number(maximumSignificance) || 0);
  if (maximum === 0 || value === 0) return 0;
  return Math.sqrt(value / maximum) * maximumRadius;
}

function interpolateHexColor(start, end, fraction) {
  const bounded = Math.max(0, Math.min(1, Number(fraction) || 0));
  const channels = [1, 3, 5].map((index) => {
    const startChannel = Number.parseInt(start.slice(index, index + 2), 16);
    const endChannel = Number.parseInt(end.slice(index, index + 2), 16);
    return Math.round(startChannel + (endChannel - startChannel) * bounded);
  });
  return `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

export function colorForNes(value, maximumAbsoluteNes) {
  const nes = Number(value);
  const maximum = Math.max(Math.abs(Number(maximumAbsoluteNes) || 0), 1e-12);
  const normalized = Math.max(-1, Math.min(1, nes / maximum));
  if (normalized < 0) {
    return interpolateHexColor(
      GSEA_NES_NEGATIVE_COLOR,
      GSEA_NES_NEUTRAL_COLOR,
      normalized + 1,
    );
  }
  return interpolateHexColor(
    GSEA_NES_NEUTRAL_COLOR,
    GSEA_NES_POSITIVE_COLOR,
    normalized,
  );
}

export function topDotPlotPathways(pathways, limit = GSEA_DOTPLOT_LIMIT) {
  return [...(pathways || [])]
    .filter(
      (row) =>
        scientificNumber(row?.nes) !== null &&
        negativeLog10Fdr(row?.fdr) !== null,
    )
    .sort((left, right) => {
      const fdrDifference = Number(left.fdr) - Number(right.fdr);
      if (fdrDifference !== 0) return fdrDifference;
      return Math.abs(Number(right.nes)) - Math.abs(Number(left.nes));
    })
    .slice(0, limit);
}
