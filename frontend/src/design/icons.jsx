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
 * @position The sole Lucide boundary and semantic icon registry for TRACE Explorer.
 *
 * SYNC: when this contract changes, update icons.test.jsx, docs/ICON_SYSTEM.md
 * and DESIGN.md as described in frontend/AGENTS.md.
 */
// Platform silhouettes from Simple Icons 11.15.0 (CC0), kept in this registry.
function GitHubIcon(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="currentColor"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" /></svg>;
}

function WindowsIcon(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="currentColor"><path d="M0,0H11.377V11.372H0ZM12.623,0H24V11.372H12.623ZM0,12.623H11.377V24H0Zm12.623,0H24V24H12.623" /></svg>;
}

function MacOSIcon(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="currentColor"><path d="M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701" /></svg>;
}

function LinuxIcon(props) {
  return <svg {...props} viewBox="0 0 24 24" fill="currentColor"><path d="M12.504 0c-.155 0-.315.008-.48.021-4.226.333-3.105 4.807-3.17 6.298-.076 1.092-.3 1.953-1.05 3.02-.885 1.051-2.127 2.75-2.716 4.521-.278.832-.41 1.684-.287 2.489a.424.424 0 00-.11.135c-.26.268-.45.6-.663.839-.199.199-.485.267-.797.4-.313.136-.658.269-.864.68-.09.189-.136.394-.132.602 0 .199.027.4.055.536.058.399.116.728.04.97-.249.68-.28 1.145-.106 1.484.174.334.535.47.94.601.81.2 1.91.135 2.774.6.926.466 1.866.67 2.616.47.526-.116.97-.464 1.208-.946.587-.003 1.23-.269 2.26-.334.699-.058 1.574.267 2.577.2.025.134.063.198.114.333l.003.003c.391.778 1.113 1.132 1.884 1.071.771-.06 1.592-.536 2.257-1.306.631-.765 1.683-1.084 2.378-1.503.348-.199.629-.469.649-.853.023-.4-.2-.811-.714-1.376v-.097l-.003-.003c-.17-.2-.25-.535-.338-.926-.085-.401-.182-.786-.492-1.046h-.003c-.059-.054-.123-.067-.188-.135a.357.357 0 00-.19-.064c.431-1.278.264-2.55-.173-3.694-.533-1.41-1.465-2.638-2.175-3.483-.796-1.005-1.576-1.957-1.56-3.368.026-2.152.236-6.133-3.544-6.139zm.529 3.405h.013c.213 0 .396.062.584.198.19.135.33.332.438.533.105.259.158.459.166.724 0-.02.006-.04.006-.06v.105a.086.086 0 01-.004-.021l-.004-.024a1.807 1.807 0 01-.15.706.953.953 0 01-.213.335.71.71 0 00-.088-.042c-.104-.045-.198-.064-.284-.133a1.312 1.312 0 00-.22-.066c.05-.06.146-.133.183-.198.053-.128.082-.264.088-.402v-.02a1.21 1.21 0 00-.061-.4c-.045-.134-.101-.2-.183-.333-.084-.066-.167-.132-.267-.132h-.016c-.093 0-.176.03-.262.132a.8.8 0 00-.205.334 1.18 1.18 0 00-.09.4v.019c.002.089.008.179.02.267-.193-.067-.438-.135-.607-.202a1.635 1.635 0 01-.018-.2v-.02a1.772 1.772 0 01.15-.768c.082-.22.232-.406.43-.533a.985.985 0 01.594-.2zm-2.962.059h.036c.142 0 .27.048.399.135.146.129.264.288.344.465.09.199.14.4.153.667v.004c.007.134.006.2-.002.266v.08c-.03.007-.056.018-.083.024-.152.055-.274.135-.393.2.012-.09.013-.18.003-.267v-.015c-.012-.133-.04-.2-.082-.333a.613.613 0 00-.166-.267.248.248 0 00-.183-.064h-.021c-.071.006-.13.04-.186.132a.552.552 0 00-.12.27.944.944 0 00-.023.33v.015c.012.135.037.2.08.334.046.134.098.2.166.268.01.009.02.018.034.024-.07.057-.117.07-.176.136a.304.304 0 01-.131.068 2.62 2.62 0 01-.275-.402 1.772 1.772 0 01-.155-.667 1.759 1.759 0 01.08-.668 1.43 1.43 0 01.283-.535c.128-.133.26-.2.418-.2zm1.37 1.706c.332 0 .733.065 1.216.399.293.2.523.269 1.052.468h.003c.255.136.405.266.478.399v-.131a.571.571 0 01.016.47c-.123.31-.516.643-1.063.842v.002c-.268.135-.501.333-.775.465-.276.135-.588.292-1.012.267a1.139 1.139 0 01-.448-.067 3.566 3.566 0 01-.322-.198c-.195-.135-.363-.332-.612-.465v-.005h-.005c-.4-.246-.616-.512-.686-.71-.07-.268-.005-.47.193-.6.224-.135.38-.271.483-.336.104-.074.143-.102.176-.131h.002v-.003c.169-.202.436-.47.839-.601.139-.036.294-.065.466-.065zm2.8 2.142c.358 1.417 1.196 3.475 1.735 4.473.286.534.855 1.659 1.102 3.024.156-.005.33.018.513.064.646-1.671-.546-3.467-1.089-3.966-.22-.2-.232-.335-.123-.335.59.534 1.365 1.572 1.646 2.757.13.535.16 1.104.021 1.67.067.028.135.06.205.067 1.032.534 1.413.938 1.23 1.537v-.043c-.06-.003-.12 0-.18 0h-.016c.151-.467-.182-.825-1.065-1.224-.915-.4-1.646-.336-1.77.465-.008.043-.013.066-.018.135-.068.023-.139.053-.209.064-.43.268-.662.669-.793 1.187-.13.533-.17 1.156-.205 1.869v.003c-.02.334-.17.838-.319 1.35-1.5 1.072-3.58 1.538-5.348.334a2.645 2.645 0 00-.402-.533 1.45 1.45 0 00-.275-.333c.182 0 .338-.03.465-.067a.615.615 0 00.314-.334c.108-.267 0-.697-.345-1.163-.345-.467-.931-.995-1.788-1.521-.63-.4-.986-.87-1.15-1.396-.165-.534-.143-1.085-.015-1.645.245-1.07.873-2.11 1.274-2.763.107-.065.037.135-.408.974-.396.751-1.14 2.497-.122 3.854a8.123 8.123 0 01.647-2.876c.564-1.278 1.743-3.504 1.836-5.268.048.036.217.135.289.202.218.133.38.333.59.465.21.201.477.335.876.335.039.003.075.006.11.006.412 0 .73-.134.997-.268.29-.134.52-.334.74-.4h.005c.467-.135.835-.402 1.044-.7zm2.185 8.958c.037.6.343 1.245.882 1.377.588.134 1.434-.333 1.791-.765l.211-.01c.315-.007.577.01.847.268l.003.003c.208.199.305.53.391.876.085.4.154.78.409 1.066.486.527.645.906.636 1.14l.003-.007v.018l-.003-.012c-.015.262-.185.396-.498.595-.63.401-1.746.712-2.457 1.57-.618.737-1.37 1.14-2.036 1.191-.664.053-1.237-.2-1.574-.898l-.005-.003c-.21-.4-.12-1.025.056-1.69.176-.668.428-1.344.463-1.897.037-.714.076-1.335.195-1.814.12-.465.308-.797.641-.984l.045-.022zm-10.814.049h.01c.053 0 .105.005.157.014.376.055.706.333 1.023.752l.91 1.664.003.003c.243.533.754 1.064 1.189 1.637.434.598.77 1.131.729 1.57v.006c-.057.744-.48 1.148-1.125 1.294-.645.135-1.52.002-2.395-.464-.968-.536-2.118-.469-2.857-.602-.369-.066-.61-.2-.723-.4-.11-.2-.113-.602.123-1.23v-.004l.002-.003c.117-.334.03-.752-.027-1.118-.055-.401-.083-.71.043-.94.16-.334.396-.4.69-.533.294-.135.64-.202.915-.47h.002v-.002c.256-.268.445-.601.668-.838.19-.201.38-.336.663-.336zm7.159-9.074c-.435.201-.945.535-1.488.535-.542 0-.97-.267-1.28-.466-.154-.134-.28-.268-.373-.335-.164-.134-.144-.333-.074-.333.109.016.129.134.199.2.096.066.215.2.36.333.292.2.68.467 1.167.467.485 0 1.053-.267 1.398-.466.195-.135.445-.334.648-.467.156-.136.149-.267.279-.267.128.016.034.134-.147.332a8.097 8.097 0 01-.69.468zm-1.082-1.583V5.64c-.006-.02.013-.042.029-.05.074-.043.18-.027.26.004.063 0 .16.067.15.135-.006.049-.085.066-.135.066-.055 0-.092-.043-.141-.068-.052-.018-.146-.008-.163-.065zm-.551 0c-.02.058-.113.049-.166.066-.047.025-.086.068-.14.068-.05 0-.13-.02-.136-.068-.01-.066.088-.133.15-.133.08-.031.184-.047.259-.005.019.009.036.03.03.05v.02h.003z" /></svg>;
}

const GLYPH_ICON_REGISTRY = Object.freeze({
  "resource.github": GitHubIcon,
  "platform.windows": WindowsIcon,
  "platform.macos": MacOSIcon,
  "platform.linux": LinuxIcon,
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
  "module.expressionComparison": { kind: "expression-comparison", family: "comparison" },
  "module.markersCutpoints": { kind: "markers-cutpoints", family: "comparison" },
  "module.geneSetEnrichment": { kind: "gene-set-enrichment", family: "molecular" },
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
  "navigation.expressionComparison": { kind: "expression-comparison", family: "comparison" },
  "navigation.gsea": { kind: "gene-set-enrichment", family: "molecular" },
  "navigation.multiverse": { kind: "nav-multiverse", family: "comparison" },
  "navigation.session": { kind: "session-history", family: "trace" },
  "navigation.panCancer": { kind: "nav-pancancer", family: "trace" },
  "navigation.examples": { kind: "nav-examples", family: "trace" },
  "navigation.dataset": { kind: "nav-summary", family: "dataset" },
  "navigation.repository": { kind: "nav-repository", family: "dataset" },
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
    throw new Error(`Unknown TRACE Explorer glyph icon role: ${role}`);
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
    throw new Error(`Unsupported TRACE Explorer icon size: ${size}`);
  }
  if (!TRACE_ICON_TONES.includes(tone)) {
    throw new Error(`Unsupported TRACE Explorer icon tone: ${tone}`);
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
    throw new Error(`Unsupported TRACE Explorer module icon frame: ${frame}`);
  }

  const moduleIcon = MODULE_ICON_REGISTRY[iconRole];
  const glyphIcon = GLYPH_ICON_REGISTRY[iconRole];
  if (!moduleIcon && !glyphIcon) {
    throw new Error(`Unknown TRACE Explorer module icon role: ${iconRole}`);
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
    throw new Error("TRACE Explorer IconButton requires a specific accessible label.");
  }
  if (!["sm", "md", "lg"].includes(size)) {
    throw new Error(`Unsupported TRACE Explorer icon button size: ${size}`);
  }
  if (!["ghost", "secondary", "destructive"].includes(variant)) {
    throw new Error(`Unsupported TRACE Explorer icon button variant: ${variant}`);
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
      return (
        <>
          <rect className="workflow-emphasis" x="3.6" y="3.8" width="16.8" height="5.6" rx="1.6"/>
          <rect className="workflow-guide" x="3.6" y="11" width="16.8" height="4.2" rx="1.4"/>
          <rect className="workflow-guide" x="3.6" y="16.8" width="16.8" height="4.2" rx="1.4"/>
          <circle className="workflow-node" cx="7.4" cy="6.6" r="1.3"/>
        </>
      );
    // The dataset inventory and the imported-cohort table are the same idea:
    // one table of what is loaded.
    case "cohort-table":
    case "nav-summary":
      return (
        <>
          <rect x="3.4" y="4.4" width="17.2" height="15.2" rx="1.8" />
          <path className="workflow-emphasis" d="M3.4 9.4h17.2" />
          <path className="workflow-guide" d="M12 9.4v10.2M3.4 14.5h17.2" />
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
          <path className="workflow-guide" d="M4.4 3.8V20h16M4.4 8h2M4.4 14h2"/>
          <path className="workflow-emphasis" d="M9 20v-5.4M14 20V9.6M19 20V5.4"/>
        </>
      );
    case "stratification":
      return (
        <>
          <rect className="workflow-guide" x="3.6" y="7.2" width="16.8" height="9.6" rx="1.6"/>
          <path className="workflow-emphasis" d="M12 4.6v14.8"/>
          <circle className="workflow-node workflow-node-soft" cx="7.6" cy="12" r="1.8"/>
          <circle className="workflow-node" cx="16.4" cy="12" r="1.8"/>
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
          <rect className="workflow-emphasis" x="3.6" y="3.8" width="16.8" height="5" rx="1.6"/>
          <path className="workflow-guide" d="M12 8.8v3.4M7 12.2h10"/>
          <rect x="4" y="14" width="6.6" height="6.6" rx="1.4"/>
          <rect x="13.4" y="14" width="6.6" height="6.6" rx="1.4"/>
        </>
      );
    case "expression-comparison":
      return (
        <>
          <path d="M8 4v2.6M8 16v2.8" />
          <rect x="4.4" y="6.6" width="7.2" height="9.4" rx="1.2" />
          <path className="workflow-emphasis" d="M4.4 11.2h7.2" />
          <path d="M16.4 7.4v2.4M16.4 17.2v1.6" />
          <rect x="13" y="9.8" width="6.8" height="7.4" rx="1.2" />
          <path className="workflow-emphasis" d="M13 13.6h6.8" />
        </>
      );
    case "markers-cutpoints":
      return (
        <>
          <path d="M3.6 18.2c3.4 0 3.4-10.4 7.2-10.4 4 0 3.6 10.4 9.6 10.4"/>
          <path className="workflow-emphasis" d="M14.4 3.8v16.6"/>
          <circle className="workflow-node" cx="14.4" cy="14.4" r="1.5"/>
        </>
      );
    case "gene-set-enrichment":
      return (
        <>
          <path
            className="workflow-emphasis"
            d="M3.4 15.4c2.7-.2 3-9.2 6.4-9.2 3.6 0 4 8.8 10.8 9.6"
          />
          <path d="M4.4 18.2v2.6M6.2 18.2v2.6M7.8 18.2v2.6M10.2 18.2v2.6M13.6 18.2v2.6M17.8 18.2v2.6" />
        </>
      );
    case "nav-multiverse":
      return (
        <>
          <path d="M3.6 6.2c5.4 0 6.6 5.8 11.6 5.8M3.6 17.8c5.4 0 6.6-5.8 11.6-5.8M3.6 12h11.6" />
          <circle className="workflow-node" cx="18.4" cy="12" r="2.2" />
        </>
      );
    case "specification-curve":
      return (
        <>
          <path className="workflow-emphasis" d="M3.6 12.8c3.8 0 4.2-3.2 6.6-4.8 2.4-1.6 4.4-2.2 10-2.4"/>
          <path className="workflow-guide" d="M3.6 16.4h16.8M3.6 20.2h16.8"/>
          <circle className="workflow-node" cx="7.2" cy="16.4" r="1.35"/>
          <circle className="workflow-node" cx="16.2" cy="16.4" r="1.35"/>
          <circle className="workflow-node" cx="11.6" cy="20.2" r="1.35"/>
        </>
      );
    case "session-history":
      return (
        <>
          <path d="M3.7 8.9A8.4 8.4 0 1 1 3.6 12" />
          <path d="M3.4 4.6v4.4h4.4" />
          <path className="workflow-emphasis" d="M12 7.7V12l3.3 2.3" />
        </>
      );
    case "pancancer-query":
      return (
        <>
          <circle cx="10.6" cy="10.6" r="6.8"/>
          <path className="workflow-emphasis" d="m15.6 15.6 5 5"/>
          <circle className="workflow-node" cx="8.2" cy="8.6" r="1.3"/>
          <circle className="workflow-node workflow-node-soft" cx="12.8" cy="8.6" r="1.3"/>
          <circle className="workflow-node workflow-node-soft" cx="8.2" cy="12.8" r="1.3"/>
          <circle className="workflow-node" cx="12.8" cy="12.8" r="1.3"/>
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
          <path className="workflow-guide" d="M12 3.6v16.8"/>
          <path d="M6.6 7.4h7M9.4 12.6h8.2M5 17.4h7.4"/>
          <rect className="workflow-node" x="8.6" y="6" width="2.8" height="2.8" rx=".5"/>
          <rect className="workflow-node" x="12.2" y="11.2" width="2.8" height="2.8" rx=".5"/>
          <rect className="workflow-node" x="7.2" y="16" width="2.8" height="2.8" rx=".5"/>
        </>
      );
    case "concordance":
      return (
        <>
          <path className="workflow-guide" d="M4 3.8V20h16.4"/>
          <path className="workflow-guide" d="M5.6 18.6 19.6 5"/>
          <circle className="workflow-node" cx="9" cy="16.4" r="1.7"/>
          <circle className="workflow-node workflow-node-soft" cx="12.6" cy="10.4" r="1.7"/>
          <circle className="workflow-node" cx="17" cy="7.6" r="1.7"/>
        </>
      );
    case "evidence":
      return (
        <>
          <path className="workflow-guide" d="M4 3.8V20h16.4"/>
          <path className="workflow-emphasis" d="M4.8 12.4h15.4"/>
          <circle className="workflow-node" cx="8.4" cy="8"  r="1.5"/>
          <circle className="workflow-node" cx="16" cy="6.6" r="1.5"/>
          <circle className="workflow-node workflow-node-soft" cx="12" cy="16.4" r="1.5"/>
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
          <path className="workflow-guide" d="M3.6 8h16.8M3.6 16h16.8"/>
          <circle className="workflow-node" cx="8.4" cy="8" r="2"/>
          <circle className="workflow-node workflow-node-soft" cx="15.6" cy="8" r="2"/>
          <circle className="workflow-node" cx="12.4" cy="16" r="2"/>
          <circle className="workflow-node workflow-node-soft" cx="18.6" cy="16" r="2"/>
        </>
      );
    case "recurrence":
      return (
        <>
          <path className="workflow-guide" d="M3.6 12h16.8"/>
          <rect className="workflow-node" x="5" y="5.6" width="3.4" height="6.4" rx="1.2"/>
          <rect className="workflow-node workflow-node-soft" x="10.3" y="12" width="3.4" height="5" rx="1.2"/>
          <rect className="workflow-node" x="15.6" y="4.4" width="3.4" height="7.6" rx="1.2"/>
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
          <path className="workflow-guide" d="M3.6 17.6h16.8"/>
          <circle className="workflow-node" cx="8.6" cy="7.4" r="2.4"/>
          <circle className="workflow-node workflow-node-soft" cx="15.4" cy="10.4" r="1.6"/>
          <path className="workflow-emphasis" d="m12 14.2 4.4 3.4-4.4 3.4-4.4-3.4z"/>
        </>
      );
    case "burden":
      return (
        <>
          <path className="workflow-guide" d="M4.4 3.8v16.4"/>
          <rect className="workflow-node" x="4.4" y="5.4" width="15.2" height="3.4" rx="1.4"/>
          <rect className="workflow-node workflow-node-soft" x="4.4" y="10.4" width="10.4" height="3.4" rx="1.4"/>
          <rect className="workflow-node" x="4.4" y="15.4" width="6.2" height="3.4" rx="1.4"/>
        </>
      );
    case "immune-programs":
      return (
        <>
          <rect x="3.6" y="4.4" width="16.8" height="4.2" rx="2.1"/>
          <rect className="workflow-guide" x="3.6" y="10.9" width="12.6" height="4.2" rx="2.1"/>
          <rect className="workflow-guide" x="3.6" y="17.4" width="9" height="4.2" rx="2.1"/>
          <circle className="workflow-node" cx="6.6" cy="6.5" r="1.1"/>
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
          <path className="workflow-guide" d="M3.6 20h16.8M12 4v16"/>
          <circle className="workflow-node" cx="9" cy="9" r="2.2"/>
          <circle cx="10.4" cy="14.6" r="2.2"/>
        </>
      );
    case "api":
    case "nav-api":
      return (
        <>
          <path d="M8.6 4.2H6.4a1.7 1.7 0 0 0-1.7 1.7v3.4L3 12l1.7 2.7v3.4a1.7 1.7 0 0 0 1.7 1.7h2.2M15.4 4.2h2.2a1.7 1.7 0 0 1 1.7 1.7v3.4L21 12l-1.7 2.7v3.4a1.7 1.7 0 0 1-1.7 1.7h-2.2" />
          <path className="workflow-guide" d="M9.2 9.6h5.6M9.2 14.4h3.4" />
          <circle className="workflow-node" cx="15.6" cy="14.4" r="1.3" />
        </>
      );
    case "ai-connectors":
      return (
        <>
          <path d="M3.6 5.4h8.2a1.5 1.5 0 0 1 1.5 1.5v4.4a1.5 1.5 0 0 1-1.5 1.5H8l-3.2 2.6v-2.6h-1.2a1.5 1.5 0 0 1-1.5-1.5V6.9a1.5 1.5 0 0 1 1.5-1.5z"/>
          <path className="workflow-emphasis" d="M13.6 17.6h3.2a3.4 3.4 0 0 0 0-6.8h-1.4"/>
          <circle className="workflow-node" cx="11.6" cy="17.6" r="1.8"/>
        </>
      );
    case "methods":
    case "nav-help":
      return (
        <>
          <path d="M6.6 3.6h7.8l4 4v12.8a.6.6 0 0 1-.6.6H6.6a.6.6 0 0 1-.6-.6V4.2a.6.6 0 0 1 .6-.6z" />
          <path className="workflow-guide" d="M14.4 3.6v4h4" />
          <path d="M9 12.2h6M9 16h3.8" />
        </>
      );
    case "endpoint-coverage":
      return (
        <>
          <rect className="workflow-guide" x="3.4" y="5" width="17.2" height="3.4" rx="1.7"/>
          <rect className="workflow-guide" x="3.4" y="10.3" width="17.2" height="3.4" rx="1.7"/>
          <rect className="workflow-guide" x="3.4" y="15.6" width="17.2" height="3.4" rx="1.7"/>
          <path className="workflow-node" d="M5.1 5h8.4a1.7 1.7 0 0 1 0 3.4H5.1a1.7 1.7 0 0 1 0-3.4z"/>
          <path className="workflow-node" d="M5.1 10.3h11.6a1.7 1.7 0 0 1 0 3.4H5.1a1.7 1.7 0 0 1 0-3.4z"/>
          <path className="workflow-node" d="M5.1 15.6h5.2a1.7 1.7 0 0 1 0 3.4H5.1a1.7 1.7 0 0 1 0-3.4z"/>
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
          <path d="M6.4 3.6h11.2M6.4 20.4h11.2"/>
          <path d="M7.4 3.6v3.2c0 2.4 4.6 3.6 4.6 5.2s-4.6 2.8-4.6 5.2v3.2M16.6 3.6v3.2c0 2.4-4.6 3.6-4.6 5.2s4.6 2.8 4.6 5.2v3.2"/>
          <path className="workflow-node" d="M9.4 17.4c0-1.4 5.2-1.4 5.2 0z"/>
        </>
      );
    case "metadata":
      return (
        <>
          <rect className="workflow-node" x="3.8" y="5.4" width="4.6" height="4.6" rx="1"/>
          <rect className="workflow-guide" x="9.7" y="5.4" width="4.6" height="4.6" rx="1"/>
          <rect className="workflow-node" x="15.6" y="5.4" width="4.6" height="4.6" rx="1"/>
          <rect className="workflow-node" x="3.8" y="14" width="4.6" height="4.6" rx="1"/>
          <rect className="workflow-node" x="9.7" y="14" width="4.6" height="4.6" rx="1"/>
          <rect className="workflow-guide" x="15.6" y="14" width="4.6" height="4.6" rx="1"/>
        </>
      );
    case "biological-annotations":
      return (
        <>
          <path d="M11.4 3.8H5.2a1.4 1.4 0 0 0-1.4 1.4v6.2c0 .4.2.7.4 1l8.4 8.4a1.4 1.4 0 0 0 2 0l6.2-6.2a1.4 1.4 0 0 0 0-2l-8.4-8.4a1.4 1.4 0 0 0-1-.4z"/>
          <circle className="workflow-node" cx="8" cy="8" r="1.6"/>
        </>
      );
    case "nav-home":
      return (
        <>
          <path d="M3.9 10.5 12 4.2l8.1 6.3v9.3a.7.7 0 0 1-.7.7H4.6a.7.7 0 0 1-.7-.7z" />
          <path d="M9.6 20.5v-5.4h4.8v5.4" />
        </>
      );
    case "nav-analysis":
      return (
        <>
          <path className="workflow-guide" d="M4 3.6V20h16.4" />
          <path className="workflow-emphasis" d="M4.6 6.4h4.2v4.3h4.2v4.3h4.8" />
          <path d="M6.8 4.9v3" />
        </>
      );
    case "nav-compare":
      return (
        <>
          <path className="workflow-emphasis" d="M3.4 5.6h4.6v3.2h4.6v3.2h5.4" />
          <path d="M3.4 12.8h3.6v3.4h3.6v3.4h5" />
        </>
      );
    case "nav-pancancer":
      return (
        <>
          <circle className="workflow-node workflow-node-soft" cx="5.4" cy="5.4" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="12" cy="5.4" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="18.6" cy="5.4" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="5.4" cy="12" r="1.7" />
          <circle className="workflow-node" cx="12" cy="12" r="2.2" />
          <circle cx="12" cy="12" r="5" />
          <circle className="workflow-node workflow-node-soft" cx="18.6" cy="12" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="5.4" cy="18.6" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="12" cy="18.6" r="1.7" />
          <circle className="workflow-node workflow-node-soft" cx="18.6" cy="18.6" r="1.7" />
        </>
      );
    case "nav-repository":
      return (
        <>
          <ellipse className="workflow-guide" cx="12" cy="6.6" rx="7.2" ry="2.8" />
          <path d="M4.8 6.6v10.6c0 1.6 3.2 2.8 7.2 2.8s7.2-1.2 7.2-2.8V6.6" />
          <path className="workflow-emphasis" d="M12 9.6v5.2m-2.5-2.4 2.5 2.4 2.5-2.4" />
        </>
      );
    case "nav-examples":
      return (
        <>
          <path className="workflow-guide" d="M12 7.2v12.4" />
          <path d="M12 7.2C10.2 5.6 7.4 5 4.2 5v12.6c3.2 0 6 .6 7.8 2" />
          <path d="M12 7.2c1.8-1.6 4.6-2.2 7.8-2.2v12.6c-3.2 0-6 .6-7.8 2" />
        </>
      );
    default:
      throw new Error(`Unknown TRACE Explorer workflow icon drawing: ${kind}`);
  }
}
