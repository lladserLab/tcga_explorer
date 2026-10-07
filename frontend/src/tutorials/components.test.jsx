// @vitest-environment jsdom

import React, { useRef } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GUIDE_ANCHORS } from "./catalog";
import { getTutorialById, getTutorialCurriculum } from "./curriculum";
import { GuideAnchor } from "./GuideAnchor";
import {
  TUTORIAL_PREFERENCES_STORAGE_KEY,
  TUTORIAL_PROGRESS_STORAGE_KEY,
} from "./progress";
import { TUTORIAL_DOCK_ID, TutorialDock } from "./TutorialDock";
import { TutorialLibrary } from "./TutorialLibrary";
import { useTutorialController } from "./useTutorialController";

function controllerFor({
  guide = null,
  lesson = null,
  step: legacyStep = 1,
  tab = "tutorials",
} = {}) {
  const curriculum = getTutorialCurriculum();
  const tutorial = guide ? getTutorialById(guide) : null;
  const requestedStep = tutorial?.steps[legacyStep - 1] || null;
  const requestedLesson = lesson
    || requestedStep?.id
    || (tutorial ? "overview" : null);
  const resolvedLesson = tutorial?.type === "quick" && requestedLesson === "overview"
    ? tutorial.steps[0]?.id
    : requestedLesson;
  const step = tutorial?.steps.find((item) => item.id === resolvedLesson) || null;
  const stepNumber = step ? tutorial.steps.indexOf(step) + 1 : 1;
  const progress = { schemaVersion: 3, activeGuideId: null, guides: {} };
  return {
    state: {
      view: step?.openView || tutorial?.steps[0]?.openView || "examples",
      tab,
      guide,
      lesson: resolvedLesson,
      step: stepNumber,
    },
    curriculum,
    tutorial,
    step,
    progress,
    preferences: { schemaVersion: 2, presentation: "auto" },
    presentation: "auto",
    isOpen: Boolean(tutorial),
    isOverview: resolvedLesson === "overview",
    isComplete: resolvedLesson === "complete",
    canResume: false,
    getGuideProgress: () => null,
    setTab() {}, setView() {}, setPresentation() {},
    start() {}, resume() {}, showOverview() {}, setLesson() {}, setStep() {},
    previous() {}, next() {}, complete() {}, close() {},
  };
}

function DockHarness({ guide = "quick-gsea", capabilities = {} }) {
  const controller = useTutorialController({
    windowLike: window,
    storage: window.localStorage,
  });
  const triggerRef = useRef(null);
  return (
    <>
      <main className="workspace"><h1 tabIndex={-1}>TRACE workspace</h1></main>
      <button
        ref={triggerRef}
        type="button"
        aria-controls={TUTORIAL_DOCK_ID}
        aria-expanded={controller.isOpen}
        onClick={() => controller.start(guide, "overview")}
      >
        Open learning guide
      </button>
      <TutorialDock
        controller={controller}
        triggerRef={triggerRef}
        capabilities={capabilities}
      />
    </>
  );
}

function setTutorialUrl({
  guide = null,
  lesson = null,
  view = "gsea",
  legacyLanguage = null,
} = {}) {
  const params = new URLSearchParams({ view, tab: "tutorials" });
  if (legacyLanguage) params.set("lang", legacyLanguage);
  if (guide) params.set("guide", guide);
  if (lesson) params.set("lesson", lesson);
  window.history.replaceState(null, "", `/?${params.toString()}`);
}

beforeEach(() => {
  window.localStorage.clear();
  setTutorialUrl({ view: "home" });
  vi.stubGlobal("requestAnimationFrame", (callback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("tutorial components", () => {
  test("GuideAnchor renders a named, focusable semantic landmark", () => {
    const markup = renderToStaticMarkup(
      <GuideAnchor anchor={GUIDE_ANCHORS.GSEA_RESULTS} label="GSEA results">
        <p>Evidence</p>
      </GuideAnchor>,
    );
    expect(markup).toContain('data-guide-anchor="gsea.results"');
    expect(markup).toContain('aria-label="GSEA results"');
    expect(markup).toContain('tabindex="-1"');
    expect(() => renderToStaticMarkup(
      <GuideAnchor anchor="unknown.anchor" label="Unknown" />,
    )).toThrow("Unknown TRACE Explorer guide anchor");
    expect(() => renderToStaticMarkup(
      <GuideAnchor anchor={GUIDE_ANCHORS.GSEA_RESULTS} />,
    )).toThrow("requires label or labelledBy");
  });

  test("GuideAnchor can make the real workflow button the tutorial target", () => {
    const markup = renderToStaticMarkup(
      <GuideAnchor
        as="button"
        anchor={GUIDE_ANCHORS.SURVIVAL_DATASET}
        label="Dataset workflow step"
        tabIndex={0}
        type="button"
      >
        Dataset
      </GuideAnchor>,
    );
    expect(markup).toMatch(/^<button/);
    expect(markup).toContain('id="trace-guide-survival-dataset"');
    expect(markup).toContain('tabindex="0"');
    expect(markup).toContain(">Dataset</button>");
  });

  test("TutorialDock uses lesson ids for non-modal accessible step navigation", () => {
    const tutorial = getTutorialById("quick-gsea");
    const markup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: tutorial.steps[1].id,
      })} />,
    );
    expect(markup).toContain("<aside");
    expect(markup).not.toContain('role="dialog"');
    expect(markup).not.toContain("aria-modal");
    expect(markup).toContain('aria-current="step"');
    expect(markup).toContain(`data-lesson="${tutorial.steps[1].id}"`);
    expect(markup).not.toContain("Apply preset");
    expect(markup).not.toContain("Show me where");
    expect(markup).not.toContain("trace-tutorial-show-workspace");
    expect(markup).not.toContain("Open module");
    expect(markup).not.toContain("Before you continue");
    expect(markup).not.toContain("Reviewed");
  });

  test("keeps plain-language analysis guidance in the final quick step", () => {
    const tutorial = getTutorialById("quick-gsea");
    const entryMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: "overview",
      })} />,
    );
    expect(entryMarkup).toContain("What to do");
    expect(entryMarkup).not.toContain("Begin guide");
    expect(entryMarkup).not.toContain("How to read this analysis");

    const interpretationMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: tutorial.steps.at(-1).id,
      })} />,
    );
    expect(interpretationMarkup).toContain("Question this analysis answers");
    expect(interpretationMarkup).toContain("Limitations");
    expect(interpretationMarkup).toContain("Bibliographic references");
    expect(interpretationMarkup).toContain("What to look for");
    expect(interpretationMarkup).not.toContain("Scientific contract");
    expect(interpretationMarkup).not.toContain("Interpretation notes");

    const routeMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: "groups-to-pathways",
        lesson: "overview",
      })} />,
    );
    expect(routeMarkup).toContain("<h3>Objectives</h3>");
    expect(routeMarkup).toContain("Begin guide");

    const fixedCaseMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: "example-gsea-direction",
        lesson: "overview",
      })} />,
    );
    expect(fixedCaseMarkup).toContain("Begin guide");
  });

  test("keeps quick setup steps focused on the action and defers interpretation detail", () => {
    const tutorial = getTutorialById("quick-gsea");
    const setupMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: tutorial.steps[0].id,
      })} />,
    );
    expect(setupMarkup).toContain("What to do");
    expect(setupMarkup).toContain("Why this matters");
    expect(setupMarkup).not.toContain("Show me where");
    expect(setupMarkup).not.toContain("trace-tutorial-show-workspace");
    expect(setupMarkup).not.toContain("Open module");
    expect(setupMarkup).not.toContain("What to look for");
    expect(setupMarkup).not.toContain("How to read this analysis");

    const interpretationMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: tutorial.steps.at(-1).id,
      })} />,
    );
    expect(interpretationMarkup).toContain("What to look for");
    expect(interpretationMarkup).toContain("Question this analysis answers");
    expect(interpretationMarkup).toContain("Limitations");
    expect(interpretationMarkup).not.toContain("Interpretation notes");
  });

  test.each([
    ["quick guide", "quick-gsea", "collection"],
    ["route guide", "included-data-first-analysis", "question"],
    ["fixed teaching case", "example-gsea-direction", "context"],
  ])("does not render a workspace-locating action in a %s", (_kind, guide, lesson) => {
    const markup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({ guide, lesson })} />,
    );

    expect(markup).not.toContain("Show me where");
    expect(markup).not.toContain("trace-tutorial-show-workspace");
  });

  test("omits empty prerequisite copy and keeps only actionable preparation", () => {
    const immediateMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: "quick-analysis",
        lesson: "overview",
      })} />,
    );
    expect(immediateMarkup).not.toContain("Prerequisites");
    expect(immediateMarkup).not.toContain("No prerequisites");
    expect(immediateMarkup).not.toContain("<h3>Before you start</h3>");

    const preparedMarkup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: "groups-to-pathways",
        lesson: "overview",
      })} />,
    );
    expect(preparedMarkup).toContain("<h3>Before you start</h3>");
    expect(preparedMarkup).toContain("An eligible cohort and a two-group hypothesis.");
  });

  test("fixed examples expose current teaching provenance without a live preset", () => {
    const markup = renderToStaticMarkup(
      <TutorialDock controller={controllerFor({
        guide: "example-gsea-direction",
        lesson: "context",
      })} />,
    );
    expect(markup).toContain("TRACE-TEACH-GSEA-DIRECTION-V1");
    expect(markup).toContain("teaching-contract-only");
    expect(markup).toContain("2026-08-05");
    expect(markup).toContain("8cc4eed344d0df08c047a0b2f71fed59addbd1242859cc5598cde815a379d002");
    expect(markup).toContain("tutorial-examples/gsea-direction.json");
    expect(markup).toContain("Open the example data");
    expect(markup).not.toContain("Apply preset");
  });

  test("renders versioned synthetic evidence inside a fixed case", async () => {
    const tutorial = getTutorialById("example-gsea-direction");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        result_id: tutorial.provenance.result_id,
        scenario: {
          dotplot_contract: {
            point_area: "min(-log10(FDR), 10)",
            display_limit: "up to the 30 pathways with lowest FDR",
          },
          synthetic_pathways: [{ pathway: "SYNTHETIC_GO_INTERFERON_RESPONSE", nes: 1.75 }],
        },
      }),
    }));
    render(
      <TutorialDock controller={controllerFor({
        guide: tutorial.id,
        lesson: "evidence",
      })} />,
    );

    expect(await screen.findByText("SYNTHETIC_GO_INTERFERON_RESPONSE")).toBeTruthy();
    expect(screen.getByText("min(-log10(FDR), 10)")).toBeTruthy();
    expect(screen.getByText("Evidence in this fixed case")).toBeTruthy();
  });

  test("applies a lesson preset when a full route has no guide-level preset", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("validation-generalization");
    const presetStep = tutorial.steps.find(
      (item) => item.presetId === "pancancer-hierarchical-cdc20",
    );
    const onApplyPreset = vi.fn();
    render(
      <TutorialDock
        controller={controllerFor({
          guide: tutorial.id,
          lesson: presetStep.id,
        })}
        onApplyPreset={onApplyPreset}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Apply preset" }));
    expect(onApplyPreset).toHaveBeenCalledWith("pancancer-hierarchical-cdc20");
  });

  test("Open module navigates to the current lesson target and closes the guide", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("included-data-first-analysis");
    const targetStep = tutorial.steps.find((item) => item.openView === "analysis");
    const controller = controllerFor({
      guide: tutorial.id,
      lesson: targetStep.id,
    });
    controller.close = vi.fn();
    const onNavigate = vi.fn();

    render(<TutorialDock controller={controller} onNavigate={onNavigate} />);
    await user.click(screen.getByRole("button", { name: "Open module" }));

    expect(onNavigate).toHaveBeenCalledWith("analysis", {
      anchor: targetStep.anchor,
      workflowStepId: targetStep.workspaceStepId || null,
    });
    expect(controller.close).toHaveBeenCalledOnce();
  });

  test("names the recommended continuation and warns when progress is ephemeral", () => {
    const route = getTutorialById("included-data-first-analysis");
    const completionController = controllerFor({
      guide: route.id,
      lesson: "complete",
    });
    completionController.persistenceAvailable = false;
    const markup = renderToStaticMarkup(
      <TutorialDock controller={completionController} />,
    );

    expect(markup).toContain("From groups to pathways");
    expect(markup).not.toContain("<strong>groups-to-pathways</strong>");
    expect(markup).toContain("Progress will be kept only until this page reloads");
  });

  test("explains unavailable evidence and offers a jump when the result already exists", () => {
    const tutorial = getTutorialById("quick-gsea");
    const resultStep = tutorial.steps.at(-1);
    const controller = controllerFor({
      guide: tutorial.id,
      lesson: tutorial.steps[0].id,
    });
    const unavailableMarkup = renderToStaticMarkup(
      <TutorialDock controller={controller} capabilities={{}} />,
    );
    expect(unavailableMarkup).toContain('data-available="false"');
    expect(unavailableMarkup).not.toContain("The result is already available");

    const readyMarkup = renderToStaticMarkup(
      <TutorialDock
        controller={controller}
        capabilities={{ "gsea.resultAvailable": true }}
      />,
    );
    expect(readyMarkup).toContain("The result is already available");
    expect(readyMarkup).toContain(`Jump to: ${resultStep.title}`);

    // Requirements explain missing evidence, but never introduce checkpoint UI.
    const route = getTutorialById("included-data-first-analysis");
    const blockedMarkup = renderToStaticMarkup(
      <TutorialDock
        controller={controllerFor({
          guide: route.id,
          lesson: route.steps.find((step) => step.requirements.some((item) => item.blocking)).id,
        })}
        capabilities={{}}
      />,
    );
    expect(blockedMarkup).toContain("Available when the analysis contains:");
    expect(blockedMarkup).not.toContain("Before you continue");
    expect(blockedMarkup).not.toContain("Reviewed");
  });

  test("library exposes only Tutorials and Manuals as tabs", () => {
    const markup = renderToStaticMarkup(
      <TutorialLibrary controller={controllerFor()} />,
    );
    expect((markup.match(/role="tab"/g) || [])).toHaveLength(2);
    expect(markup).toContain("Tutorials");
    expect(markup).toContain("Manuals");
    expect(markup).not.toContain("Reference analyses");
    expect(markup).not.toContain("Fixed teaching cases");
    expect(markup).not.toContain("This teaching case is fixed");
    expect(markup).not.toContain("Español");
    expect(markup).not.toContain('aria-label="Language"');
  });

  test("library resumes a live guide from its v3 per-guide progress", async () => {
    const user = userEvent.setup();
    const controller = controllerFor();
    const tutorial = getTutorialById("quick-gsea");
    const guideProgress = {
      contentVersion: tutorial.version,
      lastStepId: tutorial.steps[1].id,
      status: "in_progress",
    };
    controller.getGuideProgress = (guideId) => (
      guideId === tutorial.id ? guideProgress : null
    );
    controller.resume = vi.fn();
    controller.start = vi.fn();
    render(<TutorialLibrary controller={controller} />);

    const row = screen.getByRole("heading", { name: tutorial.title }).closest("li");
    expect(within(row).getByText(`Step 2/${tutorial.steps.length}`)).toBeTruthy();
    await user.click(within(row).getByRole("button", {
      name: controller.curriculum.labels.resume,
    }));
    expect(controller.resume).toHaveBeenCalledWith(tutorial.id);
    expect(controller.start).not.toHaveBeenCalled();
  });

  test("keeps finished guide progress without showing a Completed badge", () => {
    const controller = controllerFor();
    const tutorial = getTutorialById("included-data-first-analysis");
    controller.getGuideProgress = (guideId) => (
      guideId === tutorial.id
        ? {
            contentVersion: tutorial.version,
            lastStepId: tutorial.steps.at(-1).id,
            status: "completed",
          }
        : null
    );

    const markup = renderToStaticMarkup(<TutorialLibrary controller={controller} />);
    expect(markup).toContain("Review guide");
    expect(markup).not.toContain(">Completed<");
  });

  test("manuals are printable and retain concepts and references", () => {
    const manualMarkup = renderToStaticMarkup(
      <TutorialLibrary controller={controllerFor({ tab: "manuals" })} />,
    );
    expect(manualMarkup).toContain("Save guide as PDF");
    expect(manualMarkup).toContain("Prepare and upload data");
    expect(manualMarkup).toContain("Terms used in this guide");
    expect(manualMarkup).toContain("Provenance");
    expect(manualMarkup).toContain("Scientific references");
    expect(manualMarkup).toContain("The FAIR Guiding Principles");
    expect(manualMarkup).toContain('href="https://doi.org/10.1038/sdata.2016.18"');
  });

  test("opens a quick guide on the first stable lesson without an extra begin action", async () => {
    const tutorial = getTutorialById("quick-gsea");
    setTutorialUrl({ guide: tutorial.id, lesson: "overview" });
    render(
      <DockHarness
        guide={tutorial.id}
        capabilities={{ "gsea.resultAvailable": true }}
      />,
    );

    expect(screen.getByRole("heading", { name: tutorial.title })).toBeTruthy();
    expect(screen.getByRole("heading", { name: tutorial.steps[0].title })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Begin guide" })).toBeNull();
    const activeStep = screen.getByRole("button", {
      name: `Step 1 of ${tutorial.steps.length}: ${tutorial.steps[0].title}`,
    });
    expect(activeStep.getAttribute("aria-current")).toBe("step");
    expect(screen.getByRole("button", { name: "Previous" }).disabled).toBe(true);
    expect(window.location.search).toContain(`lesson=${tutorial.steps[0].id}`);
  });

  test("a module guide is informational and finishes without acknowledgements", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("quick-gsea");
    setTutorialUrl({ guide: tutorial.id, lesson: "overview" });
    render(
      <DockHarness
        guide={tutorial.id}
        capabilities={{ "gsea.resultAvailable": true }}
      />,
    );

    expect(screen.queryByText("Before you continue")).toBeNull();
    expect(screen.queryByRole("button", { name: "Reviewed" })).toBeNull();
    expect(screen.getByText("Question this analysis answers")).toBeTruthy();
    expect(screen.getByText("Limitations")).toBeTruthy();

    for (let index = 1; index < tutorial.steps.length; index += 1) {
      await user.click(screen.getByRole("button", { name: "Next" }));
      expect(screen.queryByText("Before you continue")).toBeNull();
      expect(screen.queryByRole("button", { name: "Reviewed" })).toBeNull();
    }
    expect(screen.getByText("Bibliographic references")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Finish" }));

    expect(document.getElementById(TUTORIAL_DOCK_ID)?.dataset.lesson).toBe("complete");
    expect(screen.getByRole("button", { name: "Review guide" })).toBeTruthy();
    const persisted = JSON.parse(
      window.localStorage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY),
    );
    expect(persisted.guides[tutorial.id]).toMatchObject({
      status: "completed",
      lastStepId: tutorial.steps.at(-1).id,
    });

    await user.click(screen.getByRole("button", { name: "Review guide" }));
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: tutorial.steps[0].title }),
    );
    expect(document.getElementById(TUTORIAL_DOCK_ID)?.dataset.lesson).toBe(
      tutorial.steps[0].id,
    );
    expect(screen.getByRole("button", { name: "Previous" }).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Begin guide" })).toBeNull();
  });

  test("completes a route directly without checkpoint gating", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("included-data-first-analysis");
    setTutorialUrl({
      guide: tutorial.id,
      lesson: tutorial.steps.at(-1).id,
    });
    render(
      <DockHarness
        guide={tutorial.id}
        capabilities={{ "survival.resultAvailable": true }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Finish" }));
    expect(document.getElementById(TUTORIAL_DOCK_ID)?.dataset.lesson).toBe("complete");
    expect(screen.queryByText("Completed", { exact: true })).toBeNull();
    expect(screen.getByText("You have finished this guide. You can reopen it from the first page at any time.")).toBeTruthy();
  });

  test("Escape closes the dock and restores focus to its trigger", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("quick-gsea");
    render(<DockHarness guide={tutorial.id} />);
    const trigger = screen.getByRole("button", { name: "Open learning guide" });

    await user.click(trigger);
    const heading = screen.getByRole("heading", { name: tutorial.title });
    expect(document.activeElement).toBe(heading);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("heading", { name: tutorial.title })).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  test("mini mode is explicit, reversible and persisted separately", async () => {
    const user = userEvent.setup();
    const tutorial = getTutorialById("quick-gsea");
    setTutorialUrl({ guide: tutorial.id, lesson: "overview" });
    const { container } = render(<DockHarness guide={tutorial.id} />);

    await user.click(screen.getByRole("button", { name: "Minimize tutorial" }));
    const miniDock = container.querySelector(`#${TUTORIAL_DOCK_ID}`);
    expect(miniDock?.getAttribute("data-presentation")).toBe("mini");
    expect(JSON.parse(
      window.localStorage.getItem(TUTORIAL_PREFERENCES_STORAGE_KEY),
    ).presentation).toBe("mini");
    expect(document.activeElement).toBe(
      container.querySelector(".trace-tutorial-mini-main"),
    );

    await user.click(container.querySelector(".trace-tutorial-mini-main"));
    expect(container.querySelector(`#${TUTORIAL_DOCK_ID}`)?.getAttribute("data-presentation")).toBe("auto");
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: tutorial.title }),
    );
    expect(JSON.parse(
      window.localStorage.getItem(TUTORIAL_PREFERENCES_STORAGE_KEY),
    ).presentation).toBe("auto");
  });
});
