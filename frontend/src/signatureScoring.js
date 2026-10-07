export const SIGNATURE_METHOD_OPTIONS = Object.freeze([
  Object.freeze({
    value: "single",
    label: "Single gene",
    shortLabel: "Single",
    optionLabel: "Single gene",
    family: "direct",
    minimumGenes: 1,
  }),
  Object.freeze({
    value: "singscore",
    label: "singscore",
    shortLabel: "singscore",
    optionLabel: "singscore · recommended rank score",
    family: "rank",
    minimumGenes: 2,
    recommended: true,
  }),
  Object.freeze({
    value: "ssgsea",
    label: "ssGSEA",
    shortLabel: "ssGSEA",
    optionLabel: "ssGSEA · sample-wise enrichment",
    family: "rank",
    minimumGenes: 2,
  }),
  Object.freeze({
    value: "aucell",
    label: "AUCell",
    shortLabel: "AUCell",
    optionLabel: "AUCell · top-ranked sensitivity",
    family: "rank",
    minimumGenes: 2,
    sensitivity: true,
  }),
  Object.freeze({
    value: "mean",
    label: "Mean signature",
    shortLabel: "Mean",
    optionLabel: "Mean expression",
    family: "magnitude",
    minimumGenes: 2,
  }),
  Object.freeze({
    value: "zscore",
    label: "Z-score signature",
    shortLabel: "Z-score",
    optionLabel: "Z-score signature",
    family: "weighted",
    minimumGenes: 2,
  }),
  Object.freeze({
    value: "weighted",
    label: "Weighted signature",
    shortLabel: "Weighted",
    optionLabel: "Weighted score",
    family: "weighted",
    minimumGenes: 2,
  }),
]);

export const MULTI_GENE_SIGNATURE_METHOD_OPTIONS = Object.freeze(
  SIGNATURE_METHOD_OPTIONS.filter((method) => method.value !== "single"),
);

export const RANK_SCORING_UNAVAILABLE_MESSAGE =
  "Rank-based scoring needs a complete expression matrix with at least 1,000 unique genes. This dataset does not meet that requirement. Use Mean, Z-score or Weighted, upload a complete matrix, or choose another expression layer.";

const METHODS_BY_VALUE = new Map(
  SIGNATURE_METHOD_OPTIONS.map((method) => [method.value, method]),
);

export function signatureMethodDefinition(method) {
  return METHODS_BY_VALUE.get(method) || METHODS_BY_VALUE.get("single");
}

export function signatureMethodUsesNumericWeights(method) {
  return signatureMethodDefinition(method).family === "weighted";
}

export function signatureMethodUsesDirection(method) {
  return signatureMethodDefinition(method).family === "rank";
}

export function rankScoringAvailability(
  dataset = null,
  cohort = null,
  expressionLayer = null,
) {
  const layerCapability = expressionLayer?.capabilities?.rank_based_signature_scoring
    || expressionLayer?.capabilities?.signature_scoring?.rank_based
    || null;
  const capability = layerCapability
    || dataset?.capabilities?.rank_based_signature_scoring
    || dataset?.capabilities?.signature_scoring?.rank_based
    || dataset?.capabilities?.rank_signature_scoring
    || null;
  const matrixEntryCount = capability?.matrix_entry_count == null
    ? Number.NaN
    : Number(capability.matrix_entry_count);
  const maximumMatrixEntries = capability?.maximum_matrix_entries == null
    ? Number.NaN
    : Number(capability.maximum_matrix_entries);
  if (capability?.available === false) {
    return {
      available: false,
      reason: capability.reason || RANK_SCORING_UNAVAILABLE_MESSAGE,
      detail: capability.reason || null,
      missingValueCount: capability.missing_value_count ?? null,
      matrixEntryCount: Number.isFinite(matrixEntryCount) ? matrixEntryCount : null,
      maximumMatrixEntries: Number.isFinite(maximumMatrixEntries)
        ? maximumMatrixEntries
        : null,
    };
  }
  const geneCount = Number(
    capability?.gene_count
      ?? expressionLayer?.gene_count
      ?? dataset?.gene_count
      ?? dataset?.capabilities?.expression?.gene_count
      ?? dataset?.capabilities?.expression_comparison?.gene_count
      ?? cohort?.n_genes,
  );
  if (Number.isFinite(geneCount) && geneCount < 1000) {
    return { available: false, reason: RANK_SCORING_UNAVAILABLE_MESSAGE };
  }
  if (
    Number.isFinite(matrixEntryCount)
    && Number.isFinite(maximumMatrixEntries)
    && matrixEntryCount > maximumMatrixEntries
  ) {
    return {
      available: false,
      reason: `Rank-based scoring is unavailable because the selected expression layer contains ${matrixEntryCount.toLocaleString("en-US")} matrix entries; the current limit is ${maximumMatrixEntries.toLocaleString("en-US")}. Use Mean, Z-score or Weighted, or choose a smaller expression layer.`,
      matrixEntryCount,
      maximumMatrixEntries,
    };
  }
  if (dataset && expressionLayer && !layerCapability) {
    return {
      available: false,
      reason: "Rank-based scoring is unavailable because TRACE could not verify that every value in the selected expression layer is finite. Use Mean, Z-score or Weighted, or choose a verified complete layer.",
    };
  }
  if (dataset && capability?.complete_matrix_verified !== true) {
    return {
      available: false,
      reason: capability?.reason
        || "Rank-based scoring is unavailable because TRACE could not verify that every value in the selected expression layer is finite. Use Mean, Z-score or Weighted, or choose a verified complete layer.",
      missingValueCount: capability?.missing_value_count ?? null,
    };
  }
  return {
    available: true,
    reason: capability?.reason || "The selected broad expression layer is complete.",
    missingValueCount: capability?.missing_value_count ?? 0,
    matrixEntryCount: Number.isFinite(matrixEntryCount) ? matrixEntryCount : null,
    maximumMatrixEntries: Number.isFinite(maximumMatrixEntries)
      ? maximumMatrixEntries
      : null,
  };
}

export function signatureMethodInputHint(method) {
  if (signatureMethodUsesNumericWeights(method)) {
    return "Optional weights use GENE:weight. Every weight must be non-zero.";
  }
  if (signatureMethodUsesDirection(method)) {
    return "Plain genes or GENE:1 are up; GENE:-1 marks down. Rank methods use direction, not weight magnitude.";
  }
  return "Enter gene symbols without weights.";
}

/**
 * Parse once without applying a scoring policy. The first occurrence of a
 * symbol is retained so every caller shares the same deterministic duplicate
 * rule. Method-specific validation is applied by normalizeSignatureInput.
 */
export function inspectSignatureGeneInput(rawValue) {
  const tokens = String(rawValue || "")
    .split(/[,+;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const genes = [];
  const duplicates = [];
  const seen = new Set();

  for (const token of tokens) {
    const parts = token.split(":");
    if (parts.length > 2) {
      throw new Error(`${token} has more than one weight separator.`);
    }
    const geneSymbol = String(parts[0] || "").trim().toUpperCase();
    if (!geneSymbol) throw new Error("Gene symbols must not be empty.");
    if (geneSymbol.length > 128) {
      throw new Error(`${geneSymbol} exceeds 128 characters.`);
    }
    const hasExplicitWeight = parts.length === 2;
    const rawWeight = hasExplicitWeight ? String(parts[1] || "").trim() : "";
    if (hasExplicitWeight && !rawWeight) {
      throw new Error(`${geneSymbol} is missing its weight.`);
    }
    const weight = hasExplicitWeight ? Number(rawWeight) : 1;
    if (!Number.isFinite(weight)) {
      throw new Error(`Invalid weight for ${geneSymbol}.`);
    }
    if (weight === 0) {
      throw new Error(`${geneSymbol} has weight 0. Remove the gene or use a non-zero weight.`);
    }
    if (seen.has(geneSymbol)) {
      duplicates.push(geneSymbol);
      continue;
    }
    seen.add(geneSymbol);
    genes.push({
      gene_symbol: geneSymbol,
      weight,
      has_explicit_weight: hasExplicitWeight,
    });
  }

  return { genes, duplicates: [...new Set(duplicates)] };
}

export function normalizeSignatureInput(rawValue, method) {
  const definition = METHODS_BY_VALUE.get(method);
  if (!definition) {
    return {
      valid: false,
      errors: [`Unknown signature scoring method: ${method}.`],
      warnings: [],
      genes: [],
      duplicate_queries: [],
      direction_counts: { up: 0, down: 0 },
    };
  }

  try {
    const parsed = inspectSignatureGeneInput(rawValue);
    const errors = [];
    const warnings = [];
    if (!parsed.genes.length) {
      errors.push("Enter at least one gene.");
    }
    if (method === "single" && parsed.genes.length !== 1) {
      errors.push("Single-gene scoring requires exactly one gene.");
    }
    if (parsed.genes.length > 0 && parsed.genes.length < definition.minimumGenes) {
      errors.push(`${definition.label} requires at least ${definition.minimumGenes} genes.`);
    }

    if (
      definition.family === "direct"
      || definition.family === "magnitude"
    ) {
      const qualified = parsed.genes.find((gene) => gene.has_explicit_weight);
      if (qualified) {
        errors.push(
          `${definition.label} does not use weights. Remove :${qualified.weight} from ${qualified.gene_symbol}.`,
        );
      }
    }

    if (definition.family === "rank") {
      const invalid = parsed.genes.find((gene) => Math.abs(gene.weight) !== 1);
      if (invalid) {
        errors.push(
          `${definition.label} uses direction only. Use ${invalid.gene_symbol}:1 for up or ${invalid.gene_symbol}:-1 for down.`,
        );
      }
    }

    if (parsed.duplicates.length) {
      warnings.push(
        `Duplicate ${parsed.duplicates.join(", ")} ${parsed.duplicates.length === 1 ? "entry was" : "entries were"} ignored; the first occurrence is retained.`,
      );
    }

    const genes = parsed.genes.map((gene) => {
      const base = {
        gene_symbol: gene.gene_symbol,
        weight: gene.weight,
      };
      if (definition.family === "rank") {
        return {
          ...base,
          direction: gene.weight < 0 ? "down" : "up",
        };
      }
      return base;
    });
    const directionCounts = definition.family === "rank"
      ? genes.reduce(
          (counts, gene) => ({
            ...counts,
            [gene.direction]: counts[gene.direction] + 1,
          }),
          { up: 0, down: 0 },
        )
      : { up: 0, down: 0 };
    if (method === "ssgsea") {
      for (const direction of ["up", "down"]) {
        if (directionCounts[direction] === 1) {
          errors.push(
            `ssGSEA requires at least 2 ${direction} genes when that component is present.`,
          );
        }
      }
    }

    return {
      valid: errors.length === 0,
      errors,
      warnings,
      genes,
      duplicate_queries: parsed.duplicates,
      direction_counts: directionCounts,
    };
  } catch (error) {
    return {
      valid: false,
      errors: [error.message],
      warnings: [],
      genes: [],
      duplicate_queries: [],
      direction_counts: { up: 0, down: 0 },
    };
  }
}
