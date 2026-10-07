import { getTutorialById } from "./curriculum";
import {
  TUTORIAL_LESSON_COMPLETE,
  TUTORIAL_LESSON_OVERVIEW,
  normalizeTutorialUrlState,
  tutorialEntryLesson,
} from "./urlState";

function lessonFromRequest(tutorial, lessonOrStep, fallback = TUTORIAL_LESSON_OVERVIEW) {
  if (lessonOrStep === TUTORIAL_LESSON_OVERVIEW) {
    return tutorialEntryLesson(tutorial);
  }
  if (lessonOrStep === TUTORIAL_LESSON_COMPLETE) {
    return TUTORIAL_LESSON_COMPLETE;
  }
  const requestedId = String(lessonOrStep || "").trim();
  if (tutorial.steps.some((step) => step.id === requestedId)) return requestedId;
  const numericStep = Number(lessonOrStep);
  if (Number.isInteger(numericStep) && numericStep >= 1) {
    const step = Math.min(numericStep, tutorial.steps.length);
    return tutorial.steps[step - 1].id;
  }
  return fallback === TUTORIAL_LESSON_OVERVIEW
    ? tutorialEntryLesson(tutorial)
    : fallback;
}

function stepForLesson(tutorial, lesson) {
  if (lesson === TUTORIAL_LESSON_COMPLETE) return tutorial.steps.at(-1) || null;
  if (lesson === TUTORIAL_LESSON_OVERVIEW) return tutorial.steps[0] || null;
  return tutorial.steps.find((step) => step.id === lesson) || tutorial.steps[0] || null;
}

function stateForLesson(state, tutorial, lessonOrStep, fallback) {
  const lesson = lessonFromRequest(tutorial, lessonOrStep, fallback);
  const targetStep = stepForLesson(tutorial, lesson);
  return normalizeTutorialUrlState({
    ...state,
    guide: tutorial.id,
    lesson,
    step: null,
    view: targetStep?.openView || state.view,
    tab: "tutorials",
  });
}

function currentStepIndex(tutorial, state) {
  return tutorial.steps.findIndex((step) => step.id === state.lesson);
}

export function transitionTutorialState(current, action) {
  const state = normalizeTutorialUrlState(current);
  switch (action.type) {
    case "popstate":
      return normalizeTutorialUrlState(action.state);
    case "set-tab":
      return normalizeTutorialUrlState({
        ...state,
        tab: action.tab,
        guide: null,
        lesson: null,
        step: 1,
      });
    case "open-learning-center":
      return normalizeTutorialUrlState({
        ...state,
        view: "examples",
        tab: "tutorials",
        guide: null,
        lesson: null,
        step: 1,
      });
    case "set-view": {
      const currentTutorial = state.guide ? getTutorialById(state.guide) : null;
      const contextualTutorial = currentTutorial?.type === "quick"
        ? getTutorialById(`quick-${action.view}`)
        : null;
      if (contextualTutorial && contextualTutorial.id !== currentTutorial.id) {
        return stateForLesson(
          { ...state, view: action.view },
          contextualTutorial,
          TUTORIAL_LESSON_OVERVIEW,
          TUTORIAL_LESSON_OVERVIEW,
        );
      }
      if (currentTutorial?.type === "quick" && !contextualTutorial) {
        return normalizeTutorialUrlState({
          ...state,
          view: action.view,
          guide: null,
          lesson: null,
          step: 1,
        });
      }
      return normalizeTutorialUrlState({ ...state, view: action.view });
    }
    case "start": {
      const tutorial = getTutorialById(action.guide);
      if (!tutorial) return state;
      const requestedLesson = action.lesson ?? action.step ?? TUTORIAL_LESSON_OVERVIEW;
      return stateForLesson(
        state,
        tutorial,
        requestedLesson,
        TUTORIAL_LESSON_OVERVIEW,
      );
    }
    case "show-overview": {
      const tutorial = state.guide ? getTutorialById(state.guide) : null;
      return tutorial
        ? stateForLesson(state, tutorial, TUTORIAL_LESSON_OVERVIEW)
        : state;
    }
    case "set-lesson":
    case "set-step": {
      const tutorial = state.guide ? getTutorialById(state.guide) : null;
      const requestedLesson = action.lesson ?? action.step;
      return tutorial
        ? stateForLesson(state, tutorial, requestedLesson, state.lesson)
        : state;
    }
    case "previous": {
      const tutorial = state.guide ? getTutorialById(state.guide) : null;
      if (!tutorial || state.lesson === TUTORIAL_LESSON_OVERVIEW) return state;
      if (state.lesson === TUTORIAL_LESSON_COMPLETE) {
        return stateForLesson(state, tutorial, tutorial.steps.at(-1)?.id, state.lesson);
      }
      const index = currentStepIndex(tutorial, state);
      return index <= 0
        ? stateForLesson(state, tutorial, TUTORIAL_LESSON_OVERVIEW)
        : stateForLesson(state, tutorial, tutorial.steps[index - 1].id, state.lesson);
    }
    case "next": {
      const tutorial = state.guide ? getTutorialById(state.guide) : null;
      if (!tutorial || state.lesson === TUTORIAL_LESSON_COMPLETE) return state;
      if (state.lesson === TUTORIAL_LESSON_OVERVIEW) {
        return stateForLesson(state, tutorial, tutorial.steps[0]?.id, state.lesson);
      }
      const index = currentStepIndex(tutorial, state);
      return index < 0 || index === tutorial.steps.length - 1
        ? stateForLesson(state, tutorial, TUTORIAL_LESSON_COMPLETE, state.lesson)
        : stateForLesson(state, tutorial, tutorial.steps[index + 1].id, state.lesson);
    }
    case "complete": {
      const tutorial = state.guide ? getTutorialById(state.guide) : null;
      return tutorial
        ? stateForLesson(state, tutorial, TUTORIAL_LESSON_COMPLETE, state.lesson)
        : state;
    }
    case "close":
      return normalizeTutorialUrlState({
        ...state,
        guide: null,
        lesson: null,
        step: 1,
      });
    default:
      return state;
  }
}
