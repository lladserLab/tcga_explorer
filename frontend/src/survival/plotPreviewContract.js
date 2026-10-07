export const DEFAULT_PLOT_STYLE = {
  palette: ["#1f6f8b", "#c8842d", "#b94d48"],
  font_family: "sans",
  plot_aspect: "rectangular",
  base_font_size: 12,
  axis_text_size: 11,
  axis_text_bold: false,
  axis_text_italic: false,
  axis_title_size: 12,
  axis_title_bold: false,
  axis_title_italic: false,
  plot_frame: "open",
  show_grid: false,
  show_title: false,
  plot_title: "",
  continuous: {
    effect_color: "#1f6f8b",
    reference_color: "#75817e",
    show_title: true,
    plot_title: "",
    x_axis_title: "",
    y_axis_title: "",
  },
  cox_forest: {
    lower_hazard_color: "#1f6f8b",
    higher_hazard_color: "#b94d48",
    reference_color: "#7b8582",
    model_layout: "combined",
    multivariable_display: "all",
    multivariable_model_ids: [
      "stage_adjusted",
      "grade_adjusted",
      "stage_grade_adjusted",
      "user_adjusted",
    ],
    show_title: true,
    plot_title: "",
    univariable_plot_title: "",
    multivariable_plot_title: "",
    x_axis_title: "",
  },
};

export const PLOT_ARTIFACT_OPTIONS = [
  { value: "survival", label: "Survival" },
  { value: "continuous", label: "Continuous Cox" },
  { value: "cox_forest", label: "Cox models" },
];

export const DEFAULT_COMBINED_PALETTE = [
  "#1f6f8b",
  "#c8842d",
  "#5a6f9f",
  "#b94d48",
  "#6c7a77",
  "#7b6aa8",
  "#3c8c5f",
  "#c46a42",
  "#4b5f5b",
];

const UNITS_PER_INCH = 100;
const POINTS_PER_INCH = 72;

export function plotPointSize(value) {
  return Number(value) * UNITS_PER_INCH / POINTS_PER_INCH;
}

export function survivalRiskFraction(groupCount) {
  if (groupCount <= 4) return 0.25;
  return Math.min(0.45, 0.25 + (groupCount - 4) * 0.04);
}

export function survivalPreviewGeometry({
  aspect = "rectangular",
  showRiskTable = false,
  groupCount = 2,
} = {}) {
  const width = 10 * UNITS_PER_INCH;
  const riskFraction = showRiskTable ? survivalRiskFraction(groupCount) : 0;
  let height;
  if (aspect === "square") {
    height = showRiskTable ? width / (1 - riskFraction) : width;
  } else {
    const baseHeight = 6 * UNITS_PER_INCH;
    height = showRiskTable
      ? Math.max(7.8 * UNITS_PER_INCH, baseHeight / (1 - riskFraction))
      : baseHeight;
  }
  return {
    width,
    height,
    mainHeight: showRiskTable ? height * (1 - riskFraction) : height,
    riskFraction,
  };
}

export function continuousPreviewGeometry(aspect = "rectangular") {
  return {
    width: 9.5 * UNITS_PER_INCH,
    height: (aspect === "square" ? 9.5 : 5.7) * UNITS_PER_INCH,
  };
}

export function classicForestPreviewGeometry(rowCount = 1) {
  return {
    width: 9.5 * UNITS_PER_INCH,
    height: Math.max(3.8, 1.8 + Math.max(1, rowCount) * 0.55) * UNITS_PER_INCH,
  };
}

export function signaturePanelPreviewGeometry(
  signatureCount = 2,
  aspect = "rectangular",
) {
  return {
    width: (aspect === "square" ? 7.5 : 9.4) * UNITS_PER_INCH,
    height: Math.max(4.2, 2.9 + 0.42 * Math.max(1, signatureCount))
      * UNITS_PER_INCH,
  };
}

const KM_TIMES = [
  0,
  0.025,
  0.055,
  0.09,
  0.135,
  0.19,
  0.255,
  0.33,
  0.415,
  0.505,
  0.6,
  0.7,
  0.805,
  0.905,
  1,
];

const KM_BASE_SURVIVAL = [
  1,
  0.985,
  0.965,
  0.94,
  0.91,
  0.875,
  0.84,
  0.8,
  0.755,
  0.71,
  0.67,
  0.635,
  0.605,
  0.58,
  0.56,
];

function survivalEndpoints(groupCount) {
  if (groupCount === 2) return [0.46, 0.6];
  if (groupCount === 3) return [0.45, 0.55, 0.63];
  if (groupCount === 4) return [0.51, 0.61, 0.56, 0.45];
  return [0.64, 0.6, 0.57, 0.61, 0.56, 0.52, 0.55, 0.49, 0.44]
    .slice(0, groupCount);
}

export function createSurvivalPreviewSeries(groupCount = 2) {
  return survivalEndpoints(groupCount).map((endpoint, seriesIndex) => {
    const targetDrop = 1 - endpoint;
    const baseDrop = 1 - KM_BASE_SURVIVAL[KM_BASE_SURVIVAL.length - 1];
    const points = KM_TIMES.map((time, index) => {
      const survival = 1
        - (1 - KM_BASE_SURVIVAL[index]) * targetDrop / baseDrop;
      const uncertainty = 0.012
        + time * (0.064 + seriesIndex * 0.003)
        + (time > 0.75 ? (time - 0.75) * 0.05 : 0);
      return {
        time,
        survival,
        upper: Math.min(1, survival + uncertainty),
        lower: Math.max(0.025, survival - uncertainty),
      };
    });
    const censorTimes = [0.075, 0.16, 0.285, 0.46, 0.64, 0.79, 0.93]
      .map((time, index) => Math.min(0.985, time + seriesIndex * 0.008 + index * 0.002));
    const initialN = groupCount > 4
      ? Math.max(30, 46 - seriesIndex)
      : Math.max(80, 132 - seriesIndex * 4);
    const riskFractions = [1, 0.73, 0.49, 0.29, 0.12];
    return {
      points,
      censorTimes,
      riskCounts: riskFractions.map((fraction, index) => (
        index === riskFractions.length - 1
          ? Math.max(1, Math.round(initialN * fraction) - seriesIndex)
          : Math.max(1, Math.round(initialN * fraction) - Math.floor(seriesIndex / 2))
      )),
    };
  });
}

export function valueAtStep(points, time, key = "survival") {
  let value = points[0]?.[key] ?? 1;
  points.forEach((point) => {
    if (point.time <= time) value = point[key];
  });
  return value;
}

function stepCoordinates(points, xScale, yScale, key) {
  if (!points.length) return [];
  const coordinates = [[xScale(points[0].time), yScale(points[0][key])]];
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const point = points[index];
    coordinates.push(
      [xScale(point.time), yScale(previous[key])],
      [xScale(point.time), yScale(point[key])],
    );
  }
  return coordinates;
}

export function stepLinePath(points, xScale, yScale, key = "survival") {
  return stepCoordinates(points, xScale, yScale, key)
    .map(([x, y], index) => `${index ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
}

export function stepAreaPath(points, xScale, yScale) {
  const upper = stepCoordinates(points, xScale, yScale, "upper");
  const lower = stepCoordinates(points, xScale, yScale, "lower").reverse();
  return [...upper, ...lower]
    .map(([x, y], index) => `${index ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ")
    .concat(" Z");
}

export const CONTINUOUS_PREVIEW_PROFILE = [
  { x: 3, effect: 1.48, low: 0.78, high: 2.82 },
  { x: 3.25, effect: 1.38, low: 0.8, high: 2.4 },
  { x: 3.5, effect: 1.28, low: 0.82, high: 2 },
  { x: 3.75, effect: 1.19, low: 0.84, high: 1.68 },
  { x: 4, effect: 1.12, low: 0.86, high: 1.45 },
  { x: 4.25, effect: 1.06, low: 0.87, high: 1.29 },
  { x: 4.5, effect: 1.02, low: 0.88, high: 1.18 },
  { x: 4.75, effect: 0.99, low: 0.88, high: 1.11 },
  { x: 5, effect: 0.98, low: 0.89, high: 1.08 },
  { x: 5.25, effect: 1, low: 0.91, high: 1.1 },
  { x: 5.5, effect: 1.04, low: 0.92, high: 1.18 },
  { x: 5.75, effect: 1.1, low: 0.93, high: 1.3 },
  { x: 6, effect: 1.19, low: 0.95, high: 1.49 },
  { x: 6.25, effect: 1.3, low: 0.95, high: 1.78 },
  { x: 6.5, effect: 1.45, low: 0.94, high: 2.24 },
  { x: 6.75, effect: 1.64, low: 0.9, high: 2.98 },
  { x: 7, effect: 1.88, low: 0.82, high: 4.3 },
];

export const CLASSIC_COX_PREVIEW_MODELS = [
  {
    id: "univariable",
    label: "Univariable",
    hazardRatio: 0.78,
    low: 0.59,
    high: 1.04,
    pValue: 0.084,
  },
  {
    id: "stage_adjusted",
    label: "Adjusted for ordinal stage",
    hazardRatio: 0.84,
    low: 0.62,
    high: 1.13,
    pValue: 0.246,
  },
  {
    id: "grade_adjusted",
    label: "Adjusted for ordinal grade",
    hazardRatio: 0.76,
    low: 0.56,
    high: 1.03,
    pValue: 0.073,
  },
  {
    id: "stage_grade_adjusted",
    label: "Adjusted for ordinal stage and grade",
    hazardRatio: 0.82,
    low: 0.6,
    high: 1.12,
    pValue: 0.223,
  },
  {
    id: "user_adjusted",
    label: "User-adjusted for Age",
    hazardRatio: 0.79,
    low: 0.58,
    high: 1.07,
    pValue: 0.129,
  },
];

export const PANEL_MODEL_FAMILIES = [
  { id: "univariable", label: "Univariable", shape: "circle" },
  { id: "joint", label: "Joint", shape: "triangle" },
  { id: "adjusted", label: "Joint + clinical", shape: "square" },
];

const PANEL_EFFECTS = [
  {
    univariable: [0.72, 0.54, 0.97],
    joint: [0.82, 0.61, 1.09],
    adjusted: [0.86, 0.63, 1.16],
  },
  {
    univariable: [1.34, 0.98, 1.83],
    joint: [1.18, 0.84, 1.66],
    adjusted: [1.12, 0.79, 1.6],
  },
  {
    univariable: [0.91, 0.69, 1.21],
    joint: [0.97, 0.71, 1.32],
    adjusted: [1.02, 0.74, 1.41],
  },
  {
    univariable: [1.21, 0.9, 1.62],
    joint: [1.09, 0.79, 1.51],
    adjusted: [1.05, 0.75, 1.48],
  },
  {
    univariable: [0.83, 0.6, 1.14],
    joint: [0.88, 0.61, 1.27],
    adjusted: [0.92, 0.63, 1.35],
  },
  {
    univariable: [1.16, 0.85, 1.59],
    joint: [1.08, 0.76, 1.54],
    adjusted: [1.04, 0.72, 1.51],
  },
];

export function createPanelPreviewRows(signatureNames, familyIds = null) {
  const selectedFamilies = familyIds || PANEL_MODEL_FAMILIES.map(({ id }) => id);
  return signatureNames.map((signature, signatureIndex) => ({
    signature,
    estimates: selectedFamilies.map((family) => {
      const [effect, low, high] = PANEL_EFFECTS[
        signatureIndex % PANEL_EFFECTS.length
      ][family];
      return { family, effect, low, high };
    }),
  }));
}

export function logScalePosition(value, domainMin, domainMax, rangeMin, rangeMax) {
  const domainSpan = Math.log(domainMax) - Math.log(domainMin);
  const fraction = (Math.log(value) - Math.log(domainMin)) / domainSpan;
  return rangeMin + fraction * (rangeMax - rangeMin);
}

export function endpointPreviewLabel(endpoint) {
  return {
    OS: "Overall survival",
    DSS: "Disease-specific survival",
    DFI: "Disease-free interval",
    PFI: "Progression-free interval",
    PFS: "Progression-free survival",
    RFS: "Recurrence-free survival",
  }[String(endpoint || "").toUpperCase()] || "Survival";
}

export function formatPreviewPValue(value) {
  if (!Number.isFinite(value)) return "p = NA";
  if (value < 0.001) return "p < 0.001";
  return `p = ${value.toFixed(3)}`;
}

export function formatExportDimensions(geometry) {
  const width = geometry.width / UNITS_PER_INCH;
  const height = geometry.height / UNITS_PER_INCH;
  const format = (value) => (
    Number.isInteger(value) ? value.toFixed(0) : value.toFixed(1)
  );
  return `${format(width)} × ${format(height)} in`;
}
