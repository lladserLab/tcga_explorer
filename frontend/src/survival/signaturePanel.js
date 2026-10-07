import {
  inspectSignatureGeneInput,
  normalizeSignatureInput,
  signatureMethodUsesDirection,
  signatureMethodUsesNumericWeights,
} from "../signatureScoring";

export const MIN_SIGNATURE_PANEL_SIZE = 2;
export const MAX_SIGNATURE_PANEL_SIZE = 6;

export function createPanelSignature(index = 0) {
  return {
    id: `panel-signature-${index + 1}`,
    name: `Signature ${index + 1}`,
    gene_symbol: "",
    signature_method: "zscore",
  };
}

export function parsePanelSignatureGenes(value) {
  return inspectSignatureGeneInput(value).genes.map(
    ({ has_explicit_weight: _ignored, ...gene }) => gene,
  );
}

function signatureGenesAsInput(genes, method) {
  return genes
    .map((gene) => {
      if (signatureMethodUsesDirection(method)) {
        return gene.direction === "down" ? `${gene.gene_symbol}:-1` : gene.gene_symbol;
      }
      if (signatureMethodUsesNumericWeights(method) && gene.weight !== 1) {
        return `${gene.gene_symbol}:${gene.weight}`;
      }
      return gene.gene_symbol;
    });
}

export function normalizePanelSignature(signature, fallbackIndex = 0) {
  const method = signature.signature_method || "zscore";
  const score = normalizeSignatureInput(signature.gene_symbol, method);
  const normalizedGenes = score.genes;
  return {
    name:
      String(signature.name || "").trim() ||
      `Signature ${fallbackIndex + 1}`,
    gene_symbol: signatureGenesAsInput(normalizedGenes, method).join(", "),
    signature_method: method,
    signature_genes: method === "single" ? [] : normalizedGenes,
  };
}

export function validateSignaturePanel(signatures) {
  const submitted = signatures || [];
  const normalized = submitted.map(normalizePanelSignature);
  const errors = [];
  const warnings = [];
  if (
    normalized.length < MIN_SIGNATURE_PANEL_SIZE ||
    normalized.length > MAX_SIGNATURE_PANEL_SIZE
  ) {
    errors.push("Use between 2 and 6 signatures.");
  }
  const names = normalized.map((signature) =>
    signature.name.toLocaleLowerCase(),
  );
  if (new Set(names).size !== names.length) {
    errors.push("Signature names must be unique.");
  }
  normalized.forEach((signature, index) => {
    const score = normalizeSignatureInput(
      submitted[index]?.gene_symbol || "",
      signature.signature_method,
    );
    errors.push(...score.errors.map((error) => `Signature ${index + 1}: ${error}`));
    warnings.push(...score.warnings.map((warning) => `Signature ${index + 1}: ${warning}`));
    const genes = score.genes;
    if (!genes.length) {
      errors.push(`Signature ${index + 1} requires at least one gene.`);
    }
  });
  const definitions = normalized.map((signature) => {
    const genes = parsePanelSignatureGenes(signature.gene_symbol)
      .map((gene) => `${gene.gene_symbol}:${gene.weight}`)
      .sort()
      .join("|");
    return `${signature.signature_method}|${genes}`;
  });
  if (new Set(definitions).size !== definitions.length) {
    errors.push("Two signatures use the same score definition.");
  }
  return {
    valid: errors.length === 0,
    errors: [...new Set(errors)],
    warnings: [...new Set(warnings)],
    signatures: normalized,
  };
}

export function buildSignaturePanelRequest({
  form,
  signatures,
  plotStyle,
}) {
  const validation = validateSignaturePanel(signatures);
  if (!validation.valid) {
    throw new Error(validation.errors[0]);
  }
  const nullableNumber = (value) => {
    if (value === "" || value === null || value === undefined) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  return {
    cohort: form.cohort,
    dataset_id: form.dataset_id || null,
    dataset_release_id: form.dataset_release_id || null,
    expression_layer_id: form.expression_layer_id || null,
    panel_name: String(form.signature_panel?.name || "").trim() || null,
    signatures: validation.signatures,
    endpoint: form.endpoint,
    expression_scale: form.expression_scale,
    filters: {
      ...form.filters,
      age_min: nullableNumber(form.filters.age_min),
      age_max: nullableNumber(form.filters.age_max),
      max_time_days: nullableNumber(form.filters.max_time_days),
    },
    adjustment_covariates: [
      ...new Set(form.adjustment_covariates || []),
    ],
    external_covariates: form.external_covariates || null,
    external_adjustment_covariates: [
      ...new Set(form.external_adjustment_covariates || []),
    ],
    time_unit: form.time_unit,
    plot_style: plotStyle,
  };
}
