import { curriculumContractErrors } from "./curriculumFactory";
import { curriculumEn } from "./curriculum.en";
import { scientificContractRegistryErrors } from "./scientificContracts";

export const TUTORIAL_CURRICULA = Object.freeze({
  en: curriculumEn,
});

export function getTutorialCurriculum() {
  return curriculumEn;
}

export function getTutorialById(tutorialId) {
  return curriculumEn.byId[tutorialId] || null;
}

export function hasTutorial(tutorialId) {
  return Boolean(getTutorialById(tutorialId));
}

export function tutorialStepCount(tutorialId) {
  return getTutorialById(tutorialId)?.steps.length || 0;
}

export function validateAllCurricula() {
  const errors = [...scientificContractRegistryErrors()];
  for (const curriculum of Object.values(TUTORIAL_CURRICULA)) {
    for (const error of curriculumContractErrors(curriculum)) {
      errors.push(`${curriculum.lang}: ${error}`);
    }
  }
  return errors;
}
