import React, { useEffect, useId, useRef, useState } from "react";

import { apiUrl } from "../api";
import { scientificNumber } from "../scientificNumbers";
import { hierarchicalThresholdState } from "../analysisRequestContract";
import { GUIDE_ANCHORS, GuideAnchor } from "../tutorials";
import { FieldHelp, SectionHelp, Term } from "../help";
import {
  SESSION_JOB_EVENT,
  latestSessionJobEntry,
  loadSessionHistory,
} from "../sessionHistory";

import {
  HIERARCHICAL_CONTEXT_OPTIONS,
  HIERARCHICAL_REQUEST_DEFAULTS,
  HIERARCHICAL_RESULT_VIEWS,
  HIERARCHICAL_SCOPE_OPTIONS,
  PAN_CANCER_ANALYSIS_MODES,
  forestDomain,
  forestEstimate,
  forestRowKind,
  forestTicks,
  forestX,
  heterogeneityBand,
  hierarchicalViewPayload,
  leaveOneOutIsInfluential,
  normalizeAnalysisMode,
  normalizeHierarchicalRequestState,
  normalizeResultView,
  preflightCancerGroups,
  studyIsIncluded,
  studyReasons,
  summarizePreflight,
} from "./HierarchicalPanCancerContract";
import "./HierarchicalPanCancer.css";

const HIERARCHICAL_INPUT_FINGERPRINT_VERSION =
  "hierarchical-pancancer-input-v1";

function canonicalSelection(values, { uppercase = false } = {}) {
  const normalized = (Array.isArray(values) ? values : [])
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .map((value) => (uppercase ? value.toUpperCase() : value));
  return [...new Set(normalized)].sort((left, right) =>
    left.localeCompare(right),
  );
}

function canonicalNumber(value) {
  if (value === "" || value == null) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function canonicalHierarchicalRequest(state = {}) {
  const request = normalizeHierarchicalRequestState(state);
  return {
    gene_symbol: String(request.gene_symbol || "").trim().toUpperCase(),
    scope: String(request.scope || "combined"),
    cancers: canonicalSelection(request.cancers, { uppercase: true }),
    study_ids: canonicalSelection(request.study_ids),
    endpoint: String(request.endpoint || "OS").toUpperCase(),
    clinical_context: String(
      request.clinical_context || "primary_baseline",
    ),
    time_origin_policy: String(
      request.time_origin_policy || "strict_baseline",
    ),
    effect_scale: String(request.effect_scale || "within_study_iqr"),
    overlap_policy: String(
      request.overlap_policy || "independent_clusters",
    ),
    min_patients: canonicalNumber(request.min_patients),
    min_events: canonicalNumber(request.min_events),
    min_censored: canonicalNumber(request.min_censored),
    include_exploratory: Boolean(request.include_exploratory),
    fdr_threshold: canonicalNumber(request.fdr_threshold),
  };
}

export function hierarchicalRequestFingerprint(state = {}) {
  return `${HIERARCHICAL_INPUT_FINGERPRINT_VERSION}:${JSON.stringify(
    canonicalHierarchicalRequest(state),
  )}`;
}

export function hierarchicalPreflightFingerprint(preflight) {
  if (!preflight?.request || typeof preflight.request !== "object") {
    return null;
  }
  return hierarchicalRequestFingerprint(preflight.request);
}

export function hierarchicalResultFingerprint(result) {
  const request = result?.request_snapshot || result?.preflight?.request;
  if (!request || typeof request !== "object") return null;
  return hierarchicalRequestFingerprint(request);
}

export function hierarchicalPreflightIsCurrent(preflight, requestState) {
  const preflightFingerprint = hierarchicalPreflightFingerprint(preflight);
  return Boolean(
    preflightFingerprint &&
    preflightFingerprint === hierarchicalRequestFingerprint(requestState),
  );
}

export async function fetchRecordedHierarchicalJob(
  jobId,
  fetchImpl = globalThis.fetch,
) {
  const normalizedJobId = String(jobId || "").trim();
  if (!normalizedJobId) throw new Error("A recorded job ID is required.");
  if (typeof fetchImpl !== "function") {
    throw new Error("Job recovery is unavailable in this browser.");
  }
  const response = await fetchImpl(
    apiUrl(`/api/v1/jobs/${encodeURIComponent(normalizedJobId)}`),
    {
      cache: "no-store",
      headers: { Accept: "application/json" },
    },
  );
  if (!response.ok) {
    let message = `The recorded job could not be refreshed (HTTP ${response.status}).`;
    try {
      const payload = await response.json();
      message =
        payload?.error?.message ||
        payload?.detail?.message ||
        (typeof payload?.detail === "string" ? payload.detail : message);
    } catch {
      // Keep the status-based recovery message for non-JSON responses.
    }
    throw new Error(message);
  }
  const job = await response.json();
  if (job?.kind !== "pancancer_hierarchical") {
    throw new Error("The recorded job is not a hierarchical pan-cancer run.");
  }
  return job;
}

function publishRecoveredJob(entry, job) {
  if (typeof window === "undefined" || typeof CustomEvent === "undefined") {
    return;
  }
  window.dispatchEvent(
    new CustomEvent(SESSION_JOB_EVENT, {
      detail: {
        event_id: entry.event_id,
        recorded_at: entry.recorded_at,
        summary: {
          label: entry.label,
          source_view: entry.source_view,
          design_summary: entry.design_summary,
        },
        job,
      },
    }),
  );
}

function recoveryErrorMessage(error) {
  return error instanceof Error
    ? error.message
    : "The recorded job could not be refreshed.";
}

export default function HierarchicalPanCancerModule({
  mode = "tcga_reference",
  onModeChange,
  requestState,
  onRequestChange,
  geneSelector,
  preflight,
  preflightStatus = "idle",
  preflightError = "",
  onRequestPreflight,
  onRun,
  isRunning = false,
  result,
  resultView = "all_studies",
  onResultViewChange,
  onDownload,
  disabled = false,
}) {
  const normalizedMode = normalizeAnalysisMode(mode);
  const normalizedRequest = normalizeHierarchicalRequestState(requestState);
  const requestFingerprint = hierarchicalRequestFingerprint(normalizedRequest);
  const thresholdValidation = hierarchicalThresholdState(normalizedRequest);
  const requestReady = Boolean(
    String(normalizedRequest.gene_symbol || "").trim()
    && thresholdValidation.valid,
  );
  const currentFingerprintRef = useRef(requestFingerprint);
  const preflightSequenceRef = useRef(0);
  const recoverySequenceRef = useRef(0);
  const invalidatedPreflightRef = useRef(null);
  const [acceptedPreflight, setAcceptedPreflight] = useState(null);
  const [preflightAttempt, setPreflightAttempt] = useState({
    sequence: 0,
    fingerprint: null,
    phase: "idle",
    error: "",
  });
  const [recoveredResult, setRecoveredResult] = useState(null);
  const [recovery, setRecovery] = useState({
    entry: null,
    job: null,
    status: "idle",
    error: "",
  });
  currentFingerprintRef.current = requestFingerprint;

  const suppliedPreflightFingerprint =
    hierarchicalPreflightFingerprint(preflight);
  const suppliedPreflightIsCurrent = Boolean(
    suppliedPreflightFingerprint === requestFingerprint,
  );
  const suppliedPreflightIsUsable = Boolean(
    suppliedPreflightIsCurrent &&
    preflight !== invalidatedPreflightRef.current,
  );
  const activeAttempt =
    preflightAttempt.fingerprint === requestFingerprint
      ? preflightAttempt
      : null;
  const refreshingCurrentPreflight = activeAttempt?.phase === "loading";
  // The parent owns network state. Retain only its last matching response so a
  // slower, obsolete response cannot replace the current auditable universe.
  const cachedPreflight =
    acceptedPreflight?.fingerprint === requestFingerprint
      ? acceptedPreflight.preflight
      : null;
  const effectivePreflight = refreshingCurrentPreflight
    ? null
    : suppliedPreflightIsUsable
      ? preflight
      : cachedPreflight;
  const obsoleteAttempt = Boolean(
    preflightAttempt.fingerprint &&
    preflightAttempt.fingerprint !== requestFingerprint &&
    preflightAttempt.phase !== "idle",
  );
  const stalePreflight = Boolean(
    (preflight && !suppliedPreflightIsCurrent) ||
    (acceptedPreflight &&
      acceptedPreflight.fingerprint !== requestFingerprint) ||
    obsoleteAttempt,
  );

  let effectivePreflightStatus = "idle";
  let effectivePreflightError = "";
  if (effectivePreflight) {
    effectivePreflightStatus = "ready";
  } else if (refreshingCurrentPreflight) {
    effectivePreflightStatus = "loading";
  } else if (activeAttempt?.phase === "error") {
    effectivePreflightStatus = "error";
    effectivePreflightError = activeAttempt.error;
  } else if (stalePreflight) {
    effectivePreflightStatus = "stale";
  } else if (preflightStatus === "loading") {
    effectivePreflightStatus = "loading";
  } else if (preflightStatus === "error") {
    effectivePreflightStatus = "error";
    effectivePreflightError = preflightError;
  }

  const suppliedResultFingerprint = hierarchicalResultFingerprint(result);
  const suppliedResultIsCurrent = Boolean(
    suppliedResultFingerprint === requestFingerprint,
  );
  const cachedRecoveredResult =
    recoveredResult?.fingerprint === requestFingerprint
      ? recoveredResult.result
      : null;
  const effectiveResult = isRunning
    ? null
    : suppliedResultIsCurrent
      ? result
      : cachedRecoveredResult;
  const showRecovery = Boolean(
    recovery.entry && !effectiveResult && !effectivePreflight && !isRunning,
  );

  useEffect(() => {
    if (!suppliedPreflightIsUsable) return;
    invalidatedPreflightRef.current = null;
    setAcceptedPreflight((current) =>
      current?.preflight === preflight &&
      current?.fingerprint === requestFingerprint
        ? current
        : { fingerprint: requestFingerprint, preflight },
    );
  }, [
    preflight,
    requestFingerprint,
    suppliedPreflightIsUsable,
  ]);

  useEffect(() => {
    if (
      activeAttempt?.phase !== "settled" ||
      preflightStatus !== "error" ||
      !preflightError ||
      effectivePreflight
    ) {
      return;
    }
    setPreflightAttempt((current) =>
      current.sequence === activeAttempt.sequence
        ? { ...current, phase: "error", error: preflightError }
        : current,
    );
  }, [
    activeAttempt,
    effectivePreflight,
    preflightError,
    preflightStatus,
  ]);

  async function resolveRecordedJob(entry, sequence) {
    try {
      const job = await fetchRecordedHierarchicalJob(entry.job_id);
      if (recoverySequenceRef.current !== sequence) return null;
      publishRecoveredJob(entry, job);
      setRecovery({
        entry,
        job,
        status: job.status === "completed" ? "ready" : "available",
        error: "",
      });
      return job;
    } catch (error) {
      if (recoverySequenceRef.current !== sequence) return null;
      setRecovery({
        entry,
        job: null,
        status: "error",
        error: recoveryErrorMessage(error),
      });
      return null;
    }
  }

  useEffect(() => {
    if (normalizedMode !== "hierarchical" || typeof window === "undefined") {
      recoverySequenceRef.current += 1;
      setRecovery({ entry: null, job: null, status: "idle", error: "" });
      return undefined;
    }
    const entry = latestSessionJobEntry(
      loadSessionHistory(),
      "pancancer_hierarchical",
    );
    if (!entry) {
      setRecovery({ entry: null, job: null, status: "idle", error: "" });
      return undefined;
    }
    const sequence = recoverySequenceRef.current + 1;
    recoverySequenceRef.current = sequence;
    setRecovery({ entry, job: null, status: "loading", error: "" });
    const timer = window.setTimeout(
      () => resolveRecordedJob(entry, sequence),
      0,
    );
    return () => {
      window.clearTimeout(timer);
      if (recoverySequenceRef.current === sequence) {
        recoverySequenceRef.current += 1;
      }
    };
  }, [normalizedMode]);

  async function requestCurrentPreflight() {
    const sequence = preflightSequenceRef.current + 1;
    preflightSequenceRef.current = sequence;
    invalidatedPreflightRef.current = preflight;
    setAcceptedPreflight(null);
    setRecoveredResult(null);
    setPreflightAttempt({
      sequence,
      fingerprint: requestFingerprint,
      phase: "loading",
      error: "",
    });
    if (typeof onRequestPreflight !== "function") {
      setPreflightAttempt({
        sequence,
        fingerprint: requestFingerprint,
        phase: "error",
        error: "The study eligibility check is unavailable.",
      });
      return;
    }
    try {
      await onRequestPreflight(normalizedRequest, {
        inputFingerprint: requestFingerprint,
        sequence,
      });
      if (
        preflightSequenceRef.current === sequence &&
        currentFingerprintRef.current === requestFingerprint
      ) {
        setPreflightAttempt((current) =>
          current.sequence === sequence && current.phase === "loading"
            ? { ...current, phase: "settled" }
            : current,
        );
      }
    } catch (error) {
      if (
        preflightSequenceRef.current === sequence &&
        currentFingerprintRef.current === requestFingerprint
      ) {
        setPreflightAttempt({
          sequence,
          fingerprint: requestFingerprint,
          phase: "error",
          error: recoveryErrorMessage(error),
        });
      }
    }
  }

  function runCurrentHierarchy() {
    if (
      !effectivePreflight ||
      refreshingCurrentPreflight ||
      !hierarchicalPreflightIsCurrent(effectivePreflight, normalizedRequest)
    ) {
      return;
    }
    onRun?.(normalizedRequest, effectivePreflight, {
      inputFingerprint: requestFingerprint,
    });
  }

  async function refreshRecordedJob() {
    if (!recovery.entry) return null;
    const sequence = recoverySequenceRef.current + 1;
    recoverySequenceRef.current = sequence;
    setRecovery((current) => ({
      ...current,
      status: "loading",
      error: "",
    }));
    return resolveRecordedJob(recovery.entry, sequence);
  }

  function recoverRecordedRun() {
    const recovered = recovery.job?.result;
    const snapshot =
      recovered?.request_snapshot || recovered?.preflight?.request;
    if (recovery.job?.status !== "completed" || !recovered || !snapshot) {
      setRecovery((current) => ({
        ...current,
        status: "error",
        error: "The recorded job has no recoverable hierarchical result.",
      }));
      return;
    }
    const restoredRequest = normalizeHierarchicalRequestState(snapshot);
    const restoredFingerprint = hierarchicalRequestFingerprint(restoredRequest);
    setRecoveredResult({
      fingerprint: restoredFingerprint,
      result: recovered,
    });
    setRecovery((current) => ({ ...current, status: "recovered", error: "" }));
    onRequestChange?.(restoredRequest);
  }

  return (
    <section className="hierarchical-pc-module" aria-label="Pan-cancer analysis universe">
      <HierarchicalPanCancerModeSelector
        value={normalizedMode}
        onChange={onModeChange}
        disabled={disabled || isRunning}
      />

      {normalizedMode === "hierarchical" && (
        <>
          {showRecovery && (
            <HierarchicalPanCancerJobRecovery
              recovery={recovery}
              onRefresh={refreshRecordedJob}
              onRecover={recoverRecordedRun}
              disabled={disabled || isRunning}
            />
          )}
          <HierarchicalPanCancerRequestControls
            state={normalizedRequest}
            onChange={onRequestChange}
            geneSelector={geneSelector}
            disabled={disabled || isRunning}
          />
          {!thresholdValidation.valid && (
            <div className="hierarchical-pc-error" role="alert">
              <strong>Review the study thresholds in Advanced settings</strong>
              <span>{thresholdValidation.errors[0]}</span>
            </div>
          )}
          <HierarchicalPanCancerPreflight
            preflight={effectivePreflight}
            status={effectivePreflightStatus}
            error={effectivePreflightError}
            onRefresh={requestCurrentPreflight}
            onRun={runCurrentHierarchy}
            isRunning={isRunning}
            disabled={disabled || !requestReady}
          />
          {effectiveResult && (
            <HierarchicalPanCancerResults
              result={effectiveResult}
              activeView={resultView}
              onViewChange={onResultViewChange}
              onDownload={onDownload}
            />
          )}
        </>
      )}
    </section>
  );
}

export function HierarchicalPanCancerJobRecovery({
  recovery,
  onRefresh,
  onRecover,
  disabled = false,
}) {
  const titleId = useId();
  const entry = recovery?.entry;
  if (!entry) return null;
  const job = recovery?.job;
  const status = job?.status || entry.job_status || "recorded";
  const loading = recovery.status === "loading";
  const recoverable = Boolean(job?.status === "completed" && job?.result);
  const statusLabel = String(status).replaceAll("_", " ");
  const jobIdLabel =
    entry.job_id.length > 16
      ? `${entry.job_id.slice(0, 12)}…`
      : entry.job_id;

  return (
    <section className="hierarchical-pc-panel hierarchical-pc-recovery" aria-labelledby={titleId}>
      <h2 id={titleId}>Resume the latest hierarchical run</h2>

      {loading && (
        <div className="hierarchical-pc-state" role="status" aria-live="polite">
          <span className="hierarchical-pc-progress" aria-hidden="true" />
          <div>
            <strong>Refreshing recorded job</strong>
            <small title={entry.job_id}>{jobIdLabel}</small>
          </div>
        </div>
      )}

      {recovery.error && (
        <div className="hierarchical-pc-error" role="alert">
          <strong>Recorded job could not be recovered</strong>
          <span>{recovery.error}</span>
        </div>
      )}

      {!loading && (
        <footer className="hierarchical-pc-action-row">
          <div>
            <strong>
              {entry.label || "Hierarchical pan-cancer run"} · {statusLabel}
            </strong>
            <small title={entry.job_id}>
              Job {jobIdLabel}. Recovery never runs the analysis automatically.
            </small>
          </div>
          <div>
            <button
              className="hierarchical-pc-secondary-button"
              type="button"
              onClick={() => onRefresh?.()}
              disabled={disabled}
            >
              Refresh job
            </button>
            {recoverable && (
              <button
                className="hierarchical-pc-primary-button"
                type="button"
                onClick={() => onRecover?.()}
                disabled={disabled}
              >
                Recover form and result
              </button>
            )}
          </div>
        </footer>
      )}
    </section>
  );
}

export function HierarchicalPanCancerRequestControls({
  state = HIERARCHICAL_REQUEST_DEFAULTS,
  onChange,
  geneSelector,
  disabled = false,
}) {
  const titleId = useId();
  const geneId = useId();
  const geneLabelId = useId();
  const request = normalizeHierarchicalRequestState(state);
  const contextLabel = HIERARCHICAL_CONTEXT_OPTIONS.find(
    (option) => option.value === request.clinical_context,
  )?.label || request.clinical_context;
  const updateField = (field, value) => {
    onChange?.({ ...request, [field]: value });
  };
  const geneSelectorProps = {
    id: geneId,
    value: request.gene_symbol,
    disabled,
    required: true,
    "aria-labelledby": geneLabelId,
    onChange: (value) => updateField("gene_symbol", value),
  };

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.PANCANCER_QUERY}
      className="hierarchical-pc-panel hierarchical-pc-request"
      labelledBy={titleId}
    >
      <header className="hierarchical-pc-section-header">
        <div>
          <p className="hierarchical-pc-kicker">Step 2</p>
          <div className="panel-title-row">
            <h2 id={titleId}>Choose a gene and cohorts</h2>
            <SectionHelp title="Choose a gene and cohorts" helpId="pancancerHierarchicalQuery" />
          </div>
          <p>
            Choose one gene and the cohorts to include. Each study is analyzed separately.
          </p>
        </div>
        <div className="hierarchical-pc-calibration" aria-hidden="true">
          <span>02</span><i /><i /><i />
        </div>
      </header>

      <div className="hierarchical-pc-request-grid">
        <div className="hierarchical-pc-field hierarchical-pc-gene-field">
          <label id={geneLabelId} htmlFor={geneId}>Gene marker</label>
          {typeof geneSelector === "function" ? (
            geneSelector(geneSelectorProps)
          ) : geneSelector ? (
            geneSelector
          ) : (
            <input
              {...geneSelectorProps}
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck="false"
              placeholder="e.g. ESR1"
              onChange={(event) =>
                updateField("gene_symbol", event.target.value.toUpperCase())
              }
            />
          )}
          <small>HGNC symbol; one marker per hierarchical scan.</small>
        </div>

        <div className="hierarchical-pc-field">
          <label htmlFor={`${geneId}-scope`}>Cohorts to include</label>
          <select
            id={`${geneId}-scope`}
            value={request.scope}
            disabled={disabled}
            onChange={(event) => updateField("scope", event.target.value)}
          >
            {HIERARCHICAL_SCOPE_OPTIONS.map((option) => (
              <option value={option.value} key={option.value}>{option.label}</option>
            ))}
          </select>
          <small>TCGA, curated external cohorts, or both.</small>
        </div>
      </div>

      <details className="result-disclosure hierarchical-pc-advanced">
        <summary>
          <span>
            <strong>Advanced settings</strong>
            <small>
              {contextLabel} · ≥{request.min_patients} patients, ≥{request.min_events} events,
              ≥{request.min_censored} censored{request.include_exploratory ? " · exploratory studies included" : ""}
            </small>
          </span>
          <b>Optional</b>
        </summary>
        <div className="hierarchical-pc-request-grid hierarchical-pc-advanced-grid">
          <div className="hierarchical-pc-field">
            <label htmlFor={`${geneId}-context`}>Clinical context</label>
            <select
              id={`${geneId}-context`}
              value={request.clinical_context}
              disabled={disabled}
              onChange={(event) =>
                updateField("clinical_context", event.target.value)
              }
            >
              {HIERARCHICAL_CONTEXT_OPTIONS.map((option) => (
                <option value={option.value} key={option.value}>{option.label}</option>
              ))}
            </select>
            <small>Mixed contexts are excluded rather than pooled.</small>
          </div>

          <fieldset className="hierarchical-pc-thresholds" disabled={disabled}>
            <legend>Minimum counts per study</legend>
            <FieldHelp helpId="pancancerStudyCounts" slot="does" />
            <ThresholdInput
              id={`${geneId}-patients`}
              label="Patients"
              value={request.min_patients}
              min={20}
              max={500}
              onChange={(value) => updateField("min_patients", value)}
            />
            <ThresholdInput
              id={`${geneId}-events`}
              label="Deaths"
              value={request.min_events}
              min={10}
              max={500}
              onChange={(value) => updateField("min_events", value)}
            />
            <ThresholdInput
              id={`${geneId}-censored`}
              label="Follow-up ended without death"
              value={request.min_censored}
              min={5}
              max={500}
              onChange={(value) => updateField("min_censored", value)}
            />
          </fieldset>
        </div>
        <div className="hierarchical-pc-request-footer">
          <label className="hierarchical-pc-exploratory-toggle">
            <input
              type="checkbox"
              checked={Boolean(request.include_exploratory)}
              disabled={disabled}
              onChange={(event) =>
                updateField("include_exploratory", event.target.checked)
              }
            />
            <span>
              <strong>Include exploratory-support studies</strong>
              <small>Results label these studies by evidence tier and include them in the sensitivity record.</small>
            </span>
          </label>

          <dl className="hierarchical-pc-locked-contract" aria-label="Locked hierarchical analysis settings">
            <div><dt>Endpoint</dt><dd>OS</dd></div>
            <div><dt>Time origin</dt><dd>Strict baseline</dd></div>
            <div><dt>Effect</dt><dd>Within-study IQR</dd></div>
            <div><dt>Overlap</dt><dd>Independent clusters</dd></div>
          </dl>
        </div>
      </details>
    </GuideAnchor>
  );
}

function ThresholdInput({ id, label, value, min, max, onChange }) {
  return (
    <label htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        step="1"
        inputMode="numeric"
        value={value}
        onChange={(event) =>
          onChange(event.target.value === "" ? "" : Number(event.target.value))
        }
      />
    </label>
  );
}

export function HierarchicalPanCancerModeSelector({
  value = "tcga_reference",
  onChange,
  disabled = false,
}) {
  const titleId = useId();
  const normalizedValue = normalizeAnalysisMode(value);

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.PANCANCER_MODE}
      labelledBy={titleId}
      className="hierarchical-pc-panel hierarchical-pc-mode"
    >
      <header className="hierarchical-pc-section-header">
        <div>
          <div className="panel-title-row">
            <h2 id={titleId}>1. Choose where to look</h2>
            <SectionHelp title="Choose an analysis" helpId="pancancer" />
          </div>
        </div>
      </header>

      <fieldset className="hierarchical-pc-mode-options" disabled={disabled}>
        <legend className="hierarchical-pc-sr-only">Pan-cancer analysis mode</legend>
        {PAN_CANCER_ANALYSIS_MODES.map((option) => {
          const selected = normalizedValue === option.value;
          return (
            <label
              className={`hierarchical-pc-mode-option${selected ? " is-selected" : ""}`}
              key={option.value}
            >
              <input
                type="radio"
                name="hierarchical-pan-cancer-mode"
                value={option.value}
                checked={selected}
                onChange={() => onChange?.(option.value)}
              />
              <span className="hierarchical-pc-acquisition-mark" aria-hidden="true" />
              <span className="hierarchical-pc-mode-copy">
                <strong>{option.label}</strong>
                <small>{option.description}</small>
              </span>
            </label>
          );
        })}
      </fieldset>

      <details className="hierarchical-pc-synthesis-help">
        <summary>How results are combined</summary>
        <FieldHelp helpId="pancancerSynthesis" slot="all" />
      </details>
    </GuideAnchor>
  );
}

export function HierarchicalPanCancerPreflight({
  preflight,
  status = "idle",
  error = "",
  onRefresh,
  onRun,
  isRunning = false,
  disabled = false,
}) {
  const titleId = useId();
  const liveStatusId = useId();
  const runDescriptionId = useId();
  const groups = preflightCancerGroups(preflight || {});
  const summary = summarizePreflight(preflight || {});
  const effectiveStatus = status === "idle" && preflight ? "ready" : status;
  const ready = Boolean(
    preflight &&
    groups.length &&
    (typeof preflight.summary?.can_run === "boolean"
      ? preflight.summary.can_run
      : summary.includedStudies > 0),
  );

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.PANCANCER_PREFLIGHT}
      labelledBy={titleId}
      className="hierarchical-pc-panel hierarchical-pc-preflight"
    >
      <header className="hierarchical-pc-section-header">
        <div>
          <p className="hierarchical-pc-kicker">Step 3</p>
          <div className="panel-title-row">
            <h2 id={titleId}>Check which studies qualify</h2>
            <SectionHelp title="Check which studies qualify" helpId="pancancer.preflight" />
          </div>
          <p>
            Before fitting, TRACE checks every study for a matching outcome, timing,
            clinical context, expression unit and enough patients and events.
            Excluded studies are listed with the reason.
          </p>
        </div>
        <div className="hierarchical-pc-calibration" aria-hidden="true">
          <span>03</span><i /><i /><i />
        </div>
      </header>

      {effectiveStatus === "loading" && (
        <div
          className="hierarchical-pc-state"
          role="status"
          aria-live="polite"
          aria-atomic="true"
          id={liveStatusId}
        >
          <span className="hierarchical-pc-progress" aria-hidden="true" />
          <div><strong>Checking study compatibility</strong><small>Checking study releases and patient and event counts.</small></div>
        </div>
      )}

      {effectiveStatus === "error" && error && (
        <div className="hierarchical-pc-error" role="alert">
          <strong>Preflight could not be completed</strong>
          <span>{error}</span>
        </div>
      )}

      {!preflight && effectiveStatus === "stale" && (
        <div className="hierarchical-pc-empty">
          <div>
            <strong>Inputs changed after the last eligibility check.</strong>
            <span>
              Check eligibility again for the current gene and settings before
              running the analysis.
            </span>
          </div>
          <button type="button" onClick={() => onRefresh?.()} disabled={disabled}>
            Check eligibility again
          </button>
        </div>
      )}

      {!preflight && effectiveStatus === "error" && (
        <div className="hierarchical-pc-empty">
          <div>
            <strong>Eligibility can be retried without changing the form.</strong>
            <span>Run the eligibility check again before fitting study models.</span>
          </div>
          <button type="button" onClick={() => onRefresh?.()} disabled={disabled}>
            Retry eligibility check
          </button>
        </div>
      )}

      {!preflight && effectiveStatus === "idle" && (
        <div className="hierarchical-pc-empty">
          <div>
            <strong>No eligibility check yet.</strong>
            <span>Choose a gene above, then check which studies can contribute.</span>
          </div>
          <button type="button" onClick={() => onRefresh?.()} disabled={disabled}>
            Check eligible studies
          </button>
        </div>
      )}

      {preflight && (
        <>
          <div className="hierarchical-pc-universe-summary" aria-label="Preflight universe summary">
            <PreflightMetric
              label="Cancer groups"
              value={summary.cancers}
              detail={`${formatInteger(summary.replicatedCancers)} independently replicated`}
            />
            <PreflightMetric
              label="Studies included"
              value={summary.includedStudies}
              detail={`${formatInteger(summary.excludedStudies)} excluded`}
            />
            <PreflightMetric label="Patients" value={summary.patients} />
            <PreflightMetric label="Deaths" value={summary.events} />
            <PreflightMetric label="Endpoint" value={summary.endpoint} text />
            <PreflightMetric label="Effect unit" value={summary.effectUnit} text />
          </div>

          <HierarchicalWarnings warnings={preflight.warnings || []} />

          <div className="hierarchical-pc-contract-line">
            <span>Studies checked</span>
            <strong>{formatInteger(summary.includedStudies)} / {formatInteger(summary.totalStudies)} studies pass</strong>
            <small>Counts are reported by release. Patients appearing in more than one release need to be matched before a unique-patient total can be reported.</small>
          </div>

          <details className="result-disclosure hierarchical-pc-advanced hierarchical-pc-ledger-disclosure">
            <summary>
              <span>
                <strong>Study-by-study decisions</strong>
                <small>Inclusion and exclusion reasons for every study, grouped by cancer.</small>
              </span>
              <b>{formatInteger(summary.totalStudies)} studies</b>
            </summary>
            <div className="hierarchical-pc-cancer-ledger">
              {groups.map((group, groupIndex) => (
                <PreflightCancerGroup
                  group={group}
                  key={group.cancer}
                  defaultOpen={groupIndex < 3}
                />
              ))}
            </div>
          </details>

          <footer className="hierarchical-pc-action-row">
            <div>
              <strong>
                {ready
                  ? summary.preliminaryGlobalReady
                    ? "Ready to run across studies and cancers"
                    : "Ready for per-study and per-cancer estimates only"
                  : "Not enough eligible studies to run"}
              </strong>
              <small>
                {ready && !summary.preliminaryGlobalReady
                  ? "At least two cancers with independent within-cancer replication are required for a global estimate. "
                  : ""}
                Excluded studies remain in the audit export and never contribute patient rows or weights.
              </small>
            </div>
            <div>
              <button
                className="hierarchical-pc-secondary-button"
                type="button"
                onClick={() => onRefresh?.()}
                disabled={disabled || isRunning}
              >
                Check again
              </button>
              <button
                className="hierarchical-pc-primary-button"
                type="button"
                onClick={() => onRun?.(preflight)}
                disabled={disabled || isRunning || !ready}
                aria-describedby={runDescriptionId}
              >
                {isRunning ? "Running analysis…" : "Run hierarchical analysis"}
              </button>
            </div>
          </footer>
          <span className="hierarchical-pc-sr-only" id={runDescriptionId}>
            {ready
              ? `${summary.includedStudies} studies are eligible across ${summary.cancers} cancer groups.`
              : "At least one eligible study is required."}
          </span>
        </>
      )}
    </GuideAnchor>
  );
}

function PreflightCancerGroup({ group, defaultOpen = false }) {
  const includedStudies = group.studies.filter(studyIsIncluded);
  const excludedStudies = group.studies.length - includedStudies.length;
  const includedPatients = includedStudies.reduce(
    (total, study) => total + finiteNumber(study.patients),
    0,
  );
  return (
    <details className="hierarchical-pc-cancer-group" open={defaultOpen}>
      <summary>
        <span className="hierarchical-pc-cancer-code">{group.cancer}</span>
        <span><strong>{group.label}</strong><small>{formatInteger(includedPatients)} eligible patients</small></span>
        <span className="hierarchical-pc-cancer-decision">
          <strong>{formatInteger(includedStudies.length)} included</strong>
          <small>{formatInteger(excludedStudies)} excluded</small>
        </span>
      </summary>
      <div className="hierarchical-pc-table-scroll" role="region" tabIndex="0" aria-label={`${group.label} preflight studies`}>
        <table>
          <caption className="hierarchical-pc-sr-only">
            Inclusion decisions for studies mapped to {group.label}
          </caption>
          <thead>
            <tr>
              <th scope="col">Study</th>
              <th scope="col">Endpoint definition</th>
              <th scope="col">Expression</th>
              <th scope="col">Support</th>
              <th scope="col">Decision and reason</th>
            </tr>
          </thead>
          <tbody>
            {group.studies.map((study) => (
              <PreflightStudyRow study={study} key={study.id || study.label} />
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function PreflightStudyRow({ study }) {
  const included = studyIsIncluded(study);
  const reasons = studyReasons(study);
  const exploratory =
    String(study.evidence_tier || study.status || "").toLowerCase() ===
    "exploratory";
  const decisionStatus = exploratory
    ? "exploratory"
    : included
      ? "included"
      : "excluded";
  return (
    <tr className={included ? "is-included" : "is-excluded"}>
      <th scope="row">
        <strong>{study.label || study.id}</strong>
        <small>
          {sourceLabel(study.source_kind, study.source_provider)} · {study.release_id || study.id}
        </small>
      </th>
      <td>
        <strong>{study.endpoint || "—"}</strong>
        <small>{study.time_origin || "Time origin not reported"}</small>
      </td>
      <td>
        <strong>{study.expression_unit || study.analysis_unit || "—"}</strong>
        <small>{study.tumor_context || study.sample_context || "Context not reported"}</small>
      </td>
      <td>
        <strong>{formatInteger(study.patients)} patients</strong>
        <small>{formatInteger(study.events)} events</small>
      </td>
      <td>
        <span className="hierarchical-pc-decision" data-status={decisionStatus}>
          {exploratory
            ? included
              ? "Exploratory included"
              : "Exploratory held out"
            : included
              ? "Included"
              : "Excluded"}
        </span>
        {included ? (
          <small>
            {study.decision_note ||
              (exploratory
                ? "Included in the labeled sensitivity only; never enters the primary synthesis."
                : "Meets the active hierarchical criteria.")}
          </small>
        ) : (
          <ul className="hierarchical-pc-reasons">
            {(reasons.length ? reasons : [{ code: "NOT_ELIGIBLE", label: "Does not meet the active criteria." }]).map((reason) => (
              <li key={`${reason.code}-${reason.label}`}><code>{reason.code}</code><span>{reason.label}</span></li>
            ))}
          </ul>
        )}
      </td>
    </tr>
  );
}

export function HierarchicalPanCancerResults({
  result,
  activeView = "all_studies",
  onViewChange,
  onDownload,
}) {
  const titleId = useId();
  const panelId = useId();
  const normalizedView = normalizeResultView(activeView);
  const view = hierarchicalViewPayload(result, normalizedView);
  const summary = { ...(result.summary || {}), ...(view.summary || {}) };

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.PANCANCER_RESULTS}
      labelledBy={titleId}
      className="hierarchical-pc-results"
    >
      <header className="hierarchical-pc-result-header">
        <div>
          <p className="hierarchical-pc-kicker">Step 4 · Hierarchical evidence</p>
          <div className="panel-title-row">
            <h2 id={titleId}>{result.gene_symbol || result.marker_label || "Marker"} across studies and cancers</h2>
            <SectionHelp title="Hierarchical evidence" helpId="pancancer.results" />
          </div>
          <p>
            <Term id="study_effect">Study effects</Term> retain study-specific baseline
            hazards. Diamonds summarize compatible studies{" "}
            <Term id="within_cancer_synthesis">within cancer</Term> and compatible cancer
            effects across the selected cancers.
          </p>
        </div>
        <dl className="hierarchical-pc-run-identity">
          <div><dt>Run</dt><dd>{result.analysis_id || result.scan_id || "Pending ID"}</dd></div>
          <div><dt>Pipeline</dt><dd>{result.pipeline_version || "Not reported"}</dd></div>
        </dl>
      </header>

      <div className="hierarchical-pc-view-tabs" role="tablist" aria-label="Hierarchical result view">
        {HIERARCHICAL_RESULT_VIEWS.map((option, index) => (
          <button
            type="button"
            role="tab"
            id={`${panelId}-${option.value}-tab`}
            aria-selected={normalizedView === option.value}
            aria-controls={panelId}
            tabIndex={normalizedView === option.value ? 0 : -1}
            className={normalizedView === option.value ? "is-selected" : ""}
            onClick={() => onViewChange?.(option.value)}
            onKeyDown={(event) =>
              handleResultTabKeyDown(event, index, onViewChange)
            }
            key={option.value}
          >
            <strong>{option.label}</strong>
            <small>{option.description}</small>
          </button>
        ))}
      </div>

      <div
        className="hierarchical-pc-result-panel"
        id={panelId}
        role="tabpanel"
        aria-labelledby={`${panelId}-${normalizedView}-tab`}
      >
        <div className="hierarchical-pc-result-metrics" aria-label="Selected result summary">
          <ResultMetric label="Studies" value={summary.studies ?? summary.completed_studies} />
          <ResultMetric label="Cancer effects" value={summary.cancers ?? summary.evaluable_cancers} />
          <ResultMetric label="Patients" value={summary.patients} />
          <ResultMetric label="Deaths" value={summary.events} />
          <ResultMetric
            label="Primary completed"
            value={
              summary.completed_primary_studies ??
              summary.compatible_studies ??
              summary.primary_eligible_studies
            }
          />
        </div>

        <HierarchicalWarnings warnings={result.warnings || []} />

        <HierarchicalPanCancerDownloads
          downloads={result.downloads || {}}
          onDownload={onDownload}
        />

        {view.description && <p className="hierarchical-pc-view-description">{view.description}</p>}

        <div className="hierarchical-pc-evidence-layout">
          <HierarchicalPanCancerForest
            rows={view.rows}
            markerLabel={result.gene_symbol || result.marker_label}
            effectUnit={view.effect_unit || result.effect_unit}
            endpoint={view.endpoint || result.endpoint}
          />
          <HierarchicalPanCancerDiagnostics
            heterogeneity={view.heterogeneity}
            metaAnalysis={view.meta_analysis}
            leaveOneOut={view.leaveOneOut}
          />
        </div>

        {normalizedView === "sensitivities" && (
          <HierarchicalSensitivityLedger sets={view.sensitivity_sets || view.sets || []} />
        )}
      </div>
    </GuideAnchor>
  );
}

export function HierarchicalPanCancerDownloads({ downloads = {}, onDownload }) {
  const entries = Object.entries(downloads).filter(([, url]) => Boolean(url));
  if (!entries.length) return null;
  return (
    <nav className="hierarchical-pc-downloads" aria-label="Hierarchical analysis downloads">
      <strong>Reproducible outputs</strong>
      <div>
        {entries.map(([key, url]) =>
          onDownload ? (
            <button
              type="button"
              key={key}
              onClick={() => onDownload(url, key)}
              aria-label={`Download ${downloadLabel(key)}`}
            >
              {downloadLabel(key)}
            </button>
          ) : (
            <a href={url} download key={key} aria-label={`Download ${downloadLabel(key)}`}>
              {downloadLabel(key)}
            </a>
          ),
        )}
      </div>
    </nav>
  );
}

export function HierarchicalPanCancerForest({
  rows = [],
  markerLabel = "Marker",
  effectUnit = "HR per +1 within-study expression IQR",
  endpoint = "endpoint",
}) {
  const titleId = useId();
  const descriptionId = useId();
  const tableId = useId();
  const normalizedRows = rows || [];
  const domain = forestDomain(normalizedRows);
  const ticks = forestTicks(domain);
  const width = 960;
  const plotLeft = 320;
  const plotWidth = 410;
  const estimateX = 748;
  const weightX = 918;
  const top = 58;
  const rowHeight = 48;
  const bottom = 54;
  const height = Math.max(230, top + normalizedRows.length * rowHeight + bottom);

  if (!normalizedRows.length) {
    return (
      <section className="hierarchical-pc-forest hierarchical-pc-forest-empty" aria-labelledby={titleId}>
        <h3 id={titleId}>Hierarchical forest</h3>
        <p>No estimable rows are available for this view.</p>
      </section>
    );
  }

  return (
    <figure className="hierarchical-pc-forest" aria-labelledby={titleId} aria-describedby={descriptionId}>
      <header>
        <div><p className="hierarchical-pc-kicker">Study, cancer and global estimates</p><h3 id={titleId}>Hierarchical forest</h3></div>
        <span>{normalizedRows.length} evidence rows</span>
      </header>
      <p id={descriptionId} className="hierarchical-pc-forest-description">
        Hazard ratios for {markerLabel} and {endpoint}, {effectUnit}. The vertical reference is HR 1.
        Circles and squares show study estimates. Diamonds show combined estimates for a cancer or the selected cancers.
      </p>
      <div className="hierarchical-pc-forest-scroll" role="region" tabIndex="0" aria-label="Scrollable hierarchical forest plot">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          tabIndex="0"
          aria-labelledby={`${titleId} ${descriptionId}`}
        >
          <title>{`Hierarchical forest for ${markerLabel}`}</title>
          <desc>{`${normalizedRows.length} study, cancer and global estimates on a logarithmic hazard-ratio axis. Exact values follow in a table.`}</desc>
          <text className="hierarchical-pc-svg-column-label" x="14" y="31">Evidence unit</text>
          <text className="hierarchical-pc-svg-column-label" x={plotLeft} y="31">Hazard ratio (95% CI)</text>
          <text className="hierarchical-pc-svg-column-label" x={weightX} y="31" textAnchor="end">Weight</text>

          {ticks.map((tick) => {
            const x = forestX(tick, domain, plotLeft, plotWidth);
            return (
              <g key={tick}>
                <line className={tick === 1 ? "hierarchical-pc-null-line" : "hierarchical-pc-grid-line"} x1={x} x2={x} y1="42" y2={height - bottom + 4} />
                <text className="hierarchical-pc-svg-axis-label" x={x} y={height - 18} textAnchor="middle">{formatAxisTick(tick)}</text>
              </g>
            );
          })}

          {normalizedRows.map((row, index) => {
            const kind = forestRowKind(row);
            const estimate = forestEstimate(row);
            const y = top + index * rowHeight + rowHeight / 2;
            const labelX = kind === "study" ? 36 : kind === "cancer" ? 20 : 8;
            const pointX = forestX(estimate.hazardRatio, domain, plotLeft, plotWidth);
            const lowX = forestX(estimate.confLow, domain, plotLeft, plotWidth);
            const highX = forestX(estimate.confHigh, domain, plotLeft, plotWidth);
            const rowLabel = row.label || row.study_label || row.cancer_label || row.id || "Evidence row";
            return (
              <g className={`hierarchical-pc-forest-row is-${kind}`} key={row.id || `${kind}-${index}`}>
                {kind !== "study" && <rect className="hierarchical-pc-forest-row-band" x="0" y={y - 19} width={width} height="38" />}
                <text className="hierarchical-pc-svg-row-label" x={labelX} y={y - 2}>{rowLabel}</text>
                <text className="hierarchical-pc-svg-row-meta" x={labelX} y={y + 13}>
                  {forestRowMeta(row, kind)}
                </text>
                {estimate.estimable ? (
                  <>
                    <line className="hierarchical-pc-ci-line" x1={lowX} x2={highX} y1={y} y2={y} />
                    <line className="hierarchical-pc-ci-cap" x1={lowX} x2={lowX} y1={y - 5} y2={y + 5} />
                    <line className="hierarchical-pc-ci-cap" x1={highX} x2={highX} y1={y - 5} y2={y + 5} />
                    <ForestPoint x={pointX} y={y} kind={kind} sourceKind={row.source_kind} weight={row.weight_percent ?? row.weight} />
                    <text className="hierarchical-pc-svg-estimate" x={estimateX} y={y + 4}>
                      {formatHazardRatio(estimate.hazardRatio)} [{formatHazardRatio(estimate.confLow)}, {formatHazardRatio(estimate.confHigh)}]
                    </text>
                    <text className="hierarchical-pc-svg-weight" x={weightX} y={y + 4} textAnchor="end">
                      {formatWeight(row.weight_percent ?? row.weight)}
                    </text>
                    <title>{`${rowLabel}: HR ${formatHazardRatio(estimate.hazardRatio)}, 95% CI ${formatHazardRatio(estimate.confLow)} to ${formatHazardRatio(estimate.confHigh)}${row.weight_percent == null && row.weight == null ? "" : `, weight ${formatWeight(row.weight_percent ?? row.weight)}`}`}</title>
                  </>
                ) : (
                  <text className="hierarchical-pc-svg-not-estimable" x={plotLeft} y={y + 4}>Not estimable</text>
                )}
              </g>
            );
          })}
          <text className="hierarchical-pc-svg-axis-title" x={plotLeft + plotWidth / 2} y={height - 2} textAnchor="middle">Hazard ratio on logarithmic scale</text>
        </svg>
      </div>
      <figcaption>
        <span><i className="study-tcga" aria-hidden="true" /> TCGA study</span>
        <span><i className="study-external" aria-hidden="true" /> External study</span>
        <span><i className="summary-diamond" aria-hidden="true" /> Random-effects synthesis</span>
        <small>Position and confidence interval encode the estimate; shape and text identify evidence level.</small>
      </figcaption>

      <details className="hierarchical-pc-exact-estimates">
        <summary id={tableId}>Exact estimates and support</summary>
        <div className="hierarchical-pc-table-scroll" role="region" tabIndex="0" aria-labelledby={tableId}>
          <table>
            <caption className="hierarchical-pc-sr-only">Exact hierarchical forest estimates</caption>
            <thead><tr><th scope="col">Evidence unit</th><th scope="col">Level</th><th scope="col">Patients</th><th scope="col">Events</th><th scope="col">HR</th><th scope="col">95% CI</th><th scope="col">p</th><th scope="col">FDR</th><th scope="col">Weight</th></tr></thead>
            <tbody>
              {normalizedRows.map((row, index) => {
                const estimate = forestEstimate(row);
                return (
                  <tr key={row.id || `table-${index}`}>
                    <th scope="row">{row.label || row.study_label || row.cancer_label || row.id}</th>
                    <td>{humanizeKind(forestRowKind(row), row.source_kind)}</td>
                    <td>{formatInteger(row.patients ?? row.n_patients)}</td>
                    <td>{formatInteger(row.events ?? row.n_events)}</td>
                    <td>{estimate.estimable ? formatHazardRatio(estimate.hazardRatio) : "—"}</td>
                    <td>{estimate.estimable ? `${formatHazardRatio(estimate.confLow)}–${formatHazardRatio(estimate.confHigh)}` : "Not estimable"}</td>
                    <td>{formatProbability(row.p_value ?? row.random_effect?.p_value)}</td>
                    <td>{forestRowKind(row) === "cancer" ? formatProbability(row.fdr) : "—"}</td>
                    <td>{formatWeight(row.weight_percent ?? row.weight)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}

function ForestPoint({ x, y, kind, sourceKind, weight }) {
  const numericWeight = Number(weight);
  const size = Number.isFinite(numericWeight)
    ? Math.max(4, Math.min(9, 3.5 + Math.sqrt(Math.max(0, numericWeight))))
    : 5;
  if (kind === "universe" || kind === "cancer") {
    const horizontal = kind === "universe" ? 12 : 9;
    const vertical = kind === "universe" ? 8 : 6;
    return <polygon className={`hierarchical-pc-summary-point is-${kind}`} points={`${x - horizontal},${y} ${x},${y - vertical} ${x + horizontal},${y} ${x},${y + vertical}`} />;
  }
  if (String(sourceKind || "").toLowerCase() === "tcga") {
    return <rect className="hierarchical-pc-study-point is-tcga" x={x - size} y={y - size} width={size * 2} height={size * 2} />;
  }
  return <circle className="hierarchical-pc-study-point is-external" cx={x} cy={y} r={size} />;
}

export function HierarchicalPanCancerDiagnostics({
  heterogeneity = {},
  metaAnalysis = {},
  leaveOneOut = [],
}) {
  const titleId = useId();
  const randomEffect = metaAnalysis?.random_effect || {};
  const predictionInterval = metaAnalysis?.prediction_interval || {};
  const formalSupport = metaAnalysis?.formal_pan_cancer_support || {};
  const replication = metaAnalysis?.within_cancer_replication || {};
  const iSquared = heterogeneity.i_squared;
  const evidenceUnits = Number(
    heterogeneity.units
      ?? metaAnalysis.units
      ?? metaAnalysis.cohorts
      ?? metaAnalysis.studies,
  );
  const summarizeHeterogeneity = Number.isFinite(evidenceUnits) && evidenceUnits >= 5;
  return (
    <aside className="hierarchical-pc-diagnostics" aria-labelledby={titleId}>
      <header><p className="hierarchical-pc-kicker">Stability audit</p><h3 id={titleId}>Heterogeneity and influence</h3></header>
      <dl className="hierarchical-pc-heterogeneity-grid">
        <div>
          <dt>I²</dt>
          <dd>{summarizeHeterogeneity ? formatPercent(iSquared) : "Not summarized"}</dd>
          <small>
            {summarizeHeterogeneity
              ? `${heterogeneityBand(iSquared)} heterogeneity`
              : "Fewer than five evidence units; inspect individual effects."}
          </small>
        </div>
        <div><dt>τ²</dt><dd>{formatNumber(heterogeneity.tau_squared, 3)}</dd><small>Between-unit variance</small></div>
        <div><dt>Q p</dt><dd>{formatProbability(heterogeneity.q_p_value)}</dd><small>{formatInteger(heterogeneity.df)} df</small></div>
        <div><dt>Units</dt><dd>{formatInteger(evidenceUnits)}</dd><small>{metaAnalysis.model || "Random effects"}</small></div>
      </dl>

      <div className="hierarchical-pc-pooled-estimate">
        <span>Deployed two-stage summary</span>
        <strong>
          {randomEffect.hazard_ratio == null ? "Not estimable" : `HR ${formatHazardRatio(randomEffect.hazard_ratio)}`}
        </strong>
        <small>
          {randomEffect.hr_conf_low == null
            ? metaAnalysis.reason || "No compatible pooled effect is available."
            : `95% CI ${formatHazardRatio(randomEffect.hr_conf_low)}–${formatHazardRatio(randomEffect.hr_conf_high)}`}
        </small>
      </div>

      <div className="hierarchical-pc-prediction-interval">
        <span>95% prediction interval</span>
        <strong>
          {!summarizeHeterogeneity
            ? "Not summarized"
            : predictionInterval.hazard_ratio_low == null
            ? "Not available"
            : `${formatHazardRatio(predictionInterval.hazard_ratio_low)}–${formatHazardRatio(predictionInterval.hazard_ratio_high)}`}
        </strong>
        <small>
          {summarizeHeterogeneity
            ? "Expected range for a comparable new evidence unit."
            : "At least five evidence units are required for display."}
        </small>
      </div>

      {(metaAnalysis.classification || typeof formalSupport.supported === "boolean") && (
        <div
          className="hierarchical-pc-support-classification"
          data-supported={formalSupport.supported === true}
        >
          <span>Two-stage result label</span>
          <strong>{twoStageResultLabel(metaAnalysis.classification)}</strong>
          <small>
            {formalSupport.supported
              ? `Evidence threshold met: ${formatInteger(replication.replicated_cancer_count)} cancers have independent within-cancer replication. It describes the available information; it does not establish calibrated intervals or an effect that applies to every cancer.`
              : (formalSupport.reasons || []).join("; ") ||
                "Evidence thresholds are not met; treat this two-stage summary as exploratory."}
          </small>
        </div>
      )}

      <section className="hierarchical-pc-loo" aria-labelledby={`${titleId}-loo`}>
        <header><h4 id={`${titleId}-loo`}>Leave-one-out</h4><span>{leaveOneOut.length} refits</span></header>
        {leaveOneOut.length ? (
          <div className="hierarchical-pc-table-scroll" role="region" tabIndex="0" aria-label="Leave-one-out influence analysis">
            <table>
              <caption className="hierarchical-pc-sr-only">Leave-one-out hierarchical sensitivity estimates</caption>
              <thead><tr><th scope="col">Omitted</th><th scope="col">Pooled HR</th><th scope="col">Change</th><th scope="col">Influence</th></tr></thead>
              <tbody>
                {leaveOneOut.map((row) => {
                  const influential = leaveOneOutIsInfluential(row);
                  return (
                    <tr key={row.omitted_id || row.omitted_label}>
                      <th scope="row">{row.omitted_label || row.omitted_id}</th>
                      <td>{formatHazardRatio(row.hazard_ratio ?? row.hr)}</td>
                      <td>{formatSignedPercent(row.delta_percent ?? row.relative_change)}</td>
                      <td><span className="hierarchical-pc-influence" data-influential={influential}>{influential ? "Influential" : "Stable"}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p>No leave-one-out refits are available for this view.</p>
        )}
      </section>
    </aside>
  );
}

function HierarchicalSensitivityLedger({ sets }) {
  if (!sets.length) return null;
  return (
    <section className="hierarchical-pc-sensitivity-ledger" aria-labelledby="hierarchical-pc-sensitivity-heading">
      <header><p className="hierarchical-pc-kicker">Prespecified alternatives</p><h3 id="hierarchical-pc-sensitivity-heading">Sensitivity analyses</h3></header>
      <div className="hierarchical-pc-table-scroll" role="region" tabIndex="0" aria-label="Sensitivity analysis summary">
        <table>
          <caption className="hierarchical-pc-sr-only">Prespecified hierarchical sensitivity analyses</caption>
          <thead><tr><th scope="col">Analysis</th><th scope="col">Change from primary</th><th scope="col">Evidence units</th><th scope="col">Pooled HR</th><th scope="col">Interpretation</th></tr></thead>
          <tbody>
            {sets.map((set) => (
              <tr key={set.id || set.label}>
                <th scope="row"><strong>{set.label || set.id}</strong><small>{set.id}</small></th>
                <td>{set.change || set.description || "—"}</td>
                <td>{formatInteger(set.units ?? set.studies)}</td>
                <td>{set.hazard_ratio == null ? "—" : `${formatHazardRatio(set.hazard_ratio)} [${formatHazardRatio(set.hr_conf_low)}, ${formatHazardRatio(set.hr_conf_high)}]`}</td>
                <td>{set.interpretation || set.status || "Not reported"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function HierarchicalWarnings({ warnings }) {
  if (!warnings.length) return null;
  return (
    <aside className="hierarchical-pc-warnings" aria-label="Methodological warnings">
      <strong>Methodological notes</strong>
      <ul>
        {warnings.map((warning, index) => (
          <li key={`${index}-${warning}`}>{warning}</li>
        ))}
      </ul>
    </aside>
  );
}

function handleResultTabKeyDown(event, currentIndex, onViewChange) {
  const lastIndex = HIERARCHICAL_RESULT_VIEWS.length - 1;
  let nextIndex = null;
  if (event.key === "ArrowRight" || event.key === "ArrowDown") {
    nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1;
  } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
    nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1;
  } else if (event.key === "Home") {
    nextIndex = 0;
  } else if (event.key === "End") {
    nextIndex = lastIndex;
  }
  if (nextIndex == null) return;
  event.preventDefault();
  const next = HIERARCHICAL_RESULT_VIEWS[nextIndex];
  onViewChange?.(next.value);
  const tabs = event.currentTarget
    .closest('[role="tablist"]')
    ?.querySelectorAll('[role="tab"]');
  tabs?.[nextIndex]?.focus();
}

function PreflightMetric({ label, value, detail, text = false }) {
  return <div className={text ? "is-text" : ""}><span>{label}</span><strong>{text ? value || "—" : formatInteger(value)}</strong>{detail && <small>{detail}</small>}</div>;
}

function ResultMetric({ label, value }) {
  return <div><span>{label}</span><strong>{formatInteger(value)}</strong></div>;
}

function sourceLabel(sourceKind, sourceProvider) {
  if (String(sourceKind || "").toLowerCase() === "tcga") return "TCGA reference";
  return sourceProvider || "Curated external";
}

function downloadLabel(key) {
  const labels = {
    studies: "Study effects · CSV",
    cancers: "Cancer effects · CSV",
    ledger: "Inclusion ledger · CSV",
    methodology: "Methodology · TXT",
    audit_html: "Audit report · HTML",
    attestation: "Attestation · JSON",
    result_json: "Complete result · JSON",
    zip: "Reproduction capsule · ZIP",
    study_effects_csv: "Study effects · CSV",
    cancer_effects_csv: "Cancer effects · CSV",
    global_result_json: "Global synthesis · JSON",
    leave_one_out_csv: "Leave-one-out · CSV",
    forest_svg: "Hierarchical forest · SVG",
    audit_json: "Audit record · JSON",
    reproduction_zip: "Reproduction capsule · ZIP",
  };
  return labels[key] || String(key).replace(/_/g, " ");
}

function humanizeContractValue(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/^./, (character) => character.toUpperCase());
}

function twoStageResultLabel(value) {
  const labels = {
    insufficient_support: "Evidence threshold not met",
    no_average_association: "Two-stage CI includes HR 1",
    average_pan_cancer_association: "Average direction in the two-stage summary",
    broadly_consistent: "Consistent direction in the two-stage summary",
    heterogeneous_or_context_dependent: "Heterogeneous or context dependent",
  };
  return labels[value] || humanizeContractValue(value || "not classified");
}

function forestRowMeta(row, kind) {
  if (kind === "study") {
    return `${sourceLabel(row.source_kind, row.source_provider)} · ${formatInteger(row.events ?? row.n_events)} events`;
  }
  if (kind === "cancer") {
    return `${formatInteger(row.studies)} studies · ${formatInteger(row.events ?? row.n_events)} events`;
  }
  return `${formatInteger(row.cancers)} cancers · ${formatInteger(row.studies)} studies`;
}

function humanizeKind(kind, sourceKind) {
  if (kind === "universe") return "Global synthesis";
  if (kind === "cancer") return "Cancer synthesis";
  return String(sourceKind || "").toLowerCase() === "tcga" ? "TCGA study" : "External study";
}

function finiteNumber(value) {
  return scientificNumber(value) ?? 0;
}

function formatInteger(value) {
  const numeric = scientificNumber(value);
  return numeric !== null ? Math.round(numeric).toLocaleString("en-US") : "—";
}

function formatNumber(value, digits = 2) {
  const numeric = scientificNumber(value);
  return numeric !== null ? numeric.toFixed(digits) : "—";
}

function formatHazardRatio(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "—";
  if (numeric < 0.1) return numeric.toPrecision(2);
  if (numeric >= 10) return numeric.toFixed(1);
  return numeric.toFixed(2);
}

function formatAxisTick(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "";
  if (numeric >= 1) return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
  return numeric >= 0.1 ? numeric.toFixed(2).replace(/0$/, "") : numeric.toPrecision(1);
}

function formatWeight(value) {
  const numeric = scientificNumber(value);
  return numeric !== null ? `${numeric.toFixed(1)}%` : "—";
}

function formatPercent(value) {
  const numeric = scientificNumber(value);
  return numeric !== null ? `${numeric.toFixed(1)}%` : "—";
}

function formatSignedPercent(value) {
  const numeric = scientificNumber(value);
  if (numeric === null) return "—";
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function formatProbability(value) {
  const numeric = scientificNumber(value);
  if (numeric === null || numeric < 0 || numeric > 1) return "—";
  if (numeric < 0.001) return numeric.toExponential(1);
  return numeric.toFixed(3);
}
