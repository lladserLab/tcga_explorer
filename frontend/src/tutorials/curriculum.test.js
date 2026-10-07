import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { APP_MODULES } from "../moduleRegistry";
import {
  APPROVED_ROUTE_IDS,
  QUICK_GUIDE_MODULE_ORDER,
  QUICK_GUIDE_STEP_CONTRACTS,
  QUICK_GUIDE_STEP_COUNTS,
  SEVEN_LESSON_PATTERN,
  TEACHING_EXAMPLE_PROVENANCE,
  TUTORIAL_MODULE_ORDER,
} from "./catalog";
import {
  TUTORIAL_CURRICULA,
  getTutorialById,
  validateAllCurricula,
} from "./curriculum";
import { TUTORIAL_PRESETS } from "./presets";

describe("tutorial curriculum contract", () => {
  test("ships the five approved seven-lesson routes in English", () => {
    expect(validateAllCurricula()).toEqual([]);
    expect(Object.keys(TUTORIAL_CURRICULA)).toEqual(["en"]);
    const curriculum = TUTORIAL_CURRICULA.en;
    expect(curriculum.routes.map((route) => route.id)).toEqual(APPROVED_ROUTE_IDS);
    for (const route of curriculum.routes) {
      expect(route.steps).toHaveLength(7);
      expect(route.steps.map((step) => step.phase)).toEqual(SEVEN_LESSON_PATTERN);
    }
  });

  test("own-data explicitly covers files, upload, metadata, GSEA and an error lab", () => {
    const route = getTutorialById("own-data");
    const anchors = route.steps.map((step) => step.anchor);
    expect(anchors).toContain("survival.upload.expression");
    expect(anchors).toContain("survival.upload.outcome");
    expect(anchors).toContain("survival.upload.metadata");
    expect(route.steps.some((step) => step.module === "gsea")).toBe(true);
    expect(route.steps.some((step) => step.phase === "error-lab")).toBe(true);
  });

  test("provides quick guides only for guide-enabled modules plus manuals and fixed cases", () => {
    expect(Object.keys(QUICK_GUIDE_STEP_CONTRACTS)).toEqual(QUICK_GUIDE_MODULE_ORDER);
    expect(QUICK_GUIDE_STEP_COUNTS).toEqual({
      home: 4,
      analysis: 6,
      compare: 6,
      expression: 5,
      gsea: 4,
      multiverse: 6,
      session: 3,
      pancancer: 4,
    });

    expect(APP_MODULES.filter(({ showLearnAction }) => !showLearnAction).map(({ id }) => id))
      .toEqual(["examples", "repository", "summary", "api", "help"]);
    expect(TUTORIAL_MODULE_ORDER).toEqual(APP_MODULES.map(({ id }) => id));
    for (const moduleId of ["examples", "repository", "summary", "api", "help"]) {
      expect(getTutorialById(`quick-${moduleId}`)).toBeNull();
    }

    for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
      expect(curriculum.quickGuides.map((guide) => guide.module)).toEqual(
        QUICK_GUIDE_MODULE_ORDER,
      );
      for (const guide of curriculum.quickGuides) {
        expect(guide.steps).toHaveLength(QUICK_GUIDE_STEP_COUNTS[guide.module]);
        expect(guide.steps.map(({ id, anchor, workspaceStepId }) => ({
          id,
          anchor,
          workspaceStepId: workspaceStepId ?? null,
        }))).toEqual(QUICK_GUIDE_STEP_CONTRACTS[guide.module]);
        expect(guide.steps.at(-1).id).toBe("interpret");
      }
      expect(curriculum.quickGuides.every(
        (guide) => !guide.presetId && guide.steps.every((step) => !step.presetId),
      )).toBe(true);
      expect(curriculum.manuals).toHaveLength(5);
      expect(curriculum.manuals.every((manual) => manual.sections.length >= 4)).toBe(true);
      expect(curriculum.examples).toHaveLength(5);
      expect(curriculum.examples.every((example) => example.mode === "fixed")).toBe(true);
    }
  });

  test("maps the six-step Survival guide onto all five workflow stages and interpretation", () => {
    const expectedStepIds = [
      "data",
      "marker",
      "outcome",
      "clinical",
      "review-run",
      "interpret",
    ];
    const expectedWorkspaceStepIds = [
      "data",
      "design",
      "outcome",
      "clinical",
      "review",
      undefined,
    ];

    const guide = getTutorialById("quick-analysis");
    expect(guide.steps.map((step) => step.id)).toEqual(expectedStepIds);
    expect(guide.steps.map((step) => step.workspaceStepId)).toEqual(
      expectedWorkspaceStepIds,
    );
    expect(guide.steps.every((step) => !step.presetId)).toBe(true);
    expect(guide.steps.every((step) => !Object.hasOwn(step, "checkpoint"))).toBe(true);
    expect(guide.presetId).toBeNull();
    expect(JSON.stringify(guide)).not.toMatch(/CDC20|TCGA-LIHC|included-lihc-cdc20-os/);

    const interpretation = guide.steps.at(-1);
    expect(interpretation.anchor).toBe("survival.results");
    expect(interpretation.requirements).toEqual([
      expect.objectContaining({
        capability: "survival.resultAvailable",
      }),
    ]);
  });

  test("keeps every module quick guide neutral and free of named teaching presets", () => {
    for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
      for (const guide of curriculum.quickGuides) {
        expect(guide.presetId).toBeNull();
        expect(guide.steps.every((step) => !step.presetId)).toBe(true);
      }
      expect(JSON.stringify(curriculum.quickGuides)).not.toMatch(
        /included-lihc-cdc20-os|compare-skcm-pdcd1-cutpoints|groups-expression-panel|groups-gsea-go|multiverse-lihc-cdc20|pancancer-cdc20-tcga/,
      );
    }
  });

  test("exposes one English curriculum without a Spanish runtime variant", () => {
    expect(Object.keys(TUTORIAL_CURRICULA)).toEqual(["en"]);
    expect(TUTORIAL_CURRICULA.es).toBeUndefined();
    expect(TUTORIAL_CURRICULA.en.lang).toBe("en");
    expect(TUTORIAL_CURRICULA.en.labels.next).toBe("Next");
  });

  test("every live guide or lesson preset is registered and fixed examples have none", () => {
    for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
      for (const tutorial of curriculum.tutorials) {
        if (tutorial.presetId) expect(TUTORIAL_PRESETS[tutorial.presetId]).toBeTruthy();
        for (const step of tutorial.steps) {
          if (step.presetId) expect(TUTORIAL_PRESETS[step.presetId]).toBeTruthy();
          if (tutorial.mode === "fixed") {
            expect(tutorial.presetId).toBeFalsy();
            expect(step.presetId).toBeFalsy();
          }
        }
      }
    }
  });

  test("uses the approved scientific teaching cases and TCGA catalog IDs", () => {
    expect(TUTORIAL_PRESETS["included-lihc-cdc20-os"].patches.form).toMatchObject({
      cohort: "TCGA-LIHC",
      gene_symbol: "CDC20",
      endpoint: "OS",
    });
    expect(TUTORIAL_PRESETS["compare-skcm-pdcd1-cutpoints"].patches).toMatchObject({
      form: { cohort: "TCGA-SKCM" },
      compare: { genes: "PDCD1" },
    });
    expect(TUTORIAL_PRESETS["multiverse-lihc-cdc20"].patches).toMatchObject({
      form: { cohort: "TCGA-LIHC" },
      multiverse: { genes: "CDC20" },
    });
    expect(TUTORIAL_PRESETS["groups-brca-pam50-exploratory"].patches.gsea)
      .toMatchObject({ clinical_variable: "paper_BRCA_Subtype_PAM50" });
  });

  test("backs every fixed-example digest with a versioned public artifact", () => {
    for (const provenance of Object.values(TEACHING_EXAMPLE_PROVENANCE)) {
      const content = readFileSync(
        new URL(`../../public/${provenance.artifact_path}`, import.meta.url),
      );
      const artifact = JSON.parse(content.toString("utf8"));
      expect(artifact.result_id).toBe(provenance.result_id);
      expect(artifact.pipeline_version).toBe(provenance.pipeline_version);
      expect(artifact.snapshot_date).toBe(provenance.snapshot_date);
      expect(artifact.status).toBe("not_a_computed_analysis_result");
      expect(artifact.source_kind).toBe("synthetic_case");
      expect(artifact.answer_key).toBeTruthy();
      expect(createHash("sha256").update(content).digest("hex")).toBe(provenance.sha256);
    }
  });

  test("keeps the evidence requested by each fixed lesson inside its teaching artifact", () => {
    const artifact = (tutorialId) => {
      const provenance = TEACHING_EXAMPLE_PROVENANCE[tutorialId];
      return JSON.parse(readFileSync(
        new URL(`../../public/${provenance.artifact_path}`, import.meta.url),
        "utf8",
      ));
    };

    const continuous = artifact("example-continuous-before-cutpoint").scenario.synthetic_values;
    expect(continuous.continuous_cox.confidence_interval_95).toHaveLength(2);
    expect(continuous.grouped_kaplan_meier.group_low.number_at_risk_at_months).toBeTruthy();
    expect(continuous.proportional_hazards).toMatchObject({ method: "cox.zph" });

    const privateFixture = artifact("example-private-data-error-lab").scenario;
    expect(privateFixture.fixture_files.map((row) => row.classification)).toEqual(
      expect.arrayContaining([
        "blocking_error",
        "repairable_linkage_notice",
        "analysis_ineligible_metadata",
        "post_treatment_semantic_risk",
      ]),
    );

    const gsea = artifact("example-gsea-direction").scenario;
    expect(gsea.synthetic_pathways.every((pathway) => pathway.leading_edge.length > 0)).toBe(true);
    expect(gsea.go_redundancy_context[0].shared_leading_edge_genes.length).toBeGreaterThan(0);
    expect(gsea.fdr_family.tested_gene_sets).toBe(gsea.synthetic_pathways.length);
    expect(gsea.dotplot_contract).toMatchObject({
      display_limit: "up to the 30 pathways with lowest FDR",
      point_area: "min(-log10(FDR), 10)",
      negative_log10_fdr_cap: 10,
      point_color: "NES",
    });

    const multiplicity = artifact("example-multiplicity-boundaries").scenario.multiverse_family;
    expect(multiplicity.execution_ledger).toHaveLength(multiplicity.summary.planned);
    expect(multiplicity.specification_curve.included_specification_ids).toHaveLength(
      multiplicity.summary.planned,
    );
    expect(multiplicity.failures_and_unavailable.map((row) => row.status)).toEqual(
      expect.arrayContaining(["failed", "not_evaluable"]),
    );

    const panCancer = artifact("example-pancancer-heterogeneity").scenario;
    expect(panCancer.synthetic_values.study_effects.length).toBeGreaterThan(0);
    expect(panCancer.synthetic_values.cancer_effects.every(
      (row) => row.heterogeneity && row.inference.includes("modified HKSJ"),
    )).toBe(true);
    expect(panCancer.synthetic_values.global_effect.prediction_interval_95).toHaveLength(2);
    expect(JSON.stringify(panCancer.required_evidence)).not.toMatch(/power|clinical sensitivity/i);
  });

  test("keeps English quick guides module-specific instead of repeating boilerplate", () => {
    const guides = TUTORIAL_CURRICULA.en.quickGuides;
    expect(new Set(guides.map((guide) => guide.steps[0].output)).size).toBe(guides.length);
    expect(new Set(guides.map((guide) => guide.steps[1].instruction)).size).toBe(guides.length);
    expect(new Set(guides.map((guide) => guide.steps[2].output)).size).toBe(guides.length);
  });

  test("keeps fixed-case conclusions visible as prose without answer checkpoints", () => {
    const examples = TUTORIAL_CURRICULA.en.examples;
    expect(examples.every(
      (example) => example.steps.every((step) => !Object.hasOwn(step, "checkpoint")),
    )).toBe(true);

    const evidenceConclusions = examples.map(
      (example) => example.steps.find((step) => step.id === "evidence").output,
    );
    expect(new Set(evidenceConclusions).size).toBe(examples.length);
    expect(evidenceConclusions.join(" ")).toMatch(
      /instantaneous-hazard[\s\S]*Duplicate IDs[\s\S]*Positive NES[\s\S]*run history[\s\S]*prediction interval/i,
    );
  });

  test("does not copy synthetic microcase numbers into curriculum prose", () => {
    const prose = JSON.stringify(TUTORIAL_CURRICULA);
    for (const syntheticValue of ["1.75", "-1.42", "1.08", "0.72", "1.62"]) {
      expect(prose).not.toContain(syntheticValue);
    }
  });
});
