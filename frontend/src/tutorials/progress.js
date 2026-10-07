import { getTutorialById } from "./curriculum";

export const TUTORIAL_PROGRESS_SCHEMA_VERSION = 3;
export const TUTORIAL_PROGRESS_STORAGE_KEY = "trace-learning-progress-v3";
export const LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY = "trace-learning-progress-v2";
export const LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY = "trace-learning-progress-v1";
export const LEGACY_TUTORIAL_CONTENT_VERSIONS = Object.freeze(["1.0.0", "3.1.0"]);
export const TUTORIAL_PROGRESS_FIELDS = Object.freeze([
  "schemaVersion",
  "activeGuideId",
  "guides",
]);
export const TUTORIAL_GUIDE_PROGRESS_FIELDS = Object.freeze([
  "contentVersion",
  "lastStepId",
  "status",
]);

export const TUTORIAL_PREFERENCES_SCHEMA_VERSION = 2;
export const TUTORIAL_PREFERENCES_STORAGE_KEY = "trace-learning-preferences-v2";
export const LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY = "trace-learning-preferences-v1";
export const TUTORIAL_PREFERENCE_FIELDS = Object.freeze([
  "schemaVersion",
  "presentation",
]);
export const TUTORIAL_PRESENTATIONS = Object.freeze(["auto", "mini"]);

export const DEFAULT_TUTORIAL_PREFERENCES = Object.freeze({
  schemaVersion: TUTORIAL_PREFERENCES_SCHEMA_VERSION,
  presentation: "auto",
});

function emptyTutorialProgress() {
  return {
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: null,
    guides: {},
  };
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function tutorialForProgress(tutorialId) {
  const id = String(tutorialId || "").trim();
  const tutorial = id ? getTutorialById(id) : null;
  return tutorial?.mode === "live" ? tutorial : null;
}

function sanitizeGuideProgress(tutorial, value, { acceptLegacyVersion = false } = {}) {
  if (!isRecord(value)) return null;
  if (!acceptLegacyVersion && value.contentVersion !== tutorial.version) return null;
  const stepIds = tutorial.steps.map((step) => step.id);
  if (stepIds.length === 0) return null;
  const requestedStepId = String(value.lastStepId || "").trim();
  return {
    contentVersion: tutorial.version,
    lastStepId: stepIds.includes(requestedStepId) ? requestedStepId : stepIds[0],
    status: value.status === "completed" ? "completed" : "in_progress",
  };
}

function sanitizeProgressRecord(value, {
  schemaVersion = TUTORIAL_PROGRESS_SCHEMA_VERSION,
  acceptLegacyVersion = false,
} = {}) {
  if (!isRecord(value) || value.schemaVersion !== schemaVersion || !isRecord(value.guides)) {
    return null;
  }
  const guides = {};
  for (const [tutorialId, guideProgress] of Object.entries(value.guides)) {
    const tutorial = tutorialForProgress(tutorialId);
    if (!tutorial) continue;
    const sanitized = sanitizeGuideProgress(tutorial, guideProgress, { acceptLegacyVersion });
    if (sanitized) guides[tutorial.id] = sanitized;
  }
  const requestedActiveGuideId = String(value.activeGuideId || "").trim();
  return {
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: Object.prototype.hasOwnProperty.call(guides, requestedActiveGuideId)
      ? requestedActiveGuideId
      : null,
    guides,
  };
}

export function sanitizeTutorialProgress(value) {
  return sanitizeProgressRecord(value);
}

export function sanitizeTutorialPreferences(value) {
  const source = isRecord(value) ? value : {};
  return {
    schemaVersion: TUTORIAL_PREFERENCES_SCHEMA_VERSION,
    presentation: TUTORIAL_PRESENTATIONS.includes(source.presentation)
      ? source.presentation
      : DEFAULT_TUTORIAL_PREFERENCES.presentation,
  };
}

function readStoredJson(storage, key) {
  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function removeStoredKey(storage, key) {
  try {
    storage.removeItem?.(key);
  } catch {
    // Migration cleanup is best effort after the new record is durable.
  }
}

export function loadTutorialPreferences(storage) {
  if (!storage?.getItem) return { ...DEFAULT_TUTORIAL_PREFERENCES };
  const stored = readStoredJson(storage, TUTORIAL_PREFERENCES_STORAGE_KEY);
  if (isRecord(stored) && stored.schemaVersion === TUTORIAL_PREFERENCES_SCHEMA_VERSION) {
    return sanitizeTutorialPreferences(stored);
  }

  const legacy = readStoredJson(storage, LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY);
  if (isRecord(legacy)) {
    const migrated = sanitizeTutorialPreferences(legacy);
    if (saveTutorialPreferences(storage, migrated)) {
      removeStoredKey(storage, LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY);
    }
    return migrated;
  }
  return { ...DEFAULT_TUTORIAL_PREFERENCES };
}

export function saveTutorialPreferences(storage, preferences) {
  if (!storage?.setItem) return null;
  const sanitized = sanitizeTutorialPreferences(preferences);
  try {
    storage.setItem(TUTORIAL_PREFERENCES_STORAGE_KEY, JSON.stringify(sanitized));
    return sanitized;
  } catch {
    return null;
  }
}

export function clearTutorialPreferences(storage) {
  if (!storage?.removeItem) return false;
  try {
    storage.removeItem(TUTORIAL_PREFERENCES_STORAGE_KEY);
    storage.removeItem(LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}

export function migrateLegacyTutorialProgress(value) {
  if (!isRecord(value)) return null;
  const tutorial = getTutorialById(String(value.tutorial || ""));
  const migratableVersion = value.version === tutorial?.version
    || LEGACY_TUTORIAL_CONTENT_VERSIONS.includes(value.version);
  if (!tutorial || tutorial.mode !== "live" || !migratableVersion) return null;
  const numericStep = Number(value.step);
  const stepNumber = Number.isInteger(numericStep)
    ? Math.min(Math.max(numericStep, 1), tutorial.steps.length)
    : 1;
  return {
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: tutorial.id,
    guides: {
      [tutorial.id]: {
        contentVersion: tutorial.version,
        lastStepId: tutorial.steps[stepNumber - 1].id,
        status: "in_progress",
      },
    },
  };
}

function migrateV2TutorialProgress(value) {
  return sanitizeProgressRecord(value, {
    schemaVersion: 2,
    acceptLegacyVersion: true,
  });
}

export function loadTutorialProgress(storage) {
  if (!storage?.getItem) return emptyTutorialProgress();

  const stored = sanitizeTutorialProgress(
    readStoredJson(storage, TUTORIAL_PROGRESS_STORAGE_KEY),
  );
  if (stored) return stored;

  const migratedV2 = migrateV2TutorialProgress(
    readStoredJson(storage, LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY),
  );
  if (migratedV2) {
    if (saveTutorialProgress(storage, migratedV2)) {
      removeStoredKey(storage, LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY);
    }
    return migratedV2;
  }

  const migratedV1 = migrateLegacyTutorialProgress(
    readStoredJson(storage, LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY),
  );
  if (migratedV1) {
    if (saveTutorialProgress(storage, migratedV1)) {
      removeStoredKey(storage, LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY);
    }
    return migratedV1;
  }
  return emptyTutorialProgress();
}

export function saveTutorialProgress(storage, progress) {
  if (!storage?.setItem) return null;
  const sanitized = sanitizeTutorialProgress(progress);
  if (!sanitized) return null;
  try {
    storage.setItem(TUTORIAL_PROGRESS_STORAGE_KEY, JSON.stringify(sanitized));
    return sanitized;
  } catch {
    return null;
  }
}

export function updateTutorialGuideProgress(progress, tutorialId, patch = {}) {
  const current = sanitizeTutorialProgress(progress) || emptyTutorialProgress();
  const tutorial = tutorialForProgress(tutorialId);
  if (!tutorial) return current;
  const previous = current.guides[tutorial.id];
  const candidate = {
    contentVersion: tutorial.version,
    lastStepId: patch.lastStepId ?? previous?.lastStepId ?? tutorial.steps[0]?.id,
    status: patch.status ?? previous?.status ?? "in_progress",
  };
  return sanitizeTutorialProgress({
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: patch.setActive === false ? current.activeGuideId : tutorial.id,
    guides: {
      ...current.guides,
      [tutorial.id]: candidate,
    },
  }) || current;
}

export function removeTutorialGuideProgress(progress, tutorialId) {
  const current = sanitizeTutorialProgress(progress) || emptyTutorialProgress();
  const guides = { ...current.guides };
  delete guides[tutorialId];
  return sanitizeTutorialProgress({
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: current.activeGuideId === tutorialId ? null : current.activeGuideId,
    guides,
  }) || emptyTutorialProgress();
}

export function clearTutorialProgress(storage) {
  if (!storage?.removeItem) return false;
  try {
    storage.removeItem(TUTORIAL_PROGRESS_STORAGE_KEY);
    storage.removeItem(LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY);
    storage.removeItem(LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY);
    return true;
  } catch {
    return false;
  }
}
