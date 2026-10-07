import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import PlotStylePreview from "./ScientificPlotPreview";
import { DEFAULT_PLOT_STYLE } from "./plotPreviewContract";


function previewForm(overrides = {}) {
  return {
    endpoint: "OS",
    expression_scale: "log2_tpm",
    gene_symbol: "CDC20",
    cutpoint_method: "median",
    time_unit: "months",
    show_confidence_interval: true,
    show_risk_table: true,
    plot_style: {
      ...DEFAULT_PLOT_STYLE,
      axis_text_bold: true,
      axis_text_italic: true,
      axis_title_bold: true,
      axis_title_italic: false,
      plot_frame: "box",
    },
    ...overrides,
  };
}


describe("scientific plot style preview", () => {
  it("shows the selected axis emphasis and full plot frame", () => {
    const markup = renderToStaticMarkup(
      <PlotStylePreview
        form={previewForm()}
        isCombinedMode={false}
        plotTitlePlaceholder="LIHC overall survival"
        previewTarget="survival"
      />,
    );

    expect(markup).toContain("plot-preview-frame");
    expect(markup).toContain("font-weight:700");
    expect(markup).toContain("font-style:italic");
    expect(markup).toContain("Box frame");
  });

  it("keeps open plots free of a preview boundary", () => {
    const markup = renderToStaticMarkup(
      <PlotStylePreview
        form={previewForm({
          plot_style: {
            ...DEFAULT_PLOT_STYLE,
            plot_frame: "open",
          },
        })}
        isCombinedMode={false}
        previewTarget="continuous"
      />,
    );

    expect(markup).not.toContain("plot-preview-frame");
    expect(markup).toContain("Open frame");
  });

  it("applies the shared frame contract to Cox model forests", () => {
    const markup = renderToStaticMarkup(
      <PlotStylePreview
        form={previewForm({
          show_risk_table: false,
          plot_style: {
            ...DEFAULT_PLOT_STYLE,
            plot_frame: "axes",
          },
        })}
        isCombinedMode={false}
        previewTarget="cox_forest"
      />,
    );

    expect(markup).toContain("plot-preview-frame");
    expect(markup).toContain("L axes");
  });

  it("previews only the selected multivariable rows", () => {
    const markup = renderToStaticMarkup(
      <PlotStylePreview
        form={previewForm({
          show_risk_table: false,
          plot_style: {
            ...DEFAULT_PLOT_STYLE,
            cox_forest: {
              ...DEFAULT_PLOT_STYLE.cox_forest,
              multivariable_display: "selected",
              multivariable_model_ids: ["stage_adjusted", "user_adjusted"],
            },
          },
        })}
        isCombinedMode={false}
        previewTarget="cox_forest"
      />,
    );

    expect(markup).toContain("Adjusted for ordinal stage");
    expect(markup).toContain("User-adjusted for Age");
    expect(markup).not.toContain("Adjusted for ordinal grade");
    expect(markup).not.toContain("Adjusted for ordinal stage and grade");
  });
});
