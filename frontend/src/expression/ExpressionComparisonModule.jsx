import ResultTabs, { ResultSection } from "../ResultTabs";
import React, {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import ExpressionDataSelector from "./ExpressionDataSelector";
import AuthorizedImage from "../AuthorizedImage";
import { resultSourceLabel } from "../resultSource";

import {
  apiUrl,
  createExpressionComparisonAnalysis,
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
  chooseSurvivalContrast,
  clinicalGroupingVariables,
  clinicalVariableDefinition,
  clinicalVariableLevelOptions,
  eligibleSurvivalAnalyses,
  toggleDisjointGroupValue,
} from "../gsea/gseaContract";
import {
  geneCompletionContext,
  replaceGeneCompletion,
  signatureGeneSymbols,
} from "../gsea/gseaUi";
import {
  EXPRESSION_COMPARISON_MAX_GENES,
  buildExpressionComparisonPayload,
  circularTargetGenes,
  expressionComparisonContextFingerprint,
  normalizeExpressionGenes,
  validateExpressionComparisonState,
} from "./expressionComparisonContract";

const REQUIREMENTS_ID = "expression-comparison-run-requirements";

function formatInteger(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toLocaleString() : "—";
}

function retainedSampleCount(sampleSelection = {}) {
  return Object.values(sampleSelection.retained_sample_types || {}).reduce(
    (sum, value) => sum + Number(value || 0),
    0,
  );
}

function formatSampleTypeCounts(counts = {}) {
  return Object.entries(counts)
    .map(([label, count]) => `${label} ${formatInteger(count)}`)
    .join(" · ") || "No retained sample types reported";
}

function formatNumber(value, digits = 3) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "—";
}

function formatProbability(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  if (numeric === 0) return "<1e−300";
  if (numeric < 0.001) return numeric.toExponential(2).replace("e-", "e−");
  return numeric.toFixed(3);
}

function warningText(warning) {
  if (typeof warning === "string") return warning;
  return warning?.message || warning?.detail || warning?.code || "Analysis caution";
}

function DownloadButton({ href, iconRole, label, onDownload }) {
  if (!href) return null;
  return (
    <button
      type="button"
      className="secondary-button compact"
      aria-label={`Download ${label}`}
      onClick={() => onDownload?.(href, label)}
    >
      <TraceIcon role={iconRole} size="sm" />
      {label}
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

function useDatasetGeneSuggestions({
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
    const normalizedQuery = String(query || "").trim();
    if (!cohort || !normalizedQuery) {
      setState({ genes: [], loading: false, error: "" });
      return undefined;
    }
    let cancelled = false;
    setState({ genes: [], loading: true, error: "" });
    const handle = window.setTimeout(() => {
      const lookup = datasetId
        ? searchRepositoryGenes(
            datasetId,
            normalizedQuery,
            datasetReleaseId,
            expressionLayerId,
          )
        : searchGenes(cohort, normalizedQuery);
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
  }, [cohort, query, datasetId, datasetReleaseId, expressionLayerId]);

  return state;
}

function TargetGeneSelector({
  genes,
  onChange,
  cohort,
  datasetId,
  datasetReleaseId,
  expressionLayerId,
  invalid,
}) {
  const inputRef = useRef(null);
  const listboxId = useId();
  const helpId = useId();
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const suggestionState = useDatasetGeneSuggestions({
    cohort,
    query,
    datasetId,
    datasetReleaseId,
    expressionLayerId,
  });
  const selected = normalizeExpressionGenes(genes);
  const selectedSet = new Set(selected);
  const suggestions = suggestionState.genes
    .map((gene) => String(gene).toUpperCase())
    .filter((gene) => !selectedSet.has(gene))
    .slice(0, 10);
  const atLimit = selected.length >= EXPRESSION_COMPARISON_MAX_GENES;
  const open = focused && Boolean(query.trim()) && !dismissed && !atLimit;
  const activeOptionId =
    open && suggestions[activeIndex]
      ? `${listboxId}-option-${activeIndex}`
      : undefined;

  useEffect(() => {
    setActiveIndex(0);
  }, [query, suggestionState.genes]);

  function addGene(value) {
    const gene = String(value || "").trim().toUpperCase();
    if (!gene || selectedSet.has(gene) || atLimit) return;
    onChange([...selected, gene]);
    setQuery("");
    setDismissed(false);
    window.requestAnimationFrame(() => inputRef.current?.focus());
  }

  function addDelimitedGenes(rawValue) {
    const merged = mergeClipboardGeneList(selected.join(", "), rawValue, {
      allowWeights: false,
      maximum: EXPRESSION_COMPARISON_MAX_GENES,
    });
    onChange(normalizeExpressionGenes(merged.split(",")));
    setQuery("");
  }

  function handleCopy(event) {
    const target = event.target;
    const hasTextSelection =
      target instanceof HTMLInputElement &&
      target.selectionStart !== target.selectionEnd;
    if (hasTextSelection || !selected.length) return;
    event.preventDefault();
    event.clipboardData?.setData("text/plain", selected.join("\n"));
  }

  function handleKeyDown(event) {
    if (event.key === "Backspace" && !query && selected.length) {
      onChange(selected.slice(0, -1));
      return;
    }
    if (event.key === "Escape") {
      event.preventDefault();
      setDismissed(true);
      return;
    }
    if (event.key === "ArrowDown" && open && suggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === "ArrowUp" && open && suggestions.length) {
      event.preventDefault();
      setActiveIndex(
        (current) => (current - 1 + suggestions.length) % suggestions.length,
      );
      return;
    }
    if (event.key === "Enter" || event.key === "," || event.key === ";") {
      event.preventDefault();
      addGene(suggestions[activeIndex] || query);
    }
  }

  return (
    <div className="expression-gene-selector" onCopy={handleCopy}>
      <div className="expression-gene-selector-head">
        <label htmlFor="expression-comparison-gene-input">Target genes</label>
        <span>{selected.length} / {EXPRESSION_COMPARISON_MAX_GENES}</span>
      </div>
      {!!selected.length && (
        <ul className="expression-gene-chips" aria-label="Selected target genes">
          {selected.map((gene) => (
            <li key={gene}>
              <span>{gene}</span>
              <button
                type="button"
                aria-label={`Remove ${gene}`}
                onClick={() => onChange(selected.filter((item) => item !== gene))}
              >
                <TraceIcon role="action.close" size="xsm" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="expression-gene-autocomplete-wrap">
        <input
          ref={inputRef}
          id="expression-comparison-gene-input"
          value={query}
          disabled={atLimit}
          onChange={(event) => {
            const value = event.target.value;
            if (/[,;\n]/.test(value)) {
              addDelimitedGenes(value);
            } else {
              setQuery(value);
              setDismissed(false);
            }
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData?.getData("text") || "";
            if (isGeneListClipboardValue(pasted)) {
              event.preventDefault();
              addDelimitedGenes(pasted);
            }
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            setFocused(true);
            setDismissed(false);
          }}
          onBlur={() => setFocused(false)}
          placeholder={atLimit ? "Gene limit reached" : "Type a gene symbol, for example CA9"}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-activedescendant={activeOptionId}
          aria-invalid={invalid}
          aria-describedby={`${helpId}${invalid ? ` ${REQUIREMENTS_ID}` : ""}`}
          autoComplete="off"
          spellCheck="false"
        />
        {open && (
          <div
            id={listboxId}
            className="gene-autocomplete expression-gene-autocomplete"
            role="listbox"
            aria-label={`Gene suggestions for ${query.trim().toUpperCase()}`}
            aria-busy={suggestionState.loading}
          >
            <div className="gene-autocomplete-title">
              Suggestions for <strong>{query.trim().toUpperCase()}</strong>
            </div>
            {suggestionState.loading ? (
              <div className="gene-autocomplete-empty" role="status">
                Searching dataset genes…
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
                  onClick={() => addGene(gene)}
                >
                  <strong>{gene}</strong>
                  <span>Add gene</span>
                </button>
              ))
            ) : (
              <div className="gene-autocomplete-empty">
                No matching symbols. Press Enter to submit the exact symbol.
              </div>
            )}
          </div>
        )}
      </div>
      <small id={helpId}>
        Select HGNC symbols or paste a list with Ctrl/Cmd+V. With the empty
        field focused, Ctrl/Cmd+C copies the selected genes.
      </small>
      <span className="sr-only" role="status" aria-live="polite">
        {open && !suggestionState.loading && !suggestionState.error
          ? `${suggestions.length} gene suggestion${suggestions.length === 1 ? "" : "s"} available.`
          : ""}
      </span>
    </div>
  );
}

function SignatureGeneAutocomplete({ state, update, invalid, form }) {
  const inputRef = useRef(null);
  const labelId = useId();
  const helpId = useId();
  const listboxId = useId();
  const [cursor, setCursor] = useState(state.signature_genes.length);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const context = useMemo(
    () => geneCompletionContext(state.signature_genes, cursor),
    [state.signature_genes, cursor],
  );
  const suggestionState = useDatasetGeneSuggestions({
    cohort: form.cohort,
    query: focused && !dismissed ? context.query : "",
    datasetId: form.dataset_id,
    datasetReleaseId: form.dataset_release_id,
    expressionLayerId: form.expression_layer_id,
  });
  const outsideToken =
    state.signature_genes.slice(0, context.start) +
    state.signature_genes.slice(context.end);
  const included = new Set(signatureGeneSymbols(outsideToken));
  const suggestions = suggestionState.genes
    .map((gene) => String(gene).toUpperCase())
    .filter((gene) => !included.has(gene))
    .slice(0, 10);
  const open = focused && !dismissed && Boolean(context.query);
  const activeOptionId =
    open && suggestions[activeIndex]
      ? `${listboxId}-option-${activeIndex}`
      : undefined;

  useEffect(() => setActiveIndex(0), [context.query, suggestionState.genes]);

  function selectGene(gene) {
    const completed = replaceGeneCompletion(
      state.signature_genes,
      cursor,
      gene,
    );
    update({ signature_genes: completed.value });
    setCursor(completed.cursor);
    setDismissed(true);
    window.requestAnimationFrame(() => {
      inputRef.current?.focus();
      inputRef.current?.setSelectionRange(completed.cursor, completed.cursor);
    });
  }

  function handleKeyDown(event) {
    if (!open) return;
    if (event.key === "ArrowDown" && suggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp" && suggestions.length) {
      event.preventDefault();
      setActiveIndex(
        (current) => (current - 1 + suggestions.length) % suggestions.length,
      );
    } else if (event.key === "Enter" && suggestions[activeIndex]) {
      event.preventDefault();
      selectGene(suggestions[activeIndex]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setDismissed(true);
    }
  }

  return (
    <div className="expression-signature-field">
      <span id={labelId}>Gene or signature genes</span>
      <div className="expression-gene-autocomplete-wrap">
        <textarea
          ref={inputRef}
          id="expression-comparison-signature-genes"
          rows="3"
          value={state.signature_genes}
          onChange={(event) => {
            update({ signature_genes: event.target.value });
            setCursor(event.target.selectionStart ?? event.target.value.length);
            setDismissed(false);
          }}
          onPaste={(event) => {
            const pasted = event.clipboardData?.getData("text") || "";
            if (!isGeneListClipboardValue(pasted)) return;
            event.preventDefault();
            const nextValue = mergeClipboardGeneList(
              state.signature_genes,
              pasted,
            );
            update({ signature_genes: nextValue });
            setCursor(nextValue.length);
            setDismissed(true);
          }}
          onCopy={(event) => {
            if (
              event.currentTarget.selectionStart !==
                event.currentTarget.selectionEnd ||
              !state.signature_genes.trim()
            ) return;
            event.preventDefault();
            event.clipboardData?.setData(
              "text/plain",
              state.signature_genes,
            );
          }}
          onClick={(event) =>
            setCursor(event.currentTarget.selectionStart ?? event.currentTarget.value.length)
          }
          onKeyUp={(event) =>
            setCursor(event.currentTarget.selectionStart ?? event.currentTarget.value.length)
          }
          onKeyDown={handleKeyDown}
          onFocus={() => {
            setFocused(true);
            setDismissed(false);
          }}
          onBlur={() => setFocused(false)}
          placeholder={state.signature_method === "single" ? "CA9" : "CA9, VEGFA, SLC2A1"}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={open ? listboxId : undefined}
          aria-activedescendant={activeOptionId}
          aria-labelledby={labelId}
          aria-invalid={invalid}
          aria-describedby={`${helpId}${invalid ? ` ${REQUIREMENTS_ID}` : ""}`}
          autoComplete="off"
          spellCheck="false"
        />
        {open && (
          <div
            id={listboxId}
            className="gene-autocomplete expression-gene-autocomplete"
            role="listbox"
            aria-label={`Gene suggestions for ${context.query}`}
            aria-busy={suggestionState.loading}
          >
            <div className="gene-autocomplete-title">
              Suggestions for <strong>{context.query}</strong>
            </div>
            {suggestionState.loading ? (
              <div className="gene-autocomplete-empty" role="status">Searching dataset genes…</div>
            ) : suggestionState.error ? (
              <div className="gene-autocomplete-empty" role="status">{suggestionState.error}</div>
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
            ) : (
              <div className="gene-autocomplete-empty">No matching gene symbols.</div>
            )}
          </div>
        )}
      </div>
      <small id={helpId}>
        {state.signature_method === "single"
          ? "Type and select exactly one gene symbol."
          : `Paste a list with Ctrl/Cmd+V or separate genes with commas. ${signatureMethodInputHint(state.signature_method)}`}
      </small>
    </div>
  );
}

function GroupLabelFields({ state, update, validation }) {
  const sameLabels = validation.errors.includes("Group labels must be different.");
  return (
    <div className="expression-label-grid">
      <label>
        <span>Group A · reference</span>
        <input
          id="expression-comparison-group-a-label"
          value={state.group_a_label}
          maxLength="64"
          onChange={(event) => update({ group_a_label: event.target.value })}
          aria-invalid={!state.group_a_label.trim() || sameLabels}
          aria-describedby={sameLabels ? REQUIREMENTS_ID : undefined}
        />
      </label>
      <label>
        <span>Group B · comparison</span>
        <input
          id="expression-comparison-group-b-label"
          value={state.group_b_label}
          maxLength="64"
          onChange={(event) => update({ group_b_label: event.target.value })}
          aria-invalid={!state.group_b_label.trim() || sameLabels}
          aria-describedby={sameLabels ? REQUIREMENTS_ID : undefined}
        />
      </label>
    </div>
  );
}

function ClinicalGroupBuilder({ state, setState, filters, update, validation }) {
  const variables = filters ? clinicalGroupingVariables(filters) : [];
  const definition = clinicalVariableDefinition(filters, state.clinical_variable);
  const levelOptions = clinicalVariableLevelOptions(filters, state.clinical_variable);
  const levels = levelOptions.map((item) => item.value);
  const numericVariable = definition?.value_type === "numeric";
  const levelsInvalid = validation.errors.some((error) =>
    error.startsWith("Select at least one clinical level"),
  );
  const numericInvalid = validation.errors.some((error) =>
    error.startsWith("Enter a numeric cutpoint"),
  );
  return (
    <div className="expression-group-builder">
      <label>
        <span>Clinical variable</span>
        <select
          id="expression-comparison-clinical-variable"
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
        <div className="expression-age-cutpoint">
          <label>
            <span>{definition.label} threshold</span>
            <select
              value={state.clinical_cutpoint_method}
              onChange={(event) => update({ clinical_cutpoint_method: event.target.value })}
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
                id="expression-comparison-age-cutpoint"
                type="number"
                min={definition.numeric_summary?.min ?? undefined}
                max={definition.numeric_summary?.max ?? undefined}
                step="any"
                value={state.clinical_cutpoint}
                onChange={(event) => update({ clinical_cutpoint: event.target.value })}
                aria-invalid={numericInvalid}
                aria-describedby={numericInvalid ? REQUIREMENTS_ID : undefined}
              />
            </label>
          )}
          <p className="field-note">
            Group A contains values at or below the threshold; group B contains values above it.
          </p>
        </div>
      ) : levels.length ? (
        <div
          id="expression-comparison-clinical-levels"
          className="expression-level-matrix"
          role="group"
          aria-label="Clinical levels assigned to groups A and B"
          aria-invalid={levelsInvalid}
          aria-describedby={levelsInvalid ? REQUIREMENTS_ID : undefined}
        >
          <div className="expression-level-head" aria-hidden="true">
            <span>Clinical level</span><span>A</span><span>B</span>
          </div>
          {levelOptions.map((level) => (
            <div
              className={`expression-level-row${level.analysis_eligible ? "" : " is-unavailable"}`}
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
        <p id="expression-comparison-clinical-levels" className="expression-inline-empty">
          This variable has no levels in the selected dataset.
        </p>
      )}
      <GroupLabelFields state={state} update={update} validation={validation} />
    </div>
  );
}

function SurvivalGroupBuilder({ state, analyses, update, validation }) {
  const eligible = useMemo(() => eligibleSurvivalAnalyses(analyses), [analyses]);
  const invalid = validation.errors.some((error) =>
    error.includes("completed survival") || error.includes("source survival"),
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
    <div className="expression-group-builder">
      {!!eligible.length && (
        <label>
          <span>Recent two-group result</span>
          <select
            value={eligible.some((item) => item.analysis.id === state.survival_analysis_id)
              ? state.survival_analysis_id
              : ""}
            onChange={(event) => chooseAnalysis(event.target.value)}
          >
            <option value="">Choose a completed result</option>
            {eligible.map(({ analysis, groups }) => (
              <option key={analysis.id} value={analysis.id}>
                {analysis.gene_symbol} · {analysis.cutpoint_method} · {groups.join(" / ")}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        <span>Source analysis ID</span>
        <input
          id="expression-comparison-survival-analysis"
          value={state.survival_analysis_id}
          onChange={(event) => chooseAnalysis(event.target.value.trim())}
          placeholder="Paste a completed survival analysis ID"
          aria-invalid={invalid}
          aria-describedby={invalid ? REQUIREMENTS_ID : undefined}
        />
      </label>
      {state.survival_group_a && state.survival_group_b && (
        <div className="expression-inherited-groups" aria-label="Inherited survival groups">
          <span>Reference <strong>{state.survival_group_a}</strong></span>
          <TraceIcon role="data.compare" size="sm" tone="secondary" />
          <span>Comparison <strong>{state.survival_group_b}</strong></span>
        </div>
      )}
      <p className="field-note">
        The server uses the exact patient assignments, not a reconstructed displayed threshold.
      </p>
      {!eligible.length && (
        <p className="expression-inline-empty">
          Run a binary survival analysis first, or paste an unexpired result ID.
        </p>
      )}
      <div className="expression-method-note caution" role="note">
        <TraceIcon role="status.caution" size="sm" tone="caution" />
        <span>Maxstat-derived groups are outcome-optimized and remain post-selection.</span>
      </div>
      <GroupLabelFields state={state} update={update} validation={validation} />
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
  const geneInvalid = validation.errors.some((error) =>
    error.includes("expression grouping") ||
    error.includes("Single-gene grouping") ||
    error.includes("Invalid weight") ||
    error.includes("requires at least") ||
    error.includes("does not use weights") ||
    error.includes("direction only") ||
    error.includes("weight 0"),
  );
  const percentileInvalid = validation.errors.some((error) =>
    error.includes("Expression percentile"),
  );
  const circular = circularTargetGenes(state);
  return (
    <div className="expression-group-builder">
      <SignatureGeneAutocomplete
        state={state}
        update={update}
        invalid={geneInvalid}
        form={form}
      />
      <div className="expression-method-grid">
        <FieldWithHelp
          label="Score"
          htmlFor="expression-comparison-score"
          helpId={`score.${state.signature_method}`}
        >
          <select
            id="expression-comparison-score"
            value={state.signature_method}
            onChange={(event) => update({ signature_method: event.target.value })}
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
            onChange={(event) => update({ cutpoint_method: event.target.value })}
          >
            {GSEA_EXPRESSION_CUTPOINTS.map((item) => (
              <option key={item.value} value={item.value}>{item.label}</option>
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
            id="expression-comparison-percentile"
            type="number"
            min="1"
            max="99"
            value={state.custom_percentile}
            onChange={(event) => update({ custom_percentile: event.target.value })}
            aria-invalid={percentileInvalid}
            aria-describedby={percentileInvalid ? REQUIREMENTS_ID : undefined}
          />
        </label>
      )}
      <div className="expression-method-note caution" role="note">
        <TraceIcon role="status.caution" size="sm" tone="caution" />
        <span>
          Grouping and comparison use the same matrix. This is exploratory, not independent validation.
          {circular.length
            ? ` Target overlap: ${circular.join(", ")}; inferential p and FDR values are omitted and should not be interpreted.`
            : ""}
        </span>
      </div>
      <GroupLabelFields state={state} update={update} validation={validation} />
    </div>
  );
}

function SetupPreview({
  state,
  form,
  validation,
  clinicalVariable,
  rankScoring,
}) {
  const source = GSEA_GROUP_SOURCES.find((item) => item.value === state.grouping_source);
  const rankScoringReady = state.grouping_source !== "expression"
    || !signatureMethodUsesDirection(state.signature_method)
    || rankScoring.available;
  const ready = validation.valid && rankScoringReady;
  return (
    <aside className="expression-setup-preview" aria-label="Expression comparison design summary">
      <span className="result-family-label">Design preview</span>
      <h2>{ready ? "Ready to compare" : "Complete the design"}</h2>
      <dl>
        <div><dt>Dataset</dt><dd>{form.dataset_id || form.cohort || "Pending"}</dd></div>
        <div><dt>Genes</dt><dd>{state.genes.length ? `${state.genes.length} selected` : "Pending"}</dd></div>
        <div><dt>Groups</dt><dd>{source?.label || "Pending"}</dd></div>
        {state.grouping_source === "clinical" && (
          <div>
            <dt>Clinical field</dt>
            <dd>{clinicalVariable?.label || "Pending"}</dd>
          </div>
        )}
        <div><dt>Contrast</dt><dd>{state.group_b_label || "B"} − {state.group_a_label || "A"}</dd></div>
        <div><dt>Tests</dt><dd>Welch + Mann–Whitney</dd></div>
        <div><dt>Correction</dt><dd>BH within each test · FDR 0.05</dd></div>
      </dl>
      <div
        id={REQUIREMENTS_ID}
        className={`expression-readiness ${ready ? "ready" : "pending"}`}
        role="status"
      >
        <TraceIcon
          role={ready ? "status.success" : "status.info"}
          size="sm"
          tone={ready ? "success" : "secondary"}
        />
        <div>
          <strong>{ready ? "Design is complete" : "Requirements"}</strong>
          {ready ? (
            <span>One dataset and two non-overlapping groups.</span>
          ) : (
            <ul>
              {validation.errors.map((error) => <li key={error}>{error}</li>)}
              {!rankScoringReady && <li>{rankScoring.reason}</li>}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}

function BackendSvgFigure({ src, title, description, className = "" }) {
  const titleId = useId();
  return (
    <figure className={`expression-svg-figure ${className}`.trim()} aria-labelledby={titleId}>
      <figcaption>
        <strong id={titleId}>{title}</strong>
        <span>{description}</span>
      </figcaption>
      {src ? (
        <div className="expression-svg-scroll" role="region" tabIndex="0" aria-label={`${title} plot`}>
          <AuthorizedImage src={src} alt={`${title}. ${description}`} />
        </div>
      ) : (
        <p className="expression-inline-empty">This plot was not generated for the available data.</p>
      )}
    </figure>
  );
}

export function ExpressionComparisonResult({ result, onDownload, headingRef }) {
  const summary = result.summary || {};
  const grouping = result.grouping || {};
  const sampleSelection = grouping.sample_selection || {};
  const molecularPopulation = sampleSelection.sample_population || null;
  const statistics = result.statistics || [];
  const groupA = grouping.group_a_label || statistics[0]?.group_a?.label || "Group A";
  const groupB = grouping.group_b_label || statistics[0]?.group_b?.label || "Group B";
  const groupCounts = summary.group_counts || grouping.group_counts || {};
  const resultToken = String(result.comparison_id || "result").replace(/[^a-zA-Z0-9_-]/g, "-");
  const tableHeadingId = `expression-result-table-heading-${resultToken}`;
  const warnings = (result.warnings || []).map(warningText);
  const auditHash =
    result.audit?.result_core_sha256 ||
    result.audit?.request_sha256 ||
    result.audit?.analysis_sha256 ||
    "";

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.EXPRESSION_RESULTS}
      label="Expression comparison result"
      className="expression-result"
    >
      <header className="result-header expression-result-header">
        <div>
          <span className="result-family-label">Two-group expression comparison</span>
          <h2 ref={headingRef} tabIndex="-1">{groupB} vs {groupA}</h2>
          <p className="result-context">
            {resultSourceLabel(result.data_provenance?.dataset, result.cohort)}
          </p>
        </div>
        <details className="result-export-details"><summary>Downloads</summary>
        <div className="expression-downloads" role="group" aria-label="Expression comparison downloads">
          <DownloadButton href={result.downloads?.statistics_csv} iconRole="file.csv" label="Statistics" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.values_csv} iconRole="file.csv" label="Values" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.groups_csv} iconRole="file.csv" label="Groups" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.violin_svg} iconRole="file.image" label="Violin SVG" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.boxplot_svg} iconRole="file.image" label="Boxplot SVG" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.heatmap_svg} iconRole="file.image" label="Heatmap SVG" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.methodology} iconRole="file.text" label="Methods" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.attestation} iconRole="file.audit" label="Receipt" onDownload={onDownload} />
          <DownloadButton href={result.downloads?.zip} iconRole="file.archive" label="Bundle" onDownload={onDownload} />
        </div>
        </details>
      </header>

      {molecularPopulation && (
        <details className="result-source-details">
          <summary>RNA population: {molecularPopulation.label} · {formatInteger(sampleSelection.retained_patients)} patients</summary>
          <div className="result-population-contract" role="note">
          <span>
            <strong>
              {formatInteger(sampleSelection.retained_patients)} patients · {formatInteger(retainedSampleCount(sampleSelection))} RNA samples
            </strong>
            <small>
              {formatSampleTypeCounts(sampleSelection.retained_sample_types)} · TCGA {molecularPopulation.allowed_tcga_sample_codes?.join("/")} · no cross-tissue fallback
            </small>
          </span>
          </div>
        </details>
      )}

      <div className="expression-metric-strip">
        <div>
          <span>Patients</span>
          <strong>{formatInteger(summary.patients)}</strong>
          <small>{Object.entries(groupCounts).map(([label, count]) => `${label} ${count}`).join(" · ") || "Per-gene n reported below"}</small>
        </div>
        <div>
          <span>Genes analyzed</span>
          <strong>{formatInteger(summary.genes_analyzed)}</strong>
          <small>{formatInteger(summary.genes_requested)} requested</small>
        </div>
        <div>
          <span>Welch FDR ≤ {formatProbability(summary.fdr_threshold)}</span>
          <strong>{formatInteger(summary.genes_at_fdr_welch)}</strong>
          <small>Correction across Welch tests</small>
        </div>
        <div>
          <span>Mann–Whitney FDR ≤ {formatProbability(summary.fdr_threshold)}</span>
          <strong>{formatInteger(summary.genes_at_fdr_mann_whitney)}</strong>
          <small>Correction across rank tests</small>
        </div>
      </div>

      {!!warnings.length && (
        <div className="expression-result-warnings" role="note" aria-label="Analysis warnings">
          <TraceIcon role="status.caution" size="sm" tone="caution" />
          <div>
            <strong>Interpretation notes</strong>
            <ul>{warnings.map((warning, index) => <li key={`${index}-${warning}`}>{warning}</li>)}</ul>
          </div>
        </div>
      )}

      <ResultTabs label="Expression result sections">
      <ResultSection id="statistics" title="Gene statistics" helpId="expression.results" descriptionHelpId="resultExpressionView">
      <div className="table-scroll" role="region" tabIndex="0" aria-label="Gene expression effects">
        <table className="expression-effect-summary">
          <caption className="sr-only">Expression effects for {groupB} compared with {groupA}</caption>
          <thead><tr>
            <th scope="col">Gene</th><th scope="col">n ({groupA})</th><th scope="col">n ({groupB})</th>
            <th scope="col">Mean difference [95% CI]</th><th scope="col">Hedges g</th>
            <th scope="col">Welch q</th><th scope="col">Mann–Whitney q</th>
          </tr></thead>
          <tbody>{statistics.map((row) => <tr key={row.gene_symbol}>
            <th scope="row">{row.gene_symbol}{row.inferential_status && !["standard", "inferential"].includes(row.inferential_status) && <small>{row.inferential_status.replaceAll("_", " ")}</small>}</th>
            <td>{formatInteger(row.group_a?.n)}</td><td>{formatInteger(row.group_b?.n)}</td>
            <td>{formatNumber(row.mean_difference_b_minus_a)} [{formatNumber(row.mean_difference_ci_low)}, {formatNumber(row.mean_difference_ci_high)}]</td>
            <td>{formatNumber(row.hedges_g)}</td><td>{formatProbability(row.welch_t?.fdr)}</td><td>{formatProbability(row.mann_whitney?.fdr)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <details className="result-more-details">
        <summary id={tableHeadingId}>Full gene-level statistics</summary>
      <div
        className="table-scroll expression-table-region"
        role="region"
        tabIndex="0"
        aria-labelledby={tableHeadingId}
      >
        <table className="expression-statistics-table">
          <caption className="sr-only">
            Gene expression statistics for {groupB} compared with {groupA}
          </caption>
          <thead>
            <tr>
              <th scope="col" rowSpan="2">Gene</th>
              <th scope="colgroup" colSpan="3">{groupA}</th>
              <th scope="colgroup" colSpan="3">{groupB}</th>
              <th scope="colgroup" colSpan="4">Difference and effect</th>
              <th scope="colgroup" colSpan="3">Welch t</th>
              <th scope="colgroup" colSpan="3">Mann–Whitney</th>
              <th scope="col" rowSpan="2">Status</th>
            </tr>
            <tr>
              <th scope="col">n</th><th scope="col">Mean ± SD</th><th scope="col">Median [IQR]</th>
              <th scope="col">n</th><th scope="col">Mean ± SD</th><th scope="col">Median [IQR]</th>
              <th scope="col">Mean Δ [95% CI]</th><th scope="col">Median Δ</th><th scope="col">Hedges g</th><th scope="col">Rank-biserial</th>
              <th scope="col">t</th><th scope="col">p</th><th scope="col">FDR</th>
              <th scope="col">U</th><th scope="col">p</th><th scope="col">FDR</th>
            </tr>
          </thead>
          <tbody>
            {statistics.map((row) => (
              <tr key={row.gene_symbol}>
                <th scope="row">
                  <strong>{row.gene_symbol}</strong>
                  {row.inferential_status &&
                    !["standard", "inferential"].includes(row.inferential_status) && (
                    <small>{row.inferential_status.replaceAll("_", " ")}</small>
                  )}
                </th>
                <td>{formatInteger(row.group_a?.n)}</td>
                <td>{formatNumber(row.group_a?.mean)} ± {formatNumber(row.group_a?.sd)}</td>
                <td>{formatNumber(row.group_a?.median)} [{formatNumber(row.group_a?.q1)}, {formatNumber(row.group_a?.q3)}]</td>
                <td>{formatInteger(row.group_b?.n)}</td>
                <td>{formatNumber(row.group_b?.mean)} ± {formatNumber(row.group_b?.sd)}</td>
                <td>{formatNumber(row.group_b?.median)} [{formatNumber(row.group_b?.q1)}, {formatNumber(row.group_b?.q3)}]</td>
                <td>
                  <strong>{formatNumber(row.mean_difference_b_minus_a)}</strong>{" "}
                  [{formatNumber(row.mean_difference_ci_low)}, {formatNumber(row.mean_difference_ci_high)}]
                </td>
                <td>{formatNumber(row.median_difference_b_minus_a)}</td>
                <td>{formatNumber(row.hedges_g)}</td>
                <td>{formatNumber(row.rank_biserial)}</td>
                <td>{formatNumber(row.welch_t?.statistic)}</td>
                <td>{formatProbability(row.welch_t?.p_value)}</td>
                <td><strong>{formatProbability(row.welch_t?.fdr)}</strong></td>
                <td>{formatNumber(row.mann_whitney?.u_statistic, 1)}</td>
                <td>{formatProbability(row.mann_whitney?.p_value)}</td>
                <td><strong>{formatProbability(row.mann_whitney?.fdr)}</strong></td>
                <td>
                  <span className={`expression-status ${row.status === "analyzed" ? "complete" : "limited"}`}>
                    {row.status?.replaceAll("_", " ") || "reported"}
                  </span>
                  {row.significant_at_fdr && <small>FDR threshold met</small>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!statistics.length && (
        <p className="expression-inline-empty">No evaluable gene-level rows were returned.</p>
      )}

      </details>
      </ResultSection>
      <ResultSection id="distributions" title="Expression distributions">
      <section className="expression-distribution-region" aria-label="Expression distributions">
        <div className="expression-distribution-grid">
          <BackendSvgFigure
            src={result.downloads?.violin_svg}
            title="Violin plots"
            description="Kernel-density distributions with medians and interquartile ranges."
          />
          <BackendSvgFigure
            src={result.downloads?.boxplot_svg}
            title="Boxplots"
            description="Median, interquartile range and 1.5 × IQR whiskers by group."
          />
        </div>
      </section>

      </ResultSection>
      <ResultSection id="heatmap" title="Patient heatmap">
      <BackendSvgFigure
        src={result.downloads?.heatmap_svg}
        title="Expression heatmap"
        description={`Within-gene standardized expression for up to ${formatInteger(summary.heatmap_samples)} deterministically selected patients; raw values are not replaced.`}
        className="expression-heatmap-figure"
      />

      </ResultSection>
      </ResultTabs>
      <SignatureScoringSummary
        signature={grouping.signature_resolved}
        title="Expression grouping score"
      />

      <footer className="expression-audit-line">
        <TraceIcon role="file.audit" size="sm" tone="secondary" />
        <span>
          Comparison <code>{result.comparison_id}</code>
          {auditHash ? <> · audit <code>{auditHash.slice(0, 20)}…</code></> : null}
        </span>
        <code>{result.pipeline_version || "grouped-expression-comparison-welch-wilcoxon-bh-contract-v1.4"}</code>
        <DownloadButton href={result.downloads?.audit_json} iconRole="file.audit" label="Audit" onDownload={onDownload} />
      </footer>
    </GuideAnchor>
  );
}

function firstInvalidControl(validation) {
  const first = validation.errors[0] || "";
  if (first.startsWith("Select a dataset")) return "expression-comparison-cohort";
  if (first.includes("target gene")) return "expression-comparison-gene-input";
  if (first.startsWith("Name both") || first.startsWith("Group labels")) {
    return "expression-comparison-group-a-label";
  }
  if (first.startsWith("Enter a numeric")) return "expression-comparison-age-cutpoint";
  if (first.startsWith("Select at least one clinical")) return "expression-comparison-clinical-levels";
  if (first.includes("survival analysis")) return "expression-comparison-survival-analysis";
  if (
    first.includes("expression grouping") ||
    first.includes("Single-gene") ||
    first.includes("requires at least") ||
    first.includes("does not use weights") ||
    first.includes("direction only") ||
    first.includes("weight 0")
  ) {
    return "expression-comparison-signature-genes";
  }
  if (first.includes("percentile")) return "expression-comparison-percentile";
  return REQUIREMENTS_ID;
}

export default function ExpressionComparisonModule({
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
  const validation = useMemo(
    () => validateExpressionComparisonState(state, form, filters),
    [state, form, filters],
  );
  const runTokenRef = useRef(0);
  const priorContextRef = useRef(expressionComparisonContextFingerprint(form));
  const resultHeadingRef = useRef(null);
  const priorResultIdRef = useRef(state.result?.comparison_id || "");
  const contextFingerprint = expressionComparisonContextFingerprint(form);
  const clinicalVariables = useMemo(
    () => clinicalGroupingVariables(filters),
    [filters],
  );
  const eligibility = eligibilitySummary(form.filters, clinicalVariables);
  const selectedClinicalVariable = clinicalVariables.find(
    (item) => item.value === state.clinical_variable,
  );
  const allCohortDatasets = useMemo(
    () => repositoryDatasets.filter((dataset) => dataset.tcga_cohort === form.cohort),
    [repositoryDatasets, form.cohort],
  );
  const cohortDatasets = useMemo(
    () => filterDatasetsForModule(allCohortDatasets, "expression"),
    [allCohortDatasets],
  );
  const sourceDatasets = userDataset?.tcga_cohort === form.cohort
    && datasetSupportsModule(userDataset, "expression")
    ? [...cohortDatasets, userDataset]
    : cohortDatasets;
  const selectedDataset = userDataset?.id === form.dataset_id
    ? userDataset
    : allCohortDatasets.find((dataset) => dataset.id === form.dataset_id);
  const selectedDatasetCapability = selectedDataset
    ? datasetCapability(selectedDataset, "expression")
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
      cohortSupportsModule(cohort, repositoryDatasets, "expression")
      || cohort.id === form.cohort,
    ),
    [cohorts, form.cohort, repositoryDatasets],
  );
  const circular = circularTargetGenes(state);

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
          running: false,
          result: null,
          result_context_fingerprint: "",
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
        running: false,
        result: null,
        result_context_fingerprint: "",
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
    if (priorContextRef.current === contextFingerprint) return;
    priorContextRef.current = contextFingerprint;
    runTokenRef.current += 1;
    setState((current) => ({
      ...current,
      running: false,
      result: null,
      result_context_fingerprint: "",
      error: current.running
        ? "The dataset context changed while the prior comparison was running."
        : "",
    }));
  }, [contextFingerprint, setState]);

  useEffect(() => {
    if (
      state.result &&
      state.result_context_fingerprint &&
      state.result_context_fingerprint !== contextFingerprint
    ) {
      setState((current) => ({
        ...current,
        result: null,
        result_context_fingerprint: "",
      }));
    }
  }, [contextFingerprint, setState, state.result, state.result_context_fingerprint]);

  useEffect(() => {
    const resultId = state.result?.comparison_id || "";
    if (!resultId || priorResultIdRef.current === resultId) {
      priorResultIdRef.current = resultId;
      return undefined;
    }
    priorResultIdRef.current = resultId;
    const frame = window.requestAnimationFrame(() =>
      resultHeadingRef.current?.focus({ preventScroll: false }),
    );
    return () => window.cancelAnimationFrame(frame);
  }, [state.result?.comparison_id]);

  function update(patch) {
    runTokenRef.current += 1;
    setState((current) => ({
      ...current,
      ...patch,
      running: false,
      result: null,
      result_context_fingerprint: "",
      error: "",
    }));
  }

  function changeGroupingSource(source) {
    update({
      grouping_source: source,
      group_a_label: source === "expression" ? "Low" : "Reference",
      group_b_label: source === "expression" ? "High" : "Target",
    });
  }

  async function runAnalysis() {
    const clinicalUnavailable =
      state.grouping_source === "clinical" &&
      !selectedClinicalVariable?.analysis_eligible;
    const survivalGroupingUnavailable =
      state.grouping_source === "survival" && !survivalGroupingReady;
    if (
      !datasetReady
      || !validation.valid
      || clinicalUnavailable
      || survivalGroupingUnavailable
      || rankScoringUnavailable
    ) {
      setState((current) => ({
        ...current,
        result: null,
        error:
          (!datasetReady
            ? selectedDatasetCapability.reason
            : survivalGroupingUnavailable
              ? "This release has no time-to-event result from which to inherit groups."
            : rankScoringUnavailable
              ? rankScoring.reason
            : validation.errors[0]) ||
          "Choose an available clinical variable before running.",
      }));
      window.requestAnimationFrame(() =>
        document.getElementById(
          !datasetReady
            ? "expression-comparison-dataset"
            : rankScoringUnavailable
              ? "expression-comparison-score"
            : firstInvalidControl(validation),
        )?.focus({ preventScroll: false }),
      );
      return;
    }
    const token = ++runTokenRef.current;
    const epoch = state.context_epoch;
    const payload = buildExpressionComparisonPayload(state, form);
    setState((current) => ({ ...current, running: true, error: "" }));
    try {
      const result = await createExpressionComparisonAnalysis(payload);
      if (token !== runTokenRef.current) return;
      setState((current) => {
        if (current.context_epoch !== epoch) return current;
        return {
          ...current,
          running: false,
          result,
          result_context_fingerprint: contextFingerprint,
          error: "",
        };
      });
    } catch (error) {
      if (token !== runTokenRef.current) return;
      setState((current) => {
        if (current.context_epoch !== epoch) return current;
        return {
          ...current,
          running: false,
          error: error.message || "Expression comparison failed. Your previous result is still available.",
        };
      });
    }
  }

  const runAnnouncement = state.running
    ? "Expression comparison running."
    : state.result
      ? `Expression comparison completed. ${state.result.statistics?.length || 0} gene rows are available.`
      : "";

  return (
    <div className="expression-comparison-page">
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {runAnnouncement}
      </div>
      <ActiveJobRecovery
        sourceView="expression"
        busy={state.running}
        onRecover={(result) => setState((current) => ({
          ...current,
          running: false,
          result,
          result_context_fingerprint: contextFingerprint,
          error: "",
        }))}
      />
      <div className="expression-workflow-layout">
        <section className="control-panel expression-control-panel" aria-label="Expression comparison setup" aria-busy={state.running}>
          <header className="expression-section-header">
            <ModuleIcon role="module.expressionComparison" />
            <div>
              <span className="result-family-label">Patient-level comparison</span>
              <h2>Compare expression between two groups</h2>
              <p>Choose a cohort, the genes to test and two groups to compare.</p>
            </div>
          </header>
          <fieldset className="expression-control-fieldset" disabled={state.running}>
            <legend className="sr-only">Expression comparison setup parameters</legend>
            <GuideAnchor
              as="div"
              anchor={GUIDE_ANCHORS.EXPRESSION_DATASET}
              label="Expression comparison dataset"
              className="expression-setup-section"
            >
              <div className="expression-section-title">
                <span>01</span>
                <div>
                  <div className="panel-title-row">
                    <h3>Dataset</h3>
                    <SectionHelp title="Dataset" helpId="expression.dataset" />
                  </div>
                  <p>Both groups use the same expression data, with one sample per patient.</p>
                </div>
              </div>
              <div className="expression-dataset-grid">
                <FieldWithHelp label="Cancer cohort" htmlFor="expression-comparison-cohort" helpId="dataset">
                  <select
                    id="expression-comparison-cohort"
                    value={form.cohort}
                    onChange={(event) => onSelectCohort(event.target.value)}
                    aria-invalid={!form.cohort}
                    aria-describedby={!form.cohort ? REQUIREMENTS_ID : undefined}
                  >
                    <option value="">Select cancer</option>
                    {compatibleCohorts.map((cohort) => (
                      <option key={cohort.id} value={cohort.id}>
                        {cohort.id} · {cohort.disease_type || cohort.primary_site}
                      </option>
                    ))}
                  </select>
                </FieldWithHelp>
                <FieldWithHelp label="Expression dataset" htmlFor="expression-comparison-dataset" helpId="repository">
                  <select
                    id="expression-comparison-dataset"
                    value={form.dataset_id || ""}
                    disabled={!form.cohort}
                    onChange={(event) =>
                      event.target.value
                        ? onSelectRepositoryDataset(event.target.value)
                        : onSelectRepositoryDataset(null)
                    }
                  >
                    {selectedCohort?.status !== "external_only" ? (
                      <option value="">TCGA reference cohort</option>
                    ) : (
                      <option value="" disabled>Select a ready external cohort</option>
                    )}
                    {selectedDataset && !datasetReady && (
                      <option value={selectedDataset.id} disabled>
                        Selected · unavailable for Expression · {selectedDataset.name}
                      </option>
                    )}
                    {sourceDatasets.map((dataset) => (
                      <option key={dataset.id} value={dataset.id}>
                        {dataset.kind === "user" ? "Private" : "External"} · {dataset.name}
                      </option>
                    ))}
                  </select>
                </FieldWithHelp>
                <ExpressionDataSelector variant="select" id="expression-comparison-scale" options={expressionScales} value={expressionScaleValue} onChange={onSelectExpressionScale} />
              </div>
              {!datasetReady && (
                <div className="dataset-capability-notice" role="status">
                  <TraceIcon role="status.info" size="sm" tone="secondary" />
                  <div>
                    <strong>Expression comparison is not available for this release</strong>
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
                analysisContext="expression"
                excludeVariableIds={
                  state.grouping_source === "clinical"
                    ? [state.clinical_variable]
                    : []
                }
              />
              <div className="expression-eligibility-frame">
                <div>
                  <strong>Patient selection</strong>
                  <span>{eligibility.length ? eligibility.join(" · ") : "Patients with matching expression data"}</span>
                </div>
                {!!eligibility.length && (
                  <button type="button" className="tertiary-button" onClick={onClearEligibility}>Clear shared filters</button>
                )}
              </div>
            </GuideAnchor>

            <GuideAnchor
              as="div"
              anchor={GUIDE_ANCHORS.EXPRESSION_GENES}
              label="Expression target genes"
              className="expression-setup-section"
            >
              <div className="expression-section-title">
                <span>02</span>
                <div>
                  <div className="panel-title-row">
                    <h3>Genes</h3>
                    <SectionHelp title="Genes" helpId="expression.genes" />
                  </div>
                  <p>Choose the genes to compare. A gene used to define the groups is shown descriptively, without a p-value.</p>
                </div>
              </div>
              <TargetGeneSelector
                genes={state.genes}
                onChange={(genes) => update({ genes })}
                cohort={form.cohort}
                datasetId={form.dataset_id}
                datasetReleaseId={form.dataset_release_id}
                expressionLayerId={form.expression_layer_id}
                invalid={validation.errors.some((error) => error.includes("target gene"))}
              />
            </GuideAnchor>

            <GuideAnchor
              as="div"
              anchor={GUIDE_ANCHORS.EXPRESSION_GROUPS}
              label="Expression comparison groups"
              className="expression-setup-section"
            >
              <div className="expression-section-title">
                <span>03</span>
                <div>
                  <div className="panel-title-row">
                    <h3>Groups</h3>
                    <SectionHelp title="Groups" helpId="expression.groups" />
                  </div>
                  <p>
                    Group A is the <Term id="reference_group">reference</Term>; all reported
                    differences are <Term id="contrast_b_minus_a">B minus A</Term>.
                  </p>
                </div>
              </div>
              <div className="segmented-control expression-source-tabs" role="group" aria-label="Group source">
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
              <p className="expression-source-note">
                {state.grouping_source === "survival" && !survivalGroupingReady
                  ? "Survival-derived groups are unavailable because this release has no ready time-to-event endpoint. Choose clinical or gene-expression groups."
                  : GSEA_GROUP_SOURCES.find((source) => source.value === state.grouping_source)?.note}
              </p>
              {state.grouping_source === "clinical" ? (
                <ClinicalGroupBuilder state={state} setState={setState} filters={filters} update={update} validation={validation} />
              ) : state.grouping_source === "survival" ? (
                <SurvivalGroupBuilder state={state} analyses={recentAnalyses} update={update} validation={validation} />
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
              anchor={GUIDE_ANCHORS.EXPRESSION_TEST_FAMILY}
              label="Expression comparison test family"
              className="expression-setup-section expression-review-section"
            >
              <div className="expression-section-title">
                <span>04</span>
                <div>
                  <div className="panel-title-row">
                    <h3>Test family</h3>
                    <SectionHelp title="Test family" helpId="expression.testFamily" />
                  </div>
                  <p>
                    Two-sided <Term id="welch_test">Welch</Term> and{" "}
                    <Term id="mann_whitney">Mann–Whitney</Term> tests;{" "}
                    <Term id="fdr">BH correction</Term> is separate by method.
                  </p>
                </div>
              </div>
              <dl className="expression-test-specification">
                <div><dt>Primary direction</dt><dd>{state.group_b_label || "B"} minus {state.group_a_label || "A"}</dd></div>
                <div><dt><Term id="multiplicity_family">Multiplicity</Term></dt><dd>BH per test · FDR ≤ 0.05</dd></div>
                <div><dt>Heatmap</dt><dd>Up to 300 samples · within-gene z-score for color only</dd></div>
                <div><dt>Scope</dt><dd>Binary groups · exploratory research use</dd></div>
              </dl>
              {!!circular.length && (
                <div className="expression-method-note caution" role="alert">
                  <TraceIcon role="status.caution" size="sm" tone="caution" />
                  <span>
                    {circular.join(", ")} also defines the expression groups
                    (<Term id="circularity">circularity</Term>). Inferential p and FDR values
                    are omitted and should not be interpreted.
                  </span>
                </div>
              )}
            </GuideAnchor>

            {state.error && (
              <div className="inline-error" role="alert">
                <TraceIcon role="status.error" size="sm" tone="error" />
                {state.error}
              </div>
            )}
            <div className="expression-run-row">
              <p>Results include effect estimates, plots and downloads of patient values and group assignments.</p>
              <button
                type="button"
                className="primary-button"
                disabled={state.running}
                aria-disabled={
                  state.running
                  || !validation.valid
                  || !datasetReady
                  || rankScoringUnavailable
                  || (!survivalGroupingReady && state.grouping_source === "survival")
                }
                aria-describedby={
                  (!validation.valid
                    || !datasetReady
                    || rankScoringUnavailable
                    || (!survivalGroupingReady && state.grouping_source === "survival"))
                    && !state.running
                    ? REQUIREMENTS_ID
                    : undefined
                }
                onClick={runAnalysis}
              >
                <TraceIcon
                  role={state.running ? "status.loading" : "action.run"}
                  size="sm"
                  className={state.running ? "spin" : ""}
                />
                {state.running ? "Comparing expression…" : "Run expression comparison"}
              </button>
            </div>
          </fieldset>
        </section>
        <SetupPreview
          state={state}
          form={form}
          validation={validation}
          clinicalVariable={selectedClinicalVariable}
          rankScoring={rankScoring}
        />
      </div>

      {state.running && (
        <section className="expression-running" role="status">
          <TraceIcon role="status.loading" size="lg" tone="accent" className="spin" />
          <div>
            <strong>Testing gene-level differences</strong>
            <span>Download the SVG figures and the recorded request hash with your results.</span>
            <ElapsedTime />
          </div>
        </section>
      )}
      {state.result && (
        <ExpressionComparisonResult result={state.result} onDownload={onDownload} headingRef={resultHeadingRef} />
      )}
    </div>
  );
}
