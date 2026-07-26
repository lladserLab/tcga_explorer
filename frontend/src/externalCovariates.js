import Papa from "papaparse";

export const EXTERNAL_COVARIATE_SCHEMA_VERSION =
  "tcga-trace-external-covariates-v1";
export const MAX_EXTERNAL_COVARIATES = 10;
export const MAX_EXTERNAL_COVARIATE_ROWS = 2000;
export const MAX_EXTERNAL_COVARIATE_FILE_BYTES = 2 * 1024 * 1024;

const PATIENT_ID_PATTERN = /^TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}$/;
const MISSING_TOKENS = new Set([
  "",
  "NA",
  "N/A",
  "NULL",
  "NONE",
  "NOT AVAILABLE",
  "NOT REPORTED",
  "UNKNOWN",
]);
const RESERVED_NAMES = new Set([
  "patient_id",
  "sample_barcode",
  "time_days",
  "event",
  "group",
  "expression_value",
  "age_at_index",
  "stage",
  "grade",
  "gender",
  "race",
]);

export function parseExternalCovariateCsv(csvText, sourceLabel = "") {
  const parsed = Papa.parse(csvText, {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (value) => String(value || "").trim(),
  });
  const parseError = parsed.errors.find(
    (error) => error.code !== "UndetectableDelimiter",
  );
  if (parseError) {
    throw new Error(
      `CSV parsing failed${Number.isInteger(parseError.row) ? ` at row ${parseError.row + 2}` : ""}: ${parseError.message}`,
    );
  }

  const headers = parsed.meta.fields || [];
  const patientHeader = headers.find(
    (header) => header.trim().toLowerCase() === "patient_id",
  );
  if (!patientHeader) {
    throw new Error(
      "The CSV requires a patient_id column with exact TCGA participant barcodes.",
    );
  }
  const variableHeaders = headers.filter((header) => header !== patientHeader);
  if (!variableHeaders.length) {
    throw new Error("The CSV must contain at least one covariate column.");
  }
  if (variableHeaders.length > MAX_EXTERNAL_COVARIATES) {
    throw new Error(
      `The CSV contains ${variableHeaders.length} covariates; the limit is ${MAX_EXTERNAL_COVARIATES}.`,
    );
  }
  if (!parsed.data.length) {
    throw new Error("The CSV does not contain any patient rows.");
  }
  if (parsed.data.length > MAX_EXTERNAL_COVARIATE_ROWS) {
    throw new Error(
      `The CSV contains ${parsed.data.length} rows; the limit is ${MAX_EXTERNAL_COVARIATE_ROWS}.`,
    );
  }

  const names = variableHeaders.map(normalizeExternalCovariateName);
  if (new Set(names).size !== names.length) {
    throw new Error(
      "Two or more CSV headers resolve to the same covariate name. Rename the columns and upload again.",
    );
  }

  const patientIds = new Set();
  const rows = parsed.data.map((rawRow, rowIndex) => {
    const patientId = String(rawRow[patientHeader] || "").trim().toUpperCase();
    if (!PATIENT_ID_PATTERN.test(patientId)) {
      throw new Error(
        `Row ${rowIndex + 2} has an invalid patient_id. Use an exact barcode such as TCGA-AB-1234.`,
      );
    }
    if (patientIds.has(patientId)) {
      throw new Error(`Duplicate patient_id at row ${rowIndex + 2}: ${patientId}.`);
    }
    patientIds.add(patientId);
    const values = {};
    variableHeaders.forEach((header, index) => {
      values[names[index]] = normalizeCsvValue(rawRow[header]);
    });
    return { patient_id: patientId, values };
  });

  const definitions = variableHeaders.map((header, index) =>
    inferExternalCovariateDefinition(header, names[index], rows),
  );
  return {
    schema_version: EXTERNAL_COVARIATE_SCHEMA_VERSION,
    source_label: String(sourceLabel || "").trim(),
    definitions,
    rows,
  };
}

export function updateExternalCovariateDefinition(
  dataset,
  covariateName,
  patch,
) {
  return {
    ...dataset,
    definitions: dataset.definitions.map((definition) =>
      definition.name === covariateName
        ? { ...definition, ...patch }
        : definition,
    ),
  };
}

export function changeExternalCovariateType(
  dataset,
  covariateName,
  valueType,
) {
  const values = externalCovariateValues(dataset, covariateName);
  const distinct = uniqueValues(values);
  if (valueType === "continuous") {
    if (!values.every((value) => Number.isFinite(Number(value)))) {
      throw new Error(
        `${covariateName} contains non-numeric values and cannot be continuous.`,
      );
    }
    return {
      ...updateExternalCovariateDefinition(dataset, covariateName, {
        value_type: "continuous",
        levels: [],
        reference_level: null,
        effect_unit: 1,
      }),
      rows: dataset.rows.map((row) => ({
        ...row,
        values: {
          ...row.values,
          [covariateName]:
            row.values[covariateName] === null
              ? null
              : Number(row.values[covariateName]),
        },
      })),
    };
  }
  if (distinct.length < 2) {
    throw new Error(
      `${covariateName} needs at least two observed levels for ${valueType} coding.`,
    );
  }
  if (distinct.length > 20) {
    throw new Error(
      `${covariateName} has ${distinct.length} levels; categorical and ordinal variables are limited to 20.`,
    );
  }
  const levels = distinct.map(String);
  return {
    ...updateExternalCovariateDefinition(dataset, covariateName, {
      value_type: valueType,
      levels,
      reference_level: valueType === "categorical" ? levels[0] : null,
      effect_unit: 1,
      unit: "",
    }),
    rows: dataset.rows.map((row) => ({
      ...row,
      values: {
        ...row.values,
        [covariateName]:
          row.values[covariateName] === null
            ? null
            : String(row.values[covariateName]),
      },
    })),
  };
}

export function reorderExternalCovariateLevel(
  dataset,
  covariateName,
  level,
  nextIndex,
) {
  const definition = dataset.definitions.find(
    (item) => item.name === covariateName,
  );
  if (!definition) return dataset;
  const currentIndex = definition.levels.indexOf(level);
  if (
    currentIndex < 0
    || nextIndex < 0
    || nextIndex >= definition.levels.length
  ) {
    return dataset;
  }
  const levels = [...definition.levels];
  levels.splice(currentIndex, 1);
  levels.splice(nextIndex, 0, level);
  return updateExternalCovariateDefinition(dataset, covariateName, { levels });
}

export function externalCovariateTypeOptions(dataset, covariateName) {
  const values = externalCovariateValues(dataset, covariateName);
  const distinct = uniqueValues(values);
  const options = [];
  if (values.length && values.every((value) => Number.isFinite(Number(value)))) {
    options.push("continuous");
  }
  if (distinct.length >= 2 && distinct.length <= 20) {
    options.push("categorical", "ordinal");
  }
  return [...new Set(options)];
}

function inferExternalCovariateDefinition(header, name, rows) {
  const values = externalCovariateValues({ rows }, name);
  const numeric =
    values.length > 0 && values.every((value) => Number.isFinite(Number(value)));
  if (numeric) {
    rows.forEach((row) => {
      if (row.values[name] !== null) {
        row.values[name] = Number(row.values[name]);
      }
    });
    return {
      name,
      label: humanizeHeader(header),
      value_type: "continuous",
      levels: [],
      reference_level: null,
      unit: "",
      effect_unit: 1,
      description: "",
    };
  }
  const levels = uniqueValues(values).map(String);
  if (levels.length < 2) {
    throw new Error(
      `${header} needs at least two non-missing values or levels.`,
    );
  }
  if (levels.length > 20) {
    throw new Error(
      `${header} has ${levels.length} text levels; categorical variables are limited to 20.`,
    );
  }
  return {
    name,
    label: humanizeHeader(header),
    value_type: "categorical",
    levels,
    reference_level: levels[0],
    unit: "",
    effect_unit: 1,
    description: "",
  };
}

function normalizeExternalCovariateName(header, index) {
  let normalized = String(header || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  if (!/^[a-z]/.test(normalized)) {
    normalized = `variable_${index + 1}_${normalized}`.replace(/_+$/g, "");
  }
  if (RESERVED_NAMES.has(normalized)) {
    normalized = `external_${normalized}`;
  }
  return normalized.slice(0, 32).replace(/_+$/g, "");
}

function normalizeCsvValue(value) {
  const normalized = String(value ?? "").trim();
  return MISSING_TOKENS.has(normalized.toUpperCase()) ? null : normalized;
}

function externalCovariateValues(dataset, covariateName) {
  return (dataset.rows || [])
    .map((row) => row.values[covariateName])
    .filter((value) => value !== null && value !== undefined);
}

function uniqueValues(values) {
  const seen = new Set();
  const unique = [];
  values.forEach((value) => {
    const key = String(value);
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(value);
    }
  });
  return unique;
}

function humanizeHeader(header) {
  const words = String(header || "")
    .trim()
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
  return words ? `${words.charAt(0).toUpperCase()}${words.slice(1)}` : "Covariate";
}
