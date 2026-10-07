import { describe, expect, test } from "vitest";
import {
  APP_MODULES,
  APP_NAV_GROUPS,
  APP_NAV_HOME,
} from "./moduleRegistry";

describe("workspace navigation intent groups", () => {
  test("keeps Home first and exposes every global destination once", () => {
    const groupedIds = APP_NAV_GROUPS.flatMap((group) => (
      group.items.map((item) => item.id)
    ));
    const expectedIds = APP_MODULES
      .map((module) => module.id)
      .filter((id) => !["home", "session"].includes(id));

    expect(APP_NAV_HOME.id).toBe("home");
    expect(groupedIds).toHaveLength(new Set(groupedIds).size);
    expect(new Set(groupedIds)).toEqual(new Set(expectedIds));
    expect(groupedIds).not.toContain("session");
    expect(APP_MODULES.some((module) => module.id === "session")).toBe(true);
  });

  test("uses the three researcher-intent labels in the paper release", () => {
    expect(APP_NAV_GROUPS.map((group) => group.label)).toEqual([
      "Analyze",
      "Evidence",
      "Learn & connect",
    ]);
  });
});
