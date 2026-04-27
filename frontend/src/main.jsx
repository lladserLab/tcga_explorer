import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertCircle,
  Archive,
  ArrowDownToLine,
  BarChart3,
  CalendarDays,
  ChevronDown,
  CheckCircle2,
  ClipboardList,
  Database,
  Dna,
  FileSpreadsheet,
  FileText,
  Image,
  Loader2,
  Palette,
  PieChart,
  Play,
  Search,
  Settings2,
  SlidersHorizontal,
  Table2,
  X,
} from "lucide-react";
import {
  apiUrl,
  createAnalysis,
  createAnalysesBatch,
  getCohortEndpoints,
  getCohorts,
  getDataSources,
  getDatasetSummary,
  getExpressionScales,
  getFilterOptions,
  getHealth,
  searchGenes,
} from "./api";
import "./styles.css";

const CUTPOINTS = [
  { value: "maxstat", label: "Maxstat", help: "Survival-optimized cutpoint, min 15% per group" },
  { value: "median", label: "Median", help: "Two balanced expression groups" },
  { value: "tertiles", label: "Tertiles", help: "Low, middle and high groups" },
  { value: "upper_quartile", label: "Upper quartile", help: "Top 25% against the rest" },
  { value: "upper_lower_quartile", label: "Outer quartiles", help: "Top 25% against bottom 25%" },
  { value: "percentile", label: "Percentile", help: "Custom high-expression threshold" },
];

const EXPRESSION_SCALE_FALLBACK = [
  {
    value: "log2_tpm",
    label: "log2(TPM + 1)",
    note: "Recommended normalized scale for TCGA survival analysis.",
  },
  {
    value: "log2_cpm",
    label: "log2(CPM + 1)",
    note: "Computed from raw STAR counts as a count-based fallback.",
  },
  {
    value: "log2_fpkm",
    label: "log2(FPKM + 1)",
    note: "Log-transformed FPKM from cached GDC files.",
  },
  {
    value: "log2_fpkm_uq",
    label: "log2(FPKM-UQ + 1)",
    note: "Log-transformed upper-quartile FPKM from cached GDC files.",
  },
];

const COHORT_NAMES = {
  "TCGA-ACC": "Adrenocortical Carcinoma",
  "TCGA-BLCA": "Bladder Urothelial Carcinoma",
  "TCGA-BRCA": "Breast Invasive Carcinoma",
  "TCGA-CESC": "Cervical Squamous Cell Carcinoma and Endocervical Adenocarcinoma",
  "TCGA-CHOL": "Cholangiocarcinoma",
  "TCGA-COAD": "Colon Adenocarcinoma",
  "TCGA-DLBC": "Lymphoid Neoplasm Diffuse Large B-cell Lymphoma",
  "TCGA-ESCA": "Esophageal Carcinoma",
  "TCGA-GBM": "Glioblastoma Multiforme",
  "TCGA-HNSC": "Head and Neck Squamous Cell Carcinoma",
  "TCGA-KICH": "Kidney Chromophobe",
  "TCGA-KIRC": "Kidney Renal Clear Cell Carcinoma",
  "TCGA-KIRP": "Kidney Renal Papillary Cell Carcinoma",
  "TCGA-LAML": "Acute Myeloid Leukemia",
  "TCGA-LGG": "Brain Lower Grade Glioma",
  "TCGA-LIHC": "Liver Hepatocellular Carcinoma",
  "TCGA-LUAD": "Lung Adenocarcinoma",
  "TCGA-LUSC": "Lung Squamous Cell Carcinoma",
  "TCGA-MESO": "Mesothelioma",
  "TCGA-OV": "Ovarian Serous Cystadenocarcinoma",
  "TCGA-PAAD": "Pancreatic Adenocarcinoma",
  "TCGA-PCPG": "Pheochromocytoma and Paraganglioma",
  "TCGA-PRAD": "Prostate Adenocarcinoma",
  "TCGA-READ": "Rectum Adenocarcinoma",
  "TCGA-SARC": "Sarcoma",
  "TCGA-SKCM": "Skin Cutaneous Melanoma",
  "TCGA-STAD": "Stomach Adenocarcinoma",
  "TCGA-TGCT": "Testicular Germ Cell Tumors",
  "TCGA-THCA": "Thyroid Carcinoma",
  "TCGA-THYM": "Thymoma",
  "TCGA-UCEC": "Uterine Corpus Endometrial Carcinoma",
  "TCGA-UCS": "Uterine Carcinosarcoma",
  "TCGA-UVM": "Uveal Melanoma",
};

const DEFAULT_PLOT_STYLE = {
  palette: ["#2f756f", "#d7953f", "#b44b3f"],
  font_family: "sans",
  base_font_size: 12,
  axis_text_size: 11,
  axis_title_size: 12,
  show_grid: true,
  show_title: false,
  plot_title: "",
};

const EMPTY_FILTERS = {
  sample_types: [],
  stages: [],
  genders: [],
  races: [],
  age_min: "",
  age_max: "",
  max_time_days: "",
};

const ANALYSIS_BATCH_CONCURRENCY = 10;
const ENDPOINT_FALLBACK = [
  {
    value: "OS",
    label: "Overall survival",
    available: true,
    source: "derived_sample_metadata",
    reason: "Fallback OS derived from TCGA clinical/sample metadata.",
  },
];

function getCohortName(cohortId) {
  return COHORT_NAMES[cohortId] || cohortId || "Unknown cancer";
}

function getCohortLabel(cohortId) {
  return cohortId ? `${getCohortName(cohortId)} (${cohortId})` : "Select cancer";
}

function buildAnalysisPayload(form) {
  const signatureGenes = parseSignatureGenes(form.gene_symbol);
  return {
    ...form,
    gene_symbol: form.gene_symbol.trim().toUpperCase(),
    signature_genes: form.signature_method === "single" ? [] : signatureGenes,
    custom_percentile:
      form.cutpoint_method === "percentile" ? Number(form.custom_percentile) : null,
    plot_style: {
      ...form.plot_style,
      base_font_size: Number(form.plot_style.base_font_size),
      axis_text_size: Number(form.plot_style.axis_text_size),
      axis_title_size: Number(form.plot_style.axis_title_size),
      show_grid: Boolean(form.plot_style.show_grid),
      show_title: Boolean(form.plot_style.show_title),
      plot_title: form.plot_style.show_title ? form.plot_style.plot_title.trim() || null : null,
    },
    filters: {
      ...form.filters,
      age_min: toNullableNumber(form.filters.age_min),
      age_max: toNullableNumber(form.filters.age_max),
      max_time_days: toNullableNumber(form.filters.max_time_days),
    },
  };
}

function parseSignatureGenes(text) {
  return text
    .split(/[,+;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const [gene, weight] = item.split(":").map((part) => part.trim());
      return { gene_symbol: gene.toUpperCase(), weight: Number(weight) || 1 };
    });
}

function uniqueGeneSymbols(text) {
  const seen = new Set();
  return parseSignatureGenes(text)
    .map((item) => item.gene_symbol)
    .filter((gene) => {
      if (!gene || seen.has(gene)) return false;
      seen.add(gene);
      return true;
    });
}

function currentGeneSearchTerm(text) {
  const token = text.split(/[,+;\n]/).pop()?.trim() || "";
  return token.split(":")[0]?.trim() || "";
}

function geneInputTokens(text) {
  const seen = new Set();
  return text
    .split(/[,+;\n]/)
    .map((item) => normalizeGeneToken(item))
    .filter(Boolean)
    .filter((token) => {
      const symbol = geneSymbolFromToken(token);
      if (seen.has(symbol)) return false;
      seen.add(symbol);
      return true;
    });
}

function normalizeGeneToken(item) {
  const [gene, weight] = String(item || "").split(":").map((part) => part.trim());
  const symbol = gene.toUpperCase();
  if (!symbol) return "";
  return weight ? `${symbol}:${weight}` : symbol;
}

function geneSymbolFromToken(token) {
  return String(token || "").split(":")[0].trim().toUpperCase();
}

function addGeneToken(value, token) {
  const normalized = normalizeGeneToken(token);
  if (!normalized) return geneInputTokens(value).join(", ");
  const symbol = geneSymbolFromToken(normalized);
  const existing = geneInputTokens(value).filter((item) => geneSymbolFromToken(item) !== symbol);
  return [...existing, normalized].join(", ");
}

function removeGeneToken(value, symbol) {
  const normalizedSymbol = String(symbol || "").trim().toUpperCase();
  return geneInputTokens(value)
    .filter((item) => geneSymbolFromToken(item) !== normalizedSymbol)
    .join(", ");
}

function App() {
  const resultPanelRef = useRef(null);
  const [health, setHealth] = useState(null);
  const [cohorts, setCohorts] = useState([]);
  const [datasetSummary, setDatasetSummary] = useState(null);
  const [dataSources, setDataSources] = useState([]);
  const [endpointOptions, setEndpointOptions] = useState(ENDPOINT_FALLBACK);
  const [expressionScales, setExpressionScales] = useState(EXPRESSION_SCALE_FALLBACK);
  const [filters, setFilters] = useState(null);
  const [genes, setGenes] = useState([]);
  const [analysisResults, setAnalysisResults] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [geneQuery, setGeneQuery] = useState("");
  const [cohortQuery, setCohortQuery] = useState("");
  const [cohortPickerOpen, setCohortPickerOpen] = useState(false);
  const [summaryCohort, setSummaryCohort] = useState("");
  const [activePage, setActivePage] = useState("analysis");
  const [downloadNotices, setDownloadNotices] = useState([]);
  const [compare, setCompare] = useState({
    genes: "",
    methods: ["median", "upper_quartile"],
    running: false,
    results: [],
    error: "",
  });

  const [form, setForm] = useState({
    cohort: "",
    gene_symbol: "",
    endpoint: "OS",
    signature_method: "single",
    signature_genes: [],
    expression_scale: "log2_tpm",
    cutpoint_method: "median",
    custom_percentile: 50,
    time_unit: "days",
    show_confidence_interval: true,
    show_risk_table: true,
    plot_style: DEFAULT_PLOT_STYLE,
    filters: EMPTY_FILTERS,
  });

  useEffect(() => {
    Promise.all([getHealth(), getCohorts(), getExpressionScales(), getDatasetSummary(), getDataSources()])
      .then(([healthPayload, cohortPayload, scalePayload, summaryPayload, sourcePayload]) => {
        setHealth(healthPayload);
        setCohorts(cohortPayload);
        setDatasetSummary(summaryPayload);
        setDataSources(sourcePayload?.sources || summaryPayload?.data_sources || []);
        if (scalePayload?.length) {
          setExpressionScales(scalePayload);
        }
        if (form.cohort && cohortPayload.length && !cohortPayload.find((item) => item.id === form.cohort)) {
          setForm((current) => ({ ...current, cohort: "" }));
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!form.cohort) return;
    Promise.all([getFilterOptions(form.cohort), getCohortEndpoints(form.cohort)])
      .then(([payload, endpointPayload]) => {
        setFilters(payload);
        const options = endpointPayload?.endpoints?.length ? endpointPayload.endpoints : ENDPOINT_FALLBACK;
        setEndpointOptions(options);
        const fallbackEndpoint = options.find((item) => item.available) || options[0] || ENDPOINT_FALLBACK[0];
        setForm((current) => ({
          ...current,
          endpoint: options.find((item) => item.value === current.endpoint && item.available)
            ? current.endpoint
            : fallbackEndpoint.value,
          filters: { ...EMPTY_FILTERS },
        }));
      })
      .catch((err) => setError(err.message));
  }, [form.cohort]);

  useEffect(() => {
    getDatasetSummary(summaryCohort)
      .then((payload) => setDatasetSummary(payload))
      .catch((err) => setError(err.message));
  }, [summaryCohort]);

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(geneQuery);
    if (!form.cohort || searchTerm.length < 1) {
      setGenes([]);
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(form.cohort, searchTerm)
        .then((payload) => setGenes(payload.genes))
        .catch(() => setGenes([]));
    }, 220);
    return () => clearTimeout(handle);
  }, [form.cohort, geneQuery]);

  const selectedCohort = useMemo(
    () => cohorts.find((cohort) => cohort.id === form.cohort),
    [cohorts, form.cohort],
  );

  const visibleCohorts = useMemo(() => {
    const query = cohortQuery.trim().toLowerCase();
    if (!query) return cohorts;
    return cohorts.filter((cohort) =>
      [cohort.id, getCohortName(cohort.id), cohort.primary_site, cohort.disease_type]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    );
  }, [cohorts, cohortQuery]);

  const activeFilterCount = useMemo(() => {
    const listCount =
      form.filters.sample_types.length +
      form.filters.stages.length +
      form.filters.genders.length +
      form.filters.races.length;
    const rangeCount = ["age_min", "age_max", "max_time_days"].filter(
      (key) => form.filters[key] !== "",
    ).length;
    return listCount + rangeCount;
  }, [form.filters]);

  const selectedCutpoint = CUTPOINTS.find((item) => item.value === form.cutpoint_method);
  const selectedExpressionScale =
    expressionScales.find((item) => item.value === form.expression_scale) || EXPRESSION_SCALE_FALLBACK[0];
  const selectedEndpoint =
    endpointOptions.find((item) => item.value === form.endpoint) || ENDPOINT_FALLBACK[0];
  const effectiveGeneInput = geneQuery.trim() ? addGeneToken(form.gene_symbol, geneQuery) : form.gene_symbol;
  const selectedGenes = uniqueGeneSymbols(effectiveGeneInput);
  const runCount = form.signature_method === "single" ? selectedGenes.length : Math.min(selectedGenes.length, 1);
  const canRun = Boolean(form.cohort && selectedGenes.length && selectedEndpoint.available) && !loading;
  const selectedCancerName = form.cohort ? getCohortName(form.cohort) : "Select cancer";
  const plotCancerName = form.cohort ? getCohortName(form.cohort) : "Cancer";

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateFilters(key, value) {
    setForm((current) => ({
      ...current,
      filters: { ...current.filters, [key]: value },
    }));
  }

  function updatePlotStyle(key, value) {
    setForm((current) => ({
      ...current,
      plot_style: { ...current.plot_style, [key]: value },
    }));
  }

  function updatePaletteColor(index, value) {
    setForm((current) => {
      const palette = [...current.plot_style.palette];
      palette[index] = value;
      return {
        ...current,
        plot_style: { ...current.plot_style, palette },
      };
    });
  }

  function selectCohort(value) {
    updateForm("cohort", value);
    setCohortPickerOpen(false);
    setCohortQuery("");
    setAnalysisResults([]);
    setError("");
  }

  function toggleFilterValue(key, value) {
    const current = form.filters[key] || [];
    const next = current.includes(value)
      ? current.filter((item) => item !== value)
      : [...current, value];
    updateFilters(key, next);
  }

  function clearFilter(key) {
    updateFilters(key, []);
  }

  function dismissDownloadNotice(id) {
    setDownloadNotices((current) => current.filter((notice) => notice.id !== id));
  }

  function updateDownloadNotice(id, patch) {
    setDownloadNotices((current) =>
      current.map((notice) => (notice.id === id ? { ...notice, ...patch } : notice)),
    );
  }

  async function startDownload(href, label) {
    if (!href) return;
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    setDownloadNotices((current) => [
      ...current,
      { id, label, status: "running", message: "Preparing download" },
    ]);
    try {
      const response = await fetch(apiUrl(href));
      if (!response.ok) {
        throw new Error(response.statusText || `HTTP ${response.status}`);
      }
      const blob = await response.blob();
      const filename =
        filenameFromDisposition(response.headers.get("Content-Disposition")) ||
        fallbackDownloadFilename(label, href);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      updateDownloadNotice(id, { status: "done", message: "Download ready" });
      window.setTimeout(() => dismissDownloadNotice(id), 4500);
    } catch (err) {
      updateDownloadNotice(id, {
        status: "failed",
        message: err?.message || "Download failed",
      });
    }
  }

  function scrollToResults() {
    window.requestAnimationFrame(() => {
      resultPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function runAnalysis() {
    const sourceInput = geneQuery.trim() ? addGeneToken(form.gene_symbol, geneQuery) : form.gene_symbol;
    const normalizedGenes = uniqueGeneSymbols(sourceInput);
    if (!normalizedGenes.length) {
      setError("Enter at least one gene symbol before running the analysis.");
      return;
    }

    setLoading(true);
    setError("");
    setAnalysisResults([]);
    scrollToResults();
    const normalizedInput =
      form.signature_method === "single"
        ? normalizedGenes.join(", ")
        : geneInputTokens(sourceInput).join(", ");
    setGeneQuery("");
    updateForm("gene_symbol", normalizedInput);

    try {
      if (form.signature_method === "single") {
        const payloads = normalizedGenes.map((gene) => ({
            ...buildAnalysisPayload({ ...form, gene_symbol: gene, signature_method: "single" }),
            gene_symbol: gene,
            signature_method: "single",
            signature_genes: [],
        }));
        if (payloads.length === 1) {
          const result = await createAnalysis(payloads[0]);
          setAnalysisResults([result]);
        } else {
          const batch = await createAnalysesBatch(payloads, ANALYSIS_BATCH_CONCURRENCY);
          const successful = batch.results
            .filter((item) => item.status === "completed" && item.result)
            .map((item) => item.result);
          setAnalysisResults(successful);
          if (batch.failed) {
            const firstFailure = batch.results.find((item) => item.status === "failed");
            setError(`${batch.failed} analysis${batch.failed === 1 ? "" : "es"} failed. ${formatBatchItemError(firstFailure)}`);
          }
        }
      } else {
        const payload = buildAnalysisPayload({ ...form, gene_symbol: normalizedInput });
        const result = await createAnalysis(payload);
        setAnalysisResults([result]);
      }
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Dna size={30} />
          <div>
            <strong>TCGA KM Explorer</strong>
            <span>RNA survival workspace</span>
          </div>
        </div>

        <div className="status-block">
          <StatusItem icon={<Database size={16} />} label="Cohorts" value={health?.cohorts ?? "..."} />
          <StatusItem icon={<Activity size={16} />} label="Endpoint" value={selectedEndpoint.label} />
          <StatusItem icon={<BarChart3 size={16} />} label="Expression" value={selectedExpressionScale.label} />
          <StatusItem
            icon={<CalendarDays size={16} />}
            label="Data loaded"
            value={formatDate(health?.data_dates?.database_imported_at)}
          />
        </div>

        <nav className="side-nav" aria-label="Workspace pages">
          <button
            type="button"
            className={activePage === "analysis" ? "selected" : ""}
            onClick={() => setActivePage("analysis")}
          >
            <Activity size={16} />
            KM Analysis
          </button>
          <button
            type="button"
            className={activePage === "compare" ? "selected" : ""}
            onClick={() => setActivePage("compare")}
          >
            <BarChart3 size={16} />
            Compare Analyses
          </button>
          <button
            type="button"
            className={activePage === "summary" ? "selected" : ""}
            onClick={() => setActivePage("summary")}
          >
            <ClipboardList size={16} />
            Dataset Summary
          </button>
        </nav>

      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">
              {activePage === "analysis" ? "Kaplan-Meier analysis" : activePage === "compare" ? "Compare analyses" : "Dataset summary"}
            </p>
            <h1>
              {activePage === "analysis"
                ? "Gene expression survival explorer"
                : activePage === "compare"
                  ? "Gene and cutpoint comparison"
                  : "Current TCGA data inventory"}
            </h1>
          </div>
        </header>

        {activePage === "analysis" ? (
          <>
            <div className="layout">
          <section className="control-panel" aria-label="Analysis controls">
            <PanelHeader
              icon={<Database size={18} />}
              title="Dataset"
              description="Choose one cancer cohort and one or more RNA gene symbols."
            />

            <CohortPicker
              cohorts={cohorts}
              visibleCohorts={visibleCohorts}
              selectedCohort={selectedCohort}
              selectedCohortId={form.cohort}
              query={cohortQuery}
              setQuery={setCohortQuery}
              open={cohortPickerOpen}
              setOpen={setCohortPickerOpen}
              onSelect={selectCohort}
            />

            {selectedCohort && (
              <div className="cohort-summary">
                <div className="cohort-title">
                  <strong>{getCohortName(selectedCohort.id)}</strong>
                  <span>{selectedCohort.id}</span>
                </div>
                <SummaryStat label="RNA samples" value={selectedCohort.n_samples_paired} />
                <SummaryStat label="Patients" value={selectedCohort.n_patients_paired} />
                <SummaryStat label="Tumors" value={selectedCohort.n_primary_tumor} />
                <p>{selectedCohort.primary_site}</p>
              </div>
            )}

            <GeneSelector
              label={form.signature_method === "single" ? "Gene symbols" : "Signature genes"}
              value={form.gene_symbol}
              onChange={(value) => updateForm("gene_symbol", value)}
              draft={geneQuery}
              setDraft={setGeneQuery}
              suggestions={genes}
              placeholder={form.signature_method === "single" ? "Type TP53, KRAS, EGFR..." : "Type TP53, KRAS or TP53:1"}
              help={
                form.signature_method === "single"
                  ? "Select one or more genes. Each gene produces its own Kaplan-Meier plot."
                  : "Select genes for one combined expression signature. Weighted mode accepts GENE:weight."
              }
            />

            <PanelHeader
              icon={<Activity size={18} />}
              title="Survival endpoint"
              description="TCGA-CDR endpoints are enabled only when the selected cohort passes basic patient and event QC."
            />

            <EndpointSelector
              endpoints={endpointOptions}
              selected={form.endpoint}
              onSelect={(value) => updateForm("endpoint", value)}
            />

            <PanelHeader
              icon={<Activity size={18} />}
              title="Gene analysis"
              description="Single-gene mode creates one KM plot per gene; signature modes combine multiple genes into one score."
            />

            <div className="axis-control">
              <span>Gene mode</span>
              <div>
                {[
                  ["single", "Single genes"],
                  ["mean", "Mean signature"],
                  ["zscore", "Z-score signature"],
                  ["weighted", "Weighted signature"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={form.signature_method === value ? "selected" : ""}
                    onClick={() => updateForm("signature_method", value)}
                    title={signatureHelp(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            <PanelHeader
              icon={<BarChart3 size={18} />}
              title="RNA expression scale"
              description="Use a log-scale normalized value for patient stratification."
            />

            <div className="scale-grid" aria-label="RNA expression scale">
              {expressionScales.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={form.expression_scale === item.value ? "selected" : ""}
                  onClick={() => updateForm("expression_scale", item.value)}
                  title={expressionTooltip(item.value)}
                >
                  <strong>{item.label}</strong>
                  <span>{item.note}</span>
                </button>
              ))}
            </div>

            <PanelHeader
              icon={<SlidersHorizontal size={18} />}
              title="Stratification"
              description="Split patients by expression before fitting survival curves."
            />

            <div className="method-grid">
              {CUTPOINTS.map((item) => (
                <button
                  key={item.value}
                  type="button"
                  className={form.cutpoint_method === item.value ? "selected" : ""}
                  onClick={() => updateForm("cutpoint_method", item.value)}
                  title={cutpointTooltip(item.value)}
                >
                  <strong>{item.label}</strong>
                  <span>{item.help}</span>
                </button>
              ))}
            </div>

            {form.cutpoint_method === "maxstat" && (
              <div className="method-note">
                Maxstat optimizes the cutpoint against survival separation. Treat it as exploratory
                and validate important findings externally.
              </div>
            )}

            {form.cutpoint_method === "percentile" && (
              <label className="field">
                <span>Percentile threshold</span>
                <input
                  type="number"
                  min="1"
                  max="99"
                  value={form.custom_percentile}
                  onChange={(event) => updateForm("custom_percentile", event.target.value)}
                />
              </label>
            )}

            <PanelHeader
              icon={<Settings2 size={18} />}
              title="Clinical filters"
              description="Leave a filter empty to include all available values."
            />

            <FilterGroup
              title="Sample type"
              values={filters?.sample_types || []}
              selected={form.filters.sample_types}
              onToggle={(value) => toggleFilterValue("sample_types", value)}
              onClear={() => clearFilter("sample_types")}
            />
            <FilterGroup
              title="Stage"
              values={filters?.stages || []}
              selected={form.filters.stages}
              onToggle={(value) => toggleFilterValue("stages", value)}
              onClear={() => clearFilter("stages")}
            />
            <FilterGroup
              title="Gender"
              values={filters?.genders || []}
              selected={form.filters.genders}
              onToggle={(value) => toggleFilterValue("genders", value)}
              onClear={() => clearFilter("genders")}
            />
            <FilterGroup
              title="Race"
              values={filters?.races || []}
              selected={form.filters.races}
              onToggle={(value) => toggleFilterValue("races", value)}
              onClear={() => clearFilter("races")}
            />

            <div className="range-grid">
              <label className="field">
                <span>Min age</span>
                <input
                  value={form.filters.age_min}
                  onChange={(event) => updateFilters("age_min", event.target.value)}
                  placeholder={filters?.age_min ? String(Math.floor(filters.age_min)) : ""}
                />
              </label>
              <label className="field">
                <span>Max age</span>
                <input
                  value={form.filters.age_max}
                  onChange={(event) => updateFilters("age_max", event.target.value)}
                  placeholder={filters?.age_max ? String(Math.ceil(filters.age_max)) : ""}
                />
              </label>
              <label className="field wide">
                <span>Maximum follow-up days</span>
                <input
                  value={form.filters.max_time_days}
                  onChange={(event) => updateFilters("max_time_days", event.target.value)}
                  placeholder={filters?.os_time_max_days ? String(Math.ceil(filters.os_time_max_days)) : ""}
                />
              </label>
            </div>

            <div className="axis-control">
              <span>Plot X-axis</span>
              <div>
                {["days", "months", "years"].map((unit) => (
                  <button
                    key={unit}
                    type="button"
                    className={form.time_unit === unit ? "selected" : ""}
                    onClick={() => updateForm("time_unit", unit)}
                  >
                    {unit}
                  </button>
                ))}
              </div>
            </div>

            <div className="switch-row">
              <SwitchField
                label="Confidence interval"
                checked={form.show_confidence_interval}
                onChange={(checked) => updateForm("show_confidence_interval", checked)}
              />
              <SwitchField
                label="Risk table"
                checked={form.show_risk_table}
                onChange={(checked) => updateForm("show_risk_table", checked)}
              />
            </div>

            <PanelHeader
              icon={<Palette size={18} />}
              title="Plot style"
              description="Customize colors and typography for exported PNG and SVG artifacts."
            />

            <div className="color-grid">
              <ColorField
                label="Low / group 1"
                value={form.plot_style.palette[0]}
                onChange={(value) => updatePaletteColor(0, value)}
              />
              <ColorField
                label="Mid / group 2"
                value={form.plot_style.palette[1]}
                onChange={(value) => updatePaletteColor(1, value)}
              />
              <ColorField
                label="High / group 3"
                value={form.plot_style.palette[2]}
                onChange={(value) => updatePaletteColor(2, value)}
              />
            </div>

            <div className="range-grid">
              <label className="field">
                <span>Font family</span>
                <select
                  value={form.plot_style.font_family}
                  onChange={(event) => updatePlotStyle("font_family", event.target.value)}
                >
                  <option value="sans">Sans</option>
                  <option value="serif">Serif</option>
                  <option value="mono">Mono</option>
                </select>
              </label>
              <label className="field">
                <span>Base font size</span>
                <input
                  type="number"
                  min="8"
                  max="20"
                  value={form.plot_style.base_font_size}
                  onChange={(event) => updatePlotStyle("base_font_size", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Axis values size</span>
                <input
                  type="number"
                  min="6"
                  max="24"
                  value={form.plot_style.axis_text_size}
                  onChange={(event) => updatePlotStyle("axis_text_size", event.target.value)}
                />
              </label>
              <label className="field">
                <span>Axis titles size</span>
                <input
                  type="number"
                  min="6"
                  max="26"
                  value={form.plot_style.axis_title_size}
                  onChange={(event) => updatePlotStyle("axis_title_size", event.target.value)}
                />
              </label>
              <SwitchField
                label="Plot grid"
                checked={form.plot_style.show_grid}
                onChange={(checked) => updatePlotStyle("show_grid", checked)}
              />
              <SwitchField
                label="Plot title"
                checked={form.plot_style.show_title}
                onChange={(checked) => updatePlotStyle("show_title", checked)}
              />
              {form.plot_style.show_title && (
                <label className="field wide">
                <span>Plot title</span>
                <input
                  value={form.plot_style.plot_title}
                  onChange={(event) => updatePlotStyle("plot_title", event.target.value)}
                  placeholder={`${plotCancerName} overall survival`}
                />
                </label>
              )}
            </div>

            <div className="run-summary">
              <div>
                <span>Ready request</span>
                <strong>
                  {selectedCancerName} / {runCount ? `${runCount} gene${runCount === 1 ? "" : "s"}` : "GENE"}
                </strong>
                <small>{form.signature_method === "single" ? "Separate KM plot per gene" : "Combined signature plot"}; {selectedEndpoint.label}; {selectedExpressionScale.label}</small>
              </div>
              <button className="primary-button" onClick={runAnalysis} disabled={!canRun}>
                {loading ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
                Run analysis
              </button>
            </div>
          </section>

          <section ref={resultPanelRef} className="result-panel" aria-label="Analysis result">
            {error && (
              <div className="error-box">
                <AlertCircle size={18} />
                <div>
                  <strong>Analysis did not complete</strong>
                  <span>{error}</span>
                </div>
              </div>
            )}

            {!analysisResults.length && !loading && !error && (
              <PreviewState
                cohort={selectedCohort}
                signatureMethod={form.signature_method}
                geneCount={runCount}
                endpoint={selectedEndpoint}
                expressionScale={selectedExpressionScale}
                cutpoint={selectedCutpoint}
                activeFilterCount={activeFilterCount}
              />
            )}

            {loading && (
              <LoadingState
                cohort={form.cohort}
                gene={form.gene_symbol}
                signatureMethod={form.signature_method}
                geneCount={runCount}
                completedCount={analysisResults.length}
                endpoint={selectedEndpoint}
                expressionScale={selectedExpressionScale}
              />
            )}
            {!!analysisResults.length && <AnalysisResults analyses={analysisResults} onDownload={startDownload} />}
          </section>
            </div>
          </>
        ) : activePage === "compare" ? (
          <CompareAnalyses
            form={form}
            updateForm={updateForm}
            compare={compare}
            setCompare={setCompare}
            cutpoints={CUTPOINTS}
            expressionScale={selectedExpressionScale}
            canRun={Boolean(form.cohort && selectedEndpoint.available)}
            onDownload={startDownload}
          />
        ) : (
          <DatasetSummary
            summary={datasetSummary}
            health={health}
            dataSources={dataSources}
            cohorts={cohorts}
            summaryCohort={summaryCohort}
            setSummaryCohort={setSummaryCohort}
          />
        )}
      </section>
      <DownloadNotifications notices={downloadNotices} onDismiss={dismissDownloadNotice} />
    </main>
  );
}

function StatusItem({ icon, label, value }) {
  return (
    <div className="status-item">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PanelHeader({ icon, title, description }) {
  return (
    <div className="panel-header">
      {icon}
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}

function SummaryStat({ label, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{formatInteger(value)}</strong>
    </div>
  );
}

function CohortPicker({
  cohorts,
  visibleCohorts,
  selectedCohort,
  selectedCohortId,
  query,
  setQuery,
  open,
  setOpen,
  onSelect,
}) {
  const selectedLabel = selectedCohort ? getCohortName(selectedCohort.id) : "Choose cancer cohort";
  return (
    <div className="cohort-picker">
      <button
        type="button"
        className={`cohort-trigger${open ? " open" : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls="cohort-picker-list"
      >
        <span>
          <strong>{selectedLabel}</strong>
          <small>
            {selectedCohort
              ? `${selectedCohort.id} / ${formatInteger(selectedCohort.n_patients_paired)} patients`
              : `${formatInteger(cohorts.length)} TCGA cohorts available`}
          </small>
        </span>
        <ChevronDown size={18} aria-hidden="true" />
      </button>

      {open && (
        <div className="cohort-menu">
          <label className="cohort-search">
            <Search size={16} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search cancer name, TCGA code, site or disease"
              autoFocus
            />
          </label>
          <div className="cohort-count">
            Showing {formatInteger(visibleCohorts.length)} of {formatInteger(cohorts.length)}
          </div>
          <div id="cohort-picker-list" className="cohort-browser" role="listbox" aria-label="Available TCGA cohorts">
            {visibleCohorts.map((cohort) => (
              <button
                key={cohort.id}
                type="button"
                role="option"
                aria-selected={selectedCohortId === cohort.id}
                className={selectedCohortId === cohort.id ? "selected" : ""}
                onClick={() => onSelect(cohort.id)}
              >
                <strong>{getCohortName(cohort.id)}</strong>
                <span>{cohort.id} / {formatInteger(cohort.n_patients_paired)} patients</span>
              </button>
            ))}
            {!visibleCohorts.length && (
              <div className="no-cohorts">
                No cohorts match this search.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function FilterGroup({ title, values, selected, onToggle, onClear }) {
  if (!values.length) return null;
  return (
    <div className="filter-group">
      <div className="filter-title">
        <span>{title}</span>
        {!!selected.length && (
          <button type="button" onClick={onClear}>
            Clear
          </button>
        )}
      </div>
      <div>
        {values.slice(0, 14).map((value) => (
          <button
            key={value}
            type="button"
            className={selected.includes(value) ? "selected" : ""}
            onClick={() => onToggle(value)}
          >
            {value}
          </button>
        ))}
      </div>
    </div>
  );
}

function SwitchField({ label, checked, onChange }) {
  return (
    <label className="switch-field">
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      <span aria-hidden="true" />
      <strong>{label}</strong>
    </label>
  );
}

function ColorField({ label, value, onChange }) {
  return (
    <label className="color-field">
      <span>{label}</span>
      <div>
        <input type="color" value={value} onChange={(event) => onChange(event.target.value)} />
        <strong>{value.toUpperCase()}</strong>
      </div>
    </label>
  );
}

function EndpointSelector({ endpoints, selected, onSelect }) {
  return (
    <div className="endpoint-grid" aria-label="Survival endpoint">
      {endpoints.map((item) => (
        <button
          key={item.value}
          type="button"
          className={selected === item.value ? "selected" : ""}
          onClick={() => item.available && onSelect(item.value)}
          disabled={!item.available}
          title={item.reason}
        >
          <strong>{item.label}</strong>
          <span>
            {item.available
              ? `${formatInteger(item.patients)} patients / ${formatInteger(item.events)} events`
              : item.reason}
          </span>
          <small>{formatSourceLabel(item.source)}</small>
        </button>
      ))}
    </div>
  );
}

function GeneSelector({ label, value, onChange, draft, setDraft, suggestions, placeholder, help }) {
  const tokens = geneInputTokens(value);
  const selectedSymbols = tokens.map(geneSymbolFromToken);
  const searchTerm = currentGeneSearchTerm(draft);

  function commitToken(token = draft) {
    const nextValue = addGeneToken(value, token);
    onChange(nextValue);
    setDraft("");
  }

  function handleInputChange(event) {
    const nextDraft = event.target.value;
    if (/[,+;\n]/.test(nextDraft)) {
      const nextValue = nextDraft
        .split(/[,+;\n]/)
        .reduce((current, token) => addGeneToken(current, token), value);
      onChange(nextValue);
      setDraft("");
      return;
    }
    setDraft(nextDraft);
  }

  function handleKeyDown(event) {
    if ((event.key === "Enter" || event.key === "Tab") && draft.trim()) {
      event.preventDefault();
      commitToken(event.key === "Enter" && suggestions.length ? suggestions[0] : draft);
    }
    if (event.key === "Backspace" && !draft && tokens.length) {
      event.preventDefault();
      onChange(tokens.slice(0, -1).join(", "));
    }
  }

  return (
    <div className="gene-selector">
      <div className="gene-selector-header">
        <span>{label}</span>
        {!!tokens.length && (
          <button type="button" onClick={() => onChange("")}>
            Clear all
          </button>
        )}
      </div>
      <div className="gene-autocomplete-wrap">
        <div className="gene-token-box">
          {tokens.map((token) => {
            const symbol = geneSymbolFromToken(token);
            return (
              <span key={symbol} className="gene-chip">
                {token}
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onChange(removeGeneToken(value, symbol))}
                  aria-label={`Remove ${symbol}`}
                >
                  <X size={13} />
                </button>
              </span>
            );
          })}
          <input
            value={draft}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onBlur={() => draft.trim() && commitToken()}
            placeholder={tokens.length ? "Add gene..." : placeholder}
            aria-label={label}
            autoComplete="off"
          />
        </div>
        {!!searchTerm && (
          <div className="gene-autocomplete" role="listbox" aria-label={`${label} suggestions`}>
            <div className="gene-autocomplete-title">
              Suggestions for <strong>{searchTerm.toUpperCase()}</strong>
            </div>
            {suggestions.length ? (
              suggestions.slice(0, 10).map((gene) => (
                <button
                  key={gene}
                  type="button"
                  role="option"
                  aria-selected={selectedSymbols.includes(gene)}
                  className={selectedSymbols.includes(gene) ? "selected" : ""}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => commitToken(gene)}
                >
                  <strong>{gene}</strong>
                  {selectedSymbols.includes(gene) ? <span>Selected</span> : <span>Add gene</span>}
                </button>
              ))
            ) : (
              <div className="gene-autocomplete-empty">No matching gene symbols.</div>
            )}
          </div>
        )}
      </div>
      <small className="field-help">{help}</small>
    </div>
  );
}

function CompareAnalyses({ form, compare, setCompare, cutpoints, expressionScale, canRun, onDownload }) {
  const selectedMethods = compare.methods;
  const [compareGeneQuery, setCompareGeneQuery] = useState("");
  const [compareGeneSuggestions, setCompareGeneSuggestions] = useState([]);
  const effectiveCompareInput = compareGeneQuery.trim() ? addGeneToken(compare.genes, compareGeneQuery) : compare.genes;
  const genes = uniqueGeneSymbols(effectiveCompareInput);
  const adjusted = useMemo(() => adjustCompareResults(compare.results), [compare.results]);
  const selectedCutpoints = cutpoints.filter((item) => selectedMethods.includes(item.value));

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(compareGeneQuery);
    if (!form.cohort || searchTerm.length < 1) {
      setCompareGeneSuggestions([]);
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(form.cohort, searchTerm)
        .then((payload) => setCompareGeneSuggestions(payload.genes))
        .catch(() => setCompareGeneSuggestions([]));
    }, 220);
    return () => clearTimeout(handle);
  }, [form.cohort, compareGeneQuery]);

  function toggleMethod(method) {
    setCompare((current) => ({
      ...current,
      methods: current.methods.includes(method)
        ? current.methods.filter((item) => item !== method)
        : [...current.methods, method],
    }));
  }

  async function runCompare() {
    if (!canRun || !genes.length || !selectedMethods.length) return;
    const normalizedGenes = uniqueGeneSymbols(effectiveCompareInput);
    setCompareGeneQuery("");
    setCompare((current) => ({
      ...current,
      genes: normalizedGenes.join(", "),
      running: true,
      error: "",
      results: [],
    }));
    try {
      const jobs = normalizedGenes.flatMap((gene) =>
        selectedMethods.map((method) => {
          const basePayload = buildAnalysisPayload({ ...form, gene_symbol: gene, signature_method: "single" });
          return {
            gene,
            method,
            payload: {
              ...basePayload,
              gene_symbol: gene,
              signature_method: "single",
              signature_genes: [],
              cutpoint_method: method,
              custom_percentile: method === "percentile" ? Number(form.custom_percentile) : null,
              plot_style: { ...basePayload.plot_style, show_title: false, plot_title: null },
            },
          };
        }),
      );
      const batch = await createAnalysesBatch(jobs.map((job) => job.payload), ANALYSIS_BATCH_CONCURRENCY);
      const results = batch.results.map((item) => {
        const job = jobs[item.index];
        return {
          gene: job.gene,
          method: job.method,
          result: item.status === "completed" ? item.result : null,
          error: item.status === "failed" ? formatBatchItemError(item) : null,
        };
      });
      setCompare((current) => ({
        ...current,
        results,
        error: batch.failed ? `${batch.failed} comparison${batch.failed === 1 ? "" : "s"} failed; see matrix cells.` : "",
      }));
    } catch (err) {
      setCompare((current) => ({ ...current, error: formatError(err) }));
    } finally {
      setCompare((current) => ({ ...current, running: false }));
    }
  }

  return (
    <section className="compare-page">
      <div className="compare-controls">
        <GeneSelector
          label="Genes to compare"
          value={compare.genes}
          onChange={(value) => setCompare((current) => ({ ...current, genes: value }))}
          draft={compareGeneQuery}
          setDraft={setCompareGeneQuery}
          suggestions={compareGeneSuggestions}
          placeholder="Type TP53, KRAS, EGFR..."
          help="Select genes for the comparison matrix. Each selected gene becomes one row."
        />
        <div className="method-grid compact">
          {cutpoints.map((item) => (
            <button
              key={item.value}
              type="button"
              className={selectedMethods.includes(item.value) ? "selected" : ""}
              onClick={() => toggleMethod(item.value)}
              title={cutpointTooltip(item.value)}
            >
              <strong>{item.label}</strong>
              <span>{item.help}</span>
            </button>
          ))}
        </div>
        <div className="run-summary static">
          <div>
            <span>Comparison scope</span>
            <strong>{genes.length || 0} genes x {selectedMethods.length} methods</strong>
            <small>{expressionScale.label}; up to {ANALYSIS_BATCH_CONCURRENCY} analyses run in parallel, with BH and Bonferroni adjustment across completed comparisons.</small>
          </div>
          <button className="primary-button" onClick={runCompare} disabled={!canRun || !genes.length || !selectedMethods.length || compare.running}>
            {compare.running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
            Run comparison
          </button>
        </div>
      </div>
      {compare.error && <div className="error-box"><AlertCircle size={18} /><span>{compare.error}</span></div>}
      <ComparePlotMatrix
        rows={adjusted}
        genes={genes}
        methods={selectedCutpoints}
        running={compare.running}
        onDownload={onDownload}
      />
      <div className="method-note">
        These comparisons are exploratory. Multiple-testing adjustment is applied to the displayed set only and does not replace external validation.
      </div>
    </section>
  );
}

function ComparePlotMatrix({ rows, genes, methods, running, onDownload }) {
  if (!rows.length && !running) {
    return <div className="empty-plot"><Table2 size={38} /><p>Comparison results will appear after running multiple genes or cutpoint methods.</p></div>;
  }
  const rowByKey = Object.fromEntries(rows.map((row) => [`${row.gene}::${row.method}`, row]));
  return (
    <div className="compare-matrix-scroll">
      <table className="compare-matrix-table">
        <thead>
          <tr>
            <th>Gene</th>
            {methods.map((method) => (
              <th key={method.value}>
                <strong>{method.label}</strong>
                <span>{method.help}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {genes.map((gene) => (
            <tr key={gene}>
              <th scope="row">{gene}</th>
              {methods.map((method) => (
                <td key={`${gene}-${method.value}`}>
                  <ComparePlotCell row={rowByKey[`${gene}::${method.value}`]} running={running} onDownload={onDownload} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparePlotCell({ row, running, onDownload }) {
  if (!row) {
    return (
      <div className="compare-cell-pending">
        {running ? <Loader2 className="spin" size={18} /> : <Table2 size={18} />}
        <span>{running ? "Waiting" : "Not run"}</span>
      </div>
    );
  }
  if (row.error) {
    return (
      <div className="compare-cell-error">
        <AlertCircle size={18} />
        <span>{row.error}</span>
      </div>
    );
  }
  const metrics = row.result?.metrics || {};
  const downloads = row.result?.downloads || {};
  return (
    <div className="compare-plot-cell">
      <img
        className="compare-plot-thumb"
        src={apiUrl(downloads.png)}
        alt={`${row.gene} ${row.method} Kaplan-Meier plot`}
        loading="lazy"
      />
      <div className="compare-cell-metrics">
        <span>p {formatP(metrics.logrank_p_value)}</span>
        <span>BH {formatP(row.bh)}</span>
        <span>HR {formatHr(metrics)}</span>
        <span>{formatInteger(metrics.n_patients)} pts / {formatInteger(metrics.n_events)} events</span>
      </div>
      <div className="mini-downloads">
        <MiniDownloadButton href={downloads.png} label="PNG" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.svg} label="SVG" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.csv} label="CSV" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.txt} label="TXT" onDownload={onDownload} />
        <MiniDownloadButton href={downloads.zip} label="ZIP" onDownload={onDownload} />
      </div>
    </div>
  );
}

function BiologicalAnnotations({ annotations }) {
  const entries = Object.entries(annotations);
  if (!entries.length) return <div className="empty-inline">No subtype annotation fields detected for this scope.</div>;
  return (
    <div className="annotation-list">
      {entries.map(([cohort, payload]) => (
        <div key={cohort}>
          <strong>{cohort}</strong>
          {payload.fields?.map((field) => (
            <small key={field.name}>{field.name}: {field.distribution?.slice(0, 3).map((item) => `${item.label} (${item.count})`).join(", ") || "present"}</small>
          ))}
        </div>
      ))}
    </div>
  );
}

function EndpointCoverageTable({ items }) {
  if (!items.length) return <div className="empty-inline">No endpoint coverage available.</div>;
  const visible = items
    .filter((item) => item.available || Number(item.patients || 0) > 0)
    .slice(0, 80);
  if (!visible.length) return <div className="empty-inline">No endpoint coverage available.</div>;
  return (
    <div className="table-scroll compact">
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Endpoint</th>
            <th>Source</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((item) => (
            <tr key={`${item.cohort}-${item.value}`}>
              <td>{item.cohort}</td>
              <td>{item.label}</td>
              <td>{formatSourceLabel(item.source)}</td>
              <td>{formatInteger(item.patients)}</td>
              <td>{formatInteger(item.events)}</td>
              <td>{item.available ? "Available" : "QC limited"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DatasetSummary({ summary, health, dataSources = [], cohorts = [], summaryCohort, setSummaryCohort }) {
  if (!summary) {
    return (
      <section className="summary-page">
        <div className="loading-state compact">
          <Loader2 className="spin" size={34} />
          <div>
            <p className="eyebrow">Loading dataset summary</p>
            <h2>Reading cohort and sample metadata</h2>
          </div>
        </div>
      </section>
    );
  }

  const totals = summary.totals || {};
  const dates = summary.data_dates || health?.data_dates || {};
  const distributions = summary.distributions || {};
  const sources = dataSources.length ? dataSources : summary.data_sources || [];
  const syncSources = summary.data_sync?.sources || [];
  const endpointCoverage = summary.endpoint_coverage || [];
  const topCohorts = [...(summary.cohorts || [])]
    .sort((a, b) => Number(b.patient_count || 0) - Number(a.patient_count || 0))
    .slice(0, 12);

  return (
    <section className="summary-page">
      <div className="summary-actions">
        <label className="field">
          <span>Cohort filter</span>
          <select value={summaryCohort} onChange={(event) => setSummaryCohort(event.target.value)}>
            <option value="">All cohorts</option>
            {cohorts.map((cohort) => (
              <option key={cohort.id} value={cohort.id}>
                {getCohortLabel(cohort.id)}
              </option>
            ))}
          </select>
        </label>
        <div className="download-row">
          <a href={apiUrl(`/api/dataset/summary/download/csv${summaryCohort ? `?cohort=${summaryCohort}` : ""}`)}>
            <FileSpreadsheet size={16} /> Summary CSV
          </a>
        </div>
      </div>

      <div className="summary-kpis">
        <Metric label="Cohorts" value={formatInteger(totals.cohorts)} />
        <Metric label="Samples" value={formatInteger(totals.samples)} />
        <Metric label="Patients" value={formatInteger(totals.patients)} />
        <Metric label="Usable OS" value={formatInteger(totals.usable_os_samples)} />
        <Metric label="Events" value={formatInteger(totals.events)} />
      </div>

      <div className="date-grid">
        <DateItem label="Data through" value={dates.data_through_date || dates.source_latest_metadata_file || dates.source_summary_file} />
        <DateItem label="Database created" value={dates.database_imported_at} />
        <DateItem label="Source summary snapshot" value={dates.source_summary_file} />
        <DateItem label="RNA cache generated" value={dates.rna_cache_generated_at} />
      </div>

      <div className="source-strip">
        {sources.map((source) => (
          <div key={source.id} className={`source-status ${source.status}`}>
            <span>{source.label}</span>
            <strong>{formatSourceStatus(source.status)}</strong>
            <small>{formatDateTime(source.imported_at)}</small>
          </div>
        ))}
      </div>

      {syncSources.length > 0 && (
        <div className="source-strip">
          {syncSources.map((source) => (
            <div key={source.source} className={`source-status ${source.status}`}>
              <span>{formatSourceLabel(source.source)}</span>
              <strong>{formatInteger(source.file_count)} files</strong>
              <small>Data through {formatDateTime(source.data_through_date)}</small>
            </div>
          ))}
        </div>
      )}

      <div className="summary-layout">
        <section className="summary-panel wide">
          <PanelHeader
            icon={<Activity size={18} />}
            title="Endpoint coverage"
            description="Clinical endpoints are enabled for analysis only when linked patient and event counts pass QC."
          />
          <EndpointCoverageTable items={endpointCoverage} />
        </section>

        <section className="summary-panel wide">
          <PanelHeader
            icon={<PieChart size={18} />}
            title="Cohort landscape"
            description="Ranked dot plot: X-axis is patients, dot size is OS events, color is event rate."
          />
          <CohortRankPlot cohorts={topCohorts} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<PieChart size={18} />}
            title="Sample types"
            description="Top sample categories across all cohorts."
          />
          <DonutPlot items={distributions.sample_types || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<Activity size={18} />}
            title="Vital status"
            description="Clinical survival event metadata."
          />
          <DonutPlot items={distributions.vital_status || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<Database size={18} />}
            title="Primary sites"
            description="Sample-weighted primary site distribution."
          />
          <PrimarySitePlot items={distributions.primary_site || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<CalendarDays size={18} />}
            title="Age at index"
            description="Available patient age bins."
          />
          <HistogramPlot items={distributions.age_bins || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<ClipboardList size={18} />}
            title="Metadata coverage"
            description="Non-missing sample metadata fields."
          />
          <CoverageMatrix items={summary.metadata_coverage || []} />
        </section>

        <section className="summary-panel">
          <PanelHeader
            icon={<Dna size={18} />}
            title="Biological annotations"
            description="Cohort-specific subtype fields detected in TCGA metadata."
          />
          <BiologicalAnnotations annotations={summary.biological_annotations || {}} />
        </section>

        <section className="summary-panel wide">
          <PanelHeader
            icon={<Table2 size={18} />}
            title="Cohort table"
            description="Imported samples, patients, cancer name and source metadata."
          />
          <CohortSummaryTable cohorts={summary.cohorts || []} />
        </section>
      </div>
    </section>
  );
}

function DateItem({ label, value }) {
  return (
    <div className="date-item">
      <span>{label}</span>
      <strong>{formatDateTime(value)}</strong>
    </div>
  );
}

function CohortRankPlot({ cohorts }) {
  if (!cohorts.length) return <div className="empty-inline">No cohort data available.</div>;
  const width = 760;
  const rowHeight = 31;
  const topPad = 34;
  const bottomPad = 42;
  const height = topPad + cohorts.length * rowHeight + bottomPad;
  const labelX = 20;
  const plotLeft = 170;
  const plotRight = 610;
  const countX = 632;
  const maxPatients = Math.max(...cohorts.map((cohort) => Number(cohort.patient_count || 0)), 1);
  const maxEvents = Math.max(...cohorts.map((cohort) => Number(cohort.event_count ?? cohort.sample_count ?? 0)), 1);
  const ticks = [0, Math.round(maxPatients / 2), maxPatients];
  const eventRateColor = (rate) => {
    if (rate >= 0.35) return "#b44b3f";
    if (rate >= 0.18) return "#d7953f";
    return "#2f756f";
  };
  return (
    <div className="cohort-rank-wrap">
      <svg className="cohort-rank-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Ranked cohort dot plot by patients and events">
        {ticks.map((tick) => {
          const x = plotLeft + (tick / maxPatients) * (plotRight - plotLeft);
          return (
            <g key={tick} className="axis-tick">
              <line x1={x} y1="20" x2={x} y2={height - bottomPad + 9} />
              <text x={x} y={height - 14} textAnchor="middle">{formatInteger(tick)}</text>
            </g>
          );
        })}
        <text x={(plotLeft + plotRight) / 2} y={height - 1} textAnchor="middle">Patients</text>
        <text x={labelX} y="18">Cohort</text>
        <text x={countX} y="18">Patients / events</text>
      {cohorts.map((cohort, index) => {
        const patients = Number(cohort.patient_count || 0);
        const events = Number(cohort.event_count ?? 0);
        const eventRate = patients > 0 ? events / patients : 0;
        const x = plotLeft + (patients / maxPatients) * (plotRight - plotLeft);
        const y = topPad + index * rowHeight;
        const radius = 5 + Math.sqrt(events / maxEvents) * 10;
        return (
          <g key={cohort.id} className="cohort-rank-row">
            <title>{`${cohort.id} - ${getCohortName(cohort.id)}: ${formatInteger(patients)} patients, ${formatInteger(events)} events, ${Math.round(eventRate * 100)}% event rate`}</title>
            <line x1={plotLeft} y1={y} x2={plotRight} y2={y} />
            <text x={labelX} y={y + 4}>{cohort.id}</text>
            <circle cx={x} cy={y} r={radius} fill={eventRateColor(eventRate)} />
            <text x={countX} y={y + 4}>{formatInteger(patients)} / {formatInteger(events)}</text>
          </g>
        );
      })}
      </svg>
      <div className="cohort-rank-legend" aria-hidden="true">
        <span><i className="low" />Lower event rate</span>
        <span><i className="mid" />Moderate</span>
        <span><i className="high" />Higher</span>
        <span className="size-note">Larger dot = more OS events</span>
      </div>
    </div>
  );
}

function DonutPlot({ items }) {
  if (!items.length) return <div className="empty-inline">No metadata available.</div>;
  const total = items.reduce((sum, item) => sum + Number(item.count || 0), 0) || 1;
  let offset = 0;
  const radius = 64;
  const circumference = 2 * Math.PI * radius;
  return (
    <div className="donut-wrap">
      <svg className="donut-plot" viewBox="0 0 180 180" role="img" aria-label="Composition donut plot">
        <circle cx="90" cy="90" r={radius} className="donut-bg" />
        {items.slice(0, 6).map((item, index) => {
          const value = Number(item.count || 0);
          const dash = (value / total) * circumference;
          const segment = (
            <circle
              key={item.label}
              cx="90"
              cy="90"
              r={radius}
              className={`donut-segment segment-${index}`}
              strokeDasharray={`${dash} ${circumference - dash}`}
              strokeDashoffset={-offset}
            />
          );
          offset += dash;
          return segment;
        })}
        <text x="90" y="86" textAnchor="middle">{formatInteger(total)}</text>
        <text x="90" y="104" textAnchor="middle">samples</text>
      </svg>
      <div className="donut-legend">
        {items.slice(0, 6).map((item, index) => (
          <div key={item.label}>
            <i className={`segment-${index}`} />
            <span>{item.label}</span>
            <strong>{formatInteger(item.count)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function HistogramPlot({ items }) {
  if (!items.length) return <div className="empty-inline">No age metadata available.</div>;
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  const width = 420;
  const height = 220;
  const barGap = 8;
  const barWidth = (width - 48 - barGap * (items.length - 1)) / items.length;
  return (
    <svg className="histogram-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Age distribution histogram">
      <line x1="32" y1="180" x2="408" y2="180" />
      <line x1="32" y1="24" x2="32" y2="180" />
      {items.map((item, index) => {
        const value = Number(item.count || 0);
        const barHeight = (value / maxValue) * 140;
        const x = 42 + index * (barWidth + barGap);
        const y = 180 - barHeight;
        return (
          <g key={item.label}>
            <rect x={x} y={y} width={barWidth} height={barHeight} rx="5" />
            <text x={x + barWidth / 2} y="202" textAnchor="middle">{item.label}</text>
            <text x={x + barWidth / 2} y={Math.max(18, y - 6)} textAnchor="middle">{formatInteger(value)}</text>
          </g>
        );
      })}
    </svg>
  );
}

function CoverageMatrix({ items }) {
  if (!items.length) return <div className="empty-inline">No coverage metadata available.</div>;
  return (
    <div className="coverage-matrix">
      {items.map((item) => (
        <div key={item.label}>
          <span>{item.label}</span>
          <div>
            {Array.from({ length: 10 }).map((_, index) => (
              <i key={index} className={index < Math.round((Number(item.percent) || 0) / 10) ? "filled" : ""} />
            ))}
          </div>
          <strong>{item.percent}%</strong>
        </div>
      ))}
    </div>
  );
}

function PrimarySitePlot({ items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  if (!items.length) return <div className="empty-inline">No primary-site metadata available.</div>;
  return (
    <div className="primary-site-list">
      {items.map((item) => {
        const count = Number(item.count || 0);
        const percent = maxValue > 0 ? (count / maxValue) * 100 : 0;
        return (
          <div key={item.label} className="primary-site-row" title={`${item.label}: ${formatInteger(count)} samples`}>
            <div>
              <span>{item.label}</span>
              <strong>{formatInteger(count)}</strong>
            </div>
            <i style={{ "--bar-width": `${percent}%` }} />
          </div>
        );
      })}
    </div>
  );
}

function DistributionBars({ items }) {
  const maxValue = Math.max(...items.map((item) => Number(item.count || 0)), 1);
  if (!items.length) return <div className="empty-inline">No metadata available.</div>;
  return (
    <div className="bar-list">
      {items.map((item) => (
        <div key={item.label} className="bar-row">
          <div>
            <span>{item.label}</span>
            <strong>{formatInteger(item.count)}</strong>
          </div>
          <i style={{ "--bar-width": `${(Number(item.count || 0) / maxValue) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function CohortSummaryTable({ cohorts }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Cancer</th>
            <th>Primary site</th>
            <th>Samples</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Primary tumor</th>
            <th>Solid normal</th>
          </tr>
        </thead>
        <tbody>
          {cohorts.map((cohort) => (
            <tr key={cohort.id}>
              <td>{cohort.id}</td>
              <td>{getCohortName(cohort.id)}</td>
              <td>{cohort.primary_site || "..."}</td>
              <td>{formatInteger(cohort.sample_count)}</td>
              <td>{formatInteger(cohort.patient_count)}</td>
              <td>{formatInteger(cohort.event_count)}</td>
              <td>{formatInteger(cohort.n_primary_tumor)}</td>
              <td>{formatInteger(cohort.n_solid_normal)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreviewState({ cohort, signatureMethod, geneCount, endpoint, expressionScale, cutpoint, activeFilterCount }) {
  const isSingleMode = signatureMethod === "single";
  return (
    <div className="preview-state">
      <div className="preview-header">
        <CheckCircle2 size={28} />
        <div>
          <p className="eyebrow">Ready to run</p>
          <h2>
            {geneCount
              ? isSingleMode
                ? `${geneCount} separate survival plot${geneCount === 1 ? "" : "s"}`
                : "Combined signature survival plot"
              : "Select one or more genes"}
          </h2>
        </div>
      </div>
      <div className="preview-grid">
        <PreviewItem label="Cancer" value={cohort ? getCohortName(cohort.id) : "Select a cancer"} />
        <PreviewItem label="TCGA code" value={cohort?.id || "..."} />
        <PreviewItem label="Primary site" value={cohort?.primary_site || "No cancer selected"} />
        <PreviewItem label="Available patients" value={formatInteger(cohort?.n_patients_paired)} />
        <PreviewItem label="Endpoint" value={endpoint?.label || "Overall survival"} />
        <PreviewItem label="Expression" value={expressionScale?.label || "log2(TPM + 1)"} />
        <PreviewItem label="Cutpoint" value={cutpoint?.label || "Median"} />
        <PreviewItem label="Gene mode" value={isSingleMode ? "Separate plots" : "Combined signature"} />
        <PreviewItem label="Active filters" value={activeFilterCount} />
      </div>
      <div className="empty-plot">
        <Table2 size={42} />
        <p>The plot, survival statistics and download links will appear here after the R analysis finishes.</p>
      </div>
    </div>
  );
}

function PreviewItem({ label, value }) {
  return (
    <div className="preview-item">
      <span>{label}</span>
      <strong>{value ?? "..."}</strong>
    </div>
  );
}

function LoadingState({ cohort, gene, signatureMethod, geneCount, completedCount, endpoint, expressionScale }) {
  const isSingleMode = signatureMethod === "single";
  return (
    <div className="loading-state">
      <Loader2 className="spin" size={42} />
      <div>
        <p className="eyebrow">Running R survival analysis</p>
        <h2>
          {getCohortName(cohort)} / {isSingleMode ? `${completedCount} of ${geneCount} genes completed` : gene.trim().toUpperCase()}
        </h2>
        {cohort && <small>{cohort}</small>}
        <span>
          Reading {expressionScale?.label || "expression"}, assigning groups, fitting {endpoint?.label || "survival"} curves and rendering artifacts.
        </span>
      </div>
      <div className="progress-rail">
        <i />
      </div>
    </div>
  );
}

function AnalysisResults({ analyses, onDownload }) {
  if (analyses.length === 1) {
    return <AnalysisResult analysis={analyses[0]} onDownload={onDownload} />;
  }
  return (
    <div className="analysis-stack">
      <div className="stack-header">
        <span>Separate Kaplan-Meier plots</span>
        <strong>{analyses.length} completed genes</strong>
      </div>
      {analyses.map((item) => (
        <AnalysisResult key={item.id} analysis={item} onDownload={onDownload} />
      ))}
    </div>
  );
}

function AnalysisResult({ analysis, onDownload }) {
  const metrics = analysis.metrics || {};
  const downloads = analysis.downloads || {};
  const endpointLabel = metrics.endpoint_label || "Overall survival";
  return (
    <div className="analysis-result">
      <div className="result-header">
        <div>
          <p className="eyebrow">
            {analysis.cohort} / {analysis.expression_scale_label || "Expression"} {analysis.cached ? "/ cached" : ""}
          </p>
          <h2>{getCohortName(analysis.cohort)} / {analysis.gene_symbol} {endpointLabel.toLowerCase()}</h2>
        </div>
        <div className="download-row">
          <DownloadLink href={downloads.png} icon={<Image size={16} />} label="PNG" onDownload={onDownload} />
          <DownloadLink href={downloads.svg} icon={<ArrowDownToLine size={16} />} label="SVG" onDownload={onDownload} />
          <DownloadLink href={downloads.csv} icon={<FileSpreadsheet size={16} />} label="CSV" onDownload={onDownload} />
          <DownloadLink href={downloads.txt} icon={<FileText size={16} />} label="Method TXT" onDownload={onDownload} />
          <DownloadLink href={downloads.zip} icon={<Archive size={16} />} label="ZIP" onDownload={onDownload} />
        </div>
      </div>

      <div className="metric-strip">
        <Metric label="Patients" value={metrics.n_patients} />
        <Metric label="Events" value={metrics.n_events} />
        <Metric label="Log-rank p" value={formatP(metrics.logrank_p_value)} />
        <Metric label="Hazard ratio" value={formatHr(metrics)} />
      </div>

      <div className="result-details">
        <GroupTable metrics={metrics} />
        <CutpointSummary details={metrics.cutpoint_details} />
      </div>

      <div className="result-details">
        <ExpressionDistribution distribution={metrics.expression_distribution} cutpointDetails={metrics.cutpoint_details} />
        <QualitySummary quality={metrics.quality} />
      </div>

      <img className="km-plot" src={apiUrl(downloads.png)} alt="Kaplan-Meier plot" />

      {!!analysis.warnings?.length && (
        <div className="warning-list">
          {analysis.warnings.map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value ?? "..."}</strong>
    </div>
  );
}

function GroupTable({ metrics }) {
  const groups = Object.keys(metrics.group_counts || {});
  if (!groups.length) return null;
  return (
    <div className="detail-section">
      <h3>Survival groups</h3>
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Median days</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group}>
              <td>{group}</td>
              <td>{metrics.group_counts?.[group] ?? "..."}</td>
              <td>{metrics.event_counts?.[group] ?? "..."}</td>
              <td>{formatInteger(metrics.median_survival_days?.[group])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CutpointSummary({ details }) {
  if (!details) return null;
  return (
    <div className="detail-section">
      <h3>Cutpoint</h3>
      <dl>
        {Object.entries(details).map(([key, value]) => (
          <div key={key}>
            <dt>{formatLabel(key)}</dt>
            <dd>{typeof value === "number" ? Number(value).toFixed(4) : String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ExpressionDistribution({ distribution, cutpointDetails }) {
  if (!distribution?.bins?.length) return null;
  const bins = normalizeDistributionBins(distribution.bins);
  const markers = cutpointMarkers(cutpointDetails);
  const stats = [
    ["Patients", formatInteger(distribution.n)],
    ["Min", formatExpressionValue(distribution.min)],
    ["Q1", formatExpressionValue(distribution.q1)],
    ["Median", formatExpressionValue(distribution.median)],
    ["Q3", formatExpressionValue(distribution.q3)],
    ["Max", formatExpressionValue(distribution.max)],
  ];
  return (
    <div className="detail-section expression-section">
      <h3>Expression distribution before cutpoint</h3>
      <div className="expression-summary">
        {stats.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <ExpressionHistogram distribution={distribution} bins={bins} markers={markers} />
    </div>
  );
}

function ExpressionHistogram({ distribution, bins, markers }) {
  const width = 640;
  const height = 230;
  const plot = { top: 24, right: 18, bottom: 42, left: 46 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxCount = Math.max(...bins.map((item) => item.count), 1);
  const minValue = finiteNumber(distribution.min) ?? Math.min(...bins.map((item) => item.lower));
  const maxValue = finiteNumber(distribution.max) ?? Math.max(...bins.map((item) => item.upper));
  const span = maxValue - minValue || 1;
  const scaleX = (value) => plot.left + ((value - minValue) / span) * innerWidth;
  const scaleY = (count) => plot.top + innerHeight - (count / maxCount) * innerHeight;
  const axisTicks = uniqueNumbers([minValue, finiteNumber(distribution.median), maxValue]);
  const visibleMarkers = markers.filter((marker) => marker.value >= minValue && marker.value <= maxValue);

  return (
    <div className="expression-histogram-wrap">
      <svg className="expression-histogram" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Expression histogram with cutpoint markers">
        {[0, 0.5, 1].map((fraction) => {
          const y = plot.top + innerHeight - fraction * innerHeight;
          return <line key={fraction} className="histogram-grid-line" x1={plot.left} x2={width - plot.right} y1={y} y2={y} />;
        })}
        {bins.map((bin, index) => {
          const singleValue = bin.lower === bin.upper || minValue === maxValue;
          const x = singleValue ? plot.left + innerWidth * 0.16 : scaleX(bin.lower);
          const nextX = singleValue ? plot.left + innerWidth * 0.84 : scaleX(bin.upper);
          const barWidth = Math.max(3, nextX - x - 4);
          const y = scaleY(bin.count);
          const barHeight = plot.top + innerHeight - y;
          return (
            <rect
              key={`${bin.label}-${index}`}
              className="histogram-bar"
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              rx="3"
            >
              <title>{`${bin.label}: ${formatInteger(bin.count)} patients`}</title>
            </rect>
          );
        })}
        {visibleMarkers.map((marker, index) => {
          const x = scaleX(marker.value);
          return (
            <g key={`${marker.label}-${marker.value}`} className={`cutpoint-marker marker-${index % 3}`}>
              <line x1={x} x2={x} y1={plot.top - 6} y2={plot.top + innerHeight} />
              <text x={x} y={index % 2 === 0 ? 14 : 28}>{marker.label}</text>
            </g>
          );
        })}
        <line className="histogram-axis" x1={plot.left} x2={width - plot.right} y1={plot.top + innerHeight} y2={plot.top + innerHeight} />
        {axisTicks.map((tick) => {
          const x = scaleX(tick);
          return (
            <g key={tick} className="histogram-tick">
              <line x1={x} x2={x} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
              <text x={x} y={height - 16}>{formatExpressionValue(tick)}</text>
            </g>
          );
        })}
        <text className="histogram-y-label" x="12" y={plot.top + 10}>Patients</text>
      </svg>
      {!!visibleMarkers.length && (
        <div className="expression-marker-legend">
          {visibleMarkers.map((marker, index) => (
            <span key={`${marker.label}-${marker.value}`}>
              <i className={`marker-${index % 3}`} />
              {marker.label}: {formatExpressionValue(marker.value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function normalizeDistributionBins(items) {
  return items.map((item, index) => {
    const label = String(item.label ?? "");
    const parsed = parseDistributionLabel(label);
    const lower = finiteNumber(item.lower) ?? parsed.lower ?? index;
    const upper = finiteNumber(item.upper) ?? parsed.upper ?? lower;
    return {
      label,
      count: Number(item.count || 0),
      lower,
      upper,
    };
  });
}

function parseDistributionLabel(label) {
  const range = label.match(/^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (range) {
    return { lower: Number(range[1]), upper: Number(range[2]) };
  }
  const single = label.match(/^\s*(-?\d+(?:\.\d+)?)\s*$/);
  if (single) {
    const value = Number(single[1]);
    return { lower: value, upper: value };
  }
  return {};
}

function cutpointMarkers(details) {
  if (!details) return [];
  return [
    ["threshold", "Cutpoint"],
    ["lower_quartile", "Lower quartile"],
    ["upper_quartile", "Upper quartile"],
    ["lower_tertile", "Lower tertile"],
    ["upper_tertile", "Upper tertile"],
  ]
    .map(([key, label]) => ({ label, value: finiteNumber(details[key]) }))
    .filter((marker) => marker.value !== null);
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function uniqueNumbers(values) {
  const seen = new Set();
  return values
    .filter((value) => value !== null && value !== undefined)
    .filter((value) => {
      const key = Number(value).toFixed(6);
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function QualitySummary({ quality }) {
  if (!quality?.groups) return null;
  return (
    <div className="detail-section">
      <h3>Event quality</h3>
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th>Patients</th>
            <th>Events</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(quality.groups).map(([group, item]) => (
            <tr key={group}>
              <td>{group}</td>
              <td>{item.patients}</td>
              <td>{item.events}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!!quality.low_event_groups?.length && (
        <div className="method-note">Low event count in: {quality.low_event_groups.join(", ")}.</div>
      )}
    </div>
  );
}

function DownloadLink({ href, icon, label, onDownload }) {
  if (!href) return null;
  return (
    <button type="button" onClick={() => onDownload?.(href, label)} title={`Download ${label}`}>
      {icon}
      {label}
    </button>
  );
}

function MiniDownloadButton({ href, label, onDownload }) {
  if (!href) return null;
  return (
    <button type="button" onClick={() => onDownload?.(href, label)} title={`Download ${label}`}>
      {label}
    </button>
  );
}

function DownloadNotifications({ notices, onDismiss }) {
  if (!notices.length) return null;
  return (
    <div className="download-notifications" aria-live="polite" aria-label="Download status">
      {notices.map((notice) => (
        <div key={notice.id} className={`download-notice ${notice.status}`}>
          {notice.status === "running" && <Loader2 className="spin" size={16} />}
          {notice.status === "done" && <CheckCircle2 size={16} />}
          {notice.status === "failed" && <AlertCircle size={16} />}
          <div>
            <strong>{notice.label}</strong>
            <span>{notice.message}</span>
          </div>
          <button type="button" onClick={() => onDismiss(notice.id)} aria-label={`Dismiss ${notice.label} download status`}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}

function formatP(value) {
  if (value === undefined || value === null) return "...";
  if (value < 0.001) return value.toExponential(2);
  return Number(value).toFixed(3);
}

function formatHr(metrics) {
  if (metrics.hazard_ratio === undefined || metrics.hazard_ratio === null) return "...";
  return `${Number(metrics.hazard_ratio).toFixed(2)} (${Number(metrics.hr_conf_low).toFixed(2)}-${Number(metrics.hr_conf_high).toFixed(2)})`;
}

function filenameFromDisposition(disposition) {
  if (!disposition) return "";
  const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1].replaceAll('"', ""));
  }
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || "";
}

function fallbackDownloadFilename(label, href) {
  const extension = String(label || "download").toLowerCase().replace("method txt", "txt");
  const analysisId = String(href || "").split("/").filter(Boolean).at(-3) || "analysis";
  return `${analysisId}.${extension}`;
}

function formatInteger(value) {
  if (value === undefined || value === null || value === "") return "...";
  return Number(value).toLocaleString();
}

function formatExpressionValue(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  return number.toFixed(2);
}

function formatDate(value) {
  if (!value) return "...";
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function formatDateTime(value) {
  if (!value) return "...";
  return new Date(value).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatLabel(value) {
  return value.replaceAll("_", " ");
}

function formatSourceLabel(value) {
  return {
    tcga_cdr: "TCGA-CDR",
    derived_sample_metadata: "TCGA metadata",
    tcga_rna: "TCGA RNA-seq",
  }[value] || value || "...";
}

function formatSourceStatus(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function toNullableNumber(value) {
  if (value === "" || value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function cutpointTooltip(value) {
  return {
    maxstat: "Optimizes the expression threshold against survival separation; exploratory and prone to selection bias.",
    median: "Splits patients at the median expression value.",
    tertiles: "Creates low, middle and high expression groups.",
    upper_quartile: "Compares the highest 25% expression group against the remaining 75%.",
    upper_lower_quartile: "Compares upper and lower quartiles and excludes the middle 50%.",
    percentile: "Uses a user-selected percentile as the high-expression threshold.",
  }[value] || "";
}

function expressionTooltip(value) {
  return {
    log2_tpm: "TPM from GDC STAR-count files, transformed as log2(TPM + 1).",
    log2_cpm: "CPM computed from unstranded counts and library size, transformed as log2(CPM + 1).",
    log2_fpkm: "FPKM from GDC STAR-count files, transformed as log2(FPKM + 1).",
    log2_fpkm_uq: "Upper-quartile FPKM from GDC STAR-count files, transformed as log2(FPKM-UQ + 1).",
  }[value] || "";
}

function signatureHelp(value) {
  return {
    single: "Analyze one gene.",
    mean: "Average log-scale expression across all genes in the signature.",
    zscore: "Z-score each gene across samples, then average. Useful when genes have different scales.",
    weighted: "Weighted average of expression values. Use GENE:weight syntax.",
  }[value] || "";
}

function adjustCompareResults(rows) {
  const withP = rows.map((row, index) => ({
    ...row,
    index,
    p: row.result?.metrics?.logrank_p_value,
  }));
  const valid = withP.filter((row) => Number.isFinite(row.p)).sort((a, b) => a.p - b.p);
  const m = valid.length || 1;
  const bhByIndex = {};
  let runningMin = 1;
  for (let i = valid.length - 1; i >= 0; i -= 1) {
    const rank = i + 1;
    runningMin = Math.min(runningMin, (valid[i].p * m) / rank);
    bhByIndex[valid[i].index] = Math.min(runningMin, 1);
  }
  return withP.map((row) => ({
    ...row,
    bh: bhByIndex[row.index],
    bonferroni: Number.isFinite(row.p) ? Math.min(row.p * m, 1) : undefined,
  }));
}

function formatError(error) {
  if (!error) return "";
  const labels = {
    INVALID_GROUPS: "Invalid grouping",
    INSUFFICIENT_PATIENTS: "Not enough patients",
    NO_EVENTS: "No survival events",
    NO_GENE: "Gene not found",
    CACHE_INCOMPLETE: "Cache incomplete",
    R_FAILED: "R failed",
    ENDPOINT_UNAVAILABLE: "Endpoint unavailable",
    INVALID_ANALYSIS: "Invalid analysis",
  };
  return error.code ? `${labels[error.code] || error.code}: ${error.message}` : error.message;
}

function formatBatchItemError(item) {
  if (!item) return "Analysis failed.";
  return formatError({ code: item.code, message: item.error || "Analysis failed." });
}

createRoot(document.getElementById("root")).render(<App />);
