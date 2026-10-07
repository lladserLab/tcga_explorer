import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test, vi } from "vitest";
import { getTutorialById } from "./curriculum";
import {
  TUTORIAL_PROGRESS_STORAGE_KEY,
  saveTutorialPreferences,
} from "./progress";
import { useTutorialController } from "./useTutorialController";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

function browser(search = "") {
  return {
    location: { pathname: "/tcga_explorer/", search, hash: "" },
    history: { pushState: vi.fn(), replaceState: vi.fn() },
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
}

function renderController(options) {
  let controller;
  function Probe() {
    controller = useTutorialController(options);
    return <span>controller probe</span>;
  }
  renderToStaticMarkup(<Probe />);
  return controller;
}

describe("tutorial controller contracts", () => {
  test("has no language or checkpoint API and completes a live guide directly", () => {
    const storage = memoryStorage();
    saveTutorialPreferences(storage, { presentation: "auto", lang: "es" });
    const windowLike = browser();
    const controller = renderController({ storage, windowLike });
    const tutorial = getTutorialById("included-data-first-analysis");

    expect(controller.state).not.toHaveProperty("lang");
    expect(controller.preferences).not.toHaveProperty("lang");
    expect(controller).not.toHaveProperty("setLanguage");
    expect(controller).not.toHaveProperty("completeCheckpoint");
    expect(controller).not.toHaveProperty("completedCheckpointIds");

    controller.start(tutorial.id, tutorial.steps[1].id);
    const completedState = controller.complete();

    expect(completedState.lesson).toBe("complete");
    expect(windowLike.history.pushState).toHaveBeenLastCalledWith(
      null,
      "",
      expect.stringContaining("lesson=complete"),
    );
    const persisted = JSON.parse(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY));
    expect(persisted.schemaVersion).toBe(3);
    expect(persisted.activeGuideId).toBe(tutorial.id);
    expect(persisted.guides[tutorial.id]).toEqual({
      contentVersion: tutorial.version,
      lastStepId: tutorial.steps[1].id,
      status: "completed",
    });
    expect(controller.resume(tutorial.id).lesson).toBe("complete");
  });

  test("accepts a completion deep link because guide completion is informational", () => {
    const tutorial = getTutorialById("included-data-first-analysis");
    const windowLike = browser(
      `?view=gsea&guide=${tutorial.id}&lesson=complete&lang=es`,
    );
    const controller = renderController({ storage: memoryStorage(), windowLike });

    expect(controller.state.lesson).toBe("complete");
    expect(controller.isComplete).toBe(true);
    expect(controller.state).not.toHaveProperty("lang");
  });

  test("survives a blocked localStorage getter and reports ephemeral progress", () => {
    const windowLike = browser();
    Object.defineProperty(windowLike, "localStorage", {
      get() {
        throw new DOMException("Blocked", "SecurityError");
      },
    });
    const controller = renderController({ windowLike });

    expect(controller.persistenceAvailable).toBe(false);
    expect(controller.start("quick-gsea", "overview").lesson).toBe(
      getTutorialById("quick-gsea").steps[0].id,
    );
  });

  test("reports ephemeral progress when storage exists but reads are blocked", () => {
    const storage = {
      getItem() {
        throw new DOMException("Blocked", "SecurityError");
      },
      setItem() {
        throw new DOMException("Blocked", "SecurityError");
      },
    };
    const controller = renderController({ storage, windowLike: browser() });

    expect(controller.persistenceAvailable).toBe(false);
    expect(controller.start("quick-gsea", "overview").lesson).toBe(
      getTutorialById("quick-gsea").steps[0].id,
    );
  });

  test("enters and reviews quick guides at step one without an overview", () => {
    const controller = renderController({
      storage: memoryStorage(),
      windowLike: browser(),
    });
    const tutorial = getTutorialById("quick-gsea");

    const started = controller.start(tutorial.id);
    expect(started.lesson).toBe(tutorial.steps[0].id);
    expect(controller.showOverview().lesson).toBe(tutorial.steps[0].id);
    expect(controller.previous().lesson).toBe(tutorial.steps[0].id);
  });

  test("replaces an open quick guide with the quick guide for a manually selected module", () => {
    const storage = memoryStorage();
    const windowLike = browser("?view=analysis&tab=tutorials");
    const controller = renderController({ storage, windowLike });
    const survival = getTutorialById("quick-analysis");
    const gsea = getTutorialById("quick-gsea");

    controller.start(survival.id, survival.steps[3].id);
    const historyCallsBeforeSwitch = windowLike.history.pushState.mock.calls.length;
    const switched = controller.setView("gsea");

    expect(switched).toMatchObject({
      view: "gsea",
      tab: "tutorials",
      guide: gsea.id,
      lesson: gsea.steps[0].id,
      step: 1,
    });
    expect(windowLike.history.pushState).toHaveBeenLastCalledWith(
      null,
      "",
      expect.stringMatching(
        new RegExp(`view=gsea.*guide=${gsea.id}.*lesson=${gsea.steps[0].id}`),
      ),
    );
    expect(windowLike.history.pushState).toHaveBeenCalledTimes(
      historyCallsBeforeSwitch + 1,
    );

    const persisted = JSON.parse(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY));
    expect(persisted.guides[survival.id].lastStepId).toBe(survival.steps[3].id);
    expect(persisted.guides[gsea.id].lastStepId).toBe(gsea.steps[0].id);
  });

  test.each(["examples", "repository", "summary", "api", "help"])(
    "closes an open quick guide when navigating to unguided view %s",
    (view) => {
      const storage = memoryStorage();
      const windowLike = browser("?view=analysis&tab=tutorials");
      const controller = renderController({ storage, windowLike });
      const survival = getTutorialById("quick-analysis");

      controller.start(survival.id, survival.steps[2].id);
      const switched = controller.setView(view);

      expect(switched).toMatchObject({
        view,
        guide: null,
        lesson: null,
        step: 1,
      });
      expect(windowLike.history.pushState.mock.calls.at(-1)[2]).not.toContain("guide=");
      const persisted = JSON.parse(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY));
      expect(persisted.guides[survival.id]).toMatchObject({
        lastStepId: survival.steps[2].id,
        status: "in_progress",
      });
    },
  );

  test("keeps the guide closed while manually changing modules", () => {
    const windowLike = browser("?view=analysis&tab=tutorials");
    const controller = renderController({ storage: memoryStorage(), windowLike });

    const switched = controller.setView("gsea");

    expect(switched).toMatchObject({
      view: "gsea",
      guide: null,
      lesson: null,
      step: 1,
    });
    expect(windowLike.history.pushState.mock.calls.at(-1)[2]).not.toContain("guide=");
  });

  test.each([
    ["route", "groups-to-pathways", "primary-evidence", "diagnostics", "gsea"],
    ["fixed teaching case", "example-gsea-direction", "context", "design", "examples"],
  ])(
    "keeps a %s active when its own step navigation changes context",
    (_kind, guideId, fromLesson, toLesson, view) => {
      const controller = renderController({
        storage: memoryStorage(),
        windowLike: browser(`?view=expression&guide=${guideId}&lesson=${fromLesson}`),
      });

      const next = controller.next();

      expect(next).toMatchObject({
        view,
        guide: guideId,
        lesson: toLesson,
      });
      expect(next.guide).not.toBe(`quick-${view}`);
    },
  );

  test("retains the overview for full routes and fixed teaching cases", () => {
    const controller = renderController({
      storage: memoryStorage(),
      windowLike: browser(),
    });

    expect(controller.start("groups-to-pathways").lesson).toBe("overview");
    expect(controller.start("example-gsea-direction").lesson).toBe("overview");
  });

  test("keeps fixed-example navigation and completion out of persistent progress", () => {
    const storage = memoryStorage();
    const windowLike = browser();
    const controller = renderController({ storage, windowLike });
    const fixed = getTutorialById("example-gsea-direction");

    controller.start(fixed.id, fixed.steps[0].id);
    const completedState = controller.complete();

    expect(completedState.lesson).toBe("complete");
    expect(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY)).toBeNull();
    const historyCalls = windowLike.history.pushState.mock.calls.length;
    expect(controller.resume(fixed.id).guide).toBe(fixed.id);
    expect(windowLike.history.pushState).toHaveBeenCalledTimes(historyCalls);
  });

  test("uses presentation-only preferences even when a legacy language is supplied", () => {
    const storage = memoryStorage();
    saveTutorialPreferences(storage, { lang: "es", presentation: "mini" });
    const controller = renderController({
      storage,
      windowLike: browser("?lang=es"),
    });

    expect(controller.state).not.toHaveProperty("lang");
    expect(controller.preferences).toEqual({
      schemaVersion: 2,
      presentation: "mini",
    });
    expect(controller.presentation).toBe("mini");
  });

  test("opens the Learning Center with one atomic history transition", () => {
    const storage = memoryStorage();
    const windowLike = browser(
      "?view=gsea&guide=quick-gsea&lesson=orient&lang=es&tab=tutorials",
    );
    const controller = renderController({ storage, windowLike });
    const callsBefore = windowLike.history.pushState.mock.calls.length;

    const next = controller.openLearningCenter();
    expect(next).toMatchObject({
      view: "examples",
      tab: "tutorials",
      guide: null,
      lesson: null,
    });
    expect(windowLike.history.pushState).toHaveBeenCalledTimes(callsBefore + 1);
    expect(windowLike.history.pushState.mock.calls.at(-1)[2]).not.toContain("lang=");

    controller.openLearningCenter();
    expect(windowLike.history.pushState).toHaveBeenCalledTimes(callsBefore + 1);
  });
});
