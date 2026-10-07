import { getTutorialById } from "./curriculum";
import {
  TUTORIAL_HUB_TABS,
  TUTORIAL_MODULE_ORDER,
} from "./catalog";

export const TUTORIAL_QUERY_KEYS = Object.freeze([
  "view",
  "guide",
  "lesson",
  "step",
  "tab",
]);

export const TUTORIAL_LESSON_OVERVIEW = "overview";
export const TUTORIAL_LESSON_COMPLETE = "complete";
export const LEGACY_SIGNATURE_SCORING_GUIDE_HASH =
  "#trace-guide-methods-signature-scoring";

export function tutorialEntryLesson(tutorial) {
  if (tutorial?.type === "quick") {
    return tutorial.steps[0]?.id || TUTORIAL_LESSON_OVERVIEW;
  }
  return TUTORIAL_LESSON_OVERVIEW;
}

export const DEFAULT_TUTORIAL_URL_STATE = Object.freeze({
  view: "home",
  tab: "tutorials",
  guide: null,
  lesson: null,
  step: 1,
});

function tutorialTab(tutorial) {
  return tutorial ? "tutorials" : DEFAULT_TUTORIAL_URL_STATE.tab;
}

function legacyStepNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const numericStep = Number(value);
  return Number.isInteger(numericStep) ? numericStep : null;
}

function normalizeLesson(tutorial, lessonValue, stepValue) {
  if (!tutorial) return { lesson: null, step: 1 };
  const lesson = String(lessonValue || "").trim();
  if (lesson === TUTORIAL_LESSON_OVERVIEW) {
    return { lesson: tutorialEntryLesson(tutorial), step: 1 };
  }
  if (lesson === TUTORIAL_LESSON_COMPLETE) {
    return { lesson, step: tutorial.steps.length };
  }
  const lessonIndex = tutorial.steps.findIndex((item) => item.id === lesson);
  if (lessonIndex >= 0) {
    return { lesson, step: lessonIndex + 1 };
  }
  const numericStep = legacyStepNumber(stepValue);
  if (numericStep !== null) {
    const step = Math.min(Math.max(numericStep, 1), tutorial.steps.length);
    return { lesson: tutorial.steps[step - 1].id, step };
  }
  return { lesson: tutorialEntryLesson(tutorial), step: 1 };
}

export function normalizeTutorialUrlState(value = {}) {
  const requestedView = TUTORIAL_MODULE_ORDER.includes(value.view)
    ? value.view
    : DEFAULT_TUTORIAL_URL_STATE.view;
  const requestedTab = TUTORIAL_HUB_TABS.includes(value.tab)
    ? value.tab
    : DEFAULT_TUTORIAL_URL_STATE.tab;
  const guide = String(value.guide || "").trim() || null;
  const tutorial = guide ? getTutorialById(guide) : null;
  const location = normalizeLesson(tutorial, value.lesson, value.step);
  return {
    view: requestedView,
    tab: tutorial ? tutorialTab(tutorial) : requestedTab,
    guide: tutorial?.id || null,
    lesson: tutorial ? location.lesson : null,
    step: tutorial ? location.step : 1,
  };
}

export function readTutorialUrlState(locationLike = {}) {
  const params = new URLSearchParams(locationLike.search || "");
  return normalizeTutorialUrlState({
    view: params.get("view"),
    tab: params.get("tab"),
    guide: params.get("guide"),
    lesson: params.get("lesson"),
    step: params.get("step"),
  });
}

export function legacyStaticMethodsHref(locationLike = {}, basePath = "/") {
  let hash = String(locationLike.hash || "");
  try {
    hash = decodeURIComponent(hash);
  } catch {
    // Leave malformed legacy fragments untouched.
  }
  if (hash !== LEGACY_SIGNATURE_SCORING_GUIDE_HASH) return null;
  const params = new URLSearchParams(locationLike.search || "");
  if (params.get("view") === "help") return null;
  const normalizedBase = `/${String(basePath || "/")}`
    .replace(/\/{2,}/g, "/")
    .replace(/\/?$/, "/");
  return `${normalizedBase}methods/signature-scoring/`;
}

export function buildTutorialHref(locationLike = {}, state = {}) {
  const normalized = normalizeTutorialUrlState(state);
  const params = new URLSearchParams(locationLike.search || "");
  params.set("view", normalized.view);
  // `lang` belonged to the former bilingual Guides UI. Remove it while
  // preserving unrelated query parameters and hashes in legacy links.
  params.delete("lang");
  params.set("tab", normalized.tab);
  if (normalized.guide) {
    params.set("guide", normalized.guide);
    params.set("lesson", normalized.lesson);
    params.delete("step");
  } else {
    params.delete("guide");
    params.delete("lesson");
    params.delete("step");
  }
  const search = params.toString();
  return `${locationLike.pathname || "/"}${search ? `?${search}` : ""}${locationLike.hash || ""}`;
}

export function writeTutorialUrl(windowLike, state, { replace = false } = {}) {
  if (!windowLike?.history || !windowLike?.location) return null;
  const href = buildTutorialHref(windowLike.location, state);
  const currentHref = `${windowLike.location.pathname || "/"}${windowLike.location.search || ""}${windowLike.location.hash || ""}`;
  if (href === currentHref) return href;
  const method = replace ? "replaceState" : "pushState";
  windowLike.history[method](null, "", href);
  return href;
}

export function subscribeToTutorialPopstate(windowLike, listener) {
  if (!windowLike?.addEventListener || !windowLike?.removeEventListener) {
    return () => {};
  }
  const handlePopstate = () => listener(readTutorialUrlState(windowLike.location));
  windowLike.addEventListener("popstate", handlePopstate);
  return () => windowLike.removeEventListener("popstate", handlePopstate);
}
