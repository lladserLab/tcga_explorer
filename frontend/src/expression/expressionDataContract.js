/** Project release endpoint definitions onto an explicitly verified matrix population. */
export function endpointsForExpressionLayer(endpoints, layer) {
  const coverage = layer?.coverage?.endpoints;
  if (!coverage) return endpoints;
  return endpoints.map((endpoint) => {
    const linked = coverage[endpoint.value];
    if (!linked) return { ...endpoint, patients: 0, events: 0, available: false,
      reason: "No linked outcome records in this expression layer." };
    return { ...endpoint, patients: linked.patients, patient_count: linked.patients,
      events: linked.events, event_count: linked.events,
      available: Boolean(endpoint.available && linked.available),
      reason: !endpoint.available ? endpoint.reason : linked.reason };
  });
}

export function expressionCoverageLabel(layer) {
  const coverage = layer?.coverage;
  if (!coverage || !Number.isFinite(coverage.patient_count) || !Number.isFinite(coverage.sample_count)) return "";
  const number = (value) => value.toLocaleString("en-US");
  const unit = coverage.observation_unit === "paired_contrast" ? "paired contrasts" : "RNA profiles";
  return `${number(coverage.patient_count)} patients · ${number(coverage.sample_count)} ${unit}`;
}

export function expressionTissueLabel(layer) {
  const roles = layer?.coverage?.sample_roles || {};
  return [["primary_tumor", "primary tumor profiles"], ["adjacent_non_tumor", "adjacent tissue profiles"]]
    .filter(([role]) => Number.isFinite(roles[role]) && roles[role] > 0)
    .map(([role, label]) => `${roles[role].toLocaleString("en-US")} ${label}`).join(" · ");
}
