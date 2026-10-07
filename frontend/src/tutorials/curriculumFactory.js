import {
  APPROVED_ROUTE_IDS,
  FIXED_EXAMPLE_CONTINUATIONS,
  GUIDE_ANCHORS,
  QUICK_GUIDE_MODULE_ORDER,
  QUICK_GUIDE_STEP_CONTRACTS,
  QUICK_GUIDE_STEP_COUNTS,
  QUICK_GUIDE_CONTINUATIONS,
  SEVEN_LESSON_PATTERN,
  TEACHING_EXAMPLE_PROVENANCE,
  TUTORIAL_CONTENT_VERSION,
  TUTORIAL_MODULES,
  TUTORIAL_SOURCE_KINDS,
} from "./catalog";
import { resolveTutorialCitations, TUTORIAL_CITATION_IDS } from "./citationRegistry";
import { resolveTutorialConcepts, TUTORIAL_CONCEPT_IDS } from "./conceptRegistry";
import {
  getScientificContract,
  requirementsForTutorialStep,
  SCIENTIFIC_CONTRACT_IDS,
  scientificContractIdForModule,
  scientificContractIdForStep,
} from "./scientificContracts";

const freezeList = (values) => Object.freeze([...(values || [])]);

function freezeRequirements(requirements) {
  return Object.freeze(
    (requirements || []).map((requirement) => Object.freeze({ ...requirement })),
  );
}

function normalizeObjectives(tutorialId, objectives) {
  return Object.freeze(
    (objectives || []).map((objective, index) => Object.freeze(
      typeof objective === "string"
        ? { id: `${tutorialId}.objective-${index + 1}`, text: objective }
        : { id: objective.id || `${tutorialId}.objective-${index + 1}`, ...objective },
    )),
  );
}

function enrichStep(step, index, context) {
  const stepId = step.id || `step-${index + 1}`;
  const prepared = { ...step, id: stepId };
  const contractId = scientificContractIdForStep(prepared)
    || context.scientificContractId;
  const contract = getScientificContract(contractId, context.language);
  if (!contract) throw new Error(`Unknown scientific contract: ${contractId}`);
  const commonErrors = freezeList(step.commonErrors);
  const objectiveIds = freezeList(
    step.objectiveIds?.length
      ? step.objectiveIds
      : [context.objectives[Math.min(
        context.objectives.length - 1,
        Math.floor((index * context.objectives.length) / context.stepCount),
      )]?.id].filter(Boolean),
  );
  const conceptIds = freezeList(
    step.conceptIds?.length ? step.conceptIds : contract.conceptIds,
  );
  const citationIds = freezeList(
    step.citationIds?.length ? step.citationIds : contract.citationIds,
  );
  const requirements = freezeRequirements(requirementsForTutorialStep(prepared));
  const cannotConclude = freezeList(
    step.cannotConclude?.length ? step.cannotConclude : contract.cannotConclude,
  );
  const operationalPitfalls = freezeList(
    step.operationalPitfalls?.length ? step.operationalPitfalls : commonErrors,
  );
  const inferentialPitfalls = freezeList(
    step.inferentialPitfalls?.length
      ? step.inferentialPitfalls
      : cannotConclude.slice(0, 1),
  );
  return Object.freeze({
    ...prepared,
    why: step.why || contract.question,
    cannotConclude,
    commonErrors,
    pitfalls: Object.freeze({
      operational: operationalPitfalls,
      inferential: inferentialPitfalls,
    }),
    objectiveIds,
    conceptIds,
    concepts: resolveTutorialConcepts(conceptIds, context.language),
    citationIds,
    citations: resolveTutorialCitations(citationIds),
    requirements,
    scientificContractId: contractId,
    scientificContract: contract,
  });
}

function finalizeTutorial(definition, context, rawSteps) {
  const objectives = normalizeObjectives(context.tutorialId, definition.objectives);
  const scientificContractId = definition.scientificContractId
    || scientificContractIdForModule(definition.module);
  const scientificContract = getScientificContract(scientificContractId, context.language);
  if (!scientificContract) {
    throw new Error(`Unknown scientific contract: ${scientificContractId}`);
  }
  const steps = Object.freeze(rawSteps.map((step, index) => enrichStep(step, index, {
    ...context,
    objectives,
    stepCount: rawSteps.length,
    scientificContractId,
  })));
  const conceptIds = freezeList(new Set([
    ...scientificContract.conceptIds,
    ...steps.flatMap((step) => step.conceptIds),
  ]));
  const citationIds = freezeList(new Set([
    ...scientificContract.citationIds,
    ...steps.flatMap((step) => step.citationIds),
  ]));
  return Object.freeze({
    ...definition,
    id: context.tutorialId,
    type: context.type,
    mode: context.mode,
    sourceKind: context.sourceKind,
    level: context.level,
    version: TUTORIAL_CONTENT_VERSION,
    estimatedMinutes: definition.estimatedMinutes || context.estimatedMinutes,
    iconRole: TUTORIAL_MODULES[definition.module].iconRole,
    prerequisites: freezeList(definition.prerequisites),
    objectives,
    requirements: freezeRequirements(definition.requirements),
    scientificContractId,
    scientificContract,
    conceptIds,
    concepts: resolveTutorialConcepts(conceptIds, context.language),
    citationIds,
    citations: resolveTutorialCitations(citationIds),
    steps,
  });
}

function buildRoute(definition, copy) {
  const lessons = definition.lessons.map((lesson, index) => ({
    id: SEVEN_LESSON_PATTERN[index],
    phase: SEVEN_LESSON_PATTERN[index],
    ...lesson,
  }));
  return finalizeTutorial(definition, {
    tutorialId: definition.id,
    type: "route",
    mode: "live",
    sourceKind: "live",
    level: "basic-to-advanced",
    estimatedMinutes: 18,
    language: copy.lang,
    common: copy.common,
  }, lessons);
}

function buildQuickGuide(definition, copy) {
  const module = TUTORIAL_MODULES[definition.module];
  const tutorialId = `quick-${definition.module}`;
  const prepared = {
    ...definition,
    id: tutorialId,
    objectives: definition.objectives || [definition.focus || definition.summary].filter(Boolean),
    // The continuation graph is language-neutral and always enters an approved route.
    nextGuideId: QUICK_GUIDE_CONTINUATIONS[definition.module] || null,
    // Module help explains the current workspace and never changes scientific controls.
    presetId: null,
  };
  const generatedSteps = [
    {
      id: "orient",
      title: copy.common.quickSteps.orient,
      instruction: definition.focus,
      output: definition.setupOutput,
      commonErrors: definition.setupErrors,
      module: definition.module,
      anchor: definition.startAnchor,
      openView: module.page,
    },
    {
      id: "interpret",
      title: copy.common.quickSteps.interpret,
      instruction: definition.interpretation,
      output: definition.output,
      commonErrors: definition.outputErrors,
      module: definition.module,
      anchor: definition.outputAnchor || definition.startAnchor,
      openView: module.page,
    },
    {
      id: "verify",
      title: copy.common.quickSteps.verify,
      instruction: definition.verify,
      output: definition.verificationOutput,
      commonErrors: definition.verificationErrors,
      module: definition.module,
      anchor: definition.verifyAnchor || definition.outputAnchor || definition.startAnchor,
      openView: module.page,
    },
  ];
  const steps = definition.steps?.length
    ? definition.steps.map((step) => {
        const stepModule = step.module || definition.module;
        return {
          ...step,
          module: stepModule,
          openView: step.openView || TUTORIAL_MODULES[stepModule].page,
          presetId: null,
          scientificContractId: step.scientificContractId || definition.scientificContractId,
        };
      })
    : generatedSteps;
  return finalizeTutorial(prepared, {
    tutorialId,
    type: "quick",
    mode: "live",
    sourceKind: "live",
    level: definition.level || "basic",
    estimatedMinutes: definition.estimatedMinutes || Math.max(4, Math.ceil(steps.length * 1.2)),
    language: copy.lang,
    common: copy.common,
  }, steps);
}

function buildFixedExample(definition, copy) {
  const provenance = definition.provenance || TEACHING_EXAMPLE_PROVENANCE[definition.id];
  if (!provenance) throw new Error(`Missing fixed-example provenance: ${definition.id}`);
  const subjects = [
    ["context", copy.common.exampleSteps.context, definition.context],
    ["design", copy.common.exampleSteps.design, definition.design],
    ["evidence", copy.common.exampleSteps.evidence, definition.evidence],
    ["transfer", copy.common.exampleSteps.transfer, definition.transfer],
  ];
  const scientificContractId = definition.scientificContractId || "examples.synthetic_case";
  const prepared = {
    ...definition,
    scientificContractId,
    provenance: Object.freeze({ ...provenance }),
    presetId: null,
    nextGuideId: FIXED_EXAMPLE_CONTINUATIONS[definition.id] || null,
  };
  return finalizeTutorial(prepared, {
    tutorialId: definition.id,
    type: "example",
    mode: "fixed",
    sourceKind: "synthetic_case",
    level: definition.level || "basic-to-advanced",
    estimatedMinutes: 8,
    language: copy.lang,
    common: copy.common,
  }, subjects.map(([id, title, subject]) => ({
    id,
    title,
    instruction: subject.instruction,
    output: subject.output,
    commonErrors: subject.commonErrors,
    cannotConclude: subject.cannotConclude,
    module: definition.module,
    anchor: GUIDE_ANCHORS.EXAMPLES_CATALOG,
    openView: "examples",
    scientificContractId,
  })));
}

const MANUAL_LEARNING_METADATA = Object.freeze({
  "manual-data-contracts": Object.freeze({
    conceptIds: ["population", "endpoint", "provenance", "circularity"],
    citationIds: ["wilkinson-2016"],
  }),
  "manual-survival-robustness": Object.freeze({
    conceptIds: ["hazard_ratio", "continuous_primary", "proportional_hazards", "multiplicity_family"],
    citationIds: ["cox-1972", "schoenfeld-1982", "benjamini-hochberg-1995", "simonsohn-2020"],
  }),
  "manual-groups-pathways": Object.freeze({
    conceptIds: ["contrast_b_minus_a", "within_gene_zscore", "nes", "leading_edge", "circularity"],
    citationIds: ["welch-1947", "mann-whitney-1947", "subramanian-2005", "go-consortium-2023"],
  }),
  "manual-validation-generalization": Object.freeze({
    conceptIds: ["validation", "study_effect", "within_cancer_synthesis", "hierarchical_iqr_scale", "modified_hksj", "prediction_interval"],
    citationIds: ["higgins-thompson-2002", "int-hout-2014", "riley-2011"],
  }),
  "manual-reproducibility": Object.freeze({
    conceptIds: ["provenance", "estimand", "multiplicity_family"],
    citationIds: ["wilkinson-2016"],
  }),
});

function buildManual(manual, language) {
  const metadata = MANUAL_LEARNING_METADATA[manual.id] || {};
  const conceptIds = freezeList(metadata.conceptIds);
  const citationIds = freezeList(metadata.citationIds);
  return Object.freeze({
    ...manual,
    conceptIds,
    concepts: resolveTutorialConcepts(conceptIds, language),
    citationIds,
    citations: resolveTutorialCitations(citationIds),
    sections: Object.freeze(
      manual.sections.map((section) => Object.freeze({
        ...section,
        paragraphs: freezeList(section.paragraphs),
        checklist: freezeList(section.checklist),
      })),
    ),
  });
}

export function createCurriculum(copy) {
  const routes = Object.freeze(copy.routes.map((definition) => buildRoute(definition, copy)));
  const quickGuides = Object.freeze(
    copy.quickGuides.map((definition) => buildQuickGuide(definition, copy)),
  );
  const examples = Object.freeze(
    copy.examples.map((definition) => buildFixedExample(definition, copy)),
  );
  const manuals = Object.freeze(
    (copy.manuals || []).map((manual) => buildManual(manual, copy.lang)),
  );
  const tutorials = Object.freeze([...routes, ...quickGuides, ...examples]);
  const byId = Object.freeze(
    Object.fromEntries(tutorials.map((tutorial) => [tutorial.id, tutorial])),
  );

  return Object.freeze({
    lang: copy.lang,
    labels: Object.freeze({ ...copy.labels }),
    phases: Object.freeze({ ...copy.phases }),
    routes,
    quickGuides,
    examples,
    manuals,
    tutorials,
    byId,
  });
}

function continuationCycle(curriculum) {
  const state = new Map();
  const visit = (tutorialId) => {
    if (!tutorialId || !curriculum.byId[tutorialId]) return false;
    if (state.get(tutorialId) === "visiting") return true;
    if (state.get(tutorialId) === "done") return false;
    state.set(tutorialId, "visiting");
    if (visit(curriculum.byId[tutorialId].nextGuideId)) return true;
    state.set(tutorialId, "done");
    return false;
  };
  return curriculum.tutorials.some((tutorial) => visit(tutorial.id));
}

export function curriculumContractErrors(curriculum) {
  const errors = [];
  const routeIds = curriculum.routes.map((route) => route.id);
  if (JSON.stringify(routeIds) !== JSON.stringify(APPROVED_ROUTE_IDS)) {
    errors.push("Approved route IDs or order do not match the curriculum contract.");
  }
  for (const route of curriculum.routes) {
    if (route.mode !== "live" || route.steps.length !== 7) {
      errors.push(`${route.id} must be a seven-step live route.`);
    }
    const phases = route.steps.map((step) => step.phase);
    if (JSON.stringify(phases) !== JSON.stringify(SEVEN_LESSON_PATTERN)) {
      errors.push(`${route.id} does not follow the seven-lesson pattern.`);
    }
  }
  const quickModules = curriculum.quickGuides.map((guide) => guide.module);
  if (JSON.stringify(quickModules) !== JSON.stringify(QUICK_GUIDE_MODULE_ORDER)) {
    errors.push("Quick guides must cover every guide-enabled module in navigation order.");
  }
  for (const guide of curriculum.quickGuides) {
    const expectedCount = QUICK_GUIDE_STEP_COUNTS[guide.module];
    if (guide.steps.length !== expectedCount) {
      errors.push(`${guide.id} must contain exactly ${expectedCount} steps.`);
    }
  }
  for (const guide of curriculum.quickGuides) {
    const shape = guide.steps.map((step) => ({
      id: step.id,
      anchor: step.anchor,
      workspaceStepId: step.workspaceStepId || null,
    }));
    if (JSON.stringify(shape) !== JSON.stringify(QUICK_GUIDE_STEP_CONTRACTS[guide.module])) {
      errors.push(`${guide.id} must mirror its visible subsections before interpretation.`);
    }
  }
  if (curriculum.quickGuides.some(
    (guide) => guide.presetId || guide.steps.some((step) => step.presetId),
  )) {
    errors.push("Quick guides must explain the current workspace without applying presets.");
  }
  for (const tutorial of curriculum.tutorials) {
    if (tutorial.steps.length < 3 || tutorial.steps.length > 12) {
      errors.push(`${tutorial.id} must contain between three and twelve steps.`);
    }
    if (!TUTORIAL_SOURCE_KINDS.includes(tutorial.sourceKind)) {
      errors.push(`${tutorial.id} has an unknown source kind.`);
    }
    if (!SCIENTIFIC_CONTRACT_IDS.includes(tutorial.scientificContractId)) {
      errors.push(`${tutorial.id} references an unknown scientific contract.`);
    }
    if (!Number.isInteger(tutorial.estimatedMinutes) || tutorial.estimatedMinutes < 1) {
      errors.push(`${tutorial.id} must declare a positive estimated duration.`);
    }
    const objectiveIds = new Set(tutorial.objectives.map((objective) => objective.id));
    const coveredObjectives = new Set();
    if (!tutorial.objectives.length || tutorial.objectives.some((objective) => !objective.text)) {
      errors.push(`${tutorial.id} must declare observable learning objectives.`);
    }
    for (const requirement of tutorial.requirements) {
      if (!requirement.id || !requirement.capability) {
        errors.push(`${tutorial.id} has an invalid serializable requirement.`);
      }
    }
    for (const step of tutorial.steps) {
      if (!Object.values(GUIDE_ANCHORS).includes(step.anchor)) {
        errors.push(`${tutorial.id}/${step.id} references an unknown anchor.`);
      }
      if (!TUTORIAL_MODULES[step.module]) {
        errors.push(`${tutorial.id}/${step.id} references an unknown module.`);
      }
      if (!SCIENTIFIC_CONTRACT_IDS.includes(step.scientificContractId)) {
        errors.push(`${tutorial.id}/${step.id} references an unknown scientific contract.`);
      }
      for (const objectiveId of step.objectiveIds) {
        if (!objectiveIds.has(objectiveId)) {
          errors.push(`${tutorial.id}/${step.id} references unknown objective ${objectiveId}.`);
        }
        coveredObjectives.add(objectiveId);
      }
      for (const conceptId of step.conceptIds) {
        if (!TUTORIAL_CONCEPT_IDS.includes(conceptId)) {
          errors.push(`${tutorial.id}/${step.id} references unknown concept ${conceptId}.`);
        }
      }
      for (const citationId of step.citationIds) {
        if (!TUTORIAL_CITATION_IDS.includes(citationId)) {
          errors.push(`${tutorial.id}/${step.id} references unknown citation ${citationId}.`);
        }
      }
      for (const requirement of step.requirements) {
        if (!requirement.id || !requirement.capability) {
          errors.push(`${tutorial.id}/${step.id} has an invalid serializable requirement.`);
        }
      }
    }
    for (const objectiveId of objectiveIds) {
      if (!coveredObjectives.has(objectiveId)) {
        errors.push(`${tutorial.id} objective ${objectiveId} has no step coverage.`);
      }
    }
    if (tutorial.mode === "fixed" && (tutorial.presetId || tutorial.steps.some((step) => step.presetId))) {
      errors.push(`${tutorial.id} is fixed and cannot apply a live preset.`);
    }
    if (tutorial.mode === "fixed") {
      const provenance = tutorial.provenance || {};
      if (
        tutorial.sourceKind !== "synthetic_case"
        || !provenance.result_id
        || !provenance.pipeline_version
        || !/^\d{4}-\d{2}-\d{2}$/.test(provenance.snapshot_date || "")
        || !/^[a-f0-9]{64}$/.test(provenance.sha256 || "")
        || !/^tutorial-examples\/[a-z0-9-]+\.json$/.test(provenance.artifact_path || "")
      ) {
        errors.push(`${tutorial.id} has incomplete fixed-example provenance.`);
      }
    }
    if (tutorial.nextGuideId && !curriculum.byId[tutorial.nextGuideId]) {
      errors.push(`${tutorial.id} points to missing continuation ${tutorial.nextGuideId}.`);
    }
  }
  if (continuationCycle(curriculum)) {
    errors.push("Recommended tutorial continuations must be acyclic.");
  }
  const panCancerQuick = curriculum.byId["quick-pancancer"];
  if (panCancerQuick?.steps.some((step) => step.scientificContractId !== "pancancer.mode_aware")) {
    errors.push("The quick pan-cancer guide must use the mode-aware help contract.");
  }
  return errors;
}
