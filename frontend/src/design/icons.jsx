import React, { forwardRef } from "react";
import {
  AlertCircle,
  Archive,
  ArrowDownToLine,
  BarChart3,
  BookOpen,
  BookOpenCheck,
  CalendarDays,
  ChartSpline,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Crosshair,
  Database,
  Dna,
  FileSpreadsheet,
  FileText,
  GitCompareArrows,
  Image,
  Info,
  Loader2,
  Network,
  Orbit,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PieChart,
  Play,
  Search,
  SlidersHorizontal,
  Table2,
  X,
} from "lucide-react";
import "./icons.css";

/**
 * @input A semantic role plus a named size, tone and optional accessible label.
 * @output TraceIcon, ModuleIcon and IconButton primitives for the full interface.
 * @position The sole Lucide boundary and semantic icon registry for TCGA-TRACE.
 *
 * SYNC: when this contract changes, update icons.test.jsx, docs/ICON_SYSTEM.md
 * and DESIGN.md as described in frontend/AGENTS.md.
 */
const GLYPH_ICON_REGISTRY = Object.freeze({
  "action.back": ChevronLeft,
  "action.close": X,
  "action.configure": SlidersHorizontal,
  "action.copy": ClipboardList,
  "action.download": ArrowDownToLine,
  "action.expand": ChevronDown,
  "action.next": ChevronRight,
  "action.palette": Palette,
  "action.run": Play,
  "action.search": Search,
  "action.sidebarClose": PanelLeftClose,
  "action.sidebarOpen": PanelLeftOpen,
  "data.calendar": CalendarDays,
  "data.cohort": Database,
  "data.compare": GitCompareArrows,
  "data.composition": PieChart,
  "data.endpoint": Crosshair,
  "data.expression": BarChart3,
  "data.gene": Dna,
  "data.network": Network,
  "data.orbit": Orbit,
  "data.table": Table2,
  "data.trend": ChartSpline,
  "document.api": FileText,
  "document.guide": BookOpen,
  "document.reference": BookOpenCheck,
  "file.archive": Archive,
  "file.audit": ClipboardList,
  "file.csv": FileSpreadsheet,
  "file.image": Image,
  "file.text": FileText,
  "status.caution": AlertCircle,
  "status.error": AlertCircle,
  "status.info": Info,
  "status.loading": Loader2,
  "status.success": CheckCircle2,
});

const MODULE_ICON_REGISTRY = Object.freeze({
  "module.dataset": { kind: "dataset", family: "dataset" },
  "module.geneAnalysis": { kind: "gene-analysis", family: "molecular" },
  "module.survivalEndpoint": { kind: "survival-endpoint", family: "endpoint" },
  "module.rnaScale": { kind: "rna-scale", family: "molecular" },
  "module.stratification": { kind: "stratification", family: "comparison" },
  "module.clinicalFilters": { kind: "clinical-filters", family: "comparison" },
  "module.plotOutput": { kind: "plot-output", family: "trace" },
  "module.plotStyle": { kind: "plot-style", family: "trace" },
  "module.comparisonDataset": { kind: "comparison-dataset", family: "comparison" },
  "module.markersCutpoints": { kind: "markers-cutpoints", family: "comparison" },
  "module.specificationCurve": { kind: "specification-curve", family: "comparison" },
  "module.sessionHistory": { kind: "session-history", family: "trace" },
  "module.panCancerQuery": { kind: "pancancer-query", family: "trace" },
  "module.outcomeModel": { kind: "outcome-model", family: "endpoint" },
  "module.forest": { kind: "forest", family: "trace" },
  "module.concordance": { kind: "concordance", family: "comparison" },
  "module.evidence": { kind: "evidence", family: "trace" },
  "module.precision": { kind: "precision", family: "trace" },
  "module.cohortResults": { kind: "cohort-results", family: "dataset" },
  "module.recurrence": { kind: "recurrence", family: "comparison" },
  "module.frequency": { kind: "frequency", family: "comparison" },
  "module.meta": { kind: "meta", family: "trace" },
  "module.burden": { kind: "burden", family: "dataset" },
  "module.immunePrograms": { kind: "immune-programs", family: "molecular" },
  "module.extremes": { kind: "extremes", family: "comparison" },
  "module.cohortEffects": { kind: "cohort-effects", family: "comparison" },
  "module.api": { kind: "api", family: "trace" },
  "module.aiConnectors": { kind: "ai-connectors", family: "trace" },
  "module.methods": { kind: "methods", family: "trace" },
  "module.endpointCoverage": { kind: "endpoint-coverage", family: "endpoint" },
  "module.cohortLandscape": { kind: "cohort-landscape", family: "dataset" },
  "module.sampleTypes": { kind: "sample-types", family: "dataset" },
  "module.vitalStatus": { kind: "vital-status", family: "endpoint" },
  "module.primarySites": { kind: "primary-sites", family: "dataset" },
  "module.age": { kind: "age", family: "dataset" },
  "module.metadata": { kind: "metadata", family: "dataset" },
  "module.biologicalAnnotations": { kind: "biological-annotations", family: "molecular" },
  "module.cohortTable": { kind: "cohort-table", family: "dataset" },
  "navigation.home": { kind: "nav-home", family: "trace" },
  "navigation.analysis": { kind: "nav-analysis", family: "molecular" },
  "navigation.compare": { kind: "nav-compare", family: "comparison" },
  "navigation.multiverse": { kind: "nav-multiverse", family: "comparison" },
  "navigation.session": { kind: "session-history", family: "trace" },
  "navigation.panCancer": { kind: "nav-pancancer", family: "trace" },
  "navigation.examples": { kind: "nav-examples", family: "trace" },
  "navigation.dataset": { kind: "nav-summary", family: "dataset" },
  "navigation.api": { kind: "nav-api", family: "trace" },
  "navigation.methods": { kind: "nav-help", family: "trace" },
});

export const TRACE_ICON_ROLES = Object.freeze(Object.keys(GLYPH_ICON_REGISTRY));
export const MODULE_ICON_ROLES = Object.freeze(Object.keys(MODULE_ICON_REGISTRY));
export const TRACE_ICON_SIZES = Object.freeze(["xsm", "sm", "md", "lg"]);
export const TRACE_ICON_TONES = Object.freeze([
  "inherit",
  "primary",
  "secondary",
  "accent",
  "success",
  "caution",
  "error",
  "disabled",
]);
export const MODULE_ICON_FRAMES = Object.freeze(["compact", "section", "navigation"]);

function classNames(...values) {
  return values.filter(Boolean).join(" ");
}

function accessibleIconProps(label) {
  const accessibleLabel = typeof label === "string" ? label.trim() : "";
  return accessibleLabel
    ? { role: "img", "aria-label": accessibleLabel }
    : { "aria-hidden": true };
}

function requireGlyphRole(role) {
  const Glyph = GLYPH_ICON_REGISTRY[role];
  if (!Glyph) {
    throw new Error(`Unknown TCGA-TRACE glyph icon role: ${role}`);
  }
  return Glyph;
}

export function TraceIcon({
  role: iconRole,
  size = "md",
  tone = "inherit",
  label,
  className = "",
  ...props
}) {
  if (!TRACE_ICON_SIZES.includes(size)) {
    throw new Error(`Unsupported TCGA-TRACE icon size: ${size}`);
  }
  if (!TRACE_ICON_TONES.includes(tone)) {
    throw new Error(`Unsupported TCGA-TRACE icon tone: ${tone}`);
  }

  const Glyph = requireGlyphRole(iconRole);
  return (
    <Glyph
      {...props}
      {...accessibleIconProps(label)}
      focusable="false"
      className={classNames(
        "trace-icon",
        `trace-icon-size-${size}`,
        `trace-icon-tone-${tone}`,
        className,
      )}
    />
  );
}

export function ModuleIcon({
  role: iconRole,
  frame = "section",
  label,
  className = "",
}) {
  if (!MODULE_ICON_FRAMES.includes(frame)) {
    throw new Error(`Unsupported TCGA-TRACE module icon frame: ${frame}`);
  }

  const moduleIcon = MODULE_ICON_REGISTRY[iconRole];
  const glyphIcon = GLYPH_ICON_REGISTRY[iconRole];
  if (!moduleIcon && !glyphIcon) {
    throw new Error(`Unknown TCGA-TRACE module icon role: ${iconRole}`);
  }

  const frameClass = {
    compact: "compact",
    section: "medium",
    navigation: "nav",
  }[frame];
  const family = moduleIcon?.family || "trace";
  const glyph = moduleIcon ? (
    <WorkflowIcon kind={moduleIcon.kind} />
  ) : (
    <TraceIcon role={iconRole} size={frame === "compact" ? "sm" : "md"} />
  );

  return (
    <span
      {...accessibleIconProps(label)}
      className={classNames("scientific-icon", frameClass, family, className)}
    >
      {React.cloneElement(glyph, {
        className: classNames("scientific-icon-core", glyph.props.className),
        "aria-hidden": true,
      })}
      <span className="scientific-icon-signal" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </span>
  );
}

export const IconButton = forwardRef(function IconButton(
  {
    iconRole,
    label,
    tooltip = label,
    iconSize = "sm",
    size = "md",
    variant = "ghost",
    className = "",
    type = "button",
    ...props
  },
  ref,
) {
  if (!label?.trim()) {
    throw new Error("TCGA-TRACE IconButton requires a specific accessible label.");
  }
  if (!["sm", "md", "lg"].includes(size)) {
    throw new Error(`Unsupported TCGA-TRACE icon button size: ${size}`);
  }
  if (!["ghost", "secondary", "destructive"].includes(variant)) {
    throw new Error(`Unsupported TCGA-TRACE icon button variant: ${variant}`);
  }

  return (
    <button
      {...props}
      ref={ref}
      type={type}
      aria-label={label}
      title={tooltip}
      className={classNames(
        "trace-icon-button",
        `trace-icon-button-size-${size}`,
        `trace-icon-button-${variant}`,
        className,
      )}
    >
      <TraceIcon role={iconRole} size={iconSize} />
    </button>
  );
});

function WorkflowIcon({ kind, className = "", ...props }) {
  return (
    <svg
      {...props}
      className={classNames("workflow-icon", `workflow-icon-${kind}`, className)}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      focusable="false"
    >
      {workflowIconDrawing(kind)}
    </svg>
  );
}

function workflowIconDrawing(kind) {
  switch (kind) {
    case "dataset":
    case "nav-summary":
      return (
        <>
          <path className="workflow-guide" d="M4 3.5v17M20 3.5v17" />
          <path d="M4 6h4.2m3.2 0H20M4 12h7.3m3.2 0H20M4 18h2.7m3.2 0H20" />
          <circle className="workflow-node" cx="9.8" cy="6" r="1.15" />
          <circle className="workflow-node" cx="12.9" cy="12" r="1.15" />
          <circle className="workflow-node" cx="8.3" cy="18" r="1.15" />
        </>
      );
    case "gene-analysis":
      return (
        <>
          <path d="M7 3.5c0 4.3 10 4.3 10 8.5S7 16.2 7 20.5M17 3.5c0 4.3-10 4.3-10 8.5s10 4.2 10 8.5" />
          <path className="workflow-guide" d="M9 6h6m-7.5 4h9m-9 4h9m-7.5 4h6" />
          <circle className="workflow-node" cx="12" cy="12" r="1.2" />
        </>
      );
    case "survival-endpoint":
      return (
        <>
          <path className="workflow-guide" d="M4 3.5V20h16.5" />
          <path className="workflow-emphasis" d="M5 6h5v4h4v3h3v4h3.5" />
          <path d="m15.2 8.3 2.4 2.4m0-2.4-2.4 2.4" />
          <circle className="workflow-node" cx="20.5" cy="17" r="1.15" />
        </>
      );
    case "rna-scale":
      return (
        <>
          <path className="workflow-guide" d="M4.5 3.5V20H21M4.5 7h2m-2 5h2m-2 5h2" />
          <path d="M9 18v-3m5 3v-7m5 7V5" />
          <path className="workflow-expression-trace" d="M8.7 13.2c1.8-2.2 3.2 1.1 5.1-1.6 1.5-2.1 2.7-4.8 5.4-6.8" />
          <circle className="workflow-node" cx="19.2" cy="4.8" r="1.15" />
        </>
      );
    case "stratification":
      return (
        <>
          <path className="workflow-guide" d="M3 12h5" />
          <path d="M8 12c3 0 2-6 6-6h7M8 12h13M8 12c3 0 2 6 6 6h7" />
          <circle className="workflow-node" cx="8" cy="12" r="1.25" />
          <circle className="workflow-node workflow-node-soft" cx="20.5" cy="6" r="1.05" />
          <circle className="workflow-node" cx="20.5" cy="12" r="1.05" />
          <circle className="workflow-node workflow-node-soft" cx="20.5" cy="18" r="1.05" />
        </>
      );
    case "clinical-filters":
      return (
        <>
          <path d="M3.5 5h17l-6.3 7.2v5.1L9.8 20v-7.8z" />
          <path className="workflow-guide" d="M7 8h10M9.2 11h5.6" />
          <circle className="workflow-node" cx="12" cy="5" r="1.1" />
        </>
      );
    case "plot-output":
      return (
        <>
          <rect className="workflow-guide" x="3.5" y="4" width="13" height="12" rx="1.5" />
          <path d="M6 13V9l3 2 4-5 2 2M19 11v9m-3-3 3 3 3-3" />
          <circle className="workflow-node" cx="13" cy="6" r="1" />
        </>
      );
    case "plot-style":
      return (
        <>
          <path className="workflow-guide" d="M4 6h16M4 12h16M4 18h16" />
          <circle className="workflow-node" cx="8" cy="6" r="1.6" />
          <circle className="workflow-node workflow-node-soft" cx="16" cy="12" r="1.6" />
          <circle className="workflow-node" cx="11" cy="18" r="1.6" />
        </>
      );
    case "comparison-dataset":
      return (
        <>
          <path d="M3.5 6h6v5h5v7h6M3.5 18h6v-5h5V6h6" />
          <path className="workflow-guide" d="M9.5 4v16M14.5 4v16" />
          <circle className="workflow-node" cx="14.5" cy="12" r="1.2" />
        </>
      );
    case "markers-cutpoints":
      return (
        <>
          <path className="workflow-guide" d="M3.5 18h17M14 4v16" />
          <circle className="workflow-node workflow-node-soft" cx="6" cy="14" r="1.3" />
          <circle className="workflow-node" cx="9.5" cy="10" r="1.3" />
          <circle className="workflow-node" cx="16.5" cy="7" r="1.3" />
          <circle className="workflow-node workflow-node-soft" cx="19.5" cy="12.5" r="1.3" />
        </>
      );
    case "specification-curve":
    case "nav-multiverse":
      return (
        <>
          <path className="workflow-guide" d="M3.5 18.5h17M5 4v14.5M4 10.5h17" />
          <path d="M7 13v3m0-1.5h0M11 7v8m0-4h0M15 5v9m0-5h0M19 8v8m0-4h0" />
          <path className="workflow-emphasis" d="M5 20.5h2v-1h2v1h2v-1h2v1h2v-1h2v1h3.5" />
          <circle className="workflow-node workflow-node-soft" cx="7" cy="14.5" r="1.05" />
          <circle className="workflow-node" cx="11" cy="11" r="1.05" />
          <circle className="workflow-node" cx="15" cy="9" r="1.05" />
          <circle className="workflow-node workflow-node-soft" cx="19" cy="12" r="1.05" />
        </>
      );
    case "session-history":
      return (
        <>
          <path className="workflow-guide" d="M5 3.5v17M5 6h4M5 12h4M5 18h4M9 6h10M9 12h10M9 18h10" />
          <path className="workflow-emphasis" d="M10 6c2 0 2 6 4 6s2 6 4 6" />
          <circle className="workflow-node" cx="5" cy="6" r="1.2" />
          <circle className="workflow-node workflow-node-soft" cx="5" cy="12" r="1.2" />
          <circle className="workflow-node" cx="5" cy="18" r="1.2" />
          <circle className="workflow-node workflow-node-soft" cx="19" cy="6" r="1" />
          <circle className="workflow-node" cx="19" cy="12" r="1" />
          <circle className="workflow-node workflow-node-soft" cx="19" cy="18" r="1" />
        </>
      );
    case "pancancer-query":
      return (
        <>
          <circle className="workflow-guide" cx="10.5" cy="10.5" r="6.5" />
          <path d="M6 6l9 9M4.5 10.5h12M10.5 4v13M15.2 15.2 21 21" />
          <circle className="workflow-node" cx="10.5" cy="10.5" r="1.25" />
        </>
      );
    case "outcome-model":
      return (
        <>
          <path className="workflow-guide" d="M4 4H2.8v16H4M20 4h1.2v16H20" />
          <path d="M5 7h4v4h4v3h3v3h3M7 20l5-4 5 4" />
          <circle className="workflow-node" cx="13" cy="14" r="1.1" />
        </>
      );
    case "forest":
      return (
        <>
          <path className="workflow-guide" d="M12 3v18" />
          <path d="M4 6h11m-7 6h12M3 18h12" />
          <path d="M4 4v4m11-4v4M8 10v4m12-4v4M3 16v4m12-4v4" />
          <rect className="workflow-node" x="9.8" y="4.8" width="2.4" height="2.4" rx=".3" />
          <rect className="workflow-node" x="13.8" y="10.8" width="2.4" height="2.4" rx=".3" />
          <rect className="workflow-node" x="7.8" y="16.8" width="2.4" height="2.4" rx=".3" />
        </>
      );
    case "concordance":
      return (
        <>
          <path className="workflow-guide" d="M4 4v16h16" />
          <path d="M5 17 10 12l3 2 7-8M5 8l4 3 4-5 7 6" />
          <circle className="workflow-node" cx="10" cy="12" r="1.15" />
          <circle className="workflow-node workflow-node-soft" cx="13" cy="6" r="1.15" />
        </>
      );
    case "evidence":
      return (
        <>
          <path className="workflow-guide" d="M4 20V4m0 16h16M7 14h10M12 4v16" />
          <circle className="workflow-node workflow-node-soft" cx="8" cy="15.5" r="1.15" />
          <circle className="workflow-node" cx="9.5" cy="10.5" r="1.25" />
          <circle className="workflow-node" cx="16.5" cy="7" r="1.45" />
          <circle className="workflow-node workflow-node-soft" cx="15" cy="15" r="1.05" />
        </>
      );
    case "precision":
      return (
        <>
          <circle className="workflow-guide" cx="12" cy="12" r="8.5" />
          <circle className="workflow-guide" cx="12" cy="12" r="4.5" />
          <path d="M3 12h18M12 3v18" />
          <circle className="workflow-node" cx="13.5" cy="10.5" r="1.7" />
        </>
      );
    case "cohort-results":
      return (
        <>
          <path className="workflow-guide" d="M4 5h16M4 12h16M4 19h16" />
          <path d="M4 5h8M4 12h11M4 19h6" />
          <circle className="workflow-node" cx="17.5" cy="5" r="1.25" />
          <circle className="workflow-node workflow-node-soft" cx="17.5" cy="12" r="1.25" />
          <circle className="workflow-node" cx="17.5" cy="19" r="1.25" />
        </>
      );
    case "recurrence":
      return (
        <>
          <path className="workflow-guide" d="M12 3v18M4 7h16M4 12h16M4 17h16" />
          <path d="M12 7H7m5 5h6m-6 5H5" />
          <circle className="workflow-node" cx="7" cy="7" r="1.35" />
          <circle className="workflow-node workflow-node-soft" cx="18" cy="12" r="1.35" />
          <circle className="workflow-node" cx="5" cy="17" r="1.35" />
        </>
      );
    case "frequency":
      return (
        <>
          <path className="workflow-guide" d="M4 4v16h17" />
          <path d="m5 7 4 4 4 3 4 2 3 1M5 12l4 2 4 2 4 2 3 1" />
          <circle className="workflow-node" cx="9" cy="11" r="1.05" />
          <circle className="workflow-node workflow-node-soft" cx="13" cy="16" r="1.05" />
        </>
      );
    case "meta":
      return (
        <>
          <path className="workflow-guide" d="M12 3v18M3 17h18" />
          <circle className="workflow-node workflow-node-soft" cx="7" cy="12" r="2.1" />
          <circle className="workflow-node" cx="16" cy="8" r="2.7" />
          <circle className="workflow-node workflow-node-soft" cx="18.5" cy="14" r="1.35" />
          <path d="m9.5 18.5 2.5-2 2.5 2-2.5 2z" />
        </>
      );
    case "burden":
      return (
        <>
          <path className="workflow-guide" d="M4 4v16h17" />
          <path d="M6 17h4M6 13h8M6 9h12M6 5h15" />
          <circle className="workflow-node" cx="10" cy="17" r="1" />
          <circle className="workflow-node workflow-node-soft" cx="18" cy="9" r="1" />
        </>
      );
    case "immune-programs":
      return (
        <>
          <path className="workflow-guide" d="m12 12-6-6m6 6 6-6m-6 6-6 6m6-6 6 6" />
          <circle className="workflow-node" cx="12" cy="12" r="2" />
          <circle className="workflow-node workflow-node-soft" cx="6" cy="6" r="1.4" />
          <circle className="workflow-node" cx="18" cy="6" r="1.4" />
          <circle className="workflow-node" cx="6" cy="18" r="1.4" />
          <circle className="workflow-node workflow-node-soft" cx="18" cy="18" r="1.4" />
        </>
      );
    case "extremes":
      return (
        <>
          <path className="workflow-guide" d="M3 12h18M12 4v16" />
          <path d="m7 8-4 4 4 4m10-8 4 4-4 4" />
          <circle className="workflow-node" cx="5" cy="12" r="1.35" />
          <circle className="workflow-node" cx="19" cy="12" r="1.35" />
          <circle className="workflow-node workflow-node-soft" cx="12" cy="12" r="1" />
        </>
      );
    case "cohort-effects":
      return (
        <>
          <path className="workflow-guide" d="M11 3v18" />
          <path d="M3 6h11M7 11h13M5 16h10" />
          <circle className="workflow-node workflow-node-soft" cx="8" cy="6" r="1.15" />
          <circle className="workflow-node" cx="14" cy="11" r="1.45" />
          <path d="m8.5 19 2.5-2 2.5 2-2.5 2z" />
        </>
      );
    case "api":
    case "nav-api":
      return (
        <>
          <path className="workflow-guide" d="M8 4H5v6l-2 2 2 2v6h3M16 4h3v6l2 2-2 2v6h-3" />
          <path d="M8 8h8M8 12h5M8 16h8" />
          <circle className="workflow-node" cx="16" cy="12" r="1.2" />
        </>
      );
    case "ai-connectors":
      return (
        <>
          <path className="workflow-guide" d="M3.5 5h7v6h-4l-2 2v-2h-1zM13.5 13h7v6h-1v2l-2-2h-4z" />
          <path d="m9.5 10 5 5M14.5 9l-5 6" />
          <circle className="workflow-node" cx="12" cy="12" r="1.45" />
        </>
      );
    case "methods":
    case "nav-help":
      return (
        <>
          <path className="workflow-guide" d="M6 3.5h11l2 2V20.5H6zM17 3.5v3h3" />
          <path d="M9 9h7M9 13h7M9 17h4" />
          <circle className="workflow-node" cx="16" cy="17" r="1.15" />
        </>
      );
    case "endpoint-coverage":
      return (
        <>
          <path className="workflow-guide" d="M4 5h16M4 10h16M4 15h16M4 20h16" />
          <path d="M4 5h10M4 10h7M4 15h13M4 20h5" />
          <circle className="workflow-node" cx="14" cy="5" r="1.05" />
          <circle className="workflow-node workflow-node-soft" cx="11" cy="10" r="1.05" />
          <circle className="workflow-node" cx="17" cy="15" r="1.05" />
          <circle className="workflow-node workflow-node-soft" cx="9" cy="20" r="1.05" />
        </>
      );
    case "cohort-landscape":
      return (
        <>
          <path className="workflow-guide" d="M4 20V4m0 16h16" />
          <path d="m5 17 4-5 3 2 4-8 4 6" />
          <circle className="workflow-node" cx="9" cy="12" r="1.2" />
          <circle className="workflow-node workflow-node-soft" cx="16" cy="6" r="1.35" />
        </>
      );
    case "sample-types":
      return (
        <>
          <path className="workflow-guide" d="M4 4h5M15 4h5" />
          <path d="M5 4v5l-1 9c0 2 6 2 6 0L9 9V4M16 4v5l-1 9c0 2 6 2 6 0l-1-9V4" />
          <path d="M4.5 14h5M15.5 11h5" />
          <circle className="workflow-node" cx="18" cy="15" r="1.1" />
        </>
      );
    case "vital-status":
      return (
        <>
          <path className="workflow-guide" d="M3 12h4M17 12h4" />
          <path className="workflow-emphasis" d="m3 12 5 0 2-6 3 12 2-6h6" />
          <circle className="workflow-node" cx="21" cy="12" r="1.1" />
        </>
      );
    case "primary-sites":
      return (
        <>
          <path className="workflow-guide" d="M12 3v18M3 12h18" />
          <path d="m12 5 4 3-1 5-3 6-3-6-1-5z" />
          <circle className="workflow-node" cx="12" cy="9" r="1.4" />
          <circle className="workflow-node workflow-node-soft" cx="16" cy="15" r="1.05" />
        </>
      );
    case "age":
      return (
        <>
          <circle className="workflow-guide" cx="12" cy="12" r="8.5" />
          <path d="M12 3.5V12l5 3M6 18l3-3m9-9-3 3" />
          <circle className="workflow-node" cx="12" cy="12" r="1.45" />
        </>
      );
    case "metadata":
      return (
        <>
          <path className="workflow-guide" d="M4 4h16v16H4zM4 9.3h16M4 14.7h16M9.3 4v16M14.7 4v16" />
          <circle className="workflow-node" cx="12" cy="12" r="1.15" />
          <circle className="workflow-node workflow-node-soft" cx="17.3" cy="6.7" r="1.05" />
          <circle className="workflow-node" cx="6.7" cy="17.3" r="1.05" />
        </>
      );
    case "biological-annotations":
      return (
        <>
          <path d="M6 3.5c0 4.3 8 4.3 8 8.5s-8 4.2-8 8.5M14 3.5c0 4.3-8 4.3-8 8.5s8 4.2 8 8.5" />
          <path className="workflow-guide" d="M8 6h4m-5.5 4h7m-7 4h7m-5.5 4h4" />
          <path d="M16 8h5v8h-5l-2.5-4z" />
          <circle className="workflow-node" cx="18" cy="12" r="1.05" />
        </>
      );
    case "cohort-table":
      return (
        <>
          <rect className="workflow-guide" x="3.5" y="4" width="17" height="16" rx="1" />
          <path d="M3.5 9h17M3.5 14h17M9 4v16" />
          <path className="workflow-emphasis" d="M10.5 11.5h7M10.5 16.5h4" />
          <circle className="workflow-node" cx="6.2" cy="11.5" r="1" />
        </>
      );
    case "nav-home":
      return (
        <>
          <path className="workflow-guide" d="M3.5 19.5h17M5 19.5V8.5L12 3l7 5.5v11" />
          <path d="M8 19.5v-6h8v6M8 9h8" />
          <circle className="workflow-node" cx="12" cy="9" r="1.3" />
          <circle className="workflow-node workflow-node-soft" cx="16" cy="13.5" r="1" />
        </>
      );
    case "nav-analysis":
      return (
        <>
          <path d="M5 4c0 3.5 7 3.5 7 7s-7 3.5-7 7M12 4c0 3.5-7 3.5-7 7s7 3.5 7 7" />
          <path className="workflow-guide" d="M7 6h3M6 10h5M6 14h5M7 18h3" />
          <path d="M13 7h3v4h2v3h3" />
          <circle className="workflow-node" cx="18" cy="14" r="1.15" />
        </>
      );
    case "nav-compare":
      return (
        <>
          <path d="M3 7h6l3 5 3-5h6M3 17h6l3-5 3 5h6" />
          <path className="workflow-guide" d="M12 3v18" />
          <circle className="workflow-node" cx="12" cy="12" r="1.5" />
          <circle className="workflow-node workflow-node-soft" cx="20" cy="7" r="1" />
          <circle className="workflow-node" cx="20" cy="17" r="1" />
        </>
      );
    case "nav-pancancer":
      return (
        <>
          <circle className="workflow-guide" cx="12" cy="12" r="8" />
          <path d="M12 12 6 7m6 5 6-5m-6 5-6 6m6-6 6 6" />
          <circle className="workflow-node" cx="12" cy="12" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="6" cy="7" r="1.25" />
          <circle className="workflow-node" cx="18" cy="7" r="1.25" />
          <circle className="workflow-node" cx="6" cy="18" r="1.25" />
          <circle className="workflow-node workflow-node-soft" cx="18" cy="18" r="1.25" />
        </>
      );
    case "nav-examples":
      return (
        <>
          <path className="workflow-guide" d="M4 4h7v16H4zM13 4h7v16h-7z" />
          <path d="M6 16V9h3v7M15 8h3v3h-3v5h3" />
          <circle className="workflow-node" cx="9" cy="9" r="1" />
          <circle className="workflow-node workflow-node-soft" cx="18" cy="16" r="1" />
        </>
      );
    default:
      throw new Error(`Unknown TCGA-TRACE workflow icon drawing: ${kind}`);
  }
}
