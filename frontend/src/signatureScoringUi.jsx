import React from "react";

import {
  normalizeSignatureInput,
  signatureMethodDefinition,
  signatureMethodInputHint,
  signatureMethodUsesDirection,
} from "./signatureScoring";

export const SIGNATURE_SCORING_METHODS_URL = `${String(
  import.meta.env.BASE_URL || "/",
).replace(/\/?$/, "/")}methods/signature-scoring/`;

function formatCount(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString("en-US") : "Not reported";
}

function formatPercent(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric * 100).toFixed(0)}%` : "Not reported";
}

function formatParameterName(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatParameterValue(value) {
  if (value === null || value === undefined) return "Not reported";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function SignatureInputSummary({ value, method, className = "" }) {
  const definition = signatureMethodDefinition(method);
  const result = normalizeSignatureInput(value, method);
  const hasGenes = result.genes.length > 0;
  const direction = signatureMethodUsesDirection(method)
    ? `${result.direction_counts.up} up · ${result.direction_counts.down} down`
    : `${result.genes.length} gene${result.genes.length === 1 ? "" : "s"}`;

  return (
    <div
      className={["signature-input-summary", className].filter(Boolean).join(" ")}
      role="note"
      aria-live="polite"
    >
      <span>
        <strong>{definition.shortLabel}</strong>
        {hasGenes ? <> · {direction}</> : null}
      </span>
      <small>{signatureMethodInputHint(method)}</small>
      <a
        className="signature-method-details-link"
        href={SIGNATURE_SCORING_METHODS_URL}
        target="_blank"
        rel="noreferrer"
      >
        Method details
      </a>
      {result.warnings.map((warning) => (
        <small className="signature-input-warning" key={warning}>{warning}</small>
      ))}
      {!result.valid && String(value || "").trim() && (
        <small className="signature-input-error">{result.errors[0]}</small>
      )}
    </div>
  );
}

export function SignatureScoringSummary({ signature, title = "Signature scoring" }) {
  if (!signature) return null;
  const method = signature.method || signature.signature_method || "single";
  const definition = signatureMethodDefinition(method);
  const coverage = signature.coverage || {};
  const parameters = signature.scoring_parameters || {};
  const universe = signature.gene_universe || {};
  const engine = signature.engine || {};
  const population = signature.scoring_population || {};
  const requested = coverage.requested_n;
  const mapped = coverage.mapped_n ?? coverage.resolved_n;
  const resolved = coverage.unique_resolved_n ?? coverage.resolved_n ?? mapped;
  const coverageLabel = Number.isFinite(Number(requested))
    ? `${formatCount(resolved)} resolved genes from ${formatCount(requested)} requested entries`
    : `${signature.genes?.length || 0} genes`;
  const inferredDirectionCounts = (signature.genes || []).reduce(
    (counts, gene) => {
      const direction = gene.direction || (Number(gene.weight) < 0 ? "down" : "up");
      if (direction === "down") counts.down += 1;
      else counts.up += 1;
      return counts;
    },
    { up: 0, down: 0 },
  );
  const directionCounts = signature.direction_counts
    || signature.direction
      ? {
          up: signature.direction_counts?.up
            ?? signature.direction?.up_n
            ?? signature.direction?.up_genes?.length
            ?? inferredDirectionCounts.up,
          down: signature.direction_counts?.down
            ?? signature.direction?.down_n
            ?? signature.direction?.down_genes?.length
            ?? inferredDirectionCounts.down,
        }
      : inferredDirectionCounts;
  const engineLabel = [engine.package || engine.name, engine.version]
    .filter(Boolean)
    .join(" ");
  const parameterEntries = Object.entries(parameters);

  return (
    <details className="result-disclosure signature-scoring-summary">
      <summary>
        <span>
          <strong>{title}</strong>
          <small>{coverageLabel}</small>
        </span>
        <b>{definition.shortLabel}</b>
      </summary>
      <div className="signature-scoring-contract">
        <dl>
          <div>
            <dt>Method</dt>
            <dd>{definition.label}{definition.recommended ? " · recommended rank option" : definition.sensitivity ? " · sensitivity" : ""}</dd>
          </div>
          <div>
            <dt>Coverage</dt>
            <dd>
              {coverageLabel}
              {mapped != null ? ` · ${formatCount(mapped)} mapped requests` : ""}
              {coverage.fraction != null ? ` · ${formatPercent(coverage.fraction)}` : ""}
            </dd>
          </div>
          {signatureMethodUsesDirection(method) && (
            <div>
              <dt>Direction</dt>
              <dd>{directionCounts.up} up · {directionCounts.down} down</dd>
            </div>
          )}
          {population.timing && (
            <div>
              <dt>Scoring population</dt>
              <dd>
                {formatParameterValue(population.timing)}
                {population.canonical_barcode_count != null
                  ? ` · ${formatCount(population.canonical_barcode_count)} samples in the scoring population`
                  : ""}
                {population.returned_barcode_count != null
                  ? ` · ${formatCount(population.returned_barcode_count)} retained`
                  : ""}
              </dd>
            </div>
          )}
          {(universe.gene_count != null
            || universe.expression_layer
            || universe.expression_scale_label
            || universe.expression_scale) && (
            <div>
              <dt>Measured genes</dt>
              <dd>
                {universe.gene_count != null ? `${formatCount(universe.gene_count)} genes` : ""}
                {universe.expression_layer
                  ? ` · ${universe.expression_layer}`
                  : universe.expression_scale_label
                    ? ` · ${universe.expression_scale_label}`
                    : universe.expression_scale
                      ? ` · ${universe.expression_scale}`
                      : ""}
              </dd>
            </div>
          )}
          {engineLabel && (
            <div>
              <dt>Engine</dt>
              <dd>{engineLabel}</dd>
            </div>
          )}
        </dl>
        {!!parameterEntries.length && (
          <div className="signature-scoring-parameters">
            <strong>Fixed parameters</strong>
            <dl>
              {parameterEntries.map(([key, value]) => (
                <div key={key}>
                  <dt>{formatParameterName(key)}</dt>
                  <dd>{formatParameterValue(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {!!coverage.missing_queries?.length && (
          <p className="signature-scoring-missing">
            Missing: {coverage.missing_queries.join(", ")}
          </p>
        )}
        <a
          className="signature-method-details-link"
          href={SIGNATURE_SCORING_METHODS_URL}
          target="_blank"
          rel="noreferrer"
        >
          Method details
        </a>
      </div>
    </details>
  );
}

export function SignatureScoringCollectionSummary({
  items = [],
  title = "Scoring details",
  description = "Check the genes, scoring method and population used in each analysis.",
}) {
  const availableItems = items.filter((item) => item?.signature);
  const [selectedId, setSelectedId] = React.useState(
    availableItems[0]?.id || "",
  );
  const selectId = React.useId();
  if (!availableItems.length) return null;
  const selected = availableItems.find((item) => item.id === selectedId)
    || availableItems[0];

  return (
    <section className="signature-scoring-collection" aria-labelledby={`${selectId}-title`}>
      <header>
        <div>
          <strong id={`${selectId}-title`}>{title}</strong>
          <small>{description}</small>
        </div>
        <span aria-label={`${availableItems.length} scoring records`}>
          {availableItems.length}
        </span>
      </header>
      {availableItems.length > 1 && (
        <label htmlFor={selectId}>
          <span>Inspect</span>
          <select
            id={selectId}
            value={selected.id}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {availableItems.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </label>
      )}
      <SignatureScoringSummary
        signature={selected.signature}
        title={selected.label || title}
      />
    </section>
  );
}
