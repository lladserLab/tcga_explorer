import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, test } from "vitest";

import { GUIDE_ANCHORS } from "./catalog";

function source(relativePath) {
  return readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  );
}

function expectNearby(text, anchorName, marker, maxDistance = 700) {
  const anchorToken = `GUIDE_ANCHORS.${anchorName}`;
  const anchorPositions = [
    ...text.matchAll(new RegExp(`${anchorToken.replace(".", "\\.")}(?![A-Z0-9_])`, "g")),
  ].map((match) => match.index);
  const markerPositions = [];
  let offset = 0;
  while ((offset = text.indexOf(marker, offset)) !== -1) {
    markerPositions.push(offset);
    offset += marker.length;
  }
  expect(anchorPositions, `${anchorName} must be integrated`).not.toHaveLength(0);
  expect(markerPositions, `${marker} must exist`).not.toHaveLength(0);
  const distance = Math.min(
    ...anchorPositions.flatMap((anchorPosition) =>
      markerPositions.map((markerPosition) => Math.abs(anchorPosition - markerPosition)),
    ),
  );
  expect(
    distance,
    `${anchorName} must be colocated with ${marker}`,
  ).toBeLessThanOrEqual(maxDistance);
}

describe("contextual tutorial anchors", () => {
  const main = source("../main.jsx");
  const expression = source("../expression/ExpressionComparisonModule.jsx");
  const gsea = source("../gsea/GseaModule.jsx");
  const panCancer = source("../pancancer/HierarchicalPanCancerModule.jsx");
  const panCancerStyles = source("../pancancer/HierarchicalPanCancer.css");
  const repository = source("../repository/RepositoryCatalog.jsx");
  const datasetProvenance = source("../dataset/DatasetProvenance.jsx");
  const tutorialLibrary = source("./TutorialLibrary.jsx");
  const tutorialStyles = source("./tutorials.css");
  const styles = source("../styles.css");
  const integrations = [
    main,
    expression,
    gsea,
    panCancer,
    repository,
    datasetProvenance,
    tutorialLibrary,
  ].join("\n");

  test("every catalog target is owned by a real module integration", () => {
    Object.keys(GUIDE_ANCHORS).forEach((anchorName) => {
      expect(integrations).toContain(`GUIDE_ANCHORS.${anchorName}`);
    });
  });

  test("the former grouped hidden placeholder is gone", () => {
    expect(main).not.toContain("PAGE_GUIDE_ANCHORS");
    expect(main).not.toContain("PageGuideAnchors");
    expect(styles).not.toContain("trace-page-guide-anchors");
  });

  test("guide focus and spotlight treatments stay inside their targets", () => {
    const focusRule = tutorialStyles.match(
      /\.trace-guide-anchor:focus-visible\s*\{([^}]*)\}/s,
    )?.[1];
    const spotlightRule = tutorialStyles.match(
      /\.trace-guide-anchor\[data-guide-spotlight="active"\]\s*\{([^}]*)\}/s,
    )?.[1];

    expect(focusRule).toContain("box-shadow: inset");
    expect(spotlightRule).toContain("inset 0 0 0 2px var(--accent)");
    expect(spotlightRule).toContain("color-mix(in oklch, var(--accent) 6%, transparent)");
    expect(tutorialStyles).not.toMatch(/\.trace-guide-anchor:focus\s*\{/);
    expect(spotlightRule).not.toContain("outline-offset");
    expect(spotlightRule).not.toContain("0 0 0 7px");
  });

  test("guide artifact fields use full borders instead of left-side stripes", () => {
    const artifactFieldRule = tutorialStyles.match(
      /\.trace-tutorial-artifact-fields > div\s*\{([^}]*)\}/s,
    )?.[1];

    expect(artifactFieldRule).toContain("border: 1px solid var(--line)");
    expect(artifactFieldRule).not.toContain("border-left");
    expect(tutorialStyles).not.toContain("border-left-color: var(--line-strong)");
  });

  test("decorative side stripes do not return in guided analysis containers", () => {
    expect(styles).not.toContain("border-left: 3px solid var(--accent)");
    expect(styles).not.toContain("border-left: 2px solid var(--warning)");
    expect(styles).not.toContain("border-left: 2px solid var(--muted-strong)");
    expect(styles).not.toContain(
      "linear-gradient(90deg, var(--accent) 0 3px, transparent 3px)",
    );
    expect(styles).not.toContain(".control-panel::before");
    expect(tutorialStyles).not.toContain(
      "border-left: 2px solid var(--accent-muted)",
    );
  });

  test("pan-cancer selected tabs use a contained perimeter in every viewport", () => {
    const selectedRule = panCancerStyles.match(
      /\.hierarchical-pc-view-tabs button\.is-selected\s*\{([^}]*)\}/s,
    )?.[1];

    expect(selectedRule).toContain("background: var(--accent-soft");
    expect(selectedRule).toContain("box-shadow: inset");
    expect(panCancerStyles).not.toContain(
      ".hierarchical-pc-view-tabs button::after",
    );
  });

  test("survival, compare, multiverse and session anchors sit on their controls or evidence", () => {
    [
      ["SURVIVAL_DATASET", 'label: "Data"', 120],
      ["SURVIVAL_MARKER", 'label: "Marker design"', 120],
      ["SURVIVAL_OUTCOME", 'label: "Outcome"', 120],
      ["SURVIVAL_CLINICAL", 'label: "Patient filters and adjustment"', 120],
      ["SURVIVAL_REVIEW", 'label: "Review & run"', 120],
      ["COMPARE_DATASET", 'label: "Dataset"', 120],
      ["COMPARE_MARKERS", 'label: "Markers"', 120],
      ["COMPARE_METHODS", 'label: "Methods"', 120],
      ["COMPARE_CLINICAL", 'label: "Clinical"', 120],
      ["COMPARE_REVIEW", 'label: "Review & run"', 120],
      ["MULTIVERSE_DATASET", 'label: "Dataset"', 120],
      ["MULTIVERSE_MARKER", 'label: "Marker"', 120],
      ["MULTIVERSE_DESIGN", 'label: "Decisions"', 120],
      ["MULTIVERSE_CLINICAL", 'label: "Clinical"', 120],
      ["MULTIVERSE_REVIEW", 'label: "Review & run"', 120],
      ["SURVIVAL_UPLOAD", "Upload your data", 600],
      ["SURVIVAL_UPLOAD_EXPRESSION", 'id="user-expression-file"', 180],
      ["SURVIVAL_UPLOAD_OUTCOME", 'id="user-clinical-file"', 180],
      ["SURVIVAL_UPLOAD_METADATA", "Custom clinical variables", 500],
      ["SURVIVAL_RESULTS", "result-panel", 250],
      ["SURVIVAL_DIAGNOSTICS", "Diagnostics & provenance", 450],
      ["SURVIVAL_DOWNLOADS", "result-downloads", 300],
      ["COMPARE_RESULTS", "ComparePlotMatrix", 2200],
      ["MULTIVERSE_RESULTS", "Analysis choices compared", 500],
      ["SESSION_SETUP", "Run history controls", 120],
      ["SESSION_LEDGER", "Recorded runs", 500],
      ["SESSION_INTERPRETATION", 'className="session-history-page"', 160],
    ].forEach(([anchorName, marker, maxDistance]) =>
      expectNearby(main, anchorName, marker, maxDistance),
    );
    expectNearby(main, "SURVIVAL_UPLOAD_EXPRESSION", "Expression layout", 350);
    expectNearby(main, "SURVIVAL_UPLOAD_EXPRESSION", "Expression scale in the file", 1_500);
    expectNearby(main, "SURVIVAL_UPLOAD_OUTCOME", "Patient identifier and optional survival outcome mapping", 350);
    expectNearby(main, "SURVIVAL_UPLOAD_OUTCOME", 'label="Event status"', 1_500);
    expect((main.match(/GUIDE_ANCHORS\.SURVIVAL_UPLOAD_EXPRESSION/g) || [])).toHaveLength(2);
    expect((main.match(/GUIDE_ANCHORS\.SURVIVAL_UPLOAD_OUTCOME/g) || [])).toHaveLength(2);
    expect(main).toContain("const StepButton = step.guideAnchor ? GuideAnchor : \"button\"");
    expect(main).toContain('as: "button"');
  });

  test("expression and GSEA anchors surround the numbered setup sections and results", () => {
    [
      ["EXPRESSION_DATASET", "<h3>Dataset</h3>"],
      ["EXPRESSION_GENES", "<h3>Genes</h3>"],
      ["EXPRESSION_GROUPS", "<h3>Groups</h3>"],
      ["EXPRESSION_TEST_FAMILY", "<h3>Test family</h3>"],
      ["EXPRESSION_RESULTS", 'className="expression-result"'],
    ].forEach(([anchorName, marker]) => expectNearby(expression, anchorName, marker));
    [
      ["GSEA_DATASET", "<h3>Dataset</h3>"],
      ["GSEA_GROUPS", "<h3>Groups</h3>"],
      ["GSEA_COLLECTION", "<h3>Gene sets and ranking</h3>"],
      ["GSEA_RESULTS", 'className="gsea-result"'],
    ].forEach(([anchorName, marker]) => expectNearby(gsea, anchorName, marker));
  });

  test("home, support, repository and pan-cancer anchors point to visible sections", () => {
    [
      ["HOME_OVERVIEW", 'className="home-hero"'],
      ["HOME_WORKSPACE", "What do you want to investigate?"],
      ["HOME_FOUNDATION", "Institutions"],
      ["HOME_INTERPRETATION", 'className="home-page home-reorganized"'],
      ["DATASET_OVERVIEW", 'className="summary-overview"'],
      ["DATASET_COVERAGE", 'title="Endpoint coverage"'],
      ["DATASET_COHORT_LANDSCAPE", 'title="Cohort landscape"'],
      ["DATASET_SAMPLE_TYPES", 'title="Sample types"'],
      ["DATASET_VITAL_STATUS", 'title="Vital status"'],
      ["DATASET_PRIMARY_SITES", 'title="Primary sites"'],
      ["DATASET_AGE", 'title="Age at index"'],
      ["DATASET_METADATA", 'title="Metadata coverage"'],
      ["DATASET_ANNOTATIONS", 'title="Biological annotations"'],
      ["DATASET_COHORT_TABLE", 'title="Cohort table"'],
      ["DATASET_INTERPRETATION", 'className="summary-page"'],
      ["METHODS_INPUT_OUTPUT", "Analysis input-output tree"],
      ["METHODS_ANALYSIS_INPUTS", 'title: "Analysis inputs"'],
      ["METHODS_SIGNATURE_SCORING", 'title: "Signature scoring"'],
      ["METHODS_STRATIFICATION", 'title: "Stratification"'],
      ["METHODS_SURVIVAL_OUTPUTS", 'title: "Survival outputs"'],
      ["METHODS_CROSS_MODULE", 'title: "Comparison, GSEA and pan-cancer"'],
      ["METHODS_GLOSSARY", 'title: "Statistical glossary"'],
      ["METHODS_HISTORY", "Methods history"],
      ["METHODS_INTERPRETATION", 'className="help-page"'],
      ["EXAMPLES_CATALOG", "TutorialLibrary"],
      ["API_REST", 'title="REST API v1"'],
      ["API_CONNECTORS", 'title="Claude and ChatGPT"'],
      ["API_EXECUTION", "How requests run"],
      ["API_INTERPRETATION", 'className="access-page"'],
      ["PANCANCER_QUERY", 'title="2. Choose a gene or signature"'],
      ["PANCANCER_RESULTS", 'className="pancancer-results"'],
    ].forEach(([anchorName, marker]) => expectNearby(main, anchorName, marker));
    expectNearby(datasetProvenance, "DATASET_PROVENANCE", "Data provenance");
    expectNearby(repository, "REPOSITORY_FINDER", "Find a cohort");
    expectNearby(repository, "REPOSITORY_PROVENANCE", "Find a cohort for your question");
    expectNearby(panCancer, "PANCANCER_PREFLIGHT", "Check which studies qualify");
    expectNearby(panCancer, "PANCANCER_MODE", "1. Choose where to look");
    expectNearby(panCancer, "PANCANCER_RESULTS", "Hierarchical evidence");
  });

  test("Learning center anchors match its three visible content areas and final catalog", () => {
    [
      ["EXAMPLES_ROUTES", "curriculum.routes"],
      ["EXAMPLES_QUICK", "curriculum.quickGuides"],
      ["EXAMPLES_MANUALS", "<ManualPanel"],
    ].forEach(([anchorName, marker]) => expectNearby(tutorialLibrary, anchorName, marker));
    expectNearby(main, "EXAMPLES_CATALOG", "TutorialLibrary");
  });
});
