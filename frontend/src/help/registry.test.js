import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

import { TUTORIAL_CONCEPT_IDS } from "../tutorials/conceptRegistry";
import {
  HELP_ENTRIES,
  HELP_ENTRY_IDS,
  HELP_SLOTS,
  getGlossaryTerm,
  getHelpEntry,
  helpProse,
  helpRegistryErrors,
} from "./registry";

const SOURCE_FILES = [
  "../main.jsx",
  "../expression/ExpressionComparisonModule.jsx",
  "../gsea/GseaModule.jsx",
  "../pancancer/HierarchicalPanCancerModule.jsx",
  "../pancancer/PanCancerSignatureMethodPicker.jsx",
  "../repository/RepositoryCatalog.jsx",
];

function source(relativePath) {
  return readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  );
}

const sources = Object.fromEntries(
  SOURCE_FILES.map((path) => [path, source(path)]),
);

describe("help registry contract", () => {
  test("Compare explains its exact grouped family and avoids claims of independence", () => {
    expect(HELP_ENTRIES.compareMultiplicity.does).toContain("selection-corrected");
    expect(HELP_ENTRIES.compareMultiplicity.changes).toContain("excluded from the correction");
    expect(HELP_ENTRIES.compareMultiplicity.safeDefault).toContain("before viewing results");
    expect(HELP_ENTRIES.compareGenes.safeDefault).not.toContain("biologically independent");
  });
  test("Survival copy separates genes, source counts and current versus submitted results", () => {
    expect(HELP_ENTRIES.survivalSingleGenes.does).toContain("not a combined score");
    expect(HELP_ENTRIES.survivalEndpointCounts.does).toContain("before your tissue selection");
    expect(HELP_ENTRIES.survivalAgeDefault.does).toContain("Age is selected by default");
    expect(HELP_ENTRIES.survivalPreviousResult.does).toContain("submitted analysis");
  });
  test("public scale help stays concise and file conversion rules remain beside uploads", () => {
    expect(HELP_ENTRIES.expressionScale.changes).not.toContain("private uploads");
    expect(HELP_ENTRIES.expressionUploadScale.changes).toContain("log2(CPM + 1)");
    expect(HELP_ENTRIES.expressionUploadScale.safeDefault).toContain("incorrect scale");
  });
  test("every entry satisfies the slot contract", () => {
    expect(helpRegistryErrors()).toEqual([]);
  });

  test("every entry carries a term and a does slot", () => {
    for (const entryId of HELP_ENTRY_IDS) {
      const entry = getHelpEntry(entryId);
      expect(entry.term, `${entryId}.term`).toBeTruthy();
      expect(entry.does, `${entryId}.does`).toBeTruthy();
    }
  });

  test("unknown identifiers fail loudly instead of rendering nothing", () => {
    expect(() => getHelpEntry("not-a-real-entry")).toThrow(/Unknown/);
  });

  test("prose joins the slots of one or more entries", () => {
    const single = helpProse("stratification");
    const joined = helpProse(["stratification", "cutpoint.median"]);
    expect(single).toContain(HELP_ENTRIES.stratification.does);
    expect(single).toContain(HELP_ENTRIES.stratification.safeDefault);
    expect(joined.startsWith(single)).toBe(true);
    expect(joined).toContain(HELP_ENTRIES["cutpoint.median"].does);
  });

  test("the glossary resolves English from the tutorial concept registry", () => {
    const concept = getGlossaryTerm("hazard_ratio");
    expect(concept.term).toBe("Hazard ratio");
    expect(concept.definition).toMatch(/instantaneous event rates/);
  });

  test("help copy carries no leftover translated slots", () => {
    for (const [entryId, entry] of Object.entries(HELP_ENTRIES)) {
      expect(Object.keys(entry), `${entryId} must be a flat English entry`)
        .not.toContain("es");
      for (const slot of HELP_SLOTS) {
        if (entry[slot]) expect(typeof entry[slot]).toBe("string");
      }
    }
  });
});

describe("help is wired to a single source", () => {
  test("every helpId used in the interface exists in the registry", () => {
    const referenced = new Set();
    for (const text of Object.values(sources)) {
      for (const match of text.matchAll(/helpId=(?:"([^"]+)"|\{"([^"]+)"\})/g)) {
        referenced.add(match[1] || match[2]);
      }
      for (const match of text.matchAll(/helpId=\{\[([^\]]+)\]\}/g)) {
        for (const raw of match[1].split(",")) {
          const value = raw.trim().replace(/^["']|["']$/g, "");
          if (value && !value.includes("`")) referenced.add(value);
        }
      }
      for (const match of text.matchAll(/helpId: "([^"]+)"/g)) {
        referenced.add(match[1]);
      }
    }
    expect(referenced.size).toBeGreaterThan(20);
    const unknown = [...referenced].filter((id) => !HELP_ENTRY_IDS.includes(id));
    expect(unknown).toEqual([]);
  });

  test("every Term rendered in the interface exists in the glossary", () => {
    const referenced = new Set();
    for (const text of Object.values(sources)) {
      for (const match of text.matchAll(/<Term id="([^"]+)"/g)) {
        referenced.add(match[1]);
      }
    }
    expect(referenced.size).toBeGreaterThan(0);
    const unknown = [...referenced].filter(
      (id) => !TUTORIAL_CONCEPT_IDS.includes(id),
    );
    expect(unknown).toEqual([]);
  });

  test("the workspace no longer keeps its own copy of the help prose", () => {
    const main = sources["../main.jsx"];
    for (const removed of [
      "const HELP_CONTENT",
      "const SCORE_METHOD_GUIDE",
      "const CUTPOINT_GUIDE",
      "function cutpointTooltip",
      "function signatureHelp",
      "function HelpButton",
      "function LabelWithHelp",
      "function PanelHeader",
    ]) {
      expect(main, `${removed} must not be redeclared in main.jsx`).not.toContain(
        removed,
      );
    }
  });

  test("in-place help copy is never inlined at a call site", () => {
    for (const [path, text] of Object.entries(sources)) {
      const inlined = [...text.matchAll(/\shelp="([^"]{40,})"/g)].map(
        (match) => match[1].slice(0, 60),
      );
      expect(
        inlined,
        `${path}: help copy belongs in src/help/registry.js, not at the call site`,
      ).toEqual([]);
    }
  });

  test("every module with its own file reaches the shared help surface", () => {
    for (const path of SOURCE_FILES.filter((item) => item !== "../main.jsx")) {
      expect(sources[path], `${path} must import the help surface`).toMatch(
        /from "\.\.\/help"/,
      );
    }
  });

  test("a help trigger is never nested inside a label element", () => {
    for (const [path, text] of Object.entries(sources)) {
      for (const match of text.matchAll(/<label[^>]*>([\s\S]{0,400}?)<\/label>/g)) {
        expect(
          match[1],
          `${path}: a help trigger must be a sibling of its label`,
        ).not.toMatch(/<(LabelWithHelp|HelpButton|SectionHelp)\b/);
      }
    }
  });
});
