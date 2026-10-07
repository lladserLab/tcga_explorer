import { signatureInputState } from "../analysisRequestContract";

export function multiversePercentileState(cutpointMethods = [], rawValue = "") {
  const selected = cutpointMethods.includes("percentile");
  const value = Number(rawValue);
  const valid = Boolean(
    !selected
    || (Number.isFinite(value) && value >= 1 && value <= 99),
  );
  return {
    selected,
    value,
    valid,
    requestValue: selected && valid ? value : 60,
  };
}

export function multiverseSignatureProjection(rawValue, scoringMethods = []) {
  const result = signatureInputState(rawValue, { methods: scoringMethods });
  if (!result.valid) throw new Error(result.errors[0]);
  return result.genes;
}
