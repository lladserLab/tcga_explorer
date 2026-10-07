import React, { useEffect, useRef, useState } from "react";
import { IconButton, ModuleIcon, TraceIcon } from "../design/icons";
import { resolveTutorialCitations } from "./citationRegistry";
import {
  evaluateTutorialRequirements,
  getTutorialCapabilityLabel,
} from "./scientificContracts";
import {
  clearGuideSpotlight,
  spotlightGuideAnchor,
} from "./GuideAnchor";
import "./tutorials.css";
import { GuideVideo } from "./GuideVideo";

export const TUTORIAL_DOCK_ID = "trace-tutorial-dock";

function copy(labels, key, english) {
  return labels?.[key] || english;
}

function list(values) {
  return Array.isArray(values) ? values.filter(Boolean) : [];
}

function sourceLabel(tutorial, labels) {
  if (tutorial.sourceLabel) return tutorial.sourceLabel;
  if (tutorial.sourceKind === "synthetic_case") {
    return copy(labels, "syntheticCase", "Synthetic case · not computed");
  }
  if (tutorial.sourceKind === "computed_benchmark") {
    return copy(labels, "computedBenchmark", "Computed benchmark");
  }
  return copy(labels, "liveGuide", "Current analysis");
}

function ProvenanceDisclosure({ tutorial, labels }) {
  if (tutorial.mode !== "fixed" || !tutorial.provenance) return null;
  return (
    <details className="trace-tutorial-provenance-block">
      <summary>
        <TraceIcon role="document.reference" size="sm" />
        {copy(labels, "provenance", "Case provenance")}
      </summary>
      <p className="trace-tutorial-provenance-note">
        {copy(
          labels,
          "fixedCaseNotice",
          "This is a fixed teaching example. It does not change your analysis and its values are not a result from your data.",
        )}
      </p>
      <dl className="trace-tutorial-provenance">
        <div><dt>{labels.resultId}</dt><dd>{tutorial.provenance.result_id}</dd></div>
        <div><dt>{labels.pipelineVersion}</dt><dd>{tutorial.provenance.pipeline_version}</dd></div>
        <div><dt>{labels.snapshotDate}</dt><dd>{tutorial.provenance.snapshot_date}</dd></div>
        <div><dt>{labels.sha256}</dt><dd>{tutorial.provenance.sha256}</dd></div>
      </dl>
      <a
        className="trace-tutorial-provenance-link"
        href={`${import.meta.env.BASE_URL}${tutorial.provenance.artifact_path}`}
        target="_blank"
        rel="noopener noreferrer"
      >
        <TraceIcon role="document.reference" size="sm" />
        {labels.verifyArtifact}
      </a>
    </details>
  );
}

function artifactFieldLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\bhr\b/gi, "HR")
    .replace(/\bfdr\b/gi, "FDR")
    .replace(/\bnes\b/gi, "NES")
    .replace(/\biqr\b/gi, "IQR")
    .replace(/\bid\b/gi, "ID")
    .replace(/^./, (character) => character.toUpperCase());
}

function artifactScalar(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    return new Intl.NumberFormat("en-US", {
      maximumSignificantDigits: 5,
    }).format(value);
  }
  return String(value);
}

function isArtifactScalar(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function isFlatArtifactRow(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.values(value).every((item) => (
      isArtifactScalar(item)
      || (Array.isArray(item) && item.every(isArtifactScalar))
    ));
}

function ArtifactValue({ value, depth = 0 }) {
  if (isArtifactScalar(value)) return <span>{artifactScalar(value)}</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span>—</span>;
    if (value.every(isArtifactScalar)) {
      return <span>{value.map((item) => artifactScalar(item)).join(" · ")}</span>;
    }
    if (value.every(isFlatArtifactRow)) {
      const columns = [...new Set(value.flatMap((row) => Object.keys(row)))];
      return (
        <div
          className="trace-tutorial-artifact-table-scroll"
          role="region"
          tabIndex="0"
          aria-label={`Scrollable synthetic evidence table: ${columns.map(artifactFieldLabel).join(", ")}`}
        >
          <table>
            <thead><tr>{columns.map((column) => <th key={column} scope="col">{artifactFieldLabel(column)}</th>)}</tr></thead>
            <tbody>
              {value.map((row, index) => (
                <tr key={row.id || row.study_id || row.specification_id || row.pathway || `${depth}-${index}`}>
                  {columns.map((column) => (
                    <td key={column}>
                      {Array.isArray(row[column])
                        ? row[column].map((item) => artifactScalar(item)).join(" · ")
                        : artifactScalar(row[column])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <ol className="trace-tutorial-artifact-list">
        {value.map((item, index) => (
          <li key={item?.id || item?.study_id || item?.pathway || `${depth}-${index}`}>
            <ArtifactValue value={item} depth={depth + 1} />
          </li>
        ))}
      </ol>
    );
  }
  return (
    <dl className={`trace-tutorial-artifact-fields depth-${Math.min(depth, 3)}`}>
      {Object.entries(value).map(([key, item]) => (
        <div key={key}>
          <dt>{artifactFieldLabel(key)}</dt>
          <dd><ArtifactValue value={item} depth={depth + 1} /></dd>
        </div>
      ))}
    </dl>
  );
}

function TeachingCaseEvidence({ tutorial, stepId, labels }) {
  const [artifact, setArtifact] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [expanded, setExpanded] = useState(stepId === "evidence");
  const artifactPath = tutorial.provenance?.artifact_path;

  useEffect(() => setExpanded(stepId === "evidence"), [stepId]);

  useEffect(() => {
    if (!artifactPath || typeof globalThis.fetch !== "function") return undefined;
    const controller = new AbortController();
    setArtifact(null);
    setLoadError(false);
    globalThis.fetch(`${import.meta.env.BASE_URL}${artifactPath}`, {
      signal: controller.signal,
      cache: "force-cache",
    })
      .then((response) => {
        if (!response.ok) throw new Error(`Teaching artifact ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (payload?.result_id !== tutorial.provenance.result_id) {
          throw new Error("Teaching artifact identity mismatch");
        }
        setArtifact(payload);
      })
      .catch((error) => {
        if (error?.name !== "AbortError") setLoadError(true);
      });
    return () => controller.abort();
  }, [artifactPath, tutorial.provenance?.result_id]);

  if (!artifactPath) return null;
  const titleId = `trace-tutorial-artifact-${tutorial.id}`;
  return (
    <details
      className="trace-tutorial-artifact"
      open={expanded}
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary id={titleId}>
        <TraceIcon role="document.reference" size="sm" />
        {copy(labels, "caseEvidence", "Evidence in this fixed case")}
      </summary>
      <div className="trace-tutorial-artifact-body" aria-labelledby={titleId}>
        <p>
          {copy(
            labels,
            "caseEvidenceNotice",
            "This example uses fixed synthetic values to explain the method. The values do not come from your data.",
          )}
        </p>
        {artifact?.scenario ? (
          <ArtifactValue value={artifact.scenario} />
        ) : loadError ? (
          <p role="status">
            {copy(labels, "caseEvidenceError", "The example data could not be loaded. Open the example data link above.")}
          </p>
        ) : (
          <p role="status">{copy(labels, "loading", "Loading evidence…")}</p>
        )}
      </div>
    </details>
  );
}

function CitationItems({ citationIds }) {
  const citations = resolveTutorialCitations(citationIds);
  if (!citations.length) return null;
  return (
    <ol>
      {citations.map((citation) => (
        <li key={citation.id}>
          <span>{citation.authors} ({citation.year}). {citation.title}. <i>{citation.venue}</i>.</span>
          {citation.doi && (
            <a href={`https://doi.org/${citation.doi}`} target="_blank" rel="noopener noreferrer">
              DOI
            </a>
          )}
        </li>
      ))}
    </ol>
  );
}

function GuideScientificContext({ contract, limitations, citationIds, labels }) {
  if (!contract) return null;
  const resolvedLimitations = list(limitations).length
    ? list(limitations)
    : list(contract.cannotConclude);
  const citations = resolveTutorialCitations(citationIds);
  return (
    <section className="trace-tutorial-scientific-context">
      <div className="trace-tutorial-question">
        <h4>{copy(labels, "questionAnswered", "Question this analysis answers")}</h4>
        <p>{contract.question}</p>
      </div>
      {resolvedLimitations.length > 0 && (
        <div className="trace-tutorial-limitations">
          <h4>{copy(labels, "limitations", "Limitations")}</h4>
          <ul>{resolvedLimitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      )}
      {citations.length > 0 && (
        <details className="trace-tutorial-reading">
          <summary>{copy(labels, "bibliographicReferences", "Bibliographic references")}</summary>
          <CitationItems citationIds={citationIds} />
        </details>
      )}
    </section>
  );
}

function RequirementNotice({ requirements, capabilities, labels }) {
  const evaluation = evaluateTutorialRequirements(requirements, capabilities);
  if (!evaluation.missing.length) return null;
  return (
    <aside className="trace-tutorial-requirements" aria-label={copy(labels, "requirements", "Step requirements")}>
      <TraceIcon role="status.info" size="sm" tone="secondary" />
      <div>
        <strong>{copy(labels, "availableAfter", "Available when the analysis contains:")}</strong>
        <ul>
          {evaluation.missing.map((requirement) => (
            <li key={requirement.id}>{getTutorialCapabilityLabel(requirement.capability)}</li>
          ))}
        </ul>
      </div>
    </aside>
  );
}

function TutorialContextActions({
  tutorial,
  activePresetId,
  labels,
  onApplyPreset,
  onOpenModule,
}) {
  return (
    <div className="trace-tutorial-context-actions">
      {tutorial.mode === "live" && activePresetId && (
        <button type="button" onClick={onApplyPreset}>
          <TraceIcon role="action.configure" size="sm" />
          {labels.applyPreset}
        </button>
      )}
      <button type="button" onClick={onOpenModule}>
        <TraceIcon role="action.next" size="sm" />
        {labels.openModule}
      </button>
    </div>
  );
}

function TutorialOverview({ tutorial, labels, onBegin }) {
  const stepCountLabel = tutorial.steps.length === 1
    ? labels.step.toLowerCase()
    : copy(labels, "steps", "steps");
  return (
    <div className="trace-tutorial-overview">
      <div className="trace-tutorial-overview-summary">
        <span>{tutorial.steps.length} {stepCountLabel} · {tutorial.estimatedMinutes || "–"} min</span>
        <p>{tutorial.summary}</p>
      </div>
      <section>
        <h3>{copy(labels, "objectives", "You will be able to")}</h3>
        <ul>{list(tutorial.objectives).map((objective) => <li key={objective.id}>{objective.text}</li>)}</ul>
      </section>
      {tutorial.prerequisites?.length > 0 && (
        <section>
          <h3>{copy(labels, "prerequisites", "Before you start")}</h3>
          <ul>{tutorial.prerequisites.map((item) => <li key={typeof item === "string" ? item : item.id}>{typeof item === "string" ? item : item.label}</li>)}</ul>
        </section>
      )}
      <GuideScientificContext
        contract={tutorial.scientificContract}
        limitations={tutorial.scientificContract?.cannotConclude}
        citationIds={[]}
        labels={labels}
      />
      <button type="button" className="trace-tutorial-primary-action" onClick={onBegin}>
        {copy(labels, "beginGuide", "Begin guide")}
        <TraceIcon role="action.next" size="sm" />
      </button>
    </div>
  );
}

function TutorialCompletion({
  tutorial,
  nextTutorial,
  labels,
  onReview,
  onLearningCenter,
  onContinue,
}) {
  const continuation = tutorial.continuations?.[0] || tutorial.nextGuideId;
  const continuationId = typeof continuation === "string" ? continuation : continuation?.guideId;
  return (
    <div className="trace-tutorial-completion">
      <h3>{tutorial.title}</h3>
      <p>{copy(labels, "completionMessage", "You have finished this guide. You can reopen it from the first page at any time.")}</p>
      <div className="trace-tutorial-completion-actions">
        {continuationId && (
          <button type="button" className="trace-tutorial-primary-action" onClick={() => onContinue(continuationId)}>
            <span>
              <small>{copy(labels, "recommendedNext", "Recommended next")}</small>
              <strong>{nextTutorial?.title || continuationId}</strong>
            </span>
            <TraceIcon role="action.next" size="sm" />
          </button>
        )}
        <button type="button" onClick={onReview}>
          {copy(labels, "reviewGuide", "Review guide")}
        </button>
        <button type="button" onClick={onLearningCenter}>
          {copy(labels, "learningCenter", "Learning center")}
        </button>
      </div>
    </div>
  );
}

export function TutorialDock({
  controller,
  capabilities = {},
  triggerRef,
  onNavigate,
  onApplyPreset,
  className = "",
}) {
  const { curriculum, tutorial, step, state } = controller;
  const labels = curriculum.labels;
  const [notice, setNotice] = useState("");
  const [minimized, setMinimized] = useState(controller.presentation === "mini");
  const titleRef = useRef(null);
  const stepTitleRef = useRef(null);
  const progressRef = useRef(null);
  const miniMainRef = useRef(null);
  const openTriggerRef = useRef(null);
  const previousGuideRef = useRef(null);
  const navigateRef = useRef(onNavigate);
  const pendingContentFocusRef = useRef(false);
  const pendingPresentationFocusRef = useRef(false);

  useEffect(() => {
    setMinimized(controller.presentation === "mini");
  }, [controller.presentation]);

  useEffect(() => {
    navigateRef.current = onNavigate;
  }, [onNavigate]);

  useEffect(() => {
    if (
      !tutorial
      || !step?.workspaceStepId
      || controller.isOverview
      || controller.isComplete
    ) return;
    navigateRef.current?.(step.openView, {
      anchor: null,
      workflowStepId: step.workspaceStepId,
      syncOnly: true,
    });
  }, [controller.isComplete, controller.isOverview, step?.id, tutorial?.id]);

  useEffect(() => {
    if (!tutorial) return undefined;
    setNotice("");
    setMinimized(controller.presentation === "mini");
    const active = globalThis.document?.activeElement;
    const openedFromTrigger = active?.getAttribute?.("aria-controls") === TUTORIAL_DOCK_ID;
    const capturedTrigger = controller.openTriggerRef?.current || null;
    const openedFromCapturedTrigger = Boolean(capturedTrigger);
    const changedGuide = Boolean(
      previousGuideRef.current && previousGuideRef.current !== tutorial.id,
    );
    if (openedFromTrigger || openedFromCapturedTrigger) {
      openTriggerRef.current = openedFromTrigger ? active : capturedTrigger;
    }
    if (openedFromTrigger || openedFromCapturedTrigger || changedGuide) {
      globalThis.requestAnimationFrame?.(() => titleRef.current?.focus({ preventScroll: true }));
    }
    previousGuideRef.current = tutorial.id;
    return undefined;
  }, [tutorial?.id]);

  useEffect(() => {
    if (!tutorial || !step?.anchor || controller.isOverview || controller.isComplete) {
      clearGuideSpotlight();
      return undefined;
    }
    let cancelled = false;
    let timer = null;
    let remaining = 6;
    const applySpotlight = () => {
      if (cancelled || spotlightGuideAnchor(step.anchor) || remaining <= 0) return;
      remaining -= 1;
      timer = globalThis.setTimeout?.(applySpotlight, 80);
    };
    applySpotlight();
    return () => {
      cancelled = true;
      if (timer) globalThis.clearTimeout?.(timer);
      clearGuideSpotlight();
    };
  }, [controller.isComplete, controller.isOverview, step?.anchor, step?.id, tutorial]);

  useEffect(() => {
    if (controller.isOverview || controller.isComplete) return;
    progressRef.current
      ?.querySelector('[aria-current="step"]')
      ?.scrollIntoView?.({ behavior: "auto", block: "nearest", inline: "center" });
  }, [controller.isComplete, controller.isOverview, state.lesson]);

  useEffect(() => {
    if (!pendingContentFocusRef.current) return;
    pendingContentFocusRef.current = false;
    globalThis.requestAnimationFrame?.(() => (
      stepTitleRef.current || titleRef.current
    )?.focus?.({ preventScroll: true }));
  }, [state.lesson]);

  useEffect(() => {
    if (!pendingPresentationFocusRef.current) return;
    pendingPresentationFocusRef.current = false;
    globalThis.requestAnimationFrame?.(() => (
      minimized ? miniMainRef.current : titleRef.current
    )?.focus?.({ preventScroll: true }));
  }, [minimized]);

  useEffect(() => {
    if (!tutorial) return undefined;
    function handleEscape(event) {
      if (event.key !== "Escape") return;
      if (globalThis.document?.querySelector(".trace-video-dialog[open]")) return;
      event.preventDefault();
      closeDock();
    }
    globalThis.document?.addEventListener("keydown", handleEscape);
    return () => globalThis.document?.removeEventListener("keydown", handleEscape);
  }, [tutorial]);

  useEffect(() => {
    if (!tutorial) return undefined;
    const documentLike = globalThis.document;
    const root = documentLike?.documentElement;
    if (root) root.dataset.tutorialDock = minimized ? "minimized" : "open";

    function keepFocusedControlVisible(event) {
      const target = event.target;
      if (target?.closest?.(".trace-video-dialog")) return;
      const dock = documentLike?.getElementById(TUTORIAL_DOCK_ID);
      if (!dock || dock.contains(target) || !target?.getBoundingClientRect) return;
      globalThis.requestAnimationFrame?.(() => {
        const targetRect = target.getBoundingClientRect();
        const dockRect = dock.getBoundingClientRect();
        const overlaps = targetRect.bottom > dockRect.top - 12
          && targetRect.top < dockRect.bottom + 12
          && targetRect.right > dockRect.left - 12
          && targetRect.left < dockRect.right + 12;
        if (overlaps) {
          target.scrollIntoView?.({ behavior: "auto", block: "center", inline: "nearest" });
        }
      });
    }

    documentLike?.addEventListener("focusin", keepFocusedControlVisible);
    return () => {
      documentLike?.removeEventListener("focusin", keepFocusedControlVisible);
      if (root?.dataset.tutorialDock) delete root.dataset.tutorialDock;
    };
  }, [minimized, tutorial?.id]);

  useEffect(() => () => {
    clearGuideSpotlight();
  }, []);

  if (!tutorial) return null;

  const currentIndex = step ? tutorial.steps.findIndex((item) => item.id === step.id) : -1;
  const finalStep = currentIndex === tutorial.steps.length - 1;
  const isQuick = tutorial.type === "quick";
  const activePresetId = step?.presetId || tutorial.presetId || null;
  const continuation = tutorial.continuations?.[0] || tutorial.nextGuideId;
  const continuationId = typeof continuation === "string"
    ? continuation
    : continuation?.guideId;
  const nextTutorial = continuationId ? curriculum.byId[continuationId] : null;
  const phaseLabel = step?.phase ? curriculum.phases[step.phase] : null;
  const requirements = step?.requirements || tutorial.requirements || [];
  const readyLaterStep = tutorial.type === "quick" && currentIndex === 0
    ? tutorial.steps.slice(1).find((candidate) => (
      candidate.requirements?.some((requirement) => (
        requirement.blocking && requirement.jumpWhenAvailable
      ))
      && evaluateTutorialRequirements(candidate.requirements, capabilities).available
    ))
    : null;

  function restoreFocus() {
    const target = openTriggerRef.current?.isConnected
      ? openTriggerRef.current
      : (triggerRef?.current || controller.openTriggerRef?.current)?.isConnected
        ? (triggerRef?.current || controller.openTriggerRef?.current)
        : globalThis.document?.querySelector(".workspace h1");
    globalThis.requestAnimationFrame?.(() => target?.focus?.({ preventScroll: true }));
  }

  function closeDock() {
    clearGuideSpotlight();
    controller.close();
    restoreFocus();
  }

  function openCurrentModule() {
    const view = step?.openView || step?.module || tutorial.module;
    if (!view || typeof onNavigate !== "function") return;
    onNavigate(view, {
      anchor: step?.anchor || null,
      workflowStepId: step?.workspaceStepId || null,
    });
    closeDock();
  }

  function applyPreset() {
    if (!activePresetId || tutorial.mode !== "live") return;
    onApplyPreset?.(activePresetId);
    setNotice(labels.presetApplied);
  }

  function changeLesson(action) {
    pendingContentFocusRef.current = true;
    action();
  }

  function finishGuide() {
    controller.complete();
  }

  function setUserMinimized(next) {
    pendingPresentationFocusRef.current = true;
    setMinimized(next);
    controller.setPresentation(next ? "mini" : "auto");
  }

  if (minimized) {
    return (
      <aside
        id={TUTORIAL_DOCK_ID}
        className={["trace-tutorial-dock", "is-minimized", className].filter(Boolean).join(" ")}
        aria-label={tutorial.title}
        data-presentation="mini"
      >
        <button ref={miniMainRef} type="button" className="trace-tutorial-mini-main" onClick={() => setUserMinimized(false)}>
          <ModuleIcon role={tutorial.iconRole} frame="compact" />
          <span>
            <small>{controller.isOverview
              ? copy(labels, "overview", "Overview")
              : controller.isComplete
                ? "End of guide"
                : `${labels.step} ${currentIndex + 1}/${tutorial.steps.length}`}</small>
            <strong>{step?.title || tutorial.title}</strong>
          </span>
          <TraceIcon role="action.expand" size="sm" />
        </button>
        <GuideVideo key={tutorial.id} guideId={tutorial.id} title={tutorial.title} />
        <IconButton iconRole="action.close" label={labels.close} onClick={closeDock} />
      </aside>
    );
  }

  return (
    <aside
      id={TUTORIAL_DOCK_ID}
      className={["trace-tutorial-dock", className].filter(Boolean).join(" ")}
      aria-labelledby="trace-tutorial-title"
      data-tutorial-mode={tutorial.mode}
      data-source-kind={tutorial.sourceKind}
      data-presentation="auto"
      data-lesson={state.lesson}
    >
      <header className="trace-tutorial-dock-header">
        <ModuleIcon role={tutorial.iconRole} frame="compact" />
        <div>
          <p className="trace-tutorial-eyebrow">{sourceLabel(tutorial, labels)}</p>
          <h2 id="trace-tutorial-title" ref={titleRef} tabIndex={-1}>{tutorial.title}</h2>
          <GuideVideo key={tutorial.id} guideId={tutorial.id} title={tutorial.title} />
        </div>
        <div className="trace-tutorial-dock-tools">
          <button
            type="button"
            className="trace-tutorial-minimize"
            onClick={() => setUserMinimized(true)}
            aria-label={copy(labels, "minimize", "Minimize tutorial")}
          >
            <span aria-hidden="true">−</span>
          </button>
          <IconButton iconRole="action.close" label={labels.close} onClick={closeDock} />
        </div>
      </header>

      <div className="trace-tutorial-live-region sr-only" aria-live="polite" aria-atomic="true">
        {controller.isOverview
          ? `${tutorial.title}. ${copy(labels, "overview", "Overview")}`
          : controller.isComplete
            ? `${tutorial.title}. End of guide.`
            : `${labels.step} ${currentIndex + 1} ${labels.of} ${tutorial.steps.length}: ${step?.title}`}
      </div>

      <div className="trace-tutorial-dock-body">
        {tutorial.mode === "live" && controller.persistenceAvailable === false && (
          <p className="trace-tutorial-persistence-warning" role="status">
            <TraceIcon role="status.caution" size="sm" tone="caution" />
            {copy(
              labels,
              "progressNotPersistent",
              "Browser storage is unavailable. Progress will be kept only until this page reloads.",
            )}
          </p>
        )}
        <ProvenanceDisclosure tutorial={tutorial} labels={labels} />
        {tutorial.mode === "fixed" && !controller.isOverview && !controller.isComplete && (
          <TeachingCaseEvidence
            tutorial={tutorial}
            stepId={step?.id}
            labels={labels}
          />
        )}

        {controller.isOverview ? (
          <TutorialOverview
            tutorial={tutorial}
            labels={labels}
            onBegin={() => changeLesson(controller.next)}
          />
        ) : controller.isComplete ? (
          <TutorialCompletion
            tutorial={tutorial}
            nextTutorial={nextTutorial}
            labels={labels}
            onReview={() => changeLesson(controller.showOverview)}
            onContinue={(guideId) => controller.start(guideId)}
            onLearningCenter={() => {
              clearGuideSpotlight();
              controller.openLearningCenter();
              onNavigate?.("examples", {
                tutorialStateCommitted: true,
                focusLearningCenter: true,
              });
            }}
          />
        ) : step ? (
          <>
            <nav ref={progressRef} className="trace-tutorial-progress" aria-label={labels.progress}>
              <ol>
                {tutorial.steps.map((item, index) => {
                  const availability = evaluateTutorialRequirements(item.requirements, capabilities);
                  const unavailable = availability.missing.length > 0;
                  const availabilityLabel = unavailable
                    ? copy(labels, "stepUnavailable", "Result not available yet")
                    : "";
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        aria-current={item.id === state.lesson ? "step" : undefined}
                        aria-label={`${labels.step} ${index + 1} ${labels.of} ${tutorial.steps.length}: ${item.title}${availabilityLabel ? `. ${availabilityLabel}` : ""}`}
                        title={availabilityLabel || undefined}
                        data-available={unavailable ? "false" : "true"}
                        onClick={() => changeLesson(() => controller.setLesson(item.id))}
                      >
                        <span>{index + 1}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            </nav>

            <article className="trace-tutorial-step">
              <div className="trace-tutorial-step-position">
                <span>{labels.step} {currentIndex + 1} {labels.of} {tutorial.steps.length}</span>
                {phaseLabel && <span>{phaseLabel}</span>}
              </div>
              <h3 ref={stepTitleRef} tabIndex={-1}>{step.title}</h3>
              <GuideScientificContext
                contract={step.scientificContract}
                limitations={step.cannotConclude}
                citationIds={finalStep ? tutorial.citationIds : []}
                labels={labels}
              />
              {isQuick ? (
                <>
                  <p className="trace-tutorial-instruction">
                    <strong>{copy(labels, "whatToDo", "What to do")}</strong>
                    <span>{step.instruction}</span>
                  </p>
                  <p className="trace-tutorial-why"><strong>{copy(labels, "why", "Why this matters")}</strong>{step.why}</p>
                </>
              ) : (
                <>
                  <p className="trace-tutorial-why"><strong>{copy(labels, "why", "Why this matters")}</strong>{step.why}</p>
                  <p className="trace-tutorial-instruction">{step.instruction}</p>
                </>
              )}

              <RequirementNotice requirements={requirements} capabilities={capabilities} labels={labels} />

              {readyLaterStep && (
                <button
                  type="button"
                  className="trace-tutorial-ready-jump"
                  onClick={() => changeLesson(() => controller.setLesson(readyLaterStep.id))}
                >
                  <TraceIcon role="status.success" size="sm" tone="success" />
                  <span>
                    <small>{copy(labels, "evidenceAvailable", "The result is already available")}</small>
                    <strong>{`Jump to: ${readyLaterStep.title}`}</strong>
                  </span>
                  <TraceIcon role="action.next" size="sm" />
                </button>
              )}

              {(!isQuick || finalStep) && (
                <dl className="trace-tutorial-evidence">
                  <div>
                    <dt>{isQuick
                      ? copy(labels, "whatToLookFor", "What to look for")
                      : labels.output}</dt>
                    <dd>{step.output}</dd>
                  </div>
                </dl>
              )}
            </article>

            {!isQuick && (
              <TutorialContextActions
                tutorial={tutorial}
                activePresetId={activePresetId}
                labels={labels}
                onApplyPreset={applyPreset}
                onOpenModule={openCurrentModule}
              />
            )}
          </>
        ) : null}
      </div>

      <p className="trace-tutorial-status" id="trace-tutorial-status" role="status" aria-live="polite">{notice}</p>

      {!controller.isOverview && !controller.isComplete && step && (
        <footer className="trace-tutorial-dock-footer">
          <button
            type="button"
            disabled={isQuick && currentIndex === 0}
            onClick={() => changeLesson(controller.previous)}
          >
            <TraceIcon role="action.back" size="sm" />
            {labels.previous}
          </button>
          <button
            type="button"
            className="trace-tutorial-primary-action"
            aria-describedby="trace-tutorial-status"
            onClick={() => {
              setNotice("");
              if (finalStep) {
                pendingContentFocusRef.current = true;
                finishGuide();
              } else {
                changeLesson(controller.next);
              }
            }}
          >
            {finalStep ? labels.finish : labels.next}
            <TraceIcon role={finalStep ? "status.success" : "action.next"} size="sm" />
          </button>
        </footer>
      )}
    </aside>
  );
}

export default TutorialDock;
