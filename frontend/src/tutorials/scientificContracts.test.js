import { describe, expect, test } from "vitest";
import {
  TUTORIAL_CITATIONS,
  getTutorialCitation,
} from "./citationRegistry";
import {
  TUTORIAL_CONCEPTS,
  getTutorialConcept,
} from "./conceptRegistry";
import {
  SCIENTIFIC_CONTRACTS,
  TUTORIAL_CAPABILITIES,
  evaluateTutorialRequirements,
  getScientificContract,
  scientificContractRegistryErrors,
  tutorialRequirement,
} from "./scientificContracts";
import { TUTORIAL_CURRICULA, validateAllCurricula } from "./curriculum";

describe("tutorial scientific registries", () => {
  test("resolves stable concept IDs into English entries", () => {
    expect(Object.keys(TUTORIAL_CONCEPTS).length).toBeGreaterThan(20);
    const concept = getTutorialConcept("hierarchical_iqr_scale");
    expect(concept.id).toBe("hierarchical_iqr_scale");
    expect(concept.definition).toContain("within each study");
    expect(getTutorialConcept("not-a-concept")).toBeNull();
  });

  test("keeps every scientific contract concept and citation resolvable", () => {
    expect(scientificContractRegistryErrors()).toEqual([]);
    expect(validateAllCurricula()).toEqual([]);
    expect(Object.keys(SCIENTIFIC_CONTRACTS).length).toBeGreaterThanOrEqual(14);
    expect(Object.keys(TUTORIAL_CITATIONS).length).toBeGreaterThan(10);
    expect(getTutorialCitation("cox-1972")?.doi).toBe(
      "10.1111/j.2517-6161.1972.tb00899.x",
    );
  });

  test("evaluates serializable workspace requirements without application state closures", () => {
    const requirements = [
      tutorialRequirement(TUTORIAL_CAPABILITIES.SURVIVAL_RESULT),
      tutorialRequirement(TUTORIAL_CAPABILITIES.DATASET_CATALOG, { blocking: true }),
    ];
    expect(() => JSON.stringify(requirements)).not.toThrow();
    expect(evaluateTutorialRequirements(requirements, {})).toMatchObject({
      available: false,
      missingIds: [
        TUTORIAL_CAPABILITIES.SURVIVAL_RESULT,
        TUTORIAL_CAPABILITIES.DATASET_CATALOG,
      ],
    });
    expect(evaluateTutorialRequirements(requirements, {
      [TUTORIAL_CAPABILITIES.DATASET_CATALOG]: true,
    })).toMatchObject({
      available: true,
      missingIds: [TUTORIAL_CAPABILITIES.SURVIVAL_RESULT],
    });
  });

  test("separates effect contracts while quick help remains mode-aware", () => {
    const tcga = getScientificContract("pancancer.tcga_reference");
    const hierarchical = getScientificContract("pancancer.hierarchical");
    const modeAware = getScientificContract("pancancer.mode_aware");
    expect(`${tcga.estimand} ${tcga.scale}`).toMatch(/\+1.*SD/i);
    expect(tcga.scale).toMatch(/common input-score unit/i);
    expect(tcga.scale).not.toMatch(/HR per \+1 within-study IQR/i);
    expect(hierarchical.scale).toMatch(/\+1.*IQR/i);
    expect(hierarchical.conceptIds).toContain("modified_hksj");
    expect(hierarchical.multiplicity).toMatch(/two independent studies/i);
    expect(modeAware.scale).toMatch(/IQR/i);
    expect(modeAware.scale).toMatch(/common input-score unit/i);

    const quick = TUTORIAL_CURRICULA.en.byId["quick-pancancer"];
    expect(quick.scientificContractId).toBe("pancancer.mode_aware");
    expect(quick.steps.every(
      (step) => step.scientificContractId === "pancancer.mode_aware",
    )).toBe(true);

    const route = TUTORIAL_CURRICULA.en.byId["validation-generalization"];
    const hierarchicalSteps = route.steps.filter(
      (step) => step.anchor === "pancancer.preflight"
        || (step.anchor === "pancancer.results" && step.title.toLowerCase().includes("heterogeneity")),
    );
    expect(hierarchicalSteps).toHaveLength(2);
    expect(hierarchicalSteps.every(
      (step) => step.scientificContractId === "pancancer.hierarchical",
    )).toBe(true);
  });

  test("documents the implemented survival and DotPlot scales exactly", () => {
    const survival = getScientificContract("survival.continuous");
    const gsea = getScientificContract("gsea.preranked");
    expect(survival.estimand).toMatch(/\+1.*SD/i);
    expect(survival.scale).toMatch(/raw log-expression/i);
    expect(gsea.scale).toContain("per-set residual correlation");
    expect(gsea.scale).toContain("min(-log10(CAMERA FDR), 10)");
  });

  test("keeps guides informational, without checkpoint or reveal state", () => {
    for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
      for (const tutorial of curriculum.tutorials) {
        for (const step of tutorial.steps) {
          expect(Object.hasOwn(step, "checkpoint")).toBe(false);
          expect(Object.hasOwn(step, "reveal")).toBe(false);
        }
      }
    }
  });

  test("links every observable objective to at least one guide page", () => {
    for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
      for (const tutorial of curriculum.tutorials) {
        expect(tutorial.objectives.every((objective) => objective.id && objective.text)).toBe(true);
        const covered = new Set(tutorial.steps.flatMap((step) => step.objectiveIds));
        for (const objective of tutorial.objectives) {
          expect(covered.has(objective.id)).toBe(true);
        }
      }
    }
  });

  test("links English manuals to the concept and reference registries", () => {
    for (const manual of TUTORIAL_CURRICULA.en.manuals) {
      expect(manual.concepts).toHaveLength(manual.conceptIds.length);
      expect(manual.citations).toHaveLength(manual.citationIds.length);
    }
  });

  test("gives every guide page a question, limitations and resolvable references", () => {
    for (const tutorial of TUTORIAL_CURRICULA.en.tutorials) {
      for (const step of tutorial.steps) {
        expect(step.scientificContract?.question).toBeTruthy();
        const limitations = step.cannotConclude?.length
          ? step.cannotConclude
          : step.scientificContract?.cannotConclude;
        expect(limitations?.length).toBeGreaterThan(0);
        for (const citationId of step.citationIds || []) {
          expect(getTutorialCitation(citationId)).toBeTruthy();
        }
      }
    }
  });
});
