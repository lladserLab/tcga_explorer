/**
 * Section-layer help: what the current design already decides.
 *
 * These are pure functions over values the workspace has already derived. They
 * answer the three questions a reader has while setting up an analysis:
 *
 *   decided  - what is settled so far.
 *   missing  - what still blocks a run, in the app's own words.
 *   estimand - what the result will mean if it runs exactly like this.
 *
 * Nothing here reads React state, so every sentence a user sees about their own
 * design is unit-testable.
 */

const PENDING = "Pending";

function fact(id, label, value) {
  const text = String(value ?? "").trim();
  return Object.freeze({
    id,
    label,
    value: text || PENDING,
    pending: !text,
  });
}

function clean(values) {
  return Object.freeze(
    (values || []).map((value) => String(value || "").trim()).filter(Boolean),
  );
}

function ledger({ decided, missing, estimand, compactEstimand = "", cautions = [] }) {
  const blocking = clean(missing);
  return Object.freeze({
    ready: blocking.length === 0,
    decided: Object.freeze(decided.filter(Boolean)),
    missing: blocking,
    estimand: String(estimand || "").trim(),
    compactEstimand,
    cautions: clean(cautions),
  });
}

function countLabel(count, singular, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

/**
 * Events are the currency of a survival model. This states what the app knows
 * without inventing an events-per-parameter figure: categorical covariates
 * expand into several coefficients, so only the fitted model can report it.
 */
function eventCaution({ events, covariateCount }) {
  if (!Number.isFinite(events) || events <= 0) return "";
  if (!covariateCount) {
    return events < 10
      ? `${countLabel(events, "event")} at this endpoint. With fewer than 10 events, Cox estimates can be unstable.`
      : "";
  }
  return events < covariateCount * 10
    ? `${countLabel(events, "event")} for ${countLabel(covariateCount, "selected covariate")}. The fitted model reports events per parameter and flags values below 10.`
    : "";
}

export function survivalDesignLedger({
  datasetLabel,
  markerKind = "single",
  markerSummary,
  markerCount = 0,
  endpointLabel,
  patients,
  events,
  expressionScaleLabel,
  groupingLabel,
  filterCount = 0,
  populationLabel = "",
  adjustmentSummary,
  covariateCount = 0,
  requirements = [],
} = {}) {
  const isPanel = markerKind === "signature_panel";
  const isCombined = markerKind === "combined_signatures";
  const cohortValue = [
    datasetLabel,
    Number.isFinite(patients) && Number.isFinite(events)
      ? `${countLabel(patients, "patient")} · ${countLabel(events, "event")} with this endpoint, before tissue selection, filters and adjustment`
      : "",
  ].filter(Boolean).join(" · ");

  const decided = [
    fact("dataset", "Dataset", cohortValue),
    fact("marker", "Marker", markerSummary),
    fact("endpoint", "Endpoint", endpointLabel),
    fact("scale", "Expression scale", expressionScaleLabel),
    fact("grouping", isPanel ? "Model scope" : "Grouping", groupingLabel),
    fact(
      "population",
      "Population",
      [populationLabel, filterCount ? countLabel(filterCount, "clinical filter") : populationLabel ? "No clinical restrictions" : "All eligible patients"].filter(Boolean).join(" · "),
    ),
    fact("adjustment", "Adjustment", adjustmentSummary),
  ];

  let estimand = "";
  if (isPanel) {
    estimand = `Continuous Cox main effects for ${countLabel(markerCount, "signature")} in the same patients with complete outcomes. The panel uses continuous scores without cutpoint searches or Kaplan-Meier groups.`;
  } else if (isCombined) {
    estimand = `Whether the survival association of one signature changes with the other score, with ${groupingLabel || "crossed"} groups shown alongside it. A statistical interaction does not establish a biological mechanism.`;
  } else if (markerCount > 1) {
    estimand = `${countLabel(markerCount, "separate analysis", "separate analyses")}, one per gene. Each reports a hazard ratio per +1 within-analysis standard deviation. These runs do not share a multiple-testing correction.`;
  } else {
    estimand = "A hazard ratio for a one-standard-deviation increase in the marker within this analysis. Kaplan-Meier, grouped Cox and RMST compare the selected groups as sensitivity analyses.";
  }

  return ledger({
    decided,
    missing: requirements,
    estimand,
    compactEstimand: isPanel
      ? "Joint survival associations of the selected signatures."
      : isCombined
        ? "A survival interaction between two signature scores."
        : markerCount > 1
          ? `Separate survival associations for ${countLabel(markerCount, "gene")}.`
          : "Survival association of the selected gene or signature.",
    cautions: [
      eventCaution({ events, covariateCount }),
      markerCount > 1 && !isPanel && !isCombined
        ? "Several genes run as separate analyses. Use Compare or Robustness when the set is one declared family."
        : "",
    ],
  });
}

export function compareDesignLedger({
  datasetLabel,
  geneCount = 0,
  methodLabels = [],
  endpointLabel,
  expressionScaleLabel,
  events,
  filterCount = 0,
  adjustmentSummary,
  covariateCount = 0,
  requirements = [],
} = {}) {
  const methods = clean(methodLabels);
  const cells = geneCount * methods.length;
  const decided = [
    fact("dataset", "Dataset", datasetLabel),
    fact("marker", "Rows", geneCount ? countLabel(geneCount, "gene") : ""),
    fact("methods", "Columns", methods.length ? methods.join(" · ") : ""),
    fact("endpoint", "Endpoint", endpointLabel),
    fact("scale", "Expression scale", expressionScaleLabel),
    fact(
      "population",
      "Population",
      filterCount ? countLabel(filterCount, "clinical filter") : "All eligible patients",
    ),
    fact("adjustment", "Adjustment", adjustmentSummary),
    fact("family", "Declared family", cells ? countLabel(cells, "planned cell") : ""),
  ];

  return ledger({
    decided,
    missing: requirements,
    estimand: cells
      ? `${countLabel(cells, "grouped comparison")} run as one declared family, with BH and Bonferroni applied across valid grouped tests. Maxstat uses its selection-corrected p-value. Each gene also carries one cutpoint-independent continuous reference.`
      : "Each cell is one grouped comparison under one cutpoint rule, corrected as a single declared family.",
    compactEstimand: "Compare each gene across the selected cutpoints in the same source and endpoint.",
    cautions: [
      eventCaution({ events, covariateCount }),
      methods.length > 1
        ? "Read the pattern across cutpoints. Include all comparisons, even those that do not support the association."
        : "",
    ],
  });
}

export function multiverseDesignLedger({
  datasetLabel,
  markerSummary,
  endpointLabels = [],
  scoringLabels = [],
  cutpointLabels = [],
  filterCount = 0,
  adjustmentSummary,
  requirements = [],
} = {}) {
  const endpoints = clean(endpointLabels);
  const scoring = clean(scoringLabels);
  const cutpoints = clean(cutpointLabels);
  const specifications = endpoints.length * scoring.length * cutpoints.length;
  const decided = [
    fact("dataset", "Dataset", datasetLabel),
    fact("marker", "Marker", markerSummary),
    fact("endpoints", "Endpoints", endpoints.join(" · ")),
    fact("scoring", "Scoring", scoring.join(" · ")),
    fact("cutpoints", "Cutpoints", cutpoints.join(" · ")),
    fact(
      "population",
      "Population",
      filterCount ? countLabel(filterCount, "clinical filter") : "All eligible patients",
    ),
    fact("adjustment", "Adjustment", adjustmentSummary),
    fact(
      "family",
      "Analysis choices",
      specifications ? countLabel(specifications, "specification") : "",
    ),
  ];

  return ledger({
    decided,
    missing: requirements,
    estimand: specifications
      ? `${countLabel(specifications, "planned analysis", "planned analyses")} fixed as one family when the run starts. Continuous and grouped tests receive separate corrections. The record includes every combination, including those with unavailable data or failed models.`
      : "TRACE runs every selected endpoint, scoring method and cutpoint combination as one family, fixed when execution starts.",
    cautions: [
      specifications > 0 && specifications < 4
        ? "This small set covers only a few choices and gives limited evidence about robustness."
        : "",
      "Choose all combinations before running. Choices added after viewing results are exploratory.",
    ],
  });
}
