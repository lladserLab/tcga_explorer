import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getTutorialById, getTutorialCurriculum } from "./curriculum";
import {
  loadTutorialPreferences,
  loadTutorialProgress,
  removeTutorialGuideProgress,
  sanitizeTutorialPreferences,
  sanitizeTutorialProgress,
  saveTutorialPreferences,
  saveTutorialProgress,
  TUTORIAL_PROGRESS_STORAGE_KEY,
  updateTutorialGuideProgress,
} from "./progress";
import { transitionTutorialState } from "./tutorialState";
import {
  DEFAULT_TUTORIAL_URL_STATE,
  TUTORIAL_LESSON_COMPLETE,
  TUTORIAL_LESSON_OVERVIEW,
  readTutorialUrlState,
  subscribeToTutorialPopstate,
  writeTutorialUrl,
} from "./urlState";

function defaultBrowserWindow() {
  return typeof window === "undefined" ? null : window;
}

function safeBrowserStorage(windowLike) {
  try {
    return windowLike?.localStorage || null;
  } catch {
    return null;
  }
}

function browserStorageIsReadable(storage) {
  try {
    if (typeof storage?.getItem !== "function" || typeof storage?.setItem !== "function") {
      return false;
    }
    storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

function tutorialUrlNeedsCanonicalization(locationLike, state) {
  if (!locationLike) return false;
  const params = new URLSearchParams(locationLike.search || "");
  if (params.has("lang") || params.has("step")) return true;
  const requestedGuide = String(params.get("guide") || "").trim() || null;
  if (requestedGuide !== state.guide) return true;
  if (state.guide) return params.get("lesson") !== state.lesson;
  return params.has("lesson");
}

export function useTutorialController({
  windowLike = defaultBrowserWindow(),
  storage,
  onViewChange,
} = {}) {
  const resolvedStorage = useMemo(
    () => storage === undefined ? safeBrowserStorage(windowLike) : storage,
    [storage, windowLike],
  );
  const initialSnapshot = useMemo(() => {
    const initialProgress = loadTutorialProgress(resolvedStorage);
    const initialPreferences = loadTutorialPreferences(resolvedStorage);
    const initialState = windowLike?.location
      ? readTutorialUrlState(windowLike.location)
      : { ...DEFAULT_TUTORIAL_URL_STATE };
    return {
      progress: initialProgress,
      preferences: initialPreferences,
      state: initialState,
      urlNeedsCanonicalization: tutorialUrlNeedsCanonicalization(
        windowLike?.location,
        initialState,
      ),
    };
  }, [resolvedStorage, windowLike]);

  const [state, setState] = useState(initialSnapshot.state);
  const [progress, setProgress] = useState(initialSnapshot.progress);
  const [preferences, setPreferences] = useState(initialSnapshot.preferences);
  const stateRef = useRef(initialSnapshot.state);
  const progressRef = useRef(initialSnapshot.progress);
  const preferencesRef = useRef(initialSnapshot.preferences);
  const openTriggerRef = useRef(null);
  const persistenceAvailableRef = useRef(browserStorageIsReadable(resolvedStorage));
  const [persistenceAvailable, setPersistenceAvailable] = useState(
    persistenceAvailableRef.current,
  );

  const markPersistenceUnavailable = useCallback(() => {
    if (!persistenceAvailableRef.current) return;
    persistenceAvailableRef.current = false;
    setPersistenceAvailable(false);
  }, []);

  useEffect(() => {
    if (initialSnapshot.urlNeedsCanonicalization) {
      writeTutorialUrl(windowLike, stateRef.current, { replace: true });
    }
  }, [initialSnapshot.urlNeedsCanonicalization, windowLike]);

  const persistProgress = useCallback((candidate) => {
    const sanitized = sanitizeTutorialProgress(candidate);
    if (!sanitized) return progressRef.current;
    const persisted = saveTutorialProgress(resolvedStorage, sanitized);
    if (!persisted) markPersistenceUnavailable();
    const saved = persisted || sanitized;
    progressRef.current = saved;
    setProgress(saved);
    return saved;
  }, [markPersistenceUnavailable, resolvedStorage]);

  const persistPreferences = useCallback((patch) => {
    const candidate = sanitizeTutorialPreferences({
      ...preferencesRef.current,
      ...patch,
    });
    const persisted = saveTutorialPreferences(resolvedStorage, candidate);
    if (!persisted) markPersistenceUnavailable();
    const saved = persisted || candidate;
    preferencesRef.current = saved;
    setPreferences(saved);
    return saved;
  }, [markPersistenceUnavailable, resolvedStorage]);

  const remember = useCallback((next) => {
    const tutorial = next.guide ? getTutorialById(next.guide) : null;
    if (!tutorial || tutorial.mode !== "live") return progressRef.current;
    const previous = progressRef.current.guides[tutorial.id];
    const activeStep = tutorial.steps.find((item) => item.id === next.lesson);
    const updated = updateTutorialGuideProgress(
      progressRef.current,
      tutorial.id,
      {
        lastStepId: activeStep?.id
          || previous?.lastStepId
          || tutorial.steps[0]?.id,
        status: next.lesson === TUTORIAL_LESSON_COMPLETE
          ? "completed"
          : previous?.status || "in_progress",
      },
    );
    return persistProgress(updated);
  }, [persistProgress]);

  const reconcilePersistedProgress = useCallback(() => {
    if (!persistenceAvailableRef.current || !resolvedStorage?.getItem) {
      return progressRef.current;
    }
    const latestProgress = loadTutorialProgress(resolvedStorage);
    progressRef.current = latestProgress;
    setProgress(latestProgress);
    return latestProgress;
  }, [resolvedStorage]);

  const commit = useCallback((action, options = {}) => {
    const previousState = stateRef.current;
    const previousView = previousState.view;
    const next = transitionTutorialState(previousState, action);
    const unchanged = Object.keys(next).every(
      (key) => next[key] === previousState[key],
    );
    if (unchanged) return previousState;
    stateRef.current = next;
    setState(next);
    writeTutorialUrl(windowLike, next, options);
    if (next.view !== previousView) onViewChange?.(next.view);
    remember(next);
    return next;
  }, [onViewChange, remember, windowLike]);

  useEffect(() => subscribeToTutorialPopstate(windowLike, (next) => {
    // Back/Forward can revive a BFCache snapshot whose React refs predate the
    // latest local progress write. The guide itself remains purely local.
    reconcilePersistedProgress();
    const previousView = stateRef.current.view;
    stateRef.current = next;
    setState(next);
    if (next.view !== previousView) onViewChange?.(next.view);
    if (tutorialUrlNeedsCanonicalization(windowLike?.location, next)) {
      writeTutorialUrl(windowLike, next, { replace: true });
    }
    remember(next);
  }), [onViewChange, reconcilePersistedProgress, remember, windowLike]);

  useEffect(() => {
    if (!windowLike?.addEventListener || !windowLike?.removeEventListener) return undefined;
    const handlePageShow = (event) => {
      if (event?.persisted) reconcilePersistedProgress();
    };
    windowLike.addEventListener("pageshow", handlePageShow);
    return () => windowLike.removeEventListener("pageshow", handlePageShow);
  }, [reconcilePersistedProgress, windowLike]);

  const tutorial = state.guide ? getTutorialById(state.guide) : null;
  const curriculum = getTutorialCurriculum();
  const step = tutorial?.steps.find((item) => item.id === state.lesson) || null;
  const guideProgress = tutorial ? progress.guides[tutorial.id] || null : null;

  const resetGuideProgress = useCallback((guideId) => {
    const targetGuideId = guideId
      || stateRef.current.guide
      || progressRef.current.activeGuideId;
    if (!targetGuideId) return progressRef.current;
    const targetTutorial = getTutorialById(targetGuideId);
    if (!targetTutorial || targetTutorial.mode !== "live") return progressRef.current;
    return persistProgress(
      removeTutorialGuideProgress(progressRef.current, targetGuideId),
    );
  }, [persistProgress]);

  const restart = useCallback((guideId) => {
    const targetGuideId = guideId
      || stateRef.current.guide
      || progressRef.current.activeGuideId;
    if (!targetGuideId) return stateRef.current;
    const targetTutorial = getTutorialById(targetGuideId);
    if (!targetTutorial) return stateRef.current;
    if (targetTutorial.mode === "live") {
      persistProgress(removeTutorialGuideProgress(progressRef.current, targetGuideId));
    }
    return commit({
      type: "start",
      guide: targetGuideId,
      lesson: TUTORIAL_LESSON_OVERVIEW,
    });
  }, [commit, persistProgress]);

  return {
    state,
    curriculum,
    tutorial,
    step,
    progress,
    canResume: Boolean(
      progress.activeGuideId && progress.guides[progress.activeGuideId],
    ),
    preferences,
    presentation: preferences.presentation,
    persistenceAvailable,
    openTriggerRef,
    guideProgress,
    getGuideProgress: (guideId) => progress.guides[guideId] || null,
    isOpen: Boolean(tutorial),
    isOverview: Boolean(tutorial) && state.lesson === TUTORIAL_LESSON_OVERVIEW,
    isComplete: Boolean(tutorial) && state.lesson === TUTORIAL_LESSON_COMPLETE,
    setTab: (tab) => commit({ type: "set-tab", tab }),
    openLearningCenter: () => commit({ type: "open-learning-center" }),
    setView: (view) => commit({ type: "set-view", view }),
    setPresentation: (presentation) => persistPreferences({ presentation }),
    captureTrigger: (element) => {
      if (element?.focus) openTriggerRef.current = element;
    },
    start: (guide, lessonOrStep = TUTORIAL_LESSON_OVERVIEW) => commit({
      type: "start",
      guide,
      lesson: lessonOrStep,
    }),
    resume: (guideId) => {
      const targetGuideId = guideId || progressRef.current.activeGuideId;
      const saved = targetGuideId ? progressRef.current.guides[targetGuideId] : null;
      const targetTutorial = targetGuideId ? getTutorialById(targetGuideId) : null;
      if (!saved || targetTutorial?.mode !== "live") return stateRef.current;
      persistPreferences({ presentation: "auto" });
      return commit({
        type: "start",
        guide: targetGuideId,
        lesson: saved.status === "completed"
          ? TUTORIAL_LESSON_COMPLETE
          : saved.lastStepId,
      });
    },
    showOverview: () => commit({ type: "show-overview" }),
    setLesson: (lesson) => commit({ type: "set-lesson", lesson }),
    setStep: (stepNumber) => commit({ type: "set-step", step: stepNumber }),
    previous: () => commit({ type: "previous" }),
    next: () => commit({ type: "next" }),
    complete: () => commit({ type: "complete" }),
    resetGuideProgress,
    restart,
    close: () => commit({ type: "close" }),
  };
}
