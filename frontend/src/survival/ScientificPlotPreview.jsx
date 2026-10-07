import React, { useId } from "react";

import { MAX_SIGNATURE_PANEL_SIZE } from "./signaturePanel";
import {
  CLASSIC_COX_PREVIEW_MODELS,
  CONTINUOUS_PREVIEW_PROFILE,
  DEFAULT_COMBINED_PALETTE,
  DEFAULT_PLOT_STYLE,
  PANEL_MODEL_FAMILIES,
  PLOT_ARTIFACT_OPTIONS,
  classicForestPreviewGeometry,
  continuousPreviewGeometry,
  createPanelPreviewRows,
  createSurvivalPreviewSeries,
  endpointPreviewLabel,
  formatExportDimensions,
  formatPreviewPValue,
  logScalePosition,
  plotPointSize,
  signaturePanelPreviewGeometry,
  stepAreaPath,
  stepLinePath,
  survivalPreviewGeometry,
  valueAtStep,
} from "./plotPreviewContract";

const FONT_FAMILIES = {
  serif: 'Georgia, "Times New Roman", serif',
  mono: 'ui-monospace, "SFMono-Regular", Consolas, monospace',
  sans: '"IBM Plex Sans Variable", "IBM Plex Sans", Aptos, sans-serif',
};

const SURVIVAL_TICKS = {
  days: ["0", "500", "1,000", "1,500", "2,000"],
  months: ["0", "30", "60", "90", "120"],
  years: ["0", "2", "4", "6", "8"],
};

function clamp(value, minimum, maximum, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric)
    ? Math.max(minimum, Math.min(maximum, numeric))
    : fallback;
}

function expressionScaleLabel(value) {
  return {
    log2_tpm: "log2(TPM + 1)",
    tpm: "TPM",
    fpkm: "FPKM",
    fpkm_uq: "FPKM-UQ",
    counts: "normalized counts",
  }[String(value || "").toLowerCase()] || "expression";
}

function uniqueGeneSymbols(text) {
  const seen = new Set();
  return String(text || "")
    .split(/[,+;\n]/)
    .map((item) => item.trim().split(":")[0]?.trim().toUpperCase())
    .filter((gene) => {
      if (!gene || seen.has(gene)) return false;
      seen.add(gene);
      return true;
    });
}

function combinedPalette(currentPalette, groupingMethod) {
  const required = groupingMethod === "tertiles" ? 9 : 4;
  const palette = Array.isArray(currentPalette)
    ? currentPalette.filter(Boolean)
    : [];
  if (palette.length >= required) return palette.slice(0, required);
  return DEFAULT_COMBINED_PALETTE.slice(0, required);
}

function previewGroupLabels(isCombinedMode, groupingMethod, cutpointMethod) {
  if (isCombinedMode && groupingMethod === "tertiles") {
    return [
      "Low × Low",
      "Low × Mid",
      "Low × High",
      "Mid × Low",
      "Mid × Mid",
      "Mid × High",
      "High × Low",
      "High × Mid",
      "High × High",
    ];
  }
  if (isCombinedMode) {
    return ["Low × Low", "Low × High", "High × Low", "High × High"];
  }
  if (cutpointMethod === "tertiles") return ["Low", "Mid", "High"];
  return ["Low", "High"];
}

function linePath(points, xScale, yScale, valueKey) {
  return points
    .map((point, index) => (
      `${index ? "L" : "M"} ${xScale(point.x).toFixed(2)} ${yScale(point[valueKey]).toFixed(2)}`
    ))
    .join(" ");
}

function ribbonPath(points, xScale, yScale) {
  const upper = points.map((point) => [xScale(point.x), yScale(point.high)]);
  const lower = [...points]
    .reverse()
    .map((point) => [xScale(point.x), yScale(point.low)]);
  return [...upper, ...lower]
    .map(([x, y], index) => `${index ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ")
    .concat(" Z");
}

function useScientificId(prefix) {
  const reactId = useId().replaceAll(":", "");
  return `${prefix}-${reactId}`;
}

function plotTextStyle(bold, italic) {
  return {
    fontWeight: bold ? 700 : 400,
    fontStyle: italic ? "italic" : "normal",
  };
}

function PlotPreviewFrame({
  mode = "open",
  left,
  right,
  top,
  bottom,
}) {
  if (mode === "open") return null;
  const path = mode === "box"
    ? `M ${left} ${top} H ${right} V ${bottom} H ${left} Z`
    : `M ${left} ${top} V ${bottom} H ${right}`;
  return <path className="plot-preview-frame" d={path} />;
}

export default function PlotStylePreview({
  form,
  isCombinedMode,
  isPanelMode = false,
  plotTitlePlaceholder,
  previewContext = "survival",
  previewGene = "",
  previewMethod = "",
  previewTarget = "survival",
}) {
  const plotStyle = {
    ...DEFAULT_PLOT_STYLE,
    ...(form.plot_style || {}),
  };
  const continuousStyle = {
    ...DEFAULT_PLOT_STYLE.continuous,
    ...(plotStyle.continuous || {}),
  };
  const coxForestStyle = {
    ...DEFAULT_PLOT_STYLE.cox_forest,
    ...(plotStyle.cox_forest || {}),
  };
  const activeTarget =
    (isCombinedMode || isPanelMode) && previewTarget === "continuous"
      ? "cox_forest"
      : previewTarget;
  const groupingMethod = form.combined_signature?.grouping_method || "median";
  const labels = previewGroupLabels(
    isCombinedMode,
    groupingMethod,
    form.cutpoint_method,
  );
  const groupCount = labels.length;
  const colors = isCombinedMode
    ? combinedPalette(plotStyle.palette, groupingMethod)
    : groupCount === 2
      ? [plotStyle.palette[0], plotStyle.palette[2] || plotStyle.palette[1]]
      : plotStyle.palette.slice(0, groupCount);
  const fontFamily = FONT_FAMILIES[plotStyle.font_family] || FONT_FAMILIES.sans;
  const baseFontSize = clamp(plotStyle.base_font_size, 8, 20, 12);
  const axisTextSize = clamp(plotStyle.axis_text_size, 6, 24, 11);
  const axisTitleSize = clamp(plotStyle.axis_title_size, 6, 26, 12);
  const frameLabel = {
    open: "Open frame",
    axes: "L axes",
    box: "Box frame",
  }[plotStyle.plot_frame] || "Open frame";
  const markerLabel =
    previewGene || uniqueGeneSymbols(form.gene_symbol || "")[0] || "Marker";
  const artifactLabel =
    PLOT_ARTIFACT_OPTIONS.find((option) => option.value === activeTarget)?.label
    || "Survival";
  const previewClass =
    activeTarget === "cox_forest" ? "content-driven" : plotStyle.plot_aspect;
  const panelSignatures = (form.signature_panel?.signatures || [])
    .slice(0, MAX_SIGNATURE_PANEL_SIZE);
  const geometry = activeTarget === "survival"
    ? survivalPreviewGeometry({
      aspect: plotStyle.plot_aspect,
      showRiskTable: form.show_risk_table,
      groupCount,
    })
    : activeTarget === "continuous"
      ? continuousPreviewGeometry(plotStyle.plot_aspect)
      : isPanelMode
        ? signaturePanelPreviewGeometry(
          Math.max(2, panelSignatures.length),
          plotStyle.plot_aspect,
        )
        : classicForestPreviewGeometry(
          coxForestStyle.model_layout === "separate" ? 4 : 5,
        );
  const facts = {
    survival: [
      `Export ${formatExportDimensions(geometry)}`,
      `${groupCount} groups`,
      `95% CI ${form.show_confidence_interval ? "shown" : "hidden"}`,
      `Risk table ${form.show_risk_table ? "shown" : "hidden"}`,
      frameLabel,
    ],
    continuous: [
      `Export ${formatExportDimensions(geometry)}`,
      "Log hazard-ratio axis",
      "Median reference",
      "95% confidence ribbon",
      frameLabel,
    ],
    cox_forest: [
      isPanelMode
        ? `Export ${formatExportDimensions(geometry)}`
        : "Export width 9.5 in",
      coxForestStyle.model_layout === "separate"
        ? "Separate model families"
        : "Combined model families",
      "Log hazard-ratio axis",
      isPanelMode ? "HR per +1 score SD" : "Estimate with 95% CI",
      frameLabel,
    ],
  }[activeTarget];

  return (
    <div
      className={`plot-style-preview ${previewClass} artifact-${activeTarget}${previewContext === "compare" ? " compare-cell-style-preview" : ""}`}
      style={{ fontFamily }}
    >
      <div className="plot-style-preview-toolbar">
        <span>
          {previewContext === "compare"
            ? `Representative ${artifactLabel}`
            : `${artifactLabel} export preview`}
        </span>
        <strong>
          <i aria-hidden="true" />
          {previewContext === "compare"
            ? `${previewGene} · ${previewMethod}`
            : "Simulated data"}
        </strong>
      </div>

      {activeTarget === "survival" && (
        <SurvivalPlotPreview
          form={form}
          plotStyle={plotStyle}
          plotTitlePlaceholder={plotTitlePlaceholder}
          colors={colors}
          labels={labels}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}
      {activeTarget === "continuous" && (
        <ContinuousCoxPlotPreview
          plotStyle={plotStyle}
          continuousStyle={continuousStyle}
          markerLabel={markerLabel}
          expressionLabel={expressionScaleLabel(form.expression_scale)}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}
      {activeTarget === "cox_forest" && (
        <CoxForestPlotPreview
          plotStyle={plotStyle}
          coxForestStyle={coxForestStyle}
          isCombinedMode={isCombinedMode}
          isPanelMode={isPanelMode}
          panelName={form.signature_panel?.name}
          panelSignatures={panelSignatures}
          fontFamily={fontFamily}
          baseFontSize={baseFontSize}
          axisTextSize={axisTextSize}
          axisTitleSize={axisTitleSize}
        />
      )}

      <div className="plot-style-preview-facts">
        {facts.map((fact) => <span key={fact}>{fact}</span>)}
      </div>
    </div>
  );
}

function SurvivalPlotPreview({
  form,
  plotStyle,
  plotTitlePlaceholder,
  colors,
  labels,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const clipId = useScientificId("survival-preview-clip");
  const groupCount = labels.length;
  const geometry = survivalPreviewGeometry({
    aspect: plotStyle.plot_aspect,
    showRiskTable: form.show_risk_table,
    groupCount,
  });
  const { width, height, mainHeight } = geometry;
  const baseText = plotPointSize(baseFontSize);
  const axisText = plotPointSize(axisTextSize);
  const axisTitle = plotPointSize(axisTitleSize);
  const axisTextStyle = plotTextStyle(
    plotStyle.axis_text_bold,
    plotStyle.axis_text_italic,
  );
  const axisTitleStyle = plotTextStyle(
    plotStyle.axis_title_bold,
    plotStyle.axis_title_italic,
  );
  const titleText = plotPointSize(baseFontSize + 3);
  const legendColumns = groupCount <= 3 ? groupCount : groupCount <= 4 ? 2 : 3;
  const legendRows = Math.ceil(groupCount / legendColumns);
  const legendItemWidth = groupCount > 4 ? 160 : 150;
  const legendWidth = 140 + legendColumns * legendItemWidth;
  const legendX = (width - legendWidth) / 2;
  const legendY = plotStyle.show_title ? 72 : 38;
  const plotLeft = 112;
  const plotRight = width - 48;
  const plotTop = legendY + legendRows * 25 + 24;
  const plotBottom = mainHeight - 96;
  const plotWidth = plotRight - plotLeft;
  const plotHeight = plotBottom - plotTop;
  const xScale = (time) => plotLeft + time * plotWidth;
  const yScale = (survival) => plotBottom - survival * plotHeight;
  const ticks = SURVIVAL_TICKS[form.time_unit] || SURVIVAL_TICKS.days;
  const tickFractions = [0, 0.25, 0.5, 0.75, 1];
  const yTicks = [1, 0.75, 0.5, 0.25, 0];
  const series = createSurvivalPreviewSeries(groupCount);
  const endpointLabel = endpointPreviewLabel(form.endpoint);
  const curveWidth = 3.8;
  const censorSize = 5.5;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Kaplan-Meier export preview with simulated data"
      style={{ fontFamily }}
    >
      <title>Kaplan-Meier export preview</title>
      <desc>
        Simulated step curves, censoring marks, confidence intervals, p-value
        and optional number-at-risk table using the selected export settings.
      </desc>
      <rect className="plot-preview-paper" x="0" y="0" width={width} height={height} />
      <defs>
        <clipPath id={clipId}>
          <rect x={plotLeft} y={plotTop} width={plotWidth} height={plotHeight} />
        </clipPath>
      </defs>

      {plotStyle.show_title && (
        <text
          className="plot-preview-title plot-preview-title-survival"
          x="58"
          y="38"
          fontSize={titleText}
        >
          {plotStyle.plot_title?.trim() || plotTitlePlaceholder}
        </text>
      )}

      <g className="plot-preview-legend" fontSize={baseText}>
        <text x={legendX} y={legendY + 4} className="plot-preview-legend-title">
          Expression group
        </text>
        {labels.map((label, index) => {
          const column = index % legendColumns;
          const row = Math.floor(index / legendColumns);
          const x = legendX + 140 + column * legendItemWidth;
          const y = legendY + row * 25;
          return (
            <g key={label}>
              {form.show_confidence_interval && (
                <rect
                  className="plot-preview-legend-band"
                  x={x}
                  y={y - 9}
                  width="29"
                  height="14"
                  fill={colors[index]}
                />
              )}
              <line x1={x} x2={x + 29} y1={y - 2} y2={y - 2} stroke={colors[index]} />
              <line x1={x + 15} x2={x + 15} y1={y - 8} y2={y + 4} stroke={colors[index]} />
              <text x={x + 38} y={y + 4}>{label}</text>
            </g>
          );
        })}
      </g>

      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {tickFractions.map((fraction) => (
            <line
              key={`survival-x-grid-${fraction}`}
              x1={xScale(fraction)}
              x2={xScale(fraction)}
              y1={plotTop}
              y2={plotBottom}
            />
          ))}
          {yTicks.map((value) => (
            <line
              key={`survival-y-grid-${value}`}
              x1={plotLeft}
              x2={plotRight}
              y1={yScale(value)}
              y2={yScale(value)}
            />
          ))}
        </g>
      )}

      {plotStyle.plot_frame !== "open" && (
        <g className="plot-preview-axis-ticks">
          {tickFractions.map((fraction) => (
            <line
              key={`survival-x-tick-${fraction}`}
              x1={xScale(fraction)}
              x2={xScale(fraction)}
              y1={plotBottom}
              y2={plotBottom + 6}
            />
          ))}
          {yTicks.map((value) => (
            <line
              key={`survival-y-tick-${value}`}
              x1={plotLeft - 6}
              x2={plotLeft}
              y1={yScale(value)}
              y2={yScale(value)}
            />
          ))}
        </g>
      )}
      <g
        className="plot-preview-y-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {yTicks.map((value) => (
          <text
            key={value}
            x={plotLeft - 15}
            y={yScale(value) + axisText * 0.34}
            textAnchor="end"
          >
            {value.toFixed(2)}
          </text>
        ))}
      </g>
      <g
        className="plot-preview-x-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {ticks.map((label, index) => (
          <text
            key={`${label}-${index}`}
            x={xScale(tickFractions[index])}
            y={plotBottom + 30}
            textAnchor="middle"
          >
            {label}
          </text>
        ))}
      </g>
      <text
        className="plot-preview-axis-title"
        x={(plotLeft + plotRight) / 2}
        y={mainHeight - 24}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
      >
        Time ({form.time_unit})
      </text>
      <text
        className="plot-preview-axis-title"
        x="31"
        y={(plotTop + plotBottom) / 2}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
        transform={`rotate(-90 31 ${(plotTop + plotBottom) / 2})`}
      >
        {endpointLabel} probability
      </text>

      <text
        className="plot-preview-p-value"
        x={plotRight - 4}
        y={plotTop - 11}
        textAnchor="end"
        fontSize={baseText}
      >
        p = 0.087
      </text>

      <g clipPath={`url(#${clipId})`}>
        {form.show_confidence_interval && (
          <g className="plot-preview-ci-bands">
            {series.map((item, index) => (
              <path
                key={`ci-${labels[index]}`}
                d={stepAreaPath(item.points, xScale, yScale)}
                fill={colors[index]}
              />
            ))}
          </g>
        )}
        <g className="plot-preview-curves">
          {series.map((item, index) => (
            <path
              key={labels[index]}
              d={stepLinePath(item.points, xScale, yScale)}
              stroke={colors[index]}
              style={{ strokeWidth: curveWidth }}
            />
          ))}
        </g>
        <g className="plot-preview-censors">
          {series.flatMap((item, seriesIndex) => (
            item.censorTimes.map((time, censorIndex) => {
              const x = xScale(time);
              const y = yScale(valueAtStep(item.points, time));
              return (
                <g
                  key={`${labels[seriesIndex]}-${censorIndex}`}
                  stroke={colors[seriesIndex]}
                >
                  <line x1={x - censorSize} x2={x + censorSize} y1={y} y2={y} />
                  <line x1={x} x2={x} y1={y - censorSize} y2={y + censorSize} />
                </g>
              );
            })
          ))}
        </g>
      </g>
      <PlotPreviewFrame
        mode={plotStyle.plot_frame}
        left={plotLeft}
        right={plotRight}
        top={plotTop}
        bottom={plotBottom}
      />

      {form.show_risk_table && (
        <RiskTablePreview
          colors={colors}
          labels={labels}
          series={series}
          ticks={ticks}
          tickFractions={tickFractions}
          xScale={xScale}
          width={width}
          height={height}
          mainHeight={mainHeight}
          plotLeft={plotLeft}
          plotRight={plotRight}
          showGrid={plotStyle.show_grid}
          baseText={baseText}
          axisText={axisText}
          axisTitle={axisTitle}
          axisTextStyle={axisTextStyle}
          axisTitleStyle={axisTitleStyle}
          timeUnit={form.time_unit}
        />
      )}
    </svg>
  );
}

function RiskTablePreview({
  colors,
  labels,
  series,
  ticks,
  tickFractions,
  xScale,
  width,
  height,
  mainHeight,
  plotLeft,
  plotRight,
  showGrid,
  baseText,
  axisText,
  axisTitle,
  axisTextStyle,
  axisTitleStyle,
  timeUnit,
}) {
  const sectionTop = mainHeight + 15;
  const rowStart = sectionTop + 55;
  const availableHeight = height - rowStart - 80;
  const rowGap = labels.length > 1
    ? Math.min(32, Math.max(22, availableHeight / labels.length))
    : 30;
  const lastRowY = rowStart + Math.max(0, labels.length - 1) * rowGap;
  const axisY = lastRowY + 30;
  const groupAxisY = (rowStart + lastRowY) / 2;

  return (
    <g className="plot-preview-risk-table">
      <text
        x={plotLeft}
        y={sectionTop + 23}
        fontSize={Math.max(plotPointSize(11), baseText + plotPointSize(2))}
        fontWeight="700"
      >
        Number at risk
      </text>
      <text
        className="plot-preview-axis-title"
        x="28"
        y={groupAxisY}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
        transform={`rotate(-90 28 ${groupAxisY})`}
      >
        Expression group
      </text>
      {showGrid && (
        <g className="plot-preview-grid">
          {tickFractions.map((fraction) => (
            <line
              key={`risk-x-grid-${fraction}`}
              x1={xScale(fraction)}
              x2={xScale(fraction)}
              y1={rowStart - 20}
              y2={axisY + 7}
            />
          ))}
          {labels.map((label, index) => (
            <line
              key={`risk-y-grid-${label}`}
              x1={plotLeft - 12}
              x2={plotRight}
              y1={rowStart + index * rowGap + 6}
              y2={rowStart + index * rowGap + 6}
            />
          ))}
        </g>
      )}
      {labels.map((label, rowIndex) => {
        const y = rowStart + rowIndex * rowGap;
        return (
          <g key={label} fontSize={axisText} style={axisTextStyle}>
            <text
              x={plotLeft - 46}
              y={y + axisText * 0.34}
              textAnchor="end"
              fill={colors[rowIndex]}
            >
              {label}
            </text>
            {series[rowIndex].riskCounts.map((value, columnIndex) => (
              <text
                key={`${label}-${columnIndex}`}
                x={xScale(tickFractions[columnIndex])}
                y={y + axisText * 0.34}
                textAnchor="middle"
              >
                {value}
              </text>
            ))}
          </g>
        );
      })}
      <g
        className="plot-preview-x-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {ticks.map((label, index) => (
          <text
            key={`risk-${label}-${index}`}
            x={xScale(tickFractions[index])}
            y={axisY + 24}
            textAnchor="middle"
          >
            {label}
          </text>
        ))}
      </g>
      <text
        className="plot-preview-axis-title"
        x={(plotLeft + plotRight) / 2}
        y={Math.min(height - 15, axisY + 54)}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
      >
        Time ({timeUnit})
      </text>
      <rect
        className="plot-preview-canvas-guard"
        x={width - 1}
        y={height - 1}
        width="1"
        height="1"
      />
    </g>
  );
}

function ContinuousCoxPlotPreview({
  plotStyle,
  continuousStyle,
  markerLabel,
  expressionLabel,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const clipId = useScientificId("continuous-preview-clip");
  const geometry = continuousPreviewGeometry(plotStyle.plot_aspect);
  const { width, height } = geometry;
  const baseText = plotPointSize(baseFontSize);
  const axisText = plotPointSize(axisTextSize);
  const axisTitle = plotPointSize(axisTitleSize);
  const axisTextStyle = plotTextStyle(
    plotStyle.axis_text_bold,
    plotStyle.axis_text_italic,
  );
  const axisTitleStyle = plotTextStyle(
    plotStyle.axis_title_bold,
    plotStyle.axis_title_italic,
  );
  const titleText = plotPointSize(baseFontSize + 3);
  const title = continuousStyle.plot_title?.trim()
    || "Continuous expression effect";
  const xAxisTitle = continuousStyle.x_axis_title?.trim()
    || `${markerLabel} ${expressionLabel}`;
  const yAxisTitle = continuousStyle.y_axis_title?.trim()
    || "Hazard ratio relative to median";
  const plotLeft = 92;
  const plotRight = width - 34;
  const plotTop = continuousStyle.show_title ? 104 : 74;
  const plotBottom = height - 82;
  const xDomain = [3, 7];
  const yDomain = [0.4, 4.4];
  const xScale = (value) => (
    plotLeft
    + (value - xDomain[0]) / (xDomain[1] - xDomain[0])
      * (plotRight - plotLeft)
  );
  const yScale = (value) => logScalePosition(
    value,
    yDomain[0],
    yDomain[1],
    plotBottom,
    plotTop,
  );
  const xTicks = [3, 4, 5, 6, 7];
  const yTicks = [0.5, 1, 2, 4];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Continuous Cox spline export preview with simulated data"
      style={{ fontFamily }}
    >
      <title>Continuous Cox spline export preview</title>
      <desc>
        Simulated hazard-ratio profile on a logarithmic scale with a 95 percent
        confidence ribbon and median reference.
      </desc>
      <rect className="plot-preview-paper" x="0" y="0" width={width} height={height} />
      <defs>
        <clipPath id={clipId}>
          <rect
            x={plotLeft}
            y={plotTop}
            width={plotRight - plotLeft}
            height={plotBottom - plotTop}
          />
        </clipPath>
      </defs>
      {continuousStyle.show_title && (
        <text
          className="plot-preview-title"
          x="70"
          y="37"
          fontSize={titleText}
        >
          {title}
        </text>
      )}
      <text
        className="plot-preview-subtitle"
        x="70"
        y={continuousStyle.show_title ? 69 : 39}
        fontSize={baseText}
      >
        Restricted cubic spline HR relative to median; Spline vs linear p = 0.184
      </text>

      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {xTicks.map((value) => (
            <line
              key={`continuous-x-grid-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={plotTop}
              y2={plotBottom}
            />
          ))}
          {yTicks.map((value) => (
            <line
              key={`continuous-y-grid-${value}`}
              x1={plotLeft}
              x2={plotRight}
              y1={yScale(value)}
              y2={yScale(value)}
            />
          ))}
        </g>
      )}

      <g clipPath={`url(#${clipId})`}>
        <line
          className="plot-preview-reference dashed"
          x1={plotLeft}
          x2={plotRight}
          y1={yScale(1)}
          y2={yScale(1)}
          stroke={continuousStyle.reference_color}
        />
        <line
          className="plot-preview-reference dotted"
          x1={xScale(5.25)}
          x2={xScale(5.25)}
          y1={plotTop}
          y2={plotBottom}
          stroke={continuousStyle.reference_color}
        />
        <path
          className="plot-preview-effect-ribbon"
          fill={continuousStyle.effect_color}
          d={ribbonPath(CONTINUOUS_PREVIEW_PROFILE, xScale, yScale)}
        />
        <path
          className="plot-preview-effect-line"
          stroke={continuousStyle.effect_color}
          d={linePath(CONTINUOUS_PREVIEW_PROFILE, xScale, yScale, "effect")}
        />
      </g>
      <PlotPreviewFrame
        mode={plotStyle.plot_frame}
        left={plotLeft}
        right={plotRight}
        top={plotTop}
        bottom={plotBottom}
      />

      {plotStyle.plot_frame !== "open" && (
        <g className="plot-preview-axis-ticks">
          {xTicks.map((value) => (
            <line
              key={`continuous-x-tick-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={plotBottom}
              y2={plotBottom + 6}
            />
          ))}
          {yTicks.map((value) => (
            <line
              key={`continuous-y-tick-${value}`}
              x1={plotLeft - 6}
              x2={plotLeft}
              y1={yScale(value)}
              y2={yScale(value)}
            />
          ))}
        </g>
      )}
      <g
        className="plot-preview-y-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {yTicks.map((value) => (
          <text
            key={value}
            x={plotLeft - 14}
            y={yScale(value) + axisText * 0.34}
            textAnchor="end"
          >
            {value}
          </text>
        ))}
      </g>
      <g
        className="plot-preview-x-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {xTicks.map((value) => (
          <text
            key={value}
            x={xScale(value)}
            y={plotBottom + 29}
            textAnchor="middle"
          >
            {value.toFixed(1)}
          </text>
        ))}
      </g>
      <text
        className="plot-preview-axis-title"
        x={(plotLeft + plotRight) / 2}
        y={height - 18}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
      >
        {xAxisTitle}
      </text>
      <text
        className="plot-preview-axis-title"
        x="26"
        y={(plotTop + plotBottom) / 2}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
        transform={`rotate(-90 26 ${(plotTop + plotBottom) / 2})`}
      >
        {yAxisTitle}
      </text>
    </svg>
  );
}

function CoxForestPlotPreview({
  plotStyle,
  coxForestStyle,
  isCombinedMode,
  isPanelMode,
  panelName,
  panelSignatures,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  if (isPanelMode) {
    return (
      <SignaturePanelForestPreview
        plotStyle={plotStyle}
        coxForestStyle={coxForestStyle}
        panelName={panelName}
        panelSignatures={panelSignatures}
        fontFamily={fontFamily}
        baseFontSize={baseFontSize}
        axisTextSize={axisTextSize}
        axisTitleSize={axisTitleSize}
      />
    );
  }

  const commonProps = {
    plotStyle,
    coxForestStyle,
    isCombinedMode,
    fontFamily,
    baseFontSize,
    axisTextSize,
    axisTitleSize,
  };
  const multivariableRows = coxForestStyle.multivariable_display === "selected"
    ? CLASSIC_COX_PREVIEW_MODELS.slice(1).filter((row) => (
      (coxForestStyle.multivariable_model_ids || []).includes(row.id)
    ))
    : CLASSIC_COX_PREVIEW_MODELS.slice(1);
  const displayedRows = [CLASSIC_COX_PREVIEW_MODELS[0], ...multivariableRows];
  if (coxForestStyle.model_layout === "separate") {
    return (
      <div
        className="cox-preview-split"
        role="group"
        aria-label="Separate Cox forest export previews with simulated data"
      >
        <div>
          <span className="cox-preview-family-label">Univariable output</span>
          <ClassicCoxForestPreviewFigure
            {...commonProps}
            title={coxForestStyle.univariable_plot_title?.trim()
              || "Univariable Cox model"}
            rows={CLASSIC_COX_PREVIEW_MODELS.slice(0, 1)}
            ariaLabel="Univariable Cox forest export preview with simulated data"
          />
        </div>
        <div>
          <span className="cox-preview-family-label">Multivariable output</span>
          <ClassicCoxForestPreviewFigure
            {...commonProps}
            title={coxForestStyle.multivariable_plot_title?.trim()
              || "Multivariable Cox models"}
            rows={multivariableRows}
            ariaLabel="Multivariable Cox forest export preview with simulated data"
          />
        </div>
      </div>
    );
  }

  return (
    <ClassicCoxForestPreviewFigure
      {...commonProps}
      title={coxForestStyle.plot_title?.trim()
        || "Cox proportional hazards models"}
      rows={displayedRows}
      ariaLabel="Combined Cox forest export preview with simulated data"
    />
  );
}

function ClassicCoxForestPreviewFigure({
  plotStyle,
  coxForestStyle,
  isCombinedMode,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
  title,
  rows,
  ariaLabel,
}) {
  const geometry = classicForestPreviewGeometry(rows.length);
  const { width, height } = geometry;
  const baseText = plotPointSize(baseFontSize);
  const axisText = plotPointSize(axisTextSize);
  const axisTitle = plotPointSize(axisTitleSize);
  const axisTextStyle = plotTextStyle(
    plotStyle.axis_text_bold,
    plotStyle.axis_text_italic,
  );
  const axisTitleStyle = plotTextStyle(
    plotStyle.axis_title_bold,
    plotStyle.axis_title_italic,
  );
  const titleText = plotPointSize(baseFontSize + 4);
  const xAxisTitle = coxForestStyle.x_axis_title?.trim()
    || "Hazard ratio (log scale)";
  const verticalShift = coxForestStyle.show_title ? 0 : -20;
  const rowStart = 150 + verticalShift;
  const axisY = height - 65;
  const rowGap = rows.length > 1
    ? Math.min(52, (axisY - 28 - rowStart) / (rows.length - 1))
    : 0;
  const forestLeft = 325;
  const forestRight = 570;
  const domain = [0.25, 4];
  const xScale = (value) => logScalePosition(
    value,
    domain[0],
    domain[1],
    forestLeft,
    forestRight,
  );
  const xTicks = [0.25, 0.5, 1, 2, 4];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel}
      style={{ fontFamily }}
    >
      <title>{title}</title>
      <desc>
        Simulated Cox hazard-ratio estimates, 95 percent confidence intervals
        and p-values on the same canvas used by the export renderer.
      </desc>
      <rect className="plot-preview-paper" x="0" y="0" width={width} height={height} />
      {coxForestStyle.show_title && (
        <text className="plot-preview-title" x="28" y="34" fontSize={titleText}>
          {title}
        </text>
      )}
      <text
        className="plot-preview-subtitle"
        x="28"
        y={coxForestStyle.show_title ? 67 : 37}
        fontSize={plotPointSize(baseFontSize + 1)}
      >
        {isCombinedMode
          ? "High × High vs Low × Low expression group"
          : "High vs Low expression group"}
      </text>
      <g
        className="plot-preview-forest-header"
        fontSize={baseText}
        transform={`translate(0 ${verticalShift})`}
      >
        <text x="18" y="104">Model</text>
        <text x="604" y="104">Estimate (95% CI)</text>
        <text x="928" y="104" textAnchor="end">p-value</text>
      </g>

      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {xTicks.map((value) => (
            <line
              key={`forest-grid-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={122 + verticalShift}
              y2={axisY}
            />
          ))}
        </g>
      )}
      <line
        className="plot-preview-reference dashed"
        x1={xScale(1)}
        x2={xScale(1)}
        y1={122 + verticalShift}
        y2={axisY}
        stroke={coxForestStyle.reference_color}
      />

      <g
        className="plot-preview-forest-rows"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {rows.map((row, index) => {
          const y = rowStart + index * rowGap;
          const direction = row.hazardRatio < 1 ? "lower" : "higher";
          const color = direction === "lower"
            ? coxForestStyle.lower_hazard_color
            : coxForestStyle.higher_hazard_color;
          const estimate = `${row.hazardRatio.toFixed(2)} (${row.low.toFixed(2)}-${row.high.toFixed(2)})`;
          return (
            <g key={row.label}>
              <text x="300" y={y + axisText * 0.34} textAnchor="end">
                {row.label}
              </text>
              <line
                className="plot-preview-forest-ci"
                x1={xScale(row.low)}
                x2={xScale(row.high)}
                y1={y}
                y2={y}
                stroke={color}
              />
              <circle
                className="plot-preview-forest-point"
                cx={xScale(row.hazardRatio)}
                cy={y}
                r="6.2"
                fill={color}
              />
              <text x="604" y={y + axisText * 0.34}>{estimate}</text>
              <text x="928" y={y + axisText * 0.34} textAnchor="end">
                {formatPreviewPValue(row.pValue)}
              </text>
            </g>
          );
        })}
      </g>
      <PlotPreviewFrame
        mode={plotStyle.plot_frame}
        left={forestLeft}
        right={forestRight}
        top={122 + verticalShift}
        bottom={axisY}
      />

      {plotStyle.plot_frame !== "open" && (
        <g className="plot-preview-axis-ticks">
          {xTicks.map((value) => (
            <line
              key={`forest-tick-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={axisY}
              y2={axisY + 6}
            />
          ))}
        </g>
      )}
      <g
        className="plot-preview-x-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {xTicks.map((value) => (
          <text
            key={value}
            x={xScale(value)}
            y={axisY + 27}
            textAnchor="middle"
          >
            {value}
          </text>
        ))}
      </g>
      <text
        className="plot-preview-axis-title"
        x={(forestLeft + forestRight) / 2}
        y={height - 12}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
      >
        {xAxisTitle}
      </text>
    </svg>
  );
}

function SignaturePanelForestPreview({
  plotStyle,
  coxForestStyle,
  panelName,
  panelSignatures,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
}) {
  const signatureNames = panelSignatures.length
    ? panelSignatures.map((signature, index) => (
      signature.name?.trim() || `Signature ${index + 1}`
    ))
    : ["Immune effector", "Checkpoint"];
  const commonProps = {
    plotStyle,
    coxForestStyle,
    signatureNames,
    fontFamily,
    baseFontSize,
    axisTextSize,
    axisTitleSize,
  };

  if (coxForestStyle.model_layout === "separate") {
    return (
      <div
        className="cox-preview-split"
        role="group"
        aria-label="Separate signature-panel forest export previews with simulated data"
      >
        <div>
          <span className="cox-preview-family-label">Univariable output</span>
          <SignaturePanelForestFigure
            {...commonProps}
            title={coxForestStyle.univariable_plot_title?.trim()
              || "Signature panel: univariable Cox"}
            familyIds={["univariable"]}
            ariaLabel="Signature-panel univariable forest preview with simulated data"
          />
        </div>
        <div>
          <span className="cox-preview-family-label">Joint model output</span>
          <SignaturePanelForestFigure
            {...commonProps}
            title={coxForestStyle.multivariable_plot_title?.trim()
              || "Signature panel: joint Cox"}
            familyIds={["joint", "adjusted"]}
            ariaLabel="Signature-panel joint forest preview with simulated data"
          />
        </div>
      </div>
    );
  }

  return (
    <SignaturePanelForestFigure
      {...commonProps}
      title={coxForestStyle.plot_title?.trim()
        || `${panelName?.trim() || "Signature panel"} Cox models`}
      familyIds={PANEL_MODEL_FAMILIES.map(({ id }) => id)}
      ariaLabel="Combined signature-panel forest preview with simulated data"
    />
  );
}

function ForestPointMark({
  shape,
  x,
  y,
  color,
  size = 6,
  className = "",
}) {
  if (shape === "triangle") {
    return (
      <path
        className={className}
        d={`M ${x} ${y - size} L ${x + size} ${y + size * 0.75} L ${x - size} ${y + size * 0.75} Z`}
        fill={color}
      />
    );
  }
  if (shape === "square") {
    return (
      <rect
        className={className}
        x={x - size * 0.8}
        y={y - size * 0.8}
        width={size * 1.6}
        height={size * 1.6}
        fill={color}
      />
    );
  }
  return (
    <circle
      className={className}
      cx={x}
      cy={y}
      r={size * 0.85}
      fill={color}
    />
  );
}

function SignaturePanelForestFigure({
  plotStyle,
  coxForestStyle,
  signatureNames,
  familyIds,
  fontFamily,
  baseFontSize,
  axisTextSize,
  axisTitleSize,
  title,
  ariaLabel,
}) {
  const geometry = signaturePanelPreviewGeometry(
    signatureNames.length,
    plotStyle.plot_aspect,
  );
  const { width, height } = geometry;
  const baseText = plotPointSize(baseFontSize);
  const axisText = plotPointSize(axisTextSize);
  const axisTitle = plotPointSize(axisTitleSize);
  const axisTextStyle = plotTextStyle(
    plotStyle.axis_text_bold,
    plotStyle.axis_text_italic,
  );
  const axisTitleStyle = plotTextStyle(
    plotStyle.axis_title_bold,
    plotStyle.axis_title_italic,
  );
  const titleText = plotPointSize(baseFontSize + 2);
  const xAxisTitle = coxForestStyle.x_axis_title?.trim()
    || "Hazard ratio (log scale)";
  const rows = createPanelPreviewRows(signatureNames, familyIds);
  const families = PANEL_MODEL_FAMILIES.filter(({ id }) => familyIds.includes(id));
  const plotLeft = width < 800 ? 185 : 215;
  const plotRight = width - 36;
  const plotTop = coxForestStyle.show_title ? 108 : 78;
  const plotBottom = height - 126;
  const xDomain = [0.35, 3];
  const xScale = (value) => logScalePosition(
    value,
    xDomain[0],
    xDomain[1],
    plotLeft,
    plotRight,
  );
  const xTicks = [0.5, 1, 2];
  const rowGap = rows.length > 1
    ? (plotBottom - plotTop) / (rows.length - 1)
    : 0;
  const dodge = families.length === 3
    ? [-11, 0, 11]
    : families.length === 2
      ? [-6, 6]
      : [0];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel}
      style={{ fontFamily }}
    >
      <title>{title}</title>
      <desc>
        Simulated signature main effects for the univariable, joint and
        clinically adjusted Cox model families.
      </desc>
      <rect className="plot-preview-paper" x="0" y="0" width={width} height={height} />
      {coxForestStyle.show_title && (
        <text className="plot-preview-title" x="34" y="37" fontSize={titleText}>
          {title}
        </text>
      )}
      <text
        className="plot-preview-subtitle"
        x="34"
        y={coxForestStyle.show_title ? 68 : 38}
        fontSize={baseText}
      >
        Cause-specific Cox main effects, HR per +1 within-panel score SD; 286 common patients
      </text>

      {plotStyle.show_grid && (
        <g className="plot-preview-grid">
          {xTicks.map((value) => (
            <line
              key={`panel-grid-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={plotTop - 16}
              y2={plotBottom + 16}
            />
          ))}
        </g>
      )}
      <line
        className="plot-preview-reference solid"
        x1={xScale(1)}
        x2={xScale(1)}
        y1={plotTop - 16}
        y2={plotBottom + 16}
        stroke={coxForestStyle.reference_color}
      />

      <g
        className="plot-preview-panel-rows"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {rows.map((row, rowIndex) => {
          const y = rows.length === 1
            ? (plotTop + plotBottom) / 2
            : plotTop + rowIndex * rowGap;
          return (
            <g key={row.signature}>
              <text
                className="plot-preview-panel-signature"
                x={plotLeft - 18}
                y={y + axisText * 0.34}
                textAnchor="end"
                style={axisTextStyle}
              >
                {row.signature}
              </text>
              {row.estimates.map((estimate, estimateIndex) => {
                const family = families.find(({ id }) => id === estimate.family);
                const pointY = y + dodge[estimateIndex];
                const color = estimate.effect < 1
                  ? coxForestStyle.lower_hazard_color
                  : coxForestStyle.higher_hazard_color;
                return (
                  <g key={estimate.family}>
                    <line
                      className="plot-preview-panel-ci"
                      x1={xScale(estimate.low)}
                      x2={xScale(estimate.high)}
                      y1={pointY}
                      y2={pointY}
                      stroke={color}
                    />
                    <ForestPointMark
                      shape={family?.shape}
                      x={xScale(estimate.effect)}
                      y={pointY}
                      color={color}
                      className="plot-preview-panel-point"
                    />
                  </g>
                );
              })}
            </g>
          );
        })}
      </g>
      <PlotPreviewFrame
        mode={plotStyle.plot_frame}
        left={plotLeft}
        right={plotRight}
        top={plotTop - 16}
        bottom={plotBottom + 20}
      />

      {plotStyle.plot_frame !== "open" && (
        <g className="plot-preview-axis-ticks">
          {xTicks.map((value) => (
            <line
              key={`panel-tick-${value}`}
              x1={xScale(value)}
              x2={xScale(value)}
              y1={plotBottom + 20}
              y2={plotBottom + 26}
            />
          ))}
        </g>
      )}
      <g
        className="plot-preview-x-labels"
        fontSize={axisText}
        style={axisTextStyle}
      >
        {xTicks.map((value) => (
          <text
            key={value}
            x={xScale(value)}
            y={plotBottom + 48}
            textAnchor="middle"
          >
            {value}
          </text>
        ))}
      </g>
      <text
        className="plot-preview-axis-title"
        x={(plotLeft + plotRight) / 2}
        y={plotBottom + 76}
        textAnchor="middle"
        fontSize={axisTitle}
        style={axisTitleStyle}
      >
        {xAxisTitle}
      </text>

      <g
        className="plot-preview-panel-legend"
        fontSize={Math.max(plotPointSize(9), baseText * 0.78)}
      >
        <g transform={`translate(${plotLeft - 5} ${height - 27})`}>
          <line x1="0" x2="22" y1="0" y2="0" stroke={coxForestStyle.lower_hazard_color} />
          <circle cx="11" cy="0" r="4" fill={coxForestStyle.lower_hazard_color} />
          <text x="30" y="4">Lower hazard</text>
          <line x1="130" x2="152" y1="0" y2="0" stroke={coxForestStyle.higher_hazard_color} />
          <circle cx="141" cy="0" r="4" fill={coxForestStyle.higher_hazard_color} />
          <text x="160" y="4">Higher hazard</text>
        </g>
        <g transform={`translate(${Math.min(width - 310, plotLeft + 330)} ${height - 27})`}>
          {families.map((family, index) => {
            const x = index * 105;
            return (
              <g key={family.id} transform={`translate(${x} 0)`}>
                <ForestPointMark
                  shape={family.shape}
                  x={0}
                  y={0}
                  color={coxForestStyle.reference_color}
                  size={5}
                />
                <text x="10" y="4">{family.label}</text>
              </g>
            );
          })}
        </g>
      </g>
    </svg>
  );
}
