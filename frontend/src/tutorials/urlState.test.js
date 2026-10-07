import { describe, expect, test, vi } from "vitest";
import { getTutorialById } from "./curriculum";
import { transitionTutorialState } from "./tutorialState";
import {
  DEFAULT_TUTORIAL_URL_STATE,
  buildTutorialHref,
  legacyStaticMethodsHref,
  readTutorialUrlState,
  subscribeToTutorialPopstate,
  writeTutorialUrl,
} from "./urlState";

describe("tutorial deep-link state", () => {
  test("redirects the retired signature-scoring guide anchor to the static method page", () => {
    expect(legacyStaticMethodsHref({
      pathname: "/tcga_explorer/",
      search: "?tab=tutorials&view=home",
      hash: "#trace-guide-methods-signature-scoring",
    }, "/tcga_explorer/")).toBe(
      "/tcga_explorer/methods/signature-scoring/",
    );
    expect(legacyStaticMethodsHref({ hash: "#unrelated" }, "/tcga_explorer/"))
      .toBeNull();
  });

  test("keeps the signature-scoring anchor on the canonical in-app Help route", () => {
    expect(legacyStaticMethodsHref({
      pathname: "/tcga_explorer/",
      search: "?view=help",
      hash: "#trace-guide-methods-signature-scoring",
    }, "/tcga_explorer/")).toBeNull();
    expect(readTutorialUrlState({ search: "?view=help" }).view).toBe("help");
  });

  test("defaults to Home with no open guide or language state", () => {
    expect(DEFAULT_TUTORIAL_URL_STATE).toEqual({
      view: "home",
      tab: "tutorials",
      guide: null,
      lesson: null,
      step: 1,
    });
  });

  test("ignores legacy language parameters and exposes no language state", () => {
    const state = readTutorialUrlState({ search: "?view=gsea&lang=es" });
    expect(state.view).toBe("gsea");
    expect(state).not.toHaveProperty("lang");
  });

  test("reads the canonical stable lesson id", () => {
    const state = readTutorialUrlState({
      search: "?view=gsea&guide=groups-to-pathways&lesson=error-lab&lang=es&tab=tutorials",
    });
    expect(state).toEqual({
      view: "gsea",
      tab: "tutorials",
      guide: "groups-to-pathways",
      lesson: "error-lab",
      step: 6,
    });
  });

  test("maps a legacy one-based step to a stable lesson id", () => {
    const tutorial = getTutorialById("groups-to-pathways");
    const state = readTutorialUrlState({
      search: "?view=gsea&guide=groups-to-pathways&step=99",
    });
    expect(state).toMatchObject({
      guide: tutorial.id,
      lesson: tutorial.steps.at(-1).id,
      step: tutorial.steps.length,
    });
  });

  test("opens quick guides on their first stable lesson for empty and legacy overview entries", () => {
    const tutorial = getTutorialById("quick-gsea");

    for (const search of [
      `?view=gsea&guide=${tutorial.id}`,
      `?view=gsea&guide=${tutorial.id}&lesson=overview`,
    ]) {
      expect(readTutorialUrlState({ search })).toMatchObject({
        guide: tutorial.id,
        lesson: tutorial.steps[0].id,
        step: 1,
      });
    }

    const started = transitionTutorialState(DEFAULT_TUTORIAL_URL_STATE, {
      type: "start",
      guide: tutorial.id,
    });
    expect(started.lesson).toBe(tutorial.steps[0].id);
    expect(transitionTutorialState(started, { type: "show-overview" }).lesson)
      .toBe(tutorial.steps[0].id);
    expect(transitionTutorialState(started, { type: "previous" })).toEqual(started);
  });

  test.each(["examples", "repository", "summary", "api", "help"])(
    "canonicalizes the retired quick guide for %s to the unguided page",
    (view) => {
      const location = {
        pathname: "/tcga_explorer/",
        search: `?view=${view}&guide=quick-${view}&lesson=interpret&tab=tutorials`,
        hash: "",
      };
      const state = readTutorialUrlState(location);

      expect(state).toMatchObject({
        view,
        guide: null,
        lesson: null,
        step: 1,
      });
      const href = buildTutorialHref(location, state);
      expect(href).toContain(`view=${view}`);
      expect(href).not.toContain("guide=");
      expect(href).not.toContain("lesson=");
    },
  );

  test("keeps an overview entry for full routes and fixed teaching cases", () => {
    for (const guide of ["groups-to-pathways", "example-gsea-direction"]) {
      const tutorial = getTutorialById(guide);
      const started = transitionTutorialState(DEFAULT_TUTORIAL_URL_STATE, {
        type: "start",
        guide: tutorial.id,
      });
      expect(started).toMatchObject({
        guide: tutorial.id,
        lesson: "overview",
        step: 1,
      });
    }
  });

  test("writes canonical lesson URLs and preserves unrelated parameters and hash", () => {
    const href = buildTutorialHref(
      { pathname: "/tcga_explorer/", search: "?cohort=TCGA-BRCA&step=2", hash: "#result" },
      {
        view: "expression",
        tab: "tutorials",
        guide: "groups-to-pathways",
        lesson: "primary-evidence",
      },
    );
    expect(href).toContain("cohort=TCGA-BRCA");
    expect(href).toContain("view=expression");
    expect(href).toContain("guide=groups-to-pathways");
    expect(href).toContain("lesson=primary-evidence");
    expect(href).not.toMatch(/[?&]step=/);
    expect(href).not.toMatch(/[?&]lang=/);
    expect(href).toContain("tab=tutorials");
    expect(href.endsWith("#result")).toBe(true);
  });

  test("moves through overview, steps and completion while opening each module", () => {
    const tutorial = getTutorialById("groups-to-pathways");
    let state = transitionTutorialState(DEFAULT_TUTORIAL_URL_STATE, {
      type: "start",
      guide: tutorial.id,
    });
    expect(state).toMatchObject({
      view: tutorial.steps[0].openView,
      lesson: "overview",
      step: 1,
    });

    state = transitionTutorialState(state, { type: "next" });
    expect(state.lesson).toBe(tutorial.steps[0].id);
    state = transitionTutorialState(state, { type: "set-step", step: 5 });
    expect(state).toMatchObject({
      view: tutorial.steps[4].openView,
      lesson: tutorial.steps[4].id,
      step: 5,
    });
    state = transitionTutorialState(state, { type: "set-lesson", lesson: tutorial.steps.at(-1).id });
    state = transitionTutorialState(state, { type: "next" });
    expect(state.lesson).toBe("complete");
    state = transitionTutorialState(state, { type: "previous" });
    expect(state.lesson).toBe(tutorial.steps.at(-1).id);
    state = transitionTutorialState(state, { type: "show-overview" });
    expect(state.lesson).toBe("overview");
  });

  test("removes legacy Spanish mode while preserving unrelated parameters and hash", () => {
    const href = buildTutorialHref(
      {
        pathname: "/tcga_explorer/",
        search: "?cohort=TCGA-BRCA&lang=es&view=gsea",
        hash: "#result",
      },
      {
        view: "gsea",
        tab: "tutorials",
        guide: "quick-gsea",
        lesson: "dataset",
      },
    );
    expect(href).toContain("cohort=TCGA-BRCA");
    expect(href).not.toMatch(/[?&]lang=/);
    expect(href).toContain("guide=quick-gsea");
    expect(href.endsWith("#result")).toBe(true);
  });

  test("keeps a guide open when app navigation changes independently", () => {
    const fixed = transitionTutorialState(DEFAULT_TUTORIAL_URL_STATE, {
      type: "start",
      guide: "example-gsea-direction",
      step: 2,
    });
    expect(fixed).toMatchObject({
      view: "examples",
      lesson: "design",
      step: 2,
    });
    const navigated = transitionTutorialState(fixed, { type: "set-view", view: "help" });
    expect(navigated).toMatchObject({
      view: "help",
      guide: "example-gsea-direction",
      lesson: "design",
      step: 2,
      tab: "tutorials",
    });
  });

  test("writes history and restores canonical state through popstate", () => {
    let listener;
    const windowLike = {
      location: { pathname: "/tcga_explorer/", search: "", hash: "" },
      history: { pushState: vi.fn(), replaceState: vi.fn() },
      addEventListener: vi.fn((name, callback) => { if (name === "popstate") listener = callback; }),
      removeEventListener: vi.fn(),
    };
    const href = writeTutorialUrl(windowLike, {
      view: "gsea",
      tab: "tutorials",
      guide: "groups-to-pathways",
      lesson: "error-lab",
    });
    expect(href).toContain("view=gsea");
    expect(href).toContain("lesson=error-lab");
    expect(windowLike.history.pushState).toHaveBeenCalledWith(null, "", href);

    const observed = vi.fn();
    const unsubscribe = subscribeToTutorialPopstate(windowLike, observed);
    windowLike.location.search = "?view=compare&guide=robustness-multiplicity&lesson=eligibility&lang=es&tab=tutorials";
    listener();
    expect(observed).toHaveBeenCalledWith(expect.objectContaining({
      view: "compare",
      guide: "robustness-multiplicity",
      lesson: "eligibility",
      step: 2,
    }));
    unsubscribe();
    expect(windowLike.removeEventListener).toHaveBeenCalledWith("popstate", listener);
  });
});
