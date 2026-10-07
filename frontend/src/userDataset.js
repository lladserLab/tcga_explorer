import Papa from "papaparse";

export const isLocalDesktop = () => import.meta.env.VITE_TRACE_LOCAL_DESKTOP === "true";
const tokenStorage = () => isLocalDesktop() ? window.localStorage : window.sessionStorage;

export const USER_EXPRESSION_MAX_BYTES = 100 * 1024 * 1024;
export const USER_CLINICAL_MAX_BYTES = 10 * 1024 * 1024;
export const USER_DATASET_STORAGE_KEY = "trace-explorer-user-dataset";
export const USER_DATASET_TOKEN_STORAGE_KEY = "trace-explorer-user-dataset-token";

const ID_PATTERNS = [
  /^sample_?id$/i,
  /^patient_?id$/i,
  /^case_?id$/i,
  /^subject_?id$/i,
  /^barcode$/i,
  /^id$/i,
];
const GENE_PATTERNS = [
  /^gene_?symbol$/i,
  /^hgnc_?symbol$/i,
  /^symbol$/i,
  /^gene$/i,
  /^feature$/i,
  /^gene_?id$/i,
];
const TIME_PATTERNS = [
  /^os_?(days?|months?|years?|time)$/i,
  /overall.*survival.*(time|days?|months?|years?)/i,
  /survival.*(time|days?|months?|years?)/i,
  /follow.?up.*(time|days?|months?|years?)/i,
  /^time$/i,
];
const EVENT_PATTERNS = [
  /^os_?(event|status)$/i,
  /overall.*survival.*(event|status)/i,
  /survival.*(event|status)/i,
  /^event$/i,
  /^status$/i,
  /^vital_?status$/i,
];
const COVARIATE_PATTERNS = {
  stage: [/^stage$/i, /pathologic.*stage/i, /clinical.*stage/i],
  grade: [/^grade$/i, /histologic.*grade/i],
  age_at_index: [/^age$/i, /age.*(diagnosis|index)/i],
  gender: [/^gender$/i, /^sex$/i],
  race: [/^race$/i, /ethnic/i],
};
const MISSING = new Set([
  "",
  "na",
  "n/a",
  "nan",
  "null",
  "none",
  "unknown",
  "not available",
  "not reported",
  ".",
]);

function normalize(value) {
  return String(value ?? "").trim();
}

function normalizedToken(value) {
  return normalize(value).toLowerCase();
}

function matchingHeader(headers, patterns, fallback = "") {
  return (
    headers.find((header) => patterns.some((pattern) => pattern.test(header))) ||
    fallback
  );
}

function parseTable(text, label, preview = 0) {
  const parsed = Papa.parse(text, {
    header: true,
    skipEmptyLines: "greedy",
    preview,
    transformHeader: normalize,
  });
  const blocking = parsed.errors.find(
    (error) => error.code !== "UndetectableDelimiter",
  );
  if (blocking) {
    throw new Error(
      `${label} could not be read${Number.isInteger(blocking.row) ? ` near row ${blocking.row + 2}` : ""}: ${blocking.message}`,
    );
  }
  const headers = parsed.meta.fields || [];
  if (!headers.length) {
    throw new Error(`${label} needs a header row.`);
  }
  if (new Set(headers).size !== headers.length) {
    throw new Error(`${label} contains duplicate column names.`);
  }
  return {
    headers,
    rows: parsed.data || [],
    delimiter: parsed.meta.delimiter,
  };
}

function uniqueObserved(rows, column) {
  const values = [];
  const seen = new Set();
  rows.forEach((row) => {
    const value = normalize(row[column]);
    const token = normalizedToken(value);
    if (MISSING.has(token) || seen.has(token)) return;
    seen.add(token);
    values.push(value);
  });
  return values;
}

function matchingCount(values, identifiers) {
  return values.reduce(
    (count, value) => count + (identifiers.has(normalize(value)) ? 1 : 0),
    0,
  );
}

function bestClinicalIdColumn(clinical, expression) {
  const named = matchingHeader(clinical.headers, ID_PATTERNS);
  const candidates = clinical.headers.map((column) => {
    const identifiers = new Set(
      clinical.rows.map((row) => normalize(row[column])).filter(Boolean),
    );
    const headerMatches = matchingCount(expression.headers, identifiers);
    const rowScores = expression.headers.map((expressionColumn) =>
      matchingCount(
        expression.rows.map((row) => row[expressionColumn]),
        identifiers,
      ),
    );
    return {
      column,
      score: Math.max(headerMatches, ...rowScores, 0),
      named: column === named,
    };
  });
  candidates.sort(
    (a, b) => b.score - a.score || Number(b.named) - Number(a.named),
  );
  return candidates[0]?.column || clinical.headers[0];
}

function inferOrientation(expression, clinical, clinicalIdColumn) {
  const clinicalIds = new Set(
    clinical.rows
      .map((row) => normalize(row[clinicalIdColumn]))
      .filter(Boolean),
  );
  const headerMatches = matchingCount(expression.headers, clinicalIds);
  const rowCandidates = expression.headers.map((column) => ({
    column,
    matches: matchingCount(
      expression.rows.map((row) => row[column]),
      clinicalIds,
    ),
  }));
  rowCandidates.sort((a, b) => b.matches - a.matches);
  const bestRow = rowCandidates[0] || {
    column: expression.headers[0],
    matches: 0,
  };
  const genesByRows = headerMatches >= bestRow.matches;
  return {
    orientation: genesByRows ? "genes_by_rows" : "samples_by_rows",
    expressionIdColumn: genesByRows
      ? matchingHeader(
          expression.headers,
          GENE_PATTERNS,
          expression.headers[0],
        )
      : bestRow.column,
    preliminaryMatches: Math.max(headerMatches, bestRow.matches),
    genesByRowsMatches: headerMatches,
    samplesByRowsMatches: bestRow.matches,
  };
}

function inferTimeUnit(column) {
  if (/month/i.test(column)) return "months";
  if (/year/i.test(column)) return "years";
  return "days";
}

function clinicalColumnProfile(rows, column) {
  const values = rows
    .map((row) => normalize(row[column]))
    .filter((value) => !MISSING.has(normalizedToken(value)));
  const unique = [...new Set(values.map(normalizedToken))];
  const numericCount = values.reduce((count, value) => (
    Number.isFinite(Number(value)) ? count + 1 : count
  ), 0);
  const numericFraction = values.length ? numericCount / values.length : 0;
  return {
    column,
    nonMissingCount: values.length,
    missingCount: Math.max(0, rows.length - values.length),
    uniqueCount: unique.length,
    numericFraction,
    inferredValueType:
      values.length && numericFraction >= 0.95 ? "numeric" : "categorical",
    categoricalLevelLimitExceeded: unique.length > 30,
    examples: unique.slice(0, 8),
  };
}

export function customClinicalVariableId(column) {
  const normalized = normalize(column)
    .replace(/[^A-Za-z0-9_.-]+/g, "_")
    .replace(/^[^A-Za-z]+/, "")
    .slice(0, 64);
  return normalized || "clinical_variable";
}

export function createCustomClinicalVariable(column, profile = {}) {
  return {
    source_column: column,
    id: customClinicalVariableId(column),
    label: normalize(column).replace(/[_-]+/g, " ") || "Clinical variable",
    value_type: profile.inferredValueType || "categorical",
    unit: "",
    timing: "unknown",
    expression_derived: false,
    description: "",
  };
}

export function customClinicalCandidates(inspection, mapping = {}) {
  if (!inspection) return [];
  const fixed = new Set([
    mapping.clinical_id_column,
    ...(mapping.has_survival_outcome !== false
      ? [mapping.time_column, mapping.event_column]
      : []),
    ...Object.values(mapping.covariates || {}),
    ...(mapping.custom_clinical_variables || []).map((item) => item.source_column),
  ].filter(Boolean));
  return (inspection.clinical.columnProfiles || []).filter(
    (profile) => !fixed.has(profile.column),
  );
}

export function validateCustomClinicalVariables(variables, inspection, mapping = {}) {
  const errors = [];
  const ids = new Set();
  const columns = new Set();
  const reservedIds = new Set([
    "patient_id", "sample_id", "case_id", "subject_id", "participant_id",
    "person_id", "individual_id", "donor_id", "barcode", "mrn", "time",
    "time_days", "event", "event_status", "survival_time", "followup_time",
    "follow_up_time", "os_time", "os_event", "os_status", "stage", "grade",
    "age_at_index", "gender", "race",
  ]);
  const directIdentifierColumns = new Set([
    "id", "patient_id", "sample_id", "case_id", "subject_id", "participant_id",
    "barcode", "name", "first_name", "last_name", "email", "phone", "address",
    "mrn", "medical_record_number", "full_name", "given_name", "family_name",
    "surname", "telephone", "email_address", "phone_number", "street_address",
    "date_of_birth", "birth_date", "dob",
  ]);
  const directIdentifierPattern = /(?:^|_)(?:patient|sample|case|subject|participant|person|individual|donor)_(?:id|identifier|number|barcode)(?:_|$)|(?:^|_)(?:mrn|medical_record_number|barcode|email|e_mail|phone|telephone|address|full_name|first_name|last_name|given_name|family_name|surname|date_of_birth|birth_date|dob)(?:_|$)/;
  const protectedColumns = new Set([
    mapping.clinical_id_column,
    ...(mapping.has_survival_outcome !== false
      ? [mapping.time_column, mapping.event_column]
      : []),
    ...Object.values(mapping.covariates || {}),
  ].filter(Boolean).map((value) => String(value).toLowerCase()));
  const profiles = new Map(
    (inspection?.clinical?.columnProfiles || []).map((profile) => [profile.column, profile]),
  );
  if ((variables || []).length > 10) {
    errors.push("Map no more than 10 custom clinical variables.");
  }
  (variables || []).forEach((variable, index) => {
    const label = variable.label || `Custom variable ${index + 1}`;
    if (!variable.source_column) errors.push(`${label}: choose a clinical column.`);
    if (!String(variable.label || "").trim()) {
      errors.push(`Custom variable ${index + 1}: display label is required.`);
    }
    if (!/^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(variable.id || "")) {
      errors.push(`${label}: ID must start with a letter and use only letters, numbers, dot, dash or underscore.`);
    }
    const id = String(variable.id || "").toLowerCase();
    if (reservedIds.has(id) || id.startsWith("cdr.") || id.startsWith("metadata.")) {
      errors.push(`${label}: analysis ID is reserved.`);
    }
    if (ids.has(id)) errors.push(`${label}: variable IDs must be unique.`);
    ids.add(id);
    const sourceColumn = String(variable.source_column || "").toLowerCase();
    if (columns.has(sourceColumn)) errors.push(`${label}: each source column can be mapped once.`);
    columns.add(sourceColumn);
    if (protectedColumns.has(sourceColumn)) {
      errors.push(`${label}: source column is already assigned to the endpoint or a standard covariate.`);
    }
    const normalizedSource = sourceColumn.replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
    if (
      directIdentifierColumns.has(normalizedSource)
      || directIdentifierPattern.test(normalizedSource)
    ) {
      errors.push(`${label}: source column appears to contain direct identifiers.`);
    }
    const profile = profiles.get(variable.source_column);
    if (variable.value_type === "categorical" && profile?.categoricalLevelLimitExceeded) {
      errors.push(`${label}: categorical variables may contain at most 30 observed levels.`);
    }
    if (![
      "baseline", "pre_treatment", "on_treatment", "post_treatment",
      "post_baseline", "outcome", "unknown",
    ].includes(variable.timing || "unknown")) {
      errors.push(`${label}: measurement timing is not supported.`);
    }
  });
  return errors;
}

export async function inspectUserDatasetFiles(
  expressionFile,
  clinicalFile,
) {
  if (!expressionFile || !clinicalFile) {
    throw new Error("Choose one expression table and one patient-metadata table.");
  }
  if (expressionFile.size > USER_EXPRESSION_MAX_BYTES) {
    throw new Error("The expression table exceeds the 100 MB upload limit.");
  }
  if (clinicalFile.size > USER_CLINICAL_MAX_BYTES) {
    throw new Error("The patient-metadata table exceeds the 10 MB upload limit.");
  }
  const [expressionPreviewText, clinicalText] = await Promise.all([
    expressionFile.slice(0, 4 * 1024 * 1024).text(),
    clinicalFile.text(),
  ]);
  const previewLimit = 4 * 1024 * 1024;
  const lastCompleteLine = Math.max(
    expressionPreviewText.lastIndexOf("\n"),
    expressionPreviewText.lastIndexOf("\r"),
  );
  const expressionText =
    expressionFile.size > previewLimit && lastCompleteLine > 0
      ? expressionPreviewText.slice(0, lastCompleteLine)
      : expressionPreviewText;
  const expression = parseTable(
    expressionText,
    "Expression table",
    80,
  );
  const clinical = parseTable(clinicalText, "Patient-metadata table");
  if (!clinical.rows.length) {
    throw new Error("The patient-metadata table does not contain patient rows.");
  }
  const clinicalIdColumn = bestClinicalIdColumn(clinical, expression);
  const orientation = inferOrientation(
    expression,
    clinical,
    clinicalIdColumn,
  );
  const timeColumn = matchingHeader(
    clinical.headers,
    TIME_PATTERNS,
  );
  const eventColumn = matchingHeader(
    clinical.headers,
    EVENT_PATTERNS,
  );
  const eventValues = eventColumn
    ? uniqueObserved(clinical.rows, eventColumn)
    : [];
  const covariates = Object.fromEntries(
    Object.entries(COVARIATE_PATTERNS).map(([key, patterns]) => [
      key,
      matchingHeader(clinical.headers, patterns) || null,
    ]),
  );
  return {
    expression: {
      name: expressionFile.name,
      bytes: expressionFile.size,
      headers: expression.headers,
      previewRows: expression.rows.slice(0, 5),
      delimiter: expression.delimiter,
    },
    clinical: {
      name: clinicalFile.name,
      bytes: clinicalFile.size,
      headers: clinical.headers,
      rowCount: clinical.rows.length,
      previewRows: clinical.rows.slice(0, 5),
      delimiter: clinical.delimiter,
      observedValuesByColumn: Object.fromEntries(
        clinical.headers.map((column) => [
          column,
          uniqueObserved(clinical.rows, column).slice(0, 25),
        ]),
      ),
      columnProfiles: clinical.headers.map((column) =>
        clinicalColumnProfile(clinical.rows, column)
      ),
    },
    suggestions: {
      expression_orientation: orientation.orientation,
      expression_id_column: orientation.expressionIdColumn,
      clinical_id_column: clinicalIdColumn,
      time_column: timeColumn,
      event_column: eventColumn,
      event_value: eventValues[0] || "",
      censored_value: eventValues[1] || "",
      event_values: eventValues,
      has_survival_outcome: Boolean(
        timeColumn
        && eventColumn
        && timeColumn !== eventColumn
        && eventValues.length === 2
      ),
      time_unit: inferTimeUnit(timeColumn),
      endpoint: "OS",
      expression_unit: "",
      covariates,
    },
    matching: {
      preliminary: true,
      matchedIdentifiers: orientation.preliminaryMatches,
      genesByRowsMatches: orientation.genesByRowsMatches,
      samplesByRowsMatches: orientation.samplesByRowsMatches,
    },
  };
}

export function eventValuesForColumn(inspection, column) {
  if (!inspection || !column) return [];
  return inspection.clinical.observedValuesByColumn?.[column] || [];
}

export function defaultEventMapping(values) {
  const normalized = values.map((value) => ({
    value,
    token: String(value).trim().toLowerCase(),
  }));
  const event = normalized.find(({ token }) => (
    ["1", "1.0", "event", "dead", "deceased", "died", "yes", "true"].includes(token)
    || /^1\s*[:_-]/.test(token)
  ))?.value;
  const censored = normalized.find(({ token }) => (
    ["0", "0.0", "censored", "alive", "living", "no", "false"].includes(token)
    || /^0\s*[:_-]/.test(token)
  ))?.value;
  const remainingAfterEvent = event
    ? values.find((value) => value !== event)
    : "";
  const remainingAfterCensor = censored
    ? values.find((value) => value !== censored)
    : "";
  return {
    event: event || remainingAfterCensor || "",
    censored: censored || remainingAfterEvent || "",
  };
}

const LOCAL_PROJECTS_KEY = "trace-explorer-local-projects";

export function loadLocalProjects() {
  if (!isLocalDesktop()) return [];
  try {
    return JSON.parse(window.localStorage.getItem(LOCAL_PROJECTS_KEY) || "[]")
      .filter(project => project.id && project.access_token && project.privacy?.retention_policy === "local_until_deleted");
  } catch { return []; }
}

export function forgetLocalProject(id) {
  if (!isLocalDesktop()) return;
  window.localStorage.setItem(LOCAL_PROJECTS_KEY, JSON.stringify(loadLocalProjects().filter(project => project.id !== id)));
}

export function loadUserDatasetReference() {
  try {
    const payload = JSON.parse(
      window.localStorage.getItem(USER_DATASET_STORAGE_KEY) || "null",
    );
    if (!payload?.id || (!payload.expires_at && !(isLocalDesktop() && payload.privacy?.retention_policy === "local_until_deleted"))) return null;
    const accessToken = tokenStorage().getItem(
      USER_DATASET_TOKEN_STORAGE_KEY,
    );
    if (!accessToken) {
      window.localStorage.removeItem(USER_DATASET_STORAGE_KEY);
      return null;
    }
    if (payload.expires_at && Date.parse(payload.expires_at) <= Date.now()) {
      window.localStorage.removeItem(USER_DATASET_STORAGE_KEY);
      tokenStorage().removeItem(USER_DATASET_TOKEN_STORAGE_KEY);
      return null;
    }
    return { ...payload, access_token: accessToken };
  } catch {
    return null;
  }
}

export function persistUserDatasetReference(dataset) {
  try {
    if (!dataset) {
      window.localStorage.removeItem(USER_DATASET_STORAGE_KEY);
      tokenStorage().removeItem(USER_DATASET_TOKEN_STORAGE_KEY);
      return;
    }
    if (!dataset.access_token) {
      throw new Error("Private dataset access token is unavailable.");
    }
    if (isLocalDesktop() && dataset.privacy?.retention_policy === "local_until_deleted") {
      const projects = loadLocalProjects().filter(project => project.id !== dataset.id);
      projects.push({id: dataset.id, name: dataset.name, expires_at: null, privacy: dataset.privacy, access_token: dataset.access_token});
      window.localStorage.setItem(LOCAL_PROJECTS_KEY, JSON.stringify(projects));
    }
    window.localStorage.setItem(
      USER_DATASET_STORAGE_KEY,
      JSON.stringify({
        id: dataset.id,
        name: dataset.name,
        expires_at: dataset.expires_at,
        ...(isLocalDesktop() ? {privacy: dataset.privacy} : {}),
      }),
    );
    tokenStorage().setItem(
      USER_DATASET_TOKEN_STORAGE_KEY,
      dataset.access_token,
    );
  } catch {
    // The active in-memory dataset remains usable when storage is unavailable.
  }
}

export function loadUserDatasetAccessToken() {
  try {
    return tokenStorage().getItem(USER_DATASET_TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function humanFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
