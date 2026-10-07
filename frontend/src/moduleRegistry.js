/**
 * Canonical application-module registry.
 *
 * Navigation and tutorials derive their module coverage from this data-only
 * contract so a new workspace page cannot silently ship without a learning
 * decision.
 */
export const APP_MODULES = Object.freeze([
  {
    id: "home",
    label: "Home",
    kicker: "About TRACE Explorer",
    iconRole: "navigation.home",
    title: "TRACE Explorer",
    summary: "Study survival, expression and pathways in public cohorts or your own data, with a record of each analysis.",
    showLearnAction: true,
  },
  {
    id: "analysis",
    label: "Survival",
    kicker: "Single gene or signature",
    iconRole: "navigation.analysis",
    title: "Survival analysis",
    summary: "Analyze survival for genes or signatures, check the models and export the complete record.",
    showLearnAction: true,
  },
  {
    id: "compare",
    label: "Compare",
    kicker: "Genes and cutpoints",
    iconRole: "navigation.compare",
    title: "Compare genes and cutpoints",
    summary: "Compare genes and grouping rules in the same cohort and outcome.",
    showLearnAction: true,
  },
  {
    id: "expression",
    label: "Expression",
    kicker: "Two-group distributions",
    iconRole: "navigation.expressionComparison",
    title: "Expression comparison",
    summary: "Compare gene expression between two patient groups and inspect their distributions.",
    showLearnAction: true,
  },
  {
    id: "gsea",
    label: "GSEA",
    kicker: "Two-group pathways",
    iconRole: "navigation.gsea",
    title: "Gene-set enrichment",
    summary: "Find gene sets that differ between two patient groups, then inspect their direction and contributing genes.",
    showLearnAction: true,
  },
  {
    id: "multiverse",
    label: "Robustness",
    kicker: "Across analysis choices",
    iconRole: "navigation.multiverse",
    title: "Robustness across analysis choices",
    summary: "Test whether results remain consistent across prespecified endpoint, scoring and cutpoint choices.",
    showLearnAction: true,
  },
  {
    id: "session",
    label: "Run history",
    kicker: "Exploratory record",
    iconRole: "navigation.session",
    title: "Exploratory run history",
    summary: "Review analyses saved in this browser and export selected runs with their testing families.",
    showLearnAction: true,
  },
  {
    id: "pancancer",
    label: "Pan-cancer",
    kicker: "Cox concordance",
    iconRole: "navigation.panCancer",
    title: "Survival across cancers and studies",
    summary: "Explore where a gene or signature relates to survival.",
    showLearnAction: true,
  },
  {
    id: "examples",
    label: "Guides",
    kicker: "Tutorials and manuals",
    iconRole: "navigation.examples",
    title: "Guides",
    summary: "Follow tutorials or look up a practical guide.",
    showLearnAction: false,
  },
  {
    id: "repository",
    label: "External cohorts",
    kicker: "Independent RNA-seq",
    iconRole: "navigation.repository",
    title: "Independent cohorts",
    summary: "Find external RNA-seq cohorts by cancer, source and the analyses they support.",
    showLearnAction: false,
  },
  {
    id: "summary",
    label: "Dataset",
    kicker: "Inventory",
    iconRole: "navigation.dataset",
    title: "TCGA data",
    summary: "Check patient counts, samples, outcomes and data sources.",
    showLearnAction: false,
  },
  {
    id: "api",
    label: "API & MCP",
    kicker: "Public access",
    iconRole: "navigation.api",
    title: "API & MCP",
    summary: "Use the same data and methods from code, Claude or ChatGPT.",
    showLearnAction: false,
  },
  {
    id: "help",
    label: "Methods",
    kicker: "Definitions and assumptions",
    iconRole: "navigation.methods",
    title: "Methods",
    summary: "Read how each analysis works and what you need to reproduce it.",
    showLearnAction: false,
  },
]);

export const APP_NAV = Object.freeze(
  APP_MODULES.map(({ id, label, kicker, iconRole }) => Object.freeze({
    id,
    label,
    kicker,
    iconRole,
  })),
);

const NAV_GROUP_DEFINITIONS = Object.freeze([
  Object.freeze({ id: "analyze", label: "Analyze", moduleIds: Object.freeze([
    "analysis",
    "compare",
    "expression",
    "gsea",
    "multiverse",
    "pancancer",
  ]) }),
  Object.freeze({ id: "evidence", label: "Evidence", moduleIds: Object.freeze([
    "repository",
    "summary",
  ]) }),
  Object.freeze({ id: "learn", label: "Learn & connect", moduleIds: Object.freeze([
    "examples",
    "api",
    "help",
  ]) }),
]);

/**
 * Navigation groups describe researcher intent without changing module IDs or
 * routes. Home remains the stable first destination outside the groups.
 */
export const APP_NAV_HOME = Object.freeze(APP_NAV.find(({ id }) => id === "home"));
export const APP_NAV_GROUPS = Object.freeze(NAV_GROUP_DEFINITIONS.map((group) => (
  Object.freeze({
    id: group.id,
    label: group.label,
    items: Object.freeze(group.moduleIds.map((moduleId) => (
      APP_NAV.find(({ id }) => id === moduleId)
    )).filter(Boolean)),
  })
)));

export const PAGE_META = Object.freeze(Object.fromEntries(
  APP_MODULES.map(({ id, title, summary }) => [id, Object.freeze({ title, summary })]),
));

export const APP_MODULE_ORDER = Object.freeze(APP_MODULES.map(({ id }) => id));

export function getAppModule(moduleId) {
  return APP_MODULES.find(({ id }) => id === moduleId) || null;
}
