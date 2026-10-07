import React, { useId, useRef, useState } from "react";
import { ModuleIcon, TraceIcon } from "../design/icons";
import { GUIDE_ANCHORS } from "./catalog";
import { GuideAnchor } from "./GuideAnchor";
import { TUTORIAL_DOCK_ID } from "./TutorialDock";
import "./tutorials.css";
import { GuideVideo } from "./GuideVideo";

function TutorialRow({ tutorial, labels, controller }) {
  const summaryId = `tutorial-summary-${tutorial.id}`;
  const guideProgress = controller.getGuideProgress?.(tutorial.id) || null;
  const completed = guideProgress?.status === "completed";
  const resumable = tutorial.mode === "live" && guideProgress && !completed;
  const savedStep = resumable
    ? Math.max(0, tutorial.steps.findIndex((step) => step.id === guideProgress.lastStepId)) + 1
    : null;
  const source = tutorial.sourceKind === "synthetic_case"
    ? labels.sourceKinds?.synthetic_case || labels.fixedExample
    : labels.sourceKinds?.live || labels.liveGuide;

  function openTutorial(event) {
    controller.captureTrigger?.(event.currentTarget);
    if (resumable) controller.resume(tutorial.id);
    else controller.start(tutorial.id);
  }

  return (
    <li className="trace-tutorial-row" data-status={resumable ? "in-progress" : "new"}>
      <ModuleIcon role={tutorial.iconRole} frame="compact" />
      <div className="trace-tutorial-row-copy">
        <div className="trace-tutorial-row-heading">
          <h3>{tutorial.title}</h3>
          <span className={`trace-tutorial-mode trace-tutorial-mode-${tutorial.mode}`}>
            {source}
          </span>
        </div>
        <p id={summaryId}>{tutorial.summary}</p>
        <div className="trace-tutorial-row-meta">
          <span>{tutorial.steps.length} {labels.step.toLowerCase()}{tutorial.steps.length === 1 ? "" : "s"}</span>
          {tutorial.estimatedMinutes && <span>{tutorial.estimatedMinutes} {labels.minutes || "min"}</span>}
          {savedStep && <span>{labels.step} {savedStep}/{tutorial.steps.length}</span>}
        </div>
      </div>
      <div className="trace-tutorial-row-actions">
      <button
        type="button"
        className="trace-tutorial-row-action"
        aria-describedby={summaryId}
        aria-controls={controller.tutorial?.id === tutorial.id ? TUTORIAL_DOCK_ID : undefined}
        aria-expanded={controller.tutorial?.id === tutorial.id}
        onClick={openTutorial}
      >
        {completed ? labels.reviewGuide : resumable ? labels.resume : labels.start}
        <TraceIcon role="action.next" size="sm" />
      </button>
      <GuideVideo guideId={tutorial.id} title={tutorial.title} />
      </div>
    </li>
  );
}

function ManualPanel({ curriculum, onPrint }) {
  const { labels, manuals } = curriculum;
  const [selectedId, setSelectedId] = useState(manuals[0]?.id || "");
  const selected = manuals.find((manual) => manual.id === selectedId) || manuals[0];
  if (!selected) return null;
  const selectedIndex = Math.max(0, manuals.findIndex((manual) => manual.id === selected.id));

  function printSelectedManual() {
    const body = globalThis.document?.body;
    const disclosures = Array.from(
      globalThis.document?.querySelectorAll(
        `[data-manual-id="${selected.id}"] details`,
      ) || [],
    );
    const disclosureState = disclosures.map((details) => details.open);
    disclosures.forEach((details) => { details.open = true; });
    if (body) body.dataset.printTarget = "tutorial-manual";
    const clearPrintTarget = () => {
      if (body?.dataset.printTarget === "tutorial-manual") {
        delete body.dataset.printTarget;
      }
      disclosures.forEach((details, index) => { details.open = disclosureState[index]; });
    };
    globalThis.addEventListener?.("afterprint", clearPrintTarget, { once: true });
    try {
      if (typeof onPrint === "function") onPrint(selected.id);
      else globalThis.print?.();
    } finally {
      globalThis.setTimeout?.(clearPrintTarget, 1000);
    }
  }
  return (
    <div className="trace-tutorial-manual-layout">
      <nav aria-label={labels.manualContents} className="trace-tutorial-manual-index">
        <div className="trace-tutorial-manual-index-heading">
          <h3>{labels.manualContents}</h3>
        </div>
        <div className="trace-tutorial-manual-mobile-picker">
          <label htmlFor="trace-manual-topic">{labels.manualContents}</label>
          <select
            id="trace-manual-topic"
            value={selected.id}
            onChange={(event) => setSelectedId(event.target.value)}
          >
            {manuals.map((manual) => (
              <option key={manual.id} value={manual.id}>{manual.title}</option>
            ))}
          </select>
        </div>
        <ol>
          {manuals.map((manual, index) => (
            <li key={manual.id}>
              <button
                type="button"
                aria-current={manual.id === selected.id ? "page" : undefined}
                aria-controls="trace-manual-content"
                onClick={() => setSelectedId(manual.id)}
              >
                <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <strong>{manual.title}</strong>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <article
        id="trace-manual-content"
        className="trace-tutorial-manual"
        aria-labelledby={`trace-${selected.id}-title`}
        data-manual-id={selected.id}
      >
        <header>
          <div>
            <p className="trace-tutorial-eyebrow">
              {labels.manualGuide} {selectedIndex + 1} of {manuals.length}
            </p>
            <h3 id={`trace-${selected.id}-title`}>{selected.title}</h3>
            <p>{selected.summary}</p>
          </div>
          <button
            type="button"
            className="trace-tutorial-print"
            onClick={printSelectedManual}
          >
            <TraceIcon role="file.text" size="sm" />
            {labels.printManual}
          </button>
        </header>
        <div className="trace-tutorial-manual-sections">
          {selected.sections.map((section, index) => (
            <section key={section.id} aria-labelledby={`trace-${selected.id}-${section.id}`}>
              <span className="trace-tutorial-manual-section-number" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <h4 id={`trace-${selected.id}-${section.id}`}>{section.title}</h4>
                {section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
                {section.checklist.length > 0 && (
                  <div className="trace-tutorial-manual-checks">
                    <p>{labels.manualChecks}</p>
                    <ul>{section.checklist.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                )}
              </div>
            </section>
          ))}
        </div>
        {selected.concepts?.length > 0 && (
          <details
            className="trace-tutorial-manual-concepts"
          >
            <summary>
              <span>{labels.manualConcepts || labels.concepts}</span>
              <small>{selected.concepts.length} terms</small>
            </summary>
            <div>
              <dl>
                {selected.concepts.map((concept) => (
                  <div key={concept.id}>
                    <dt>{concept.term}</dt>
                    <dd>{concept.definition}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </details>
        )}
        {selected.citations?.length > 0 && (
          <details
            className="trace-tutorial-manual-references"
          >
            <summary>
              <span>{labels.manualReferences || labels.references}</span>
              <small>{selected.citations.length} {selected.citations.length === 1 ? "reference" : "references"}</small>
            </summary>
            <div>
              <ol>
                {selected.citations.map((citation) => (
                  <li key={citation.id}>
                    <span>{citation.authors} ({citation.year}). {citation.title}. <i>{citation.venue}</i>.</span>{" "}
                    {citation.doi && (
                      <a href={`https://doi.org/${citation.doi}`}>doi:{citation.doi}</a>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          </details>
        )}
      </article>
    </div>
  );
}

export function TutorialLibrary({
  controller,
  className = "",
  onPrint,
}) {
  const { curriculum, state } = controller;
  const { labels } = curriculum;
  const id = useId().replaceAll(":", "");
  const tabRefs = useRef([]);
  const tabs = [
    { id: "tutorials", label: labels.guides },
    { id: "manuals", label: labels.manuals },
  ];

  function handleTabKeyDown(event, index) {
    let nextIndex = null;
    if (event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    controller.setTab(tabs[nextIndex].id);
    tabRefs.current[nextIndex]?.focus();
  }

  return (
    <section
      className={["trace-tutorial-library", className].filter(Boolean).join(" ")}
      aria-label={labels.learningCenter}
    >
      <div className="trace-tutorial-tabs" role="tablist" aria-label={labels.learningCenter}>
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            ref={(element) => { tabRefs.current[index] = element; }}
            type="button"
            role="tab"
            id={`${id}-tab-${tab.id}`}
            aria-selected={state.tab === tab.id}
            aria-controls={`${id}-panel`}
            tabIndex={state.tab === tab.id ? 0 : -1}
            onClick={() => controller.setTab(tab.id)}
            onKeyDown={(event) => handleTabKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        id={`${id}-panel`}
        role="tabpanel"
        aria-labelledby={`${id}-tab-${state.tab}`}
        className="trace-tutorial-tab-panel"
      >
        {state.tab !== "manuals" ? (
          <>
            <GuideAnchor anchor={GUIDE_ANCHORS.EXAMPLES_QUICK} labelledBy={`${id}-quick`}>
              <h3 id={`${id}-quick`}>{labels.quickGuides}</h3>
              <ul className="trace-tutorial-list">
                {curriculum.quickGuides.map((tutorial) => (
                  <TutorialRow
                    key={tutorial.id}
                    tutorial={tutorial}
                    labels={labels}
                    controller={controller}
                  />
                ))}
              </ul>
            </GuideAnchor>
            <GuideAnchor anchor={GUIDE_ANCHORS.EXAMPLES_ROUTES} labelledBy={`${id}-routes`}>
              <h3 id={`${id}-routes`}>{labels.routes}</h3>
              <ol className="trace-tutorial-list trace-tutorial-route-list">
                {curriculum.routes.map((tutorial) => (
                  <TutorialRow
                    key={tutorial.id}
                    tutorial={tutorial}
                    labels={labels}
                    controller={controller}
                  />
                ))}
              </ol>
            </GuideAnchor>
          </>
        ) : (
          <GuideAnchor anchor={GUIDE_ANCHORS.EXAMPLES_MANUALS} label={labels.manuals}>
            <ManualPanel
              curriculum={curriculum}
              onPrint={onPrint}
            />
          </GuideAnchor>
        )}
      </div>
    </section>
  );
}

export default TutorialLibrary;
