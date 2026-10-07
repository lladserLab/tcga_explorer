import { describe, expect, it } from "vitest";

import {
  DEFAULT_PLOT_STYLE,
  classicForestPreviewGeometry,
  continuousPreviewGeometry,
  createPanelPreviewRows,
  createSurvivalPreviewSeries,
  formatExportDimensions,
  plotPointSize,
  signaturePanelPreviewGeometry,
  survivalPreviewGeometry,
  survivalRiskFraction,
  valueAtStep,
} from "./plotPreviewContract";

describe("scientific plot preview contract", () => {
  it("keeps presentation defaults backward compatible", () => {
    expect(DEFAULT_PLOT_STYLE).toMatchObject({
      axis_text_bold: false,
      axis_text_italic: false,
      axis_title_bold: false,
      axis_title_italic: false,
      plot_frame: "open",
      cox_forest: {
        multivariable_display: "all",
        multivariable_model_ids: [
          "stage_adjusted",
          "grade_adjusted",
          "stage_grade_adjusted",
          "user_adjusted",
        ],
      },
    });
  });

  it("matches survival export dimensions from the R renderer", () => {
    expect(survivalPreviewGeometry()).toMatchObject({
      width: 1000,
      height: 600,
      mainHeight: 600,
    });
    expect(survivalPreviewGeometry({
      showRiskTable: true,
      groupCount: 2,
    })).toMatchObject({
      width: 1000,
      height: 800,
      mainHeight: 600,
      riskFraction: 0.25,
    });
    expect(survivalPreviewGeometry({
      aspect: "square",
      showRiskTable: true,
      groupCount: 2,
    }).height).toBeCloseTo(1333.33, 1);
  });

  it("expands the risk-table allocation for dense grouped analyses", () => {
    expect(survivalRiskFraction(4)).toBe(0.25);
    expect(survivalRiskFraction(9)).toBe(0.45);
  });

  it("matches continuous and forest renderer canvases", () => {
    expect(continuousPreviewGeometry("rectangular")).toEqual({
      width: 950,
      height: 570,
    });
    expect(continuousPreviewGeometry("square")).toEqual({
      width: 950,
      height: 950,
    });
    expect(classicForestPreviewGeometry(3)).toEqual({
      width: 950,
      height: 380,
    });
    expect(classicForestPreviewGeometry(5)).toEqual({
      width: 950,
      height: 455,
    });
    expect(signaturePanelPreviewGeometry(4)).toEqual({
      width: 940,
      height: 458,
    });
  });

  it("uses point-sized typography in the export coordinate system", () => {
    expect(plotPointSize(12)).toBeCloseTo(16.67, 1);
  });

  it("keeps deterministic, monotone survival fixtures", () => {
    const series = createSurvivalPreviewSeries(3);
    expect(series).toHaveLength(3);
    series.forEach(({ points, riskCounts }) => {
      for (let index = 1; index < points.length; index += 1) {
        expect(points[index].survival).toBeLessThanOrEqual(
          points[index - 1].survival,
        );
      }
      expect(riskCounts).toHaveLength(5);
      expect(valueAtStep(points, 0.5)).toBeGreaterThan(0);
    });
  });

  it("builds every requested signature and model family", () => {
    const rows = createPanelPreviewRows(["A", "B"], ["joint", "adjusted"]);
    expect(rows).toHaveLength(2);
    expect(rows[0].estimates.map(({ family }) => family)).toEqual([
      "joint",
      "adjusted",
    ]);
    expect(formatExportDimensions(signaturePanelPreviewGeometry(2)))
      .toBe("9.4 × 4.2 in");
  });
});
