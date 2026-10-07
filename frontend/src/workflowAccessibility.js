/**
 * A step button controls the one panel that exists in the DOM. Inactive steps
 * intentionally omit aria-controls until their panel is rendered.
 */
export function activeWorkflowPanelId(idPrefix, stepId, isActive) {
  if (!isActive) return undefined;
  const prefix = String(idPrefix || "").trim();
  const step = String(stepId || "").trim();
  return prefix && step ? `${prefix}-panel-${step}` : undefined;
}
