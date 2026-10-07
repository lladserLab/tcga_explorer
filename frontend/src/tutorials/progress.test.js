import { describe, expect, test } from "vitest";
import { getTutorialById } from "./curriculum";
import {
  DEFAULT_TUTORIAL_PREFERENCES,
  LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY,
  LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY,
  LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY,
  TUTORIAL_GUIDE_PROGRESS_FIELDS,
  TUTORIAL_PREFERENCE_FIELDS,
  TUTORIAL_PREFERENCES_SCHEMA_VERSION,
  TUTORIAL_PREFERENCES_STORAGE_KEY,
  TUTORIAL_PROGRESS_FIELDS,
  TUTORIAL_PROGRESS_SCHEMA_VERSION,
  TUTORIAL_PROGRESS_STORAGE_KEY,
  loadTutorialPreferences,
  loadTutorialProgress,
  saveTutorialPreferences,
  saveTutorialProgress,
  updateTutorialGuideProgress,
} from "./progress";

function memoryStorage(initial = {}, failSetKey = null) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      if (key === failSetKey) throw new Error("storage unavailable");
      values.set(key, value);
    },
    removeItem: (key) => values.delete(key),
  };
}

function emptyProgress() {
  return {
    schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
    activeGuideId: null,
    guides: {},
  };
}

describe("tutorial local progress", () => {
  test("persists only navigation status through the v3 scientific-data-free allowlist", () => {
    const storage = memoryStorage();
    const route = getTutorialById("own-data");
    const quick = getTutorialById("quick-gsea");
    let progress = updateTutorialGuideProgress(emptyProgress(), route.id, {
      lastStepId: route.steps[4].id,
      checkpointId: "legacy-checkpoint-must-be-ignored",
      completedCheckpointIds: ["legacy-checkpoint-must-be-ignored"],
    });
    progress = updateTutorialGuideProgress(progress, quick.id, {
      lastStepId: quick.steps[1].id,
      status: "completed",
    });
    progress.dataset = "must not persist";
    progress.guides[quick.id].result = { hazardRatio: 1.4 };
    progress.guides[quick.id].completedCheckpointIds = ["must-not-persist"];

    const saved = saveTutorialProgress(storage, progress);
    const raw = JSON.parse(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY));

    expect(TUTORIAL_PROGRESS_SCHEMA_VERSION).toBe(3);
    expect(Object.keys(raw)).toEqual(TUTORIAL_PROGRESS_FIELDS);
    expect(Object.keys(raw.guides[route.id])).toEqual(TUTORIAL_GUIDE_PROGRESS_FIELDS);
    expect(Object.keys(raw.guides[quick.id])).toEqual(TUTORIAL_GUIDE_PROGRESS_FIELDS);
    expect(raw.activeGuideId).toBe(quick.id);
    expect(raw.guides[route.id]).toEqual({
      contentVersion: route.version,
      lastStepId: route.steps[4].id,
      status: "in_progress",
    });
    expect(raw.guides[quick.id].status).toBe("completed");
    expect(JSON.stringify(raw)).not.toMatch(/hazardRatio|completedCheckpointIds|checkpoint/i);
    expect(saved).toEqual(raw);
    expect(loadTutorialProgress(storage)).toEqual(raw);
  });

  test("marks a live guide completed without checkpoint evidence", () => {
    const tutorial = getTutorialById("included-data-first-analysis");
    const progress = updateTutorialGuideProgress(emptyProgress(), tutorial.id, {
      lastStepId: tutorial.steps.at(-1).id,
      status: "completed",
    });

    expect(progress.guides[tutorial.id]).toEqual({
      contentVersion: tutorial.version,
      lastStepId: tutorial.steps.at(-1).id,
      status: "completed",
    });
  });

  test("drops fixed, retired, stale and unknown guides while normalizing an invalid lesson", () => {
    const storage = memoryStorage();
    const tutorial = getTutorialById("quick-gsea");
    const fixed = getTutorialById("example-gsea-direction");
    const progress = {
      schemaVersion: TUTORIAL_PROGRESS_SCHEMA_VERSION,
      activeGuideId: fixed.id,
      guides: {
        "missing-guide": {
          contentVersion: "1.0.0",
          lastStepId: "orient",
          status: "completed",
        },
        "quick-help": {
          contentVersion: tutorial.version,
          lastStepId: "versions",
          status: "in_progress",
        },
        [tutorial.id]: {
          contentVersion: tutorial.version,
          lastStepId: "missing-step",
          status: "in_progress",
        },
        "own-data": {
          contentVersion: "stale",
          lastStepId: "question",
          status: "completed",
        },
        [fixed.id]: {
          contentVersion: fixed.version,
          lastStepId: fixed.steps[0].id,
          status: "completed",
        },
      },
    };

    const saved = saveTutorialProgress(storage, progress);
    expect(saved.activeGuideId).toBeNull();
    expect(Object.keys(saved.guides)).toEqual([tutorial.id]);
    expect(saved.guides[tutorial.id].lastStepId).toBe(tutorial.steps[0].id);
  });

  test("migrates v2 progress to v3, preserves lessons and status, and drops checkpoints", () => {
    const inProgress = getTutorialById("quick-gsea");
    const completed = getTutorialById("own-data");
    const legacy = {
      schemaVersion: 2,
      activeGuideId: completed.id,
      guides: {
        [inProgress.id]: {
          contentVersion: "3.1.0",
          lastStepId: inProgress.steps[1].id,
          status: "in_progress",
          completedCheckpointIds: ["quick-gsea.groups.checkpoint"],
        },
        [completed.id]: {
          contentVersion: "3.1.0",
          lastStepId: completed.steps.at(-1).id,
          status: "completed",
          completedCheckpointIds: ["legacy-answer-state"],
        },
      },
    };
    const storage = memoryStorage({
      [LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY]: JSON.stringify(legacy),
    });

    const migrated = loadTutorialProgress(storage);

    expect(migrated.schemaVersion).toBe(3);
    expect(migrated.activeGuideId).toBe(completed.id);
    expect(migrated.guides[inProgress.id]).toEqual({
      contentVersion: inProgress.version,
      lastStepId: inProgress.steps[1].id,
      status: "in_progress",
    });
    expect(migrated.guides[completed.id]).toMatchObject({
      contentVersion: completed.version,
      status: "completed",
    });
    expect(JSON.stringify(migrated)).not.toContain("completedCheckpointIds");
    expect(JSON.parse(storage.getItem(TUTORIAL_PROGRESS_STORAGE_KEY))).toEqual(migrated);
    expect(storage.getItem(LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY)).toBeNull();
  });

  test("keeps v2 progress when writing its v3 migration fails", () => {
    const tutorial = getTutorialById("quick-gsea");
    const legacy = JSON.stringify({
      schemaVersion: 2,
      activeGuideId: tutorial.id,
      guides: {
        [tutorial.id]: {
          contentVersion: "3.1.0",
          lastStepId: tutorial.steps[1].id,
          status: "in_progress",
          completedCheckpointIds: [],
        },
      },
    });
    const storage = memoryStorage(
      { [LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY]: legacy },
      TUTORIAL_PROGRESS_STORAGE_KEY,
    );

    const migrated = loadTutorialProgress(storage);

    expect(migrated.guides[tutorial.id].lastStepId).toBe(tutorial.steps[1].id);
    expect(storage.getItem(LEGACY_TUTORIAL_PROGRESS_V2_STORAGE_KEY)).toBe(legacy);
  });

  test("migrates v1 numeric progress once and discards its former language", () => {
    const tutorial = getTutorialById("own-data");
    const storage = memoryStorage({
      [LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY]: JSON.stringify({
        tutorial: tutorial.id,
        version: "1.0.0",
        step: 5,
        lang: "es",
        dataset: "must not migrate",
      }),
    });

    const migrated = loadTutorialProgress(storage);

    expect(migrated.activeGuideId).toBe(tutorial.id);
    expect(migrated.guides[tutorial.id]).toEqual({
      contentVersion: tutorial.version,
      lastStepId: tutorial.steps[4].id,
      status: "in_progress",
    });
    expect(JSON.stringify(migrated)).not.toContain("lang");
    expect(storage.getItem(LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY)).toBeNull();
  });

  test("does not delete v1 when writing the migrated v3 record fails", () => {
    const tutorial = getTutorialById("quick-gsea");
    const legacy = JSON.stringify({
      tutorial: tutorial.id,
      version: "1.0.0",
      step: 99,
      lang: "es",
    });
    const storage = memoryStorage(
      { [LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY]: legacy },
      TUTORIAL_PROGRESS_STORAGE_KEY,
    );

    const migrated = loadTutorialProgress(storage);

    expect(migrated.guides[tutorial.id].lastStepId).toBe(tutorial.steps.at(-1).id);
    expect(storage.getItem(LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY)).toBe(legacy);
  });

  test("does not migrate an unknown v1 content version", () => {
    const tutorial = getTutorialById("quick-gsea");
    const legacy = JSON.stringify({
      tutorial: tutorial.id,
      version: "0.4.0",
      step: 2,
      lang: "es",
    });
    const storage = memoryStorage({
      [LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY]: legacy,
    });

    expect(loadTutorialProgress(storage)).toEqual(emptyProgress());
    expect(storage.getItem(LEGACY_TUTORIAL_PROGRESS_STORAGE_KEY)).toBe(legacy);
  });

  test("stores only presentation in v2 preferences", () => {
    const storage = memoryStorage();
    const saved = saveTutorialPreferences(storage, {
      lang: "es",
      presentation: "mini",
      dataset: "must not persist",
      lastResult: { nes: 2.1 },
    });
    const raw = JSON.parse(storage.getItem(TUTORIAL_PREFERENCES_STORAGE_KEY));

    expect(TUTORIAL_PREFERENCES_SCHEMA_VERSION).toBe(2);
    expect(Object.keys(raw)).toEqual(TUTORIAL_PREFERENCE_FIELDS);
    expect(saved).toEqual({ schemaVersion: 2, presentation: "mini" });
    expect(raw).toEqual(saved);
    expect(JSON.stringify(raw)).not.toContain("lang");
    expect(loadTutorialPreferences(storage)).toEqual(saved);
    expect(loadTutorialPreferences(memoryStorage())).toEqual(DEFAULT_TUTORIAL_PREFERENCES);
  });

  test("migrates v1 preferences without carrying language into the new record", () => {
    const legacy = JSON.stringify({
      schemaVersion: 1,
      lang: "es",
      presentation: "mini",
    });
    const storage = memoryStorage({
      [LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY]: legacy,
    });

    const migrated = loadTutorialPreferences(storage);

    expect(migrated).toEqual({ schemaVersion: 2, presentation: "mini" });
    expect(JSON.parse(storage.getItem(TUTORIAL_PREFERENCES_STORAGE_KEY))).toEqual(migrated);
    expect(storage.getItem(LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY)).toBeNull();
  });

  test("keeps v1 preferences when writing their v2 migration fails", () => {
    const legacy = JSON.stringify({
      schemaVersion: 1,
      lang: "es",
      presentation: "mini",
    });
    const storage = memoryStorage(
      { [LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY]: legacy },
      TUTORIAL_PREFERENCES_STORAGE_KEY,
    );

    expect(loadTutorialPreferences(storage)).toEqual({
      schemaVersion: 2,
      presentation: "mini",
    });
    expect(storage.getItem(LEGACY_TUTORIAL_PREFERENCES_STORAGE_KEY)).toBe(legacy);
  });
});
