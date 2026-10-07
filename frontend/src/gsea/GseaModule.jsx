import ResultTabs, { ResultSection } from "../ResultTabs";
import React, {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import ExpressionDataSelector from "../expression/ExpressionDataSelector";
import { scientificNumber } from "../scientificNumbers";
import {
  createGseaAnalysis,
  getGseaCollections,
  searchGenes,
  searchRepositoryGenes,
} from "../api";
import { ModuleIcon, TraceIcon } from "../design/icons";
import MolecularPopulationSelector from "../MolecularPopulationSelector";
import ClinicalFilterControls, {
  ClinicalVariableProvenance,
  clinicalFilterSummary,
} from "../clinical/ClinicalFilterControls";
import {
  isGeneListClipboardValue,
  mergeClipboardGeneList,
} from "../geneListClipboard";
import { GUIDE_ANCHORS, GuideAnchor } from "../tutorials";
import { FieldWithHelp, SectionHelp, Term } from "../help";
import { ActiveJobRecovery, ElapsedTime } from "../resilience/Resilience";
import {
  SIGNATURE_METHOD_OPTIONS,
  rankScoringAvailability,
  signatureMethodInputHint,
  signatureMethodUsesDirection,
} from "../signatureScoring";
import {
  SignatureInputSummary,
  SignatureScoringSummary,
} from "../signatureScoringUi";
import {
  cohortSupportsModule,
  datasetCapability,
  datasetSupportsModule,
  filterDatasetsForModule,
} from "../datasetCapabilities";
import {
  GSEA_EXPRESSION_CUTPOINTS,
  GSEA_GROUP_SOURCES,
  buildGseaPayload,
  chooseSurvivalContrast,
  clinicalGroupingVariables,
  clinicalVariableDefinition,
  clinicalVariableLevelOptions,
  eligibleSurvivalAnalyses,
  toggleDisjointGroupValue,
  validateGseaState,
} from "./gseaContract";
import {
  GSEA_DOTPLOT_NEG_LOG10_FDR_CAP,
  GSEA_TABLE_PAGE_SIZE,
  colorForNes,
  dotPlotSizeValue,
  dotRadiusForSignificance,
  geneCompletionContext,
  negativeLog10Fdr,
  replaceGeneCompletion,
  signatureGeneSymbols,
  topDotPlotPathways,
} from "./gseaUi";

function formatNumber(value, digits = 2) {
  const numeric = scientificNumber(value);
  if (numeric === null) return "NA";
  return numeric.toLocaleString("en-US", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatProbability(value) {
  const numeric = scientificNumber(value);
  if (numeric === null || numeric < 0 || numeric > 1) return "NA";
  if (numeric < 0.001) return numeric.toExponential(2);
  return numeric.toFixed(3);
}

function retainedSampleCount(sampleSelection = {}) {
  return Object.values(sampleSelection.retained_sample_types || {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  );
}

function formatSampleTypeCounts(counts = {}) {
  return Object.entries(counts)
    .map(([label, count]) => `${label} ${Number(count || 0).toLocaleString("en-US")}`)
    .join(" · ") || "No retained sample types reported";
}

const GSEA_REQUIREMENTS_ID = "gsea-run-requirements";

function validationHas(validation, ...fragments) {
  return validation.errors.some((error) =>
    fragments.some((fragment) => error.includes(fragment)),
  );
}

function firstInvalidControlId(state, form, validation, catalog) {
  if (!form.cohort) return "gsea-cohort";
  const firstError = validation.errors[0] || "";
  if (firstError === "Name both groups.") {
    return state.group_a_label.trim()
      ? "gsea-group-b-label"
      : "gsea-group-a-label";
  }
  if (firstError === "Group labels must be different.") {
    return "gsea-group-b-label";
  }
  if (firstError === "Choose a clinical variable.") {
    return "gsea-clinical-variable";
  }
  if (firstError.startsWith("Enter a numeric cutpoint")) {
    return "gsea-age-cutpoint";
  }
  if (firstError.startsWith("Select at least one clinical level")) {
    return "gsea-clinical-groups";
  }
  if (
    firstError.startsWith("Choose or enter a completed survival") ||
    firstError.startsWith("Select both source survival")
  ) {
    return "gsea-survival-analysis";
  }
  if (
    firstError.startsWith("Enter at least one gene") ||
    firstError.startsWith("Single-gene grouping") ||
    firstError.startsWith("Invalid weight") ||
    firstError.includes("requires at least") ||
    firstError.includes("does not use weights") ||
    firstError.includes("direction only") ||
    firstError.includes("weight 0")
  ) {
    return "gsea-signature-genes";
  }
  if (firstError.startsWith("Expression percentile")) {
    return "gsea-expression-percentile";
  }
  if (firstError.startsWith("Minimum gene-set")) {
    return "gsea-min-set-size";
  }
  if (firstError.startsWith("Maximum gene-set")) {
    return "gsea-max-set-size";
  }
  if (firstError.startsWith("Permutations")) return "gsea-permutations";
  if (firstError.startsWith("Seed")) return "gsea-seed";
  if (catalog.error || !catalog.collections.length) {
    return GSEA_REQUIREMENTS_ID;
  }
  return GSEA_REQUIREMENTS_ID;
}

function DownloadAnchor({
  href,
  iconRole,
  children,
  onDownload,
  ariaLabel,
}) {
  if (!href) return null;
  return (
    <button
      type="button"
      className="secondary-button compact"
      aria-label={ariaLabel}
      onClick={() => onDownload?.(href, String(children))}
    >
      <TraceIcon role={iconRole} size="sm" />
      {children}
    </button>
  );
}

function eligibilitySummary(filters = {}, variables = []) {
  const parts = [];
  [
    ["Sample", filters.sample_types],
    ["Stage", filters.stages],
    ["Grade", filters.grades],
    ["Gender", filters.genders],
    ["Race", filters.races],
  ].forEach(([label, values]) => {
    if (values?.length) parts.push(`${label}: ${values.join(", ")}`);
  });
  if (filters.age_min !== "" && filters.age_min != null) {
    parts.push(`Age ≥ ${filters.age_min}`);
  }
  if (filters.age_max !== "" && filters.age_max != null) {
    parts.push(`Age ≤ ${filters.age_max}`);
  }
  parts.push(...clinicalFilterSummary(filters.custom_filters || [], variables));
  return parts;
}

function useGseaGeneSuggestions({
  cohort,
  query,
  datasetId,
  datasetReleaseId,
  expressionLayerId,
}) {
  const [state, setState] = useState({
    genes: [],
    loading: false,
    error: "",
  });

  useEffect(() => {
    if (!cohort || !query) {
      setState({ genes: [], loading: false, error: "" });
      return undefined;
    }

    let cancelled = false;
    setState({ genes: [], loading: true, error: "" });
    const handle = window.setTimeout(() => {
      const lookup = datasetId
        ? searchRepositoryGenes(
            datasetId,
            query,
            datasetReleaseId,
            expressionLayerId,
          )
        : searchGenes(cohort, query);
      lookup
        .then((payload) => {
          if (!cancelled) {
            setState({
              genes: payload.genes || [],
              loading: false,
              error: "",
            });
          }
        })
        .catch(() => {
          if (!cancelled) {
            setState({
              genes: [],
              loading: false,
              error: "Gene suggestions are temporarily unavailable.",
            });
          }
        });
    }, 220);

    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [
    cohort,
    query,
    datasetId,
    datasetReleaseId,
    expressionLayerId,
  ]);

  return state;
}

function GeneExpressionAutocomplete({
  value,
  onChange,
  method,
  invalid,
  cohort,
  datasetId,
  datasetReleaseId,
  expressionLayerId,
}) {
  const inputRef = useRef(null);
  const labelId = useId();
  const helpId = useId();
  const listboxId = useId();
  const [cursor, setCursor] = useState(String(value || "").length);
  const [focused, setFocused] = useState(false);
  const [searchEnabled, setSearchEnabled] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const context = useMemo(
    () => geneCompletionContext(value, cursor),
    [value, cursor],
  );
  const query = context.query;
  const suggestionState = useGseaGeneSuggestions({
    cohort,
    query: searchEnabled ? query : "",
    datasetId,
    datasetReleaseId,
    expressionLayerId,
  });
  const outsideCurrentToken =
    String(value || "").slice(0, context.start) +
    String(value || "").slice(context.end);
  const alreadyIncluded = new Set(
    signatureGeneSymbols(outsideCurrentToken),
  );
  const suggestions = suggestionState.genes
    .filter((gene) => !alreadyIncluded.has(gene.toUpperCase()))
    .slice(0, 10);
  const open =
    focused && searchEnabled && Boolean(query) && !dismissed;
  const activeOptionId =
    open && suggestions[activeIndex]
      ? `${listboxId}-option-${activeIndex}`
      : undefined;
  const describedBy = [helpId, invalid ? GSEA_REQUIREMENTS_ID : null]
    .filter(Boolean)
    .join(" ");

  useEffect(() => {
    setActiveIndex(0);
  }, [query, suggestionState.genes]);

  function syncCursor(event) {
    setCursor(
      event.currentTarget.selectionStart ?? event.currentTarget.value.length,
    );
  }

  function selectGene(gene) {
    const normalized = String(gene || "").toUpperCase();
    const completed = replaceGeneCompletion(value, cursor, normalized);
    onChange(completed.value);
    setCursor(completed.cursor);
    setSearchEnabled(false);
    setDismissed(true);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(
        completed.cursor,
        completed.cursor,
      );
    });
  }

  function handleKeyDown(event) {
    if (!open) return;
    if (event.key === "ArrowDown" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp" && suggestions.length) {
      event.preventDefault();
      setActiveIndex(
        (current) => (current - 1 + suggestions.length) % suggestions.length,
      );
      return;
    }
    if (event.key === "Enter" && suggestions[activeIndex]) {
      event.preventDefault();
      selectGene(suggestions[activeIndex]);
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setDismissed(true);
    }
  }

  return (
    <div className="gsea-gene-field">
      <span id={labelId} className="gsea-gene-field-label">
        Gene or signature genes
      </span>
      <div className="gsea-gene-autocomplete-wrap">
        <textarea
          ref={inputRef}
          id="gsea-signature-genes"
          rows="3"
          value={value}
          onChange={(event) => {
            onChange(event.target.value);
            setCursor(event.target.selectionStart ?? event.target.value.length);
            setSearchEnabled(true);
            setDismissed(false);
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData?.getData("text") || "";
            if (!isGeneListClipboardValue(pasted)) return;
            event.preventDefault();
            const nextValue = mergeClipboardGeneList(value, pasted);
            onChange(nextValue);
            setCursor(nextValue.length);
            setSearchEnabled(false);
            setDismissed(true);
          }}
          onCopy={(event) => {
            if (
              event.currentTarget.selectionStart !==
                event.currentTarget.selectionEnd ||
              !String(value || "").trim()
            ) return;
            event.preventDefault();
            event.clipboardData?.setData("text/plain", String(value));
          }}
          onClick={syncCursor}
          onKeyUp={syncCursor}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            setSearchEnabled(false);
          }}
          placeholder={method === "single" ? "CA9" : "CA9, VEGFA, SLC2A1"}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-activedescendant={activeOptionId}
          aria-labelledby={labelId}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          autoComplete="off"
          spellCheck="false"
        />
        {open && (
          <div
            id={listboxId}
            className="gene-autocomplete gsea-gene-autocomplete"
            role="listbox"
            aria-label={`Gene suggestions for ${query}`}
            aria-busy={suggestionState.loading}
          >
            <div className="gene-autocomplete-title">
              Suggestions for <strong>{query}</strong>
            </div>
            {suggestionState.loading ? (
              <div className="gene-autocomplete-empty" role="status">
                Searching dataset genes...
              </div>
            ) : suggestionState.error ? (
              <div className="gene-autocomplete-empty" role="status">
                {suggestionState.error}
              </div>
            ) : suggestions.length ? (
              suggestions.map((gene, index) => (
                <button
                  id={`${listboxId}-option-${index}`}
                  key={gene}
                  type="button"
                  role="option"
                  tabIndex="-1"
                  aria-selected={index === activeIndex}
                  className={index === activeIndex ? "active" : ""}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => selectGene(gene)}
                >
                  <strong>{gene}</strong>
                  <span>Use gene</span>
                </button>
              ))
            ) : suggestionState.genes.length ? (
              <div className="gene-autocomplete-empty">
                Matching genes are already included.
              </div>
            ) : (
              <div className="gene-autocomplete-empty">
                No matching gene symbols.
              </div>
            )}
          </div>
        )}
      </div>
      <small id={helpId}>
        {method === "single"
          ? "Type and select exactly one HGNC gene symbol."
          : method === "weighted"
            ? "Paste a list with Ctrl/Cmd+V or separate genes with commas. Weighted mode preserves GENE:weight values when completing a symbol. Every weight must be non-zero."
            : `Paste a list with Ctrl/Cmd+V or separate genes with commas. ${signatureMethodInputHint(method)}`}
      </small>
      <span className="sr-only" role="status" aria-live="polite">
        {open && !suggestionState.loading && !suggestionState.error
          ? `${suggestions.length} gene suggestion${suggestions.length === 1 ? "" : "s"} available.`
          : ""}
      </span>
    </div>
  );
}

function GroupLabelFields({ state, update, validation }) {
  const groupAInvalid =
    !state.group_a_label.trim() ||
    validationHas(validation, "Group labels must be different.");
  const groupBInvalid =
    !state.group_b_label.trim() ||
    validationHas(validation, "Group labels must be different.");
  return (
    <div className="gsea-label-grid">
      <label>
        <span>Group A · reference</span>
        <input
          id="gsea-group-a-label"
          value={state.group_a_label}
          onChange={(event) => update({ group_a_label: event.target.value })}
          maxLength={64}
          aria-invalid={groupAInvalid}
          aria-describedby={groupAInvalid ? GSEA_REQUIREMENTS_ID : undefined}
        />
      </label>
      <label>
        <span>Group B · target</span>
        <input
          id="gsea-group-b-label"
          value={state.group_b_label}
          onChange={(event) => update({ group_b_label: event.target.value })}
          maxLength={64}
          aria-invalid={groupBInvalid}
          aria-describedby={groupBInvalid ? GSEA_REQUIREMENTS_ID : undefined}
        />
      </label>
    </div>
  );
}

function ClinicalGroupBuilder({
  state,
  setState,
  filters,
  update,
  validation,
}) {
  const variables = filters ? clinicalGroupingVariables(filters) : [];
  const definition = clinicalVariableDefinition(
    filters,
    state.clinical_variable,
  );
  const levelOptions = clinicalVariableLevelOptions(
    filters,
    state.clinical_variable,
  );
  const levels = levelOptions.map((item) => item.value);
  const numericVariable = definition?.value_type === "numeric";
  const numericInvalid = validationHas(validation, "Enter a numeric cutpoint");
  const groupsInvalid = validationHas(
    validation,
    "Select at least one clinical level",
  );
  return (
    <div className="gsea-group-builder">
      <label>
        <span>Clinical variable</span>
        <select
          id="gsea-clinical-variable"
          value={state.clinical_variable}
          disabled={!filters}
          onChange={(event) =>
            update({
              clinical_variable: event.target.value,
              group_a_values: [],
              group_b_values: [],
            })
          }
        >
          <option value="">
            {filters ? "Choose a clinical variable" : "Loading clinical metadata…"}
          </option>
          {[...new Set(variables.map((item) => item.category_label))].map(
            (categoryLabel) => (
              <optgroup key={categoryLabel} label={categoryLabel}>
                {variables
                  .filter((item) => item.category_label === categoryLabel)
                  .map((item) => (
                    <option
                      key={item.value}
                      value={item.value}
                      disabled={!item.analysis_eligible}
                    >
                      {item.label}
                      {item.non_missing_count != null
                        ? ` · n=${item.non_missing_count}`
                        : ""}
                      {!item.analysis_eligible ? " · unavailable" : ""}
                    </option>
                  ))}
              </optgroup>
            ),
          )}
        </select>
      </label>

      {definition && (
        <ClinicalVariableProvenance variable={definition} />
      )}

      {numericVariable ? (
        <div className="gsea-age-cutpoint">
          <label>
            <span>{definition.label} threshold</span>
            <select
              value={state.clinical_cutpoint_method}
              onChange={(event) =>
                update({ clinical_cutpoint_method: event.target.value })
              }
            >
              <option value="median">Cohort median</option>
              <option value="value">Fixed value</option>
            </select>
          </label>
          {state.clinical_cutpoint_method === "value" && (
            <label>
              <span>
                Value
                {definition.numeric_summary?.unit
                  ? ` (${definition.numeric_summary.unit})`
                  : ""}
              </span>
              <input
                id="gsea-age-cutpoint"
                type="number"
                min={definition.numeric_summary?.min ?? undefined}
                max={definition.numeric_summary?.max ?? undefined}
                step="any"
                value={state.clinical_cutpoint}
                onChange={(event) =>
                  update({ clinical_cutpoint: event.target.value })
                }
                aria-invalid={numericInvalid}
                aria-describedby={
                  numericInvalid ? GSEA_REQUIREMENTS_ID : undefined
                }
              />
            </label>
          )}
          <p className="field-note">
            Group A contains values at or below the threshold. Group B contains
            values above it.
          </p>
        </div>
      ) : levels.length ? (
        <div
          id="gsea-clinical-groups"
          className="gsea-level-matrix"
          role="group"
          aria-label="Clinical levels assigned to groups A and B"
          aria-invalid={groupsInvalid}
          aria-describedby={
            groupsInvalid ? GSEA_REQUIREMENTS_ID : undefined
          }
          tabIndex={groupsInvalid ? -1 : undefined}
        >
          <div className="gsea-level-head" aria-hidden="true">
            <span>Clinical level</span>
            <span>A</span>
            <span>B</span>
          </div>
          {levelOptions.map((level) => (
            <div
              className={`gsea-level-row${level.analysis_eligible ? "" : " is-unavailable"}`}
              key={level.value}
            >
              <span>
                {level.label}
                {level.count != null && (
                  <small>
                    n={level.count}
                    {!level.analysis_eligible ? " · unavailable for an individual group" : ""}
                  </small>
                )}
              </span>
              <label title={level.unavailable_reason || `Assign ${level.label} to group A`}>
                <input
                  type="checkbox"
                  disabled={!level.analysis_eligible}
                  checked={state.group_a_values.includes(level.value)}
                  onChange={() =>
                    setState((current) =>
                      toggleDisjointGroupValue(current, "a", level.value),
                    )
                  }
                  aria-label={`Assign ${level.label} to group A`}
                />
              </label>
              <label title={level.unavailable_reason || `Assign ${level.label} to group B`}>
                <input
                  type="checkbox"
                  disabled={!level.analysis_eligible}
                  checked={state.group_b_values.includes(level.value)}
                  onChange={() =>
                    setState((current) =>
                      toggleDisjointGroupValue(current, "b", level.value),
                    )
                  }
                  aria-label={`Assign ${level.label} to group B`}
                />
              </label>
            </div>
          ))}
        </div>
      ) : (
        <p
          id="gsea-clinical-groups"
          className="gsea-inline-empty"
          tabIndex="-1"
          aria-describedby={GSEA_REQUIREMENTS_ID}
        >
          This variable has no levels in the selected dataset.
        </p>
      )}
      <GroupLabelFields
        state={state}
        update={update}
        validation={validation}
      />
    </div>
  );
}

function SurvivalGroupBuilder({ state, analyses, update, validation }) {
  const eligible = useMemo(
    () => eligibleSurvivalAnalyses(analyses),
    [analyses],
  );
  const analysisInvalid = validationHas(
    validation,
    "Choose or enter a completed survival",
    "Select both source survival",
  );

  function chooseAnalysis(value) {
    const item = eligible.find((entry) => entry.analysis.id === value);
    if (!item) {
      update({
        survival_analysis_id: value,
        survival_group_a: "",
        survival_group_b: "",
      });
      return;
    }
    const contrast = chooseSurvivalContrast(item.groups);
    update({
      survival_analysis_id: item.analysis.id,
      survival_group_a: contrast.groupA,
      survival_group_b: contrast.groupB,
      group_a_label: contrast.groupA,
      group_b_label: contrast.groupB,
    });
  }

  return (
    <div className="gsea-group-builder">
      {eligible.length > 0 && (
        <label>
          <span>Recent two-group result</span>
          <select
            value={
              eligible.some(
                (item) => item.analysis.id === state.survival_analysis_id,
              )
                ? state.survival_analysis_id
                : ""
            }
            onChange={(event) => chooseAnalysis(event.target.value)}
          >
            <option value="">Choose a completed result</option>
            {eligible.map(({ analysis, groups }) => (
              <option key={analysis.id} value={analysis.id}>
                {analysis.gene_symbol} · {analysis.cutpoint_method} ·{" "}
                {groups.join(" / ")}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <span>Source analysis ID</span>
        <input
          id="gsea-survival-analysis"
          value={state.survival_analysis_id}
          onChange={(event) => chooseAnalysis(event.target.value.trim())}
          placeholder="Paste a completed survival analysis ID"
          aria-invalid={analysisInvalid}
          aria-describedby={
            analysisInvalid ? GSEA_REQUIREMENTS_ID : undefined
          }
        />
      </label>
      {state.survival_group_a && state.survival_group_b && (
        <div
          className="gsea-inherited-groups"
          role="group"
          aria-label="Inherited groups"
        >
          <span>
            Reference <strong>{state.survival_group_a}</strong>
          </span>
          <TraceIcon role="data.compare" size="sm" tone="secondary" />
          <span>
            Target <strong>{state.survival_group_b}</strong>
          </span>
        </div>
      )}
      <p className="field-note">
        The server reads the exact patient assignments from the source result.
        It does not reconstruct them from the displayed threshold.
      </p>
      {!eligible.length && (
        <p className="gsea-inline-empty">
          Run a two-group survival analysis first, or paste an unexpired result
          ID.
        </p>
      )}
      <GroupLabelFields
        state={state}
        update={update}
        validation={validation}
      />
    </div>
  );
}

function ExpressionGroupBuilder({
  state,
  update,
  validation,
  form,
  rankScoring,
}) {
  const genesInvalid = validationHas(
    validation,
    "Enter at least one gene",
    "Single-gene grouping",
    "Invalid weight",
    "requires at least",
    "does not use weights",
    "direction only",
    "weight 0",
  );
  const percentileInvalid = validationHas(
    validation,
    "Expression percentile",
  );
  return (
    <div className="gsea-group-builder">
      <GeneExpressionAutocomplete
        value={state.signature_genes}
        onChange={(signatureGenes) =>
          update({ signature_genes: signatureGenes })
        }
        method={state.signature_method}
        invalid={genesInvalid}
        cohort={form.cohort}
        datasetId={form.dataset_id}
        datasetReleaseId={form.dataset_release_id}
        expressionLayerId={form.expression_layer_id}
      />
      <div className="gsea-method-grid">
        <FieldWithHelp
          label="Score"
          htmlFor="gsea-expression-score"
          helpId={`score.${state.signature_method}`}
        >
          <select
            id="gsea-expression-score"
            value={state.signature_method}
            onChange={(event) =>
              update({ signature_method: event.target.value })
            }
          >
            {SIGNATURE_METHOD_OPTIONS.map((method) => (
              <option
                key={method.value}
                value={method.value}
                disabled={
                  signatureMethodUsesDirection(method.value)
                  && !rankScoring.available
                }
              >
                {method.optionLabel}
              </option>
            ))}
          </select>
        </FieldWithHelp>
        <label>
          <span>Two-group cutpoint</span>
          <select
            value={state.cutpoint_method}
            onChange={(event) =>
              update({ cutpoint_method: event.target.value })
            }
          >
            {GSEA_EXPRESSION_CUTPOINTS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <SignatureInputSummary
        method={state.signature_method}
        value={state.signature_genes}
      />
      {signatureMethodUsesDirection(state.signature_method)
        && !rankScoring.available && (
        <p className="signature-rank-unavailable" role="alert">
          {rankScoring.reason}
        </p>
      )}
      {state.cutpoint_method === "percentile" && (
        <label>
          <span>Percentile threshold</span>
          <input
            id="gsea-expression-percentile"
            type="number"
            min="1"
            max="99"
            value={state.custom_percentile}
            onChange={(event) =>
              update({ custom_percentile: event.target.value })
            }
            aria-invalid={percentileInvalid}
            aria-describedby={
              percentileInvalid ? GSEA_REQUIREMENTS_ID : undefined
            }
          />
        </label>
      )}
      <div className="gsea-method-note" role="note">
        <TraceIcon role="status.info" size="sm" tone="secondary" />
        <span>
          These groups come from the same expression matrix used for ranking.
          The result is descriptive and not an independent validation.
        </span>
      </div>
      <GroupLabelFields
        state={state}
        update={update}
        validation={validation}
      />
    </div>
  );
}

function GseaSetupPreview({
  state,
  form,
  validation,
  selectedCollection,
  catalog,
  clinicalVariable,
  rankScoring,
}) {
  const source = GSEA_GROUP_SOURCES.find(
    (item) => item.value === state.grouping_source,
  );
  const catalogReady =
    !catalog.loading &&
    !catalog.error &&
    catalog.collections.length > 0;
  const clinicalReady =
    state.grouping_source !== "clinical" ||
    clinicalVariable?.analysis_eligible;
  const rankScoringReady = state.grouping_source !== "expression"
    || !signatureMethodUsesDirection(state.signature_method)
    || rankScoring.available;
  const ready = Boolean(
    form.cohort
    && validation.valid
    && catalogReady
    && clinicalReady
    && rankScoringReady,
  );
  const requirements = [
    ...(!form.cohort ? ["Select a dataset."] : []),
    ...validation.errors,
    ...(!clinicalReady ? ["Choose an available clinical variable."] : []),
    ...(!rankScoringReady ? [rankScoring.reason] : []),
    ...(catalog.loading ? ["Wait for the gene-set catalog to load."] : []),
    ...(catalog.error ? [catalog.error] : []),
    ...(!catalog.loading && !catalog.error && !catalog.collections.length
      ? ["No gene-set collection is currently available."]
      : []),
  ];
  const readinessMessage = ready
    ? "Ready to rank genes and test pathways."
    : !form.cohort
      ? "Select a dataset to continue."
      : validation.errors[0] ||
        (!rankScoringReady ? rankScoring.reason : "") ||
        (catalog.loading
          ? "Loading the gene-set catalog."
          : catalog.error ||
            "No gene-set collection is currently available.");
  return (
    <aside className="result-panel gsea-preview" aria-label="GSEA design preview">
      <header className="gsea-preview-header">
        <ModuleIcon role="module.geneSetEnrichment" />
        <div>
          <span className="result-family-label">Planned contrast</span>
          <h2>
            {state.group_b_label || "Group B"} vs{" "}
            {state.group_a_label || "Group A"}
          </h2>
        </div>
      </header>
      <dl className="gsea-design-ledger">
        <div>
          <dt>Dataset</dt>
          <dd>{form.dataset_id || form.cohort || "Not selected"}</dd>
        </div>
        <div>
          <dt>Groups</dt>
          <dd>{source?.label || "Not selected"}</dd>
        </div>
        {state.grouping_source === "clinical" && (
          <div>
            <dt>Clinical field</dt>
            <dd>{clinicalVariable?.label || "Not selected"}</dd>
          </div>
        )}
        <div>
          <dt>Collection</dt>
          <dd>{selectedCollection?.label || state.gene_set_collection}</dd>
        </div>
        <div>
          <dt>Ranking</dt>
          <dd>Group B minus group A · {state.ranking_metric}</dd>
        </div>
        <div>
          <dt>NES normalization</dt>
          <dd>{state.permutations} permutations normalize descriptive NES · seed {state.seed}</dd>
        </div>
        <div>
          <dt>Multiple-testing correction</dt>
          <dd>CAMERA with per-set estimated correlation · BH across tested pathways</dd>
        </div>
      </dl>
      <div
        className={`gsea-readiness ${ready ? "ready" : ""}`}
        role="status"
      >
        <TraceIcon
          role={
            ready ? "status.success" : "status.info"
          }
          size="sm"
          tone={ready ? "success" : "secondary"}
        />
        <span>{readinessMessage}</span>
      </div>
      <p className="gsea-direction-note">
        Positive NES favors <strong>{state.group_b_label || "group B"}</strong>.
        Negative NES favors <strong>{state.group_a_label || "group A"}</strong>.
      </p>
      {!ready && (
        <ul
          id={GSEA_REQUIREMENTS_ID}
          className="gsea-requirements"
          aria-label="Requirements to run GSEA"
          tabIndex="-1"
        >
          {requirements.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
    </aside>
  );
}

function truncatePathwayLabel(value, maximum = 42) {
  const label = String(value || "");
  return label.length > maximum
    ? `${label.slice(0, maximum - 1)}…`
    : label;
}

export function GseaDotPlot({
  pathways,
  groupA,
  groupB,
  fdrLabel = "CAMERA FDR",
}) {
  const rows = topDotPlotPathways(pathways);
  const token = useId().replaceAll(":", "");
  const titleId = `gsea-dotplot-title-${token}`;
  const descriptionId = `gsea-dotplot-description-${token}`;
  const width = 1040;
  const plotLeft = 48;
  const plotRight = 612;
  const plotWidth = plotRight - plotLeft;
  const pathwayLabelX = plotRight + 18;
  const rowHeight = 34;
  const plotTop = 22;
  const plotBottom = plotTop + rows.length * rowHeight;
  const height = Math.max(180, plotBottom + 62);
  const maximumAbsoluteNes = Math.max(
    1,
    ...rows.map((row) => Math.abs(Number(row.nes))),
  );
  const positionLimit = maximumAbsoluteNes * 1.06;
  const significances = rows.map((row) => negativeLog10Fdr(row.fdr) || 0);
  const sizeValues = rows.map((row) => dotPlotSizeValue(row.fdr) || 0);
  const maximumSignificance = GSEA_DOTPLOT_NEG_LOG10_FDR_CAP;
  const sizeLegendValues = [1, 3, GSEA_DOTPLOT_NEG_LOG10_FDR_CAP];
  const xPosition = (nes) =>
    plotLeft +
    ((Number(nes) + positionLimit) / (2 * positionLimit)) *
      plotWidth;
  const negativeColor = colorForNes(
    -maximumAbsoluteNes,
    maximumAbsoluteNes,
  );
  const neutralColor = colorForNes(0, maximumAbsoluteNes);
  const positiveColor = colorForNes(
    maximumAbsoluteNes,
    maximumAbsoluteNes,
  );

  return (
    <figure
      className="gsea-dotplot"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      <figcaption>
        <div>
          <strong id={titleId}>Pathway DotPlot</strong>
          <span id={descriptionId}>
            Top {rows.length} pathways by {fdrLabel}. Point area is{" "}
            min(−log10({fdrLabel}), {GSEA_DOTPLOT_NEG_LOG10_FDR_CAP}); horizontal
            position and blue–white–red color are NES.
          </span>
        </div>
        <div className="gsea-dotplot-direction" aria-label="NES direction">
          <span>{groupA}</span>
          <i aria-hidden="true" />
          <span>{groupB}</span>
        </div>
      </figcaption>
      {rows.length ? (
        <>
          <div
            className="gsea-dotplot-legends"
            data-position="top"
            aria-label="DotPlot legends"
          >
            <div className="gsea-dotplot-size-legend">
              <strong>Point area</strong>
              <span>
                min(−log10({fdrLabel}), {GSEA_DOTPLOT_NEG_LOG10_FDR_CAP})
              </span>
              {sizeLegendValues.map((value) => (
                <span key={value}>
                  <i
                    aria-hidden="true"
                    style={{
                      "--gsea-dot-size": `${Math.max(
                        2,
                        dotRadiusForSignificance(
                          value,
                          maximumSignificance,
                        ) * 2,
                      )}px`,
                    }}
                  />
                  {formatNumber(value, 0)}
                </span>
              ))}
              <span>× marks {fdrLabel} = 1</span>
            </div>
            <div className="gsea-dotplot-color-legend">
              <strong>Color</strong>
              <span>NES</span>
              <i
                aria-hidden="true"
                style={{
                  "--gsea-negative-color": negativeColor,
                  "--gsea-neutral-color": neutralColor,
                  "--gsea-positive-color": positiveColor,
                }}
              />
              <span>
                {formatNumber(-maximumAbsoluteNes, 2)} · 0 ·{" "}
                {formatNumber(maximumAbsoluteNes, 2)}
              </span>
            </div>
          </div>
          <div
            className="gsea-dotplot-canvas"
            role="img"
            tabIndex="0"
            aria-label={`Dot plot of ${rows.length} pathways. Negative NES favors ${groupA}; positive NES favors ${groupB}. Circle area encodes negative log10 ${fdrLabel}. A dashed vertical line marks NES zero.`}
          >
            <svg
              viewBox={`0 0 ${width} ${height}`}
              aria-hidden="true"
              focusable="false"
            >
              <rect
                className="gsea-dotplot-panel"
                x={plotLeft}
                y={plotTop}
                width={plotWidth}
                height={plotBottom - plotTop}
              />
              <line
                className="zero"
                data-role="nes-zero-reference"
                x1={xPosition(0)}
                x2={xPosition(0)}
                y1={plotTop}
                y2={plotBottom}
              />
              <g data-role="nes-axis" data-position="bottom">
                {[-maximumAbsoluteNes, 0, maximumAbsoluteNes].map((tick) => {
                  const x = xPosition(tick);
                  return (
                    <g key={tick}>
                      <line
                        className="gsea-dotplot-axis-tick"
                        x1={x}
                        x2={x}
                        y1={plotBottom}
                        y2={plotBottom + 5}
                      />
                      <text
                        className="gsea-dotplot-axis-label"
                        x={x}
                        y={plotBottom + 20}
                        textAnchor={
                          tick < 0 ? "start" : tick > 0 ? "end" : "middle"
                        }
                      >
                        {formatNumber(tick, 2)}
                      </text>
                    </g>
                  );
                })}
                <text
                  className="gsea-dotplot-axis-title"
                  x={(plotLeft + plotRight) / 2}
                  y={plotBottom + 46}
                  textAnchor="middle"
                >
                  Normalized enrichment score (NES)
                </text>
              </g>
              {rows.map((row, index) => {
                const nes = Number(row.nes);
                const significance = significances[index];
                const sizeValue = sizeValues[index];
                const y = plotTop + index * rowHeight + rowHeight / 2;
                const radius = dotRadiusForSignificance(
                  sizeValue,
                  maximumSignificance,
                );
                return (
                  <g className="gsea-dotplot-row" key={row.pathway}>
                    <text
                      data-role="pathway-label"
                      data-axis-side="right"
                      x={pathwayLabelX}
                      y={y + 4}
                      textAnchor="start"
                    >
                      {truncatePathwayLabel(row.pathway, 55)}
                    </text>
                    {sizeValue === 0 ? (
                      <path
                        className="gsea-dotplot-zero-mark"
                        d={`M ${xPosition(nes) - 3} ${y - 3} L ${
                          xPosition(nes) + 3
                        } ${y + 3} M ${xPosition(nes) + 3} ${y - 3} L ${
                          xPosition(nes) - 3
                        } ${y + 3}`}
                        data-negative-log10-fdr={significance}
                        data-size-value={sizeValue}
                        data-nes={nes}
                      >
                        <title>{`${row.pathway}: NES ${formatNumber(
                          nes,
                          3,
                        )}, ${fdrLabel} ${formatProbability(
                          row.fdr,
                        )}, −log10(${fdrLabel}) ${formatNumber(
                          significance,
                          3,
                        )}`}</title>
                      </path>
                    ) : (
                      <circle
                        cx={xPosition(nes)}
                        cy={y}
                        r={radius}
                        fill={colorForNes(nes, maximumAbsoluteNes)}
                        data-negative-log10-fdr={significance}
                        data-size-value={sizeValue}
                        data-nes={nes}
                      >
                        <title>{`${row.pathway}: NES ${formatNumber(
                          nes,
                          3,
                        )}, ${fdrLabel} ${formatProbability(
                          row.fdr,
                        )}, −log10(${fdrLabel}) ${formatNumber(
                          significance,
                          3,
                        )}`}</title>
                      </circle>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
          <ol className="sr-only">
            {rows.map((row, index) => (
              <li key={row.pathway}>
                {row.pathway}: NES {formatNumber(row.nes, 3)}, {fdrLabel}{" "}
                {formatProbability(row.fdr)}, negative log10 {fdrLabel}{" "}
                {formatNumber(significances[index], 3)}
                {row.camera_direction
                  ? `, CAMERA direction ${row.camera_direction === "group_b" ? groupB : groupA}, ${row.direction_concordant ? "same as" : "different from"} NES direction`
                  : ""}.
              </li>
            ))}
          </ol>
        </>
      ) : (
        <p className="gsea-inline-empty">
          No finite NES and {fdrLabel} values are available for the DotPlot.
        </p>
      )}
      <p className="gsea-dotplot-scope">
        The plot is limited to the 30 strongest pathways ranked by {fdrLabel}. The table
        and pathway CSV retain all {pathways.length} tested pathways.
      </p>
    </figure>
  );
}

export const GseaLandscape = GseaDotPlot;

export function GseaResult({ result, onDownload, headingRef }) {
  const [tablePage, setTablePage] = useState(0);
  const summary = result.summary || {};
  const ranking = result.ranking || {};
  const inference = result.inference || {};
  const cameraContract =
    result.schema_version === "tcga-trace-camera-preranked-gsea-result-v2"
    || inference.primary_method === "limma_camera";
  const fdrLabel = cameraContract ? "CAMERA FDR" : "legacy permutation FDR";
  const grouping = result.grouping || {};
  const sampleSelection = grouping.sample_selection || {};
  const molecularPopulation = sampleSelection.sample_population || null;
  const pathways = result.pathways || [];
  const groupA = summary.group_a_label || "Group A";
  const groupB = summary.group_b_label || "Group B";
  const resultToken = String(result.gsea_id || "result").replace(
    /[^a-zA-Z0-9_-]/g,
    "-",
  );
  const tableHeadingId = `gsea-result-table-heading-${resultToken}`;
  const tableStatusId = `gsea-result-table-status-${resultToken}`;
  const tablePageCount = Math.max(
    1,
    Math.ceil(pathways.length / GSEA_TABLE_PAGE_SIZE),
  );
  const safeTablePage = Math.min(tablePage, tablePageCount - 1);
  const tableStart = safeTablePage * GSEA_TABLE_PAGE_SIZE;
  const visiblePathways = pathways.slice(
    tableStart,
    tableStart + GSEA_TABLE_PAGE_SIZE,
  );

  useEffect(() => {
    setTablePage(0);
  }, [resultToken]);

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.GSEA_RESULTS}
      label="GSEA result"
      className="gsea-result"
    >
      <header className="result-header gsea-result-header">
        <div>
          <span className="result-family-label">
            {cameraContract
              ? "CAMERA inference · preranked effect"
              : "Archived preranked GSEA · v1 method"}
          </span>
          <h2 ref={headingRef} tabIndex="-1">
            {groupB} vs {groupA}
          </h2>
          <p className="result-context">
            {result.cohort} · {result.gene_set_collection?.label} ·{" "}
            {ranking.genes_ranked?.toLocaleString()} ranked genes
          </p>
        </div>
        <details className="result-export-details"><summary>Downloads</summary>
        <div
          className="gsea-downloads"
          role="group"
          aria-label="GSEA downloads"
        >
          <DownloadAnchor
            href={result.downloads?.csv}
            iconRole="file.csv"
            onDownload={onDownload}
            ariaLabel="Download pathway results as CSV"
          >
            Pathways
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.ranking_csv}
            iconRole="file.csv"
            onDownload={onDownload}
            ariaLabel="Download ranked genes as CSV"
          >
            Ranking
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.dotplot_svg}
            iconRole="file.image"
            onDownload={onDownload}
            ariaLabel="Download GSEA DotPlot as SVG"
          >
            DotPlot
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.svg}
            iconRole="file.image"
            onDownload={onDownload}
            ariaLabel="Download bidirectional NES landscape as SVG"
          >
            Landscape
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.methodology}
            iconRole="file.text"
            onDownload={onDownload}
            ariaLabel="Download GSEA methodology"
          >
            Methods
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.attestation}
            iconRole="file.audit"
            onDownload={onDownload}
            ariaLabel="Download signed GSEA receipt"
          >
            Receipt
          </DownloadAnchor>
          <DownloadAnchor
            href={result.downloads?.zip}
            iconRole="file.archive"
            onDownload={onDownload}
            ariaLabel="Download complete GSEA bundle"
          >
            Bundle
          </DownloadAnchor>
        </div>
        </details>
      </header>
      {molecularPopulation && (
        <details className="result-source-details">
          <summary>RNA population: {molecularPopulation.label} · {Number(sampleSelection.retained_patients || 0).toLocaleString("en-US")} patients</summary>
          <div className="result-population-contract" role="note">
          <span>
            <strong>
              {Number(sampleSelection.retained_patients || 0).toLocaleString("en-US")} patients · {retainedSampleCount(sampleSelection).toLocaleString("en-US")} RNA samples
            </strong>
            <small>
              {formatSampleTypeCounts(sampleSelection.retained_sample_types)} · TCGA {molecularPopulation.allowed_tcga_sample_codes?.join("/")} · no cross-tissue fallback
            </small>
          </span>
          </div>
        </details>
      )}

      <div className="gsea-metric-strip">
        <div>
          <span>Patients</span>
          <strong>
            {Object.values(grouping.group_counts || {}).reduce(
              (sum, value) => sum + Number(value || 0),
              0,
            )}
          </strong>
          <small>{Object.entries(grouping.group_counts || {}).map(([label, count]) => `${label} ${count}`).join(" · ")}</small>
        </div>
        <div>
          <span>Pathways tested</span>
          <strong>{summary.pathways_tested}</strong>
          <small>{result.gene_set_collection?.version}</small>
        </div>
        <div>
          <span>At {fdrLabel} ≤ {formatNumber(summary.fdr_threshold, 2)}</span>
          <strong>{summary.pathways_at_fdr}</strong>
          <small>
            {summary.enriched_in_group_b} toward target · {summary.enriched_in_group_a} toward reference
            {cameraContract ? " · CAMERA direction" : " · NES direction"}
          </small>
        </div>

      </div>

      <div className="gsea-method-contract" role="note">
        <TraceIcon role="status.info" size="sm" tone="secondary" />
        {cameraContract ? (
          <p>
            CAMERA accounts for gene correlation when testing each pathway; FDR uses BH correction.
            NES and leading-edge genes describe the ranked effect. {inference.inferential_role === "conditional_exploratory"
              ? "These groups were derived from expression, so the pathway results describe that split rather than independently validate it."
              : "The group definition is independent of the tested transcriptome."}
          </p>
        ) : (
          <p>
            <strong>Archived v1 result.</strong>{" "}
            Its p values and FDR come from the original gene-set-permutation method,
            which did not adjust for inter-gene correlation. They are shown only to
            reproduce that historical run and are not CAMERA results.
          </p>
        )}
      </div>

      {!!result.warnings?.length && (
        <div className="gsea-notices" role="note">
          <TraceIcon role="status.caution" size="sm" tone="caution" />
          <ul>
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <ResultTabs label="Pathway result sections">
      <ResultSection id="overview" title="Pathway overview">
      <GseaDotPlot
        pathways={pathways}
        groupA={groupA}
        groupB={groupB}
        fdrLabel={fdrLabel}
      />

      </ResultSection>
      <ResultSection id="pathways" title="All pathways" helpId="gsea.results">
      <div className="gsea-table-heading" id={tableHeadingId}>
        <div>
          <p>
            Positive <Term id="nes">NES</Term> indicates concentration toward {groupB};
            negative NES indicates concentration toward {groupA}.
            {cameraContract && " CAMERA direction is reported separately for every pathway."}
          </p>
        </div>
        <span>
          {pathways.length} tested · {cameraContract ? "CAMERA + BH" : "archived v1 method"}
        </span>
      </div>
      <div
        className="table-scroll gsea-table-region"
        role="region"
        tabIndex="0"
        aria-labelledby={tableHeadingId}
        aria-describedby={tableStatusId}
      >
        <table className="gsea-result-table">
          <caption className="sr-only">
            Gene-set enrichment results for {groupB} versus {groupA}, page{" "}
            {safeTablePage + 1} of {tablePageCount}
          </caption>
          <thead>
            <tr>
              <th scope="col">Pathway</th>
              <th scope="col">NES direction</th>
              <th scope="col">Size</th>
              <th scope="col">ES</th>
              <th scope="col"><Term id="nes">NES</Term></th>
              <th scope="col">{cameraContract ? "CAMERA p" : "Legacy permutation p"}</th>
              <th scope="col">{cameraContract ? "CAMERA " : "Legacy permutation "}<Term id="fdr">FDR</Term></th>
              {cameraContract && <th scope="col">Residual ρ</th>}
              {cameraContract && <th scope="col">CAMERA direction</th>}
              {cameraContract && <th scope="col">Agreement</th>}
              <th scope="col"><Term id="leading_edge">Leading edge</Term></th>
            </tr>
          </thead>
          <tbody>
            {visiblePathways.map((row) => {
              const leadingEdge = row.leading_edge || [];
              return (
                <tr key={row.pathway}>
                  <th scope="row">
                    <strong>{row.pathway}</strong>
                    {row.description && <small>{row.description}</small>}
                  </th>
                  <td>
                    <span className={`gsea-direction ${row.nes >= 0 ? "positive" : "negative"}`}>
                      {row.nes >= 0 ? groupB : groupA}
                    </span>
                  </td>
                  <td>{row.size_used}</td>
                  <td>{formatNumber(row.es, 3)}</td>
                  <td><strong>{formatNumber(row.nes, 3)}</strong></td>
                  <td>{formatProbability(row.p_value)}</td>
                  <td>{formatProbability(row.fdr)}</td>
                  {cameraContract && <td>{formatNumber(row.camera_correlation, 3)}</td>}
                  {cameraContract && (
                    <td>
                      <span className={`gsea-direction ${row.camera_direction === "group_b" ? "positive" : "negative"}`}>
                        {row.camera_direction === "group_b" ? groupB : groupA}
                      </span>
                    </td>
                  )}
                  {cameraContract && (
                    <td>
                      <span className={`gsea-direction-check ${row.direction_concordant ? "concordant" : "discordant"}`}>
                        {row.direction_concordant
                          ? "Same direction"
                          : "Different directions"}
                      </span>
                    </td>
                  )}
                  <td>
                    <span className="gsea-leading-edge" aria-hidden="true">
                      {leadingEdge.slice(0, 5).join(", ")}
                      {leadingEdge.length > 5
                        ? ` +${leadingEdge.length - 5}`
                        : ""}
                    </span>
                    <span className="sr-only">
                      {leadingEdge.length
                        ? `Leading-edge genes: ${leadingEdge.join(", ")}`
                        : "No leading-edge genes reported."}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="gsea-table-pagination">
        <p id={tableStatusId} aria-live="polite">
          {pathways.length
            ? `Showing ${tableStart + 1}–${Math.min(
                tableStart + GSEA_TABLE_PAGE_SIZE,
                pathways.length,
              )} of ${pathways.length} pathways.`
            : "No pathways to display."}{" "}
          The pathway CSV contains the complete result.
        </p>
        {tablePageCount > 1 && (
          <div role="group" aria-label="Gene-set result pages">
            <button
              type="button"
              className="secondary-button compact"
              disabled={safeTablePage === 0}
              onClick={() =>
                setTablePage((current) => Math.max(0, current - 1))
              }
            >
              Previous
            </button>
            <span>
              Page {safeTablePage + 1} of {tablePageCount}
            </span>
            <button
              type="button"
              className="secondary-button compact"
              disabled={safeTablePage >= tablePageCount - 1}
              onClick={() =>
                setTablePage((current) =>
                  Math.min(tablePageCount - 1, current + 1),
                )
              }
            >
              Next
            </button>
          </div>
        )}
      </div>
      </ResultSection>
      </ResultTabs>
      <details className="result-more-details"><summary>Ranking and score settings</summary>
        <div>
          <span>NES permutations</span>
          <strong>{ranking.permutations?.toLocaleString()}</strong>
          <small>Seed {ranking.seed}</small>
        </div>      <SignatureScoringSummary
        signature={grouping.signature_resolved}
        title="Expression grouping score"
      />

      </details>
      <footer className="gsea-audit-line">
        <TraceIcon role="file.audit" size="sm" tone="secondary" />
        <span>
          Audit hash <code>{result.audit?.result_core_sha256?.slice(0, 20)}…</code>
        </span>
          <code>
            {result.pipeline_version ||
              "camera-estimated-correlation-bh-preranked-effect-contract-v2.1"}
          </code>
        <DownloadAnchor
          href={result.downloads?.audit_json}
          iconRole="file.audit"
          onDownload={onDownload}
          ariaLabel="Download GSEA audit report as JSON"
        >
          Audit
        </DownloadAnchor>
      </footer>
    </GuideAnchor>
  );
}

export default function GseaModule({
  state,
  setState,
  form,
  cohorts,
  repositoryDatasets,
  userDataset,
  filters,
  expressionScales,
  expressionScaleValue,
  onSelectCohort,
  onSelectRepositoryDataset,
  onSelectExpressionScale,
  onSamplePopulationChange,
  onClinicalFiltersChange,
  onClearEligibility,
  recentAnalyses,
  onDownload,
}) {
  const [catalog, setCatalog] = useState({
    loading: true,
    collections: [],
    error: "",
  });
  const validation = useMemo(
    () => validateGseaState(state, filters, form),
    [state, filters, form],
  );
  const clinicalVariables = useMemo(
    () => clinicalGroupingVariables(filters),
    [filters],
  );
  const eligibility = eligibilitySummary(form.filters, clinicalVariables);
  const selectedClinicalVariable = clinicalVariables.find(
    (item) => item.value === state.clinical_variable,
  );
  const runTokenRef = useRef(0);
  const designFingerprintRef = useRef("");
  const resultHeadingRef = useRef(null);
  const priorResultIdRef = useRef(state.result?.gsea_id || "");
  const designFingerprint = JSON.stringify({
    state: Object.fromEntries(
      Object.entries(state).filter(
        ([key]) => !["running", "result", "error"].includes(key),
      ),
    ),
    context: {
      cohort: form.cohort,
      dataset_id: form.dataset_id,
      dataset_release_id: form.dataset_release_id,
      expression_layer_id: form.expression_layer_id,
      expression_scale: form.expression_scale,
      filters: form.filters,
    },
  });
  const allCohortDatasets = useMemo(
    () =>
      repositoryDatasets.filter(
        (dataset) => dataset.tcga_cohort === form.cohort,
      ),
    [repositoryDatasets, form.cohort],
  );
  const cohortDatasets = useMemo(
    () => filterDatasetsForModule(allCohortDatasets, "gsea"),
    [allCohortDatasets],
  );
  const sourceDatasets = userDataset?.tcga_cohort === form.cohort
    && datasetSupportsModule(userDataset, "gsea")
    ? [...cohortDatasets, userDataset]
    : cohortDatasets;
  const selectedDataset = userDataset?.id === form.dataset_id
    ? userDataset
    : allCohortDatasets.find((dataset) => dataset.id === form.dataset_id);
  const selectedDatasetCapability = selectedDataset
    ? datasetCapability(selectedDataset, "gsea")
    : null;
  const datasetReady = !selectedDataset || selectedDatasetCapability.available;
  const survivalGroupingReady = !selectedDataset
    || datasetSupportsModule(selectedDataset, "analysis");
  const selectedCohort = cohorts.find((cohort) => cohort.id === form.cohort);
  const selectedExpressionLayer = form.dataset_id
    ? expressionScales.find((item) => item.value === expressionScaleValue)
    : null;
  const rankScoring = rankScoringAvailability(
    selectedDataset,
    selectedCohort,
    selectedExpressionLayer,
  );
  const rankScoringUnavailable = Boolean(
    state.grouping_source === "expression"
    && signatureMethodUsesDirection(state.signature_method)
    && !rankScoring.available,
  );
  const compatibleCohorts = useMemo(
    () => cohorts.filter((cohort) =>
      cohortSupportsModule(cohort, repositoryDatasets, "gsea")
      || cohort.id === form.cohort,
    ),
    [cohorts, form.cohort, repositoryDatasets],
  );
  const selectedCollection = catalog.collections.find(
    (item) => item.id === state.gene_set_collection,
  );
  const canRunAnalysis = Boolean(
    form.cohort &&
    datasetReady &&
    (state.grouping_source !== "survival" || survivalGroupingReady) &&
    !rankScoringUnavailable &&
    validation.valid &&
    (state.grouping_source !== "clinical" ||
      selectedClinicalVariable?.analysis_eligible) &&
    !catalog.loading &&
    !catalog.error &&
    catalog.collections.length,
  );
  const runAnnouncement = state.running
    ? "GSEA analysis running."
    : state.result
      ? `GSEA analysis completed. ${state.result.pathways?.length || 0} pathways are available.`
      : "";

  useEffect(() => {
    if (
      state.grouping_source !== "clinical" ||
      !Array.isArray(filters?.clinical_grouping_variables)
    ) {
      return;
    }
    const selected = filters.clinical_grouping_variables.find(
      (item) => (item.id || item.value) === state.clinical_variable,
    );
    if (!selected?.analysis_eligible) {
      if (
        state.clinical_variable ||
        state.group_a_values.length ||
        state.group_b_values.length
      ) {
        setState((current) => ({
          ...current,
          clinical_variable: "",
          group_a_values: [],
          group_b_values: [],
          result: null,
          error: "",
        }));
      }
      return;
    }
    if (selected.value_type !== "categorical") return;
    const known = new Set(
      (selected.levels || [])
        .filter((level) => level.analysis_eligible !== false)
        .map((level) => level.value),
    );
    const groupA = state.group_a_values.filter((value) => known.has(value));
    const groupB = state.group_b_values.filter((value) => known.has(value));
    if (
      groupA.length !== state.group_a_values.length ||
      groupB.length !== state.group_b_values.length
    ) {
      setState((current) => ({
        ...current,
        group_a_values: groupA,
        group_b_values: groupB,
        result: null,
        error: "",
      }));
    }
  }, [
    filters,
    setState,
    state.clinical_variable,
    state.group_a_values,
    state.group_b_values,
    state.grouping_source,
  ]);

  useEffect(() => {
    let cancelled = false;
    getGseaCollections()
      .then((payload) => {
        if (cancelled) return;
        const collections = (payload.collections || []).filter(
          (item) => item.available,
        );
        setCatalog({ loading: false, collections, error: "" });
        if (
          collections.length &&
          !collections.some(
            (item) => item.id === state.gene_set_collection,
          )
        ) {
          setState((current) => ({
            ...current,
            gene_set_collection:
              payload.default_collection || collections[0].id,
          }));
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setCatalog({
            loading: false,
            collections: [],
            error: error.message || "Gene-set catalog is unavailable.",
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!designFingerprintRef.current) {
      designFingerprintRef.current = designFingerprint;
      return;
    }
    if (designFingerprintRef.current === designFingerprint) return;
    designFingerprintRef.current = designFingerprint;
    runTokenRef.current += 1;
    setState((current) => {
      if (!current.running && !current.result) return current;
      return {
        ...current,
        running: false,
        result: null,
        error: current.running
          ? "The setup changed while the prior job was running. Its response will not replace this design."
          : "",
      };
    });
  }, [designFingerprint, setState]);

  useEffect(() => {
    const resultId = state.result?.gsea_id || "";
    if (!resultId || priorResultIdRef.current === resultId) {
      priorResultIdRef.current = resultId;
      return undefined;
    }
    priorResultIdRef.current = resultId;
    if (typeof window === "undefined") return undefined;
    const frame = window.requestAnimationFrame(() => {
      resultHeadingRef.current?.focus({ preventScroll: false });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [state.result?.gsea_id]);

  function update(patch) {
    setState((current) => ({
      ...current,
      ...patch,
      result: null,
      error: "",
    }));
  }

  function changeGroupingSource(source) {
    const labels =
      source === "expression"
        ? { group_a_label: "Low", group_b_label: "High" }
        : { group_a_label: "Reference", group_b_label: "Target" };
    update({ grouping_source: source, ...labels });
  }

  async function runAnalysis() {
    const checked = validateGseaState(state, filters, form);
    const catalogUnavailable =
      catalog.loading || catalog.error || !catalog.collections.length;
    const survivalGroupingUnavailable =
      state.grouping_source === "survival" && !survivalGroupingReady;
    if (
      !form.cohort
      || !datasetReady
      || survivalGroupingUnavailable
      || rankScoringUnavailable
      || !checked.valid
      || catalogUnavailable
    ) {
      const message = !form.cohort
        ? "Select a dataset before running GSEA."
        : !datasetReady
          ? selectedDatasetCapability.reason
        : survivalGroupingUnavailable
          ? "This release has no time-to-event result from which to inherit groups."
        : rankScoringUnavailable
          ? rankScoring.reason
        : checked.errors[0] ||
          (catalog.loading
            ? "Wait for the gene-set catalog to load."
            : catalog.error ||
              "No gene-set collection is currently available.");
      setState((current) => ({
        ...current,
        result: null,
        error: message,
      }));
      if (typeof window !== "undefined") {
        const targetId = firstInvalidControlId(
          state,
          form,
          checked,
          catalog,
        );
        window.requestAnimationFrame(() => {
          document.getElementById(
            !datasetReady
              ? "gsea-expression-dataset"
              : rankScoringUnavailable
                ? "gsea-expression-score"
                : targetId,
          )?.focus({ preventScroll: false });
        });
      }
      return;
    }
    const runToken = ++runTokenRef.current;
    const payload = buildGseaPayload(state, form);
    setState((current) => ({
      ...current,
      running: true,
      error: "",
    }));
    try {
      const result = await createGseaAnalysis(payload);
      if (runToken !== runTokenRef.current) return;
      setState((current) => ({
        ...current,
        running: false,
        result,
        error: "",
      }));
    } catch (error) {
      if (runToken !== runTokenRef.current) return;
      setState((current) => ({
        ...current,
        running: false,
        error: error.message || "GSEA failed. Your previous result is still available.",
      }));
    }
  }

  return (
    <div className="gsea-page">
      <div
        className="sr-only"
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        {runAnnouncement}
      </div>
      <ActiveJobRecovery
        sourceView="gsea"
        busy={state.running}
        onRecover={(result) => setState((current) => ({
          ...current,
          running: false,
          result,
          error: "",
        }))}
      />
      <div className="gsea-workflow-layout">
        <section
          className="control-panel gsea-control-panel"
          aria-label="GSEA setup"
          aria-busy={state.running}
        >
          <header className="gsea-section-header">
            <ModuleIcon role="module.geneSetEnrichment" />
            <div>
              <span className="result-family-label">Two-group analysis</span>
              <h2>Define the contrast</h2>
              <p>
                Choose two groups and a gene-set collection. CAMERA tests their differences;
                ranked enrichment shows which group each set favors.
              </p>
            </div>
          </header>

          <fieldset className="gsea-control-fieldset" disabled={state.running}>
          <legend className="sr-only">GSEA setup parameters</legend>
          <GuideAnchor
            as="div"
            anchor={GUIDE_ANCHORS.GSEA_DATASET}
            label="GSEA dataset"
            className="gsea-setup-section"
          >
            <div className="gsea-section-title">
              <span>01</span>
              <div>
                <div className="panel-title-row">
                  <h3>Dataset</h3>
                  <SectionHelp title="Dataset" helpId="gsea.dataset" />
                </div>
                <p>Both groups use the same bulk RNA-seq data, with one sample per patient.</p>
              </div>
            </div>
            <div className="gsea-dataset-grid">
              <FieldWithHelp label="Cancer cohort" htmlFor="gsea-cohort" helpId="dataset">
                <select
                  id="gsea-cohort"
                  value={form.cohort}
                  onChange={(event) => onSelectCohort(event.target.value)}
                  aria-invalid={!form.cohort}
                  aria-describedby={
                    !form.cohort ? GSEA_REQUIREMENTS_ID : undefined
                  }
                >
                  <option value="">Select cancer</option>
                  {compatibleCohorts.map((cohort) => (
                    <option key={cohort.id} value={cohort.id}>
                      {cohort.id} · {cohort.disease_type || cohort.primary_site}
                    </option>
                  ))}
                </select>
              </FieldWithHelp>
              <FieldWithHelp label="Expression dataset" htmlFor="gsea-expression-dataset" helpId="repository">
                <select
                  id="gsea-expression-dataset"
                  value={form.dataset_id || ""}
                  disabled={!form.cohort}
                  onChange={(event) => {
                    if (event.target.value) {
                      onSelectRepositoryDataset(event.target.value);
                    } else {
                      onSelectRepositoryDataset(null);
                    }
                  }}
                >
                  {selectedCohort?.status !== "external_only" ? (
                    <option value="">TCGA reference cohort</option>
                  ) : (
                    <option value="" disabled>Select a ready external cohort</option>
                  )}
                  {selectedDataset && !datasetReady && (
                    <option value={selectedDataset.id} disabled>
                      Selected · unavailable for GSEA · {selectedDataset.name}
                    </option>
                  )}
                  {sourceDatasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.kind === "user" ? "Private" : "External"} ·{" "}
                      {dataset.name}
                    </option>
                  ))}
                </select>
              </FieldWithHelp>
              <ExpressionDataSelector variant="select" id="gsea-expression-scale" options={expressionScales} value={expressionScaleValue} onChange={onSelectExpressionScale} />
            </div>
            {!datasetReady && (
              <div className="dataset-capability-notice" role="status">
                <TraceIcon role="status.info" size="sm" tone="secondary" />
                <div>
                  <strong>GSEA is not available for this release</strong>
                  <span>{selectedDatasetCapability.reason} Your setup remains visible; choosing another source will re-check source-dependent groups.</span>
                </div>
              </div>
            )}
            <MolecularPopulationSelector
              form={form}
              filters={filters}
              compact
              onChange={onSamplePopulationChange}
            />
            <ClinicalFilterControls
              variables={filters?.clinical_grouping_variables || []}
              value={form.filters.custom_filters || []}
              onChange={onClinicalFiltersChange}
              analysisContext="gsea"
              excludeVariableIds={
                state.grouping_source === "clinical"
                  ? [state.clinical_variable]
                  : []
              }
            />
            <div className="gsea-eligibility-frame">
              <div>
                <strong>Patient selection</strong>
                <span>
                  {eligibility.length
                    ? eligibility.join(" · ")
                    : "Patients with matching expression data"}
                </span>
              </div>
              {!!eligibility.length && (
                <button
                  type="button"
                  className="tertiary-button"
                  onClick={onClearEligibility}
                >
                  Clear shared filters
                </button>
              )}
            </div>
          </GuideAnchor>

          <GuideAnchor
            as="div"
            anchor={GUIDE_ANCHORS.GSEA_GROUPS}
            label="GSEA comparison groups"
            className="gsea-setup-section"
          >
            <div className="gsea-section-title">
              <span>02</span>
              <div>
                <div className="panel-title-row">
                  <h3>Groups</h3>
                  <SectionHelp title="Groups" helpId="gsea.groups" />
                </div>
                <p>Group A is the reference; positive enrichment favors group B.</p>
              </div>
            </div>
            <div className="segmented-control gsea-source-tabs" role="group" aria-label="Group source">
              {GSEA_GROUP_SOURCES.map((source) => (
                <button
                  key={source.value}
                  type="button"
                  aria-pressed={state.grouping_source === source.value}
                  className={state.grouping_source === source.value ? "selected" : ""}
                  disabled={source.value === "survival" && !survivalGroupingReady}
                  onClick={() => changeGroupingSource(source.value)}
                  title={source.value === "survival" && !survivalGroupingReady
                    ? "This release has no ready time-to-event endpoint."
                    : source.note}
                >
                  {source.label}
                </button>
              ))}
            </div>
            <p className="gsea-source-note">
              {state.grouping_source === "survival" && !survivalGroupingReady
                ? "Survival-derived groups are unavailable because this release has no ready time-to-event endpoint. Choose clinical or gene-expression groups."
                : GSEA_GROUP_SOURCES.find(
                  (source) => source.value === state.grouping_source,
                )?.note}
            </p>
            {state.grouping_source === "clinical" ? (
              <ClinicalGroupBuilder
                state={state}
                setState={setState}
                filters={filters}
                update={update}
                validation={validation}
              />
            ) : state.grouping_source === "survival" ? (
              <SurvivalGroupBuilder
                state={state}
                analyses={recentAnalyses}
                update={update}
                validation={validation}
              />
            ) : (
              <ExpressionGroupBuilder
                state={state}
                update={update}
                validation={validation}
                form={form}
                rankScoring={rankScoring}
              />
            )}
          </GuideAnchor>

          <GuideAnchor
            as="div"
            anchor={GUIDE_ANCHORS.GSEA_COLLECTION}
            label="GSEA gene-set collection and ranking"
            className="gsea-setup-section"
          >
            <div className="gsea-section-title">
              <span>03</span>
              <div>
                <div className="panel-title-row">
                  <h3>Gene sets and ranking</h3>
                  <SectionHelp title="Gene sets and ranking" helpId="gsea.collection" />
                </div>
                <p>BH correction covers all tested pathways in the selected collection.</p>
              </div>
            </div>
            {catalog.error && (
              <div
                id="gsea-catalog-error"
                className="inline-error"
                role="alert"
              >
                {catalog.error}
              </div>
            )}
            <div className="gsea-parameter-grid">
              <div className="gsea-collection-field">
                <FieldWithHelp label="Collection" htmlFor="gsea-collection" helpId="gsea.collection">
                  <select
                    id="gsea-collection"
                    value={state.gene_set_collection}
                    disabled={catalog.loading || !catalog.collections.length}
                    onChange={(event) =>
                      update({ gene_set_collection: event.target.value })
                    }
                    aria-invalid={
                      Boolean(catalog.error) ||
                      (!catalog.loading && !catalog.collections.length)
                    }
                    aria-describedby={
                      catalog.error
                        ? "gsea-catalog-error"
                        : !catalog.loading && !catalog.collections.length
                          ? GSEA_REQUIREMENTS_ID
                          : selectedCollection
                            ? "gsea-collection-provenance"
                            : undefined
                    }
                  >
                    {catalog.loading && <option>Loading collections…</option>}
                    {catalog.collections.map((collection) => (
                      <option key={collection.id} value={collection.id}>
                        {collection.label} · {collection.gene_set_count} sets
                      </option>
                    ))}
                  </select>
                </FieldWithHelp>
                {selectedCollection && (
                  <dl
                    id="gsea-collection-provenance"
                    className="gsea-collection-provenance"
                    aria-label="Selected collection provenance"
                  >
                    <div>
                      <dt>Version</dt>
                      <dd>{selectedCollection.version}</dd>
                    </div>
                    {(selectedCollection.source ||
                      selectedCollection.source_url ||
                      selectedCollection.release_doi) && (
                      <div>
                        <dt>Source</dt>
                        <dd>
                          {selectedCollection.source_url ? (
                            <a
                              href={selectedCollection.source_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {selectedCollection.source ||
                                selectedCollection.release_doi ||
                                "Source record"}
                            </a>
                          ) : (
                            selectedCollection.source ||
                            selectedCollection.release_doi
                          )}
                        </dd>
                      </div>
                    )}
                    {selectedCollection.release_doi && (
                      <div>
                        <dt>DOI</dt>
                        <dd>
                          <a
                            href={`https://doi.org/${selectedCollection.release_doi}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {selectedCollection.release_doi}
                          </a>
                        </dd>
                      </div>
                    )}
                    {selectedCollection.license && (
                      <div>
                        <dt>License</dt>
                        <dd>
                          {selectedCollection.license_url ? (
                            <a
                              href={selectedCollection.license_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {selectedCollection.license}
                            </a>
                          ) : (
                            selectedCollection.license
                          )}
                        </dd>
                      </div>
                    )}
                  </dl>
                )}
              </div>
              <label>
                <span>Ranking statistic</span>
                <select
                  value={state.ranking_metric}
                  onChange={(event) =>
                    update({ ranking_metric: event.target.value })
                  }
                >
                  <option value="welch_t">Welch t · B minus A</option>
                  <option value="signal_to_noise">Signal-to-noise · B minus A</option>
                </select>
              </label>
              <label>
                <span>Minimum set size</span>
                <input
                  id="gsea-min-set-size"
                  type="number"
                  min="5"
                  max="500"
                  value={state.min_gene_set_size}
                  onChange={(event) =>
                    update({ min_gene_set_size: event.target.value })
                  }
                  aria-invalid={validationHas(
                    validation,
                    "Minimum gene-set",
                  )}
                  aria-describedby={
                    validationHas(validation, "Minimum gene-set")
                      ? GSEA_REQUIREMENTS_ID
                      : undefined
                  }
                />
              </label>
              <label>
                <span>Maximum set size</span>
                <input
                  id="gsea-max-set-size"
                  type="number"
                  min="10"
                  max="5000"
                  value={state.max_gene_set_size}
                  onChange={(event) =>
                    update({ max_gene_set_size: event.target.value })
                  }
                  aria-invalid={validationHas(
                    validation,
                    "Maximum gene-set",
                  )}
                  aria-describedby={
                    validationHas(validation, "Maximum gene-set")
                      ? GSEA_REQUIREMENTS_ID
                      : undefined
                  }
                />
              </label>
              <label>
                <span>Permutations</span>
                <input
                  id="gsea-permutations"
                  type="number"
                  min="100"
                  max="5000"
                  step="100"
                  value={state.permutations}
                  onChange={(event) =>
                    update({ permutations: event.target.value })
                  }
                  aria-invalid={validationHas(validation, "Permutations")}
                  aria-describedby={
                    validationHas(validation, "Permutations")
                      ? GSEA_REQUIREMENTS_ID
                      : undefined
                  }
                />
              </label>
              <label>
                <span>Seed</span>
                <input
                  id="gsea-seed"
                  type="number"
                  min="0"
                  value={state.seed}
                  onChange={(event) => update({ seed: event.target.value })}
                  aria-invalid={validationHas(validation, "Seed")}
                  aria-describedby={
                    validationHas(validation, "Seed")
                      ? GSEA_REQUIREMENTS_ID
                      : undefined
                  }
                />
              </label>
            </div>
          </GuideAnchor>

          {state.error && (
            <div className="inline-error" role="alert">
              <TraceIcon role="status.error" size="sm" tone="error" />
              {state.error}
            </div>
          )}
          <div className="gsea-run-row">
            <p>
              CAMERA tests pathway differences with gene-correlation adjustment. NES describes the ranked effect.
            </p>
            <button
              type="button"
              className="primary-button"
              disabled={state.running}
              aria-disabled={state.running || !canRunAnalysis}
              aria-describedby={
                !canRunAnalysis && !state.running
                  ? GSEA_REQUIREMENTS_ID
                  : undefined
              }
              onClick={runAnalysis}
            >
              <TraceIcon
                role={state.running ? "status.loading" : "action.run"}
                size="sm"
                className={state.running ? "spin" : ""}
              />
              {state.running ? "Running GSEA…" : "Run GSEA"}
            </button>
          </div>
          </fieldset>
        </section>

        <GseaSetupPreview
          state={state}
          form={form}
          validation={validation}
          selectedCollection={selectedCollection}
          catalog={catalog}
          clinicalVariable={selectedClinicalVariable}
          rankScoring={rankScoring}
        />
      </div>

      {state.running && (
        <section className="gsea-running">
          <TraceIcon role="status.loading" size="lg" tone="accent" className="spin" />
          <div>
            <strong>Ranking genes and permuting gene sets</strong>
            <span>
              Large cohorts can take several minutes. The queued job remains
              reproducible by its request hash.
            </span>
            <ElapsedTime />
          </div>
        </section>
      )}
      {state.result && (
        <GseaResult
          result={state.result}
          onDownload={onDownload}
          headingRef={resultHeadingRef}
        />
      )}
    </div>
  );
}
