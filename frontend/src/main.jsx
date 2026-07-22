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
  Network,
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
  createCombinedAnalysis,
  createPanCancerSurvival,
  getCohortEndpoints,
  getCohorts,
  getDataSources,
  getDatasetSummary,
  getExpressionScales,
  getFilterOptions,
  getHealth,
  getImmunePanCancerScreen,
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

const DICHOTOMIZATION_METHODS = [
  "maxstat",
  "median",
  "upper_quartile",
  "upper_lower_quartile",
  "percentile",
];
const ROBUSTNESS_ALPHA = 0.05;

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
  plot_aspect: "rectangular",
  base_font_size: 12,
  axis_text_size: 11,
  axis_title_size: 12,
  show_grid: true,
  show_title: false,
  plot_title: "",
};

const DEFAULT_COMBINED_PALETTE = [
  "#2f756f",
  "#d7953f",
  "#5a6f9f",
  "#b44b3f",
  "#6c7a77",
  "#7b6aa8",
  "#3c8c5f",
  "#c46a42",
  "#4b5f5b",
];

const EMPTY_FILTERS = {
  sample_types: [],
  stages: [],
  grades: [],
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

const PANCANCER_ENDPOINTS = [
  { value: "OS", label: "Overall survival" },
  { value: "DSS", label: "Disease-specific survival" },
  { value: "PFI", label: "Progression-free interval" },
  { value: "DFI", label: "Disease-free interval" },
];

const PANCANCER_ENDPOINT_MODES = [
  {
    value: "same_endpoint",
    label: "Same endpoint",
    help: "Require each cancer to pass QC for the selected endpoint.",
  },
  {
    value: "death_like",
    label: "Death-like",
    help: "Use DSS when available, otherwise OS.",
  },
  {
    value: "progression_like",
    label: "Progression-like",
    help: "Use PFI or DFI depending on cohort availability.",
  },
  {
    value: "best_available",
    label: "Best available",
    help: "Use the selected endpoint first, then a TCGA-CDR fallback.",
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
      plot_aspect: form.plot_style.plot_aspect,
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

function buildCombinedAnalysisPayload(form, signatureAInput, signatureBInput) {
  const groupingMethod = form.combined_signature.grouping_method;
  return {
    cohort: form.cohort,
    signature_a: buildSignatureSpec(form.combined_signature.signature_a, signatureAInput, "Signature A"),
    signature_b: buildSignatureSpec(form.combined_signature.signature_b, signatureBInput, "Signature B"),
    endpoint: form.endpoint,
    expression_scale: form.expression_scale,
    combination_method: groupingMethod,
    time_unit: form.time_unit,
    show_confidence_interval: form.show_confidence_interval,
    show_risk_table: form.show_risk_table,
    plot_style: {
      ...form.plot_style,
      palette: combinedPalette(form.plot_style.palette, groupingMethod),
      plot_aspect: form.plot_style.plot_aspect,
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

function buildSignatureSpec(signature, geneInput, fallbackName) {
  const normalizedInput = geneInputTokens(geneInput).join(", ");
  return {
    name: signature.name.trim() || fallbackName,
    gene_symbol: normalizedInput,
    signature_method: signature.signature_method,
    signature_genes: signature.signature_method === "single" ? [] : parseSignatureGenes(normalizedInput),
  };
}

function combinedPalette(currentPalette, groupingMethod) {
  const required = groupingMethod === "tertiles" ? 9 : 4;
  const palette = Array.isArray(currentPalette) ? currentPalette.filter(Boolean) : [];
  if (palette.length >= required) {
    return palette.slice(0, required);
  }
  return DEFAULT_COMBINED_PALETTE.slice(0, required);
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
  const [combinedGeneQueries, setCombinedGeneQueries] = useState({ a: "", b: "" });
  const [combinedGeneSuggestions, setCombinedGeneSuggestions] = useState({ a: [], b: [] });
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
  const [panCancer, setPanCancer] = useState({
    gene_symbol: "",
    geneQuery: "",
    geneSuggestions: [],
    index_cohort: "",
    endpoint: "OS",
    endpoint_mode: "same_endpoint",
    expression_scale: "log2_tpm",
    min_patients: 10,
    min_events: 5,
    fdr_threshold: 0.1,
    running: false,
    result: null,
    immuneScreen: null,
    immuneScreenLoading: false,
    immuneScreenError: "",
    error: "",
  });

  const [form, setForm] = useState({
    cohort: "",
    gene_symbol: "",
    analysis_kind: "single_signature",
    endpoint: "OS",
    signature_method: "single",
    signature_genes: [],
    combined_signature: {
      grouping_method: "median",
      signature_a: {
        name: "Signature A",
        gene_symbol: "",
        signature_method: "zscore",
      },
      signature_b: {
        name: "Signature B",
        gene_symbol: "",
        signature_method: "zscore",
      },
    },
    expression_scale: "log2_tpm",
    cutpoint_method: "median",
    custom_percentile: 50,
    time_unit: "days",
    show_confidence_interval: true,
    show_risk_table: true,
    plot_style: DEFAULT_PLOT_STYLE,
    filters: EMPTY_FILTERS,
  });

  const geneSuggestionCohort = form.cohort || cohorts[0]?.id || "";

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
    if (!geneSuggestionCohort || searchTerm.length < 1) {
      setGenes([]);
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(geneSuggestionCohort, searchTerm)
        .then((payload) => setGenes(payload.genes))
        .catch(() => setGenes([]));
    }, 220);
    return () => clearTimeout(handle);
  }, [geneSuggestionCohort, geneQuery]);

  useEffect(() => {
    const handles = ["a", "b"].map((key) => {
      const searchTerm = currentGeneSearchTerm(combinedGeneQueries[key]);
      if (!geneSuggestionCohort || searchTerm.length < 1) {
        setCombinedGeneSuggestions((current) => ({ ...current, [key]: [] }));
        return null;
      }
      return setTimeout(() => {
        searchGenes(geneSuggestionCohort, searchTerm)
          .then((payload) => setCombinedGeneSuggestions((current) => ({ ...current, [key]: payload.genes })))
          .catch(() => setCombinedGeneSuggestions((current) => ({ ...current, [key]: [] })));
      }, 220);
    });
    return () => handles.forEach((handle) => handle && clearTimeout(handle));
  }, [geneSuggestionCohort, combinedGeneQueries.a, combinedGeneQueries.b]);

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(panCancer.geneQuery);
    const cohort = panCancer.index_cohort || form.cohort || cohorts[0]?.id || "";
    if (!cohort || searchTerm.length < 1) {
      setPanCancer((current) => ({ ...current, geneSuggestions: [] }));
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(cohort, searchTerm)
        .then((payload) => setPanCancer((current) => ({ ...current, geneSuggestions: payload.genes })))
        .catch(() => setPanCancer((current) => ({ ...current, geneSuggestions: [] })));
    }, 220);
    return () => clearTimeout(handle);
  }, [cohorts, form.cohort, panCancer.index_cohort, panCancer.geneQuery]);

  useEffect(() => {
    if (activePage !== "pancancer" || panCancer.immuneScreen || panCancer.immuneScreenLoading || panCancer.immuneScreenError) return;
    setPanCancer((current) => ({ ...current, immuneScreenLoading: true, immuneScreenError: "" }));
    getImmunePanCancerScreen()
      .then((payload) => setPanCancer((current) => ({ ...current, immuneScreen: payload, immuneScreenError: "" })))
      .catch((err) => setPanCancer((current) => ({ ...current, immuneScreenError: formatError(err) })))
      .finally(() => setPanCancer((current) => ({ ...current, immuneScreenLoading: false })));
  }, [activePage, panCancer.immuneScreen, panCancer.immuneScreenLoading, panCancer.immuneScreenError]);

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
      form.filters.grades.length +
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
  const effectiveSignatureAInput = combinedGeneQueries.a.trim()
    ? addGeneToken(form.combined_signature.signature_a.gene_symbol, combinedGeneQueries.a)
    : form.combined_signature.signature_a.gene_symbol;
  const effectiveSignatureBInput = combinedGeneQueries.b.trim()
    ? addGeneToken(form.combined_signature.signature_b.gene_symbol, combinedGeneQueries.b)
    : form.combined_signature.signature_b.gene_symbol;
  const selectedSignatureAGenes = uniqueGeneSymbols(effectiveSignatureAInput);
  const selectedSignatureBGenes = uniqueGeneSymbols(effectiveSignatureBInput);
  const isCombinedMode = form.analysis_kind === "combined_signatures";
  const runCount = isCombinedMode
    ? selectedSignatureAGenes.length && selectedSignatureBGenes.length ? 2 : 0
    : form.signature_method === "single"
      ? selectedGenes.length
      : Math.min(selectedGenes.length, 1);
  const canRun = isCombinedMode
    ? Boolean(form.cohort && selectedSignatureAGenes.length && selectedSignatureBGenes.length && selectedEndpoint.available) && !loading
    : Boolean(form.cohort && selectedGenes.length && selectedEndpoint.available) && !loading;
  const previewCutpoint = isCombinedMode
    ? {
        label: form.combined_signature.grouping_method === "tertiles"
          ? "Tertiles x tertiles"
          : "Median x median",
      }
    : selectedCutpoint;
  const selectedCancerName = form.cohort ? getCohortName(form.cohort) : "Select cancer";
  const plotCancerName = form.cohort ? getCohortName(form.cohort) : "Cancer";

  function updateForm(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateCombinedSignature(key, patch) {
    setForm((current) => ({
      ...current,
      combined_signature: {
        ...current.combined_signature,
        [key]: {
          ...current.combined_signature[key],
          ...patch,
        },
      },
    }));
  }

  function updateCombinedGroupingMethod(value) {
    setForm((current) => ({
      ...current,
      combined_signature: {
        ...current.combined_signature,
        grouping_method: value,
      },
    }));
  }

  function updateCombinedGeneQuery(key, value) {
    setCombinedGeneQueries((current) => ({ ...current, [key]: value }));
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
    setCompare((current) => ({ ...current, results: [], error: "" }));
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

  function updatePanCancer(key, value) {
    setPanCancer((current) => ({ ...current, [key]: value }));
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

  async function startPlotDownload(svgSelector, filenameBase, format) {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const label = `${filenameBase}.${format}`;
    setDownloadNotices((current) => [
      ...current,
      { id, label, status: "running", message: "Rendering plot" },
    ]);
    try {
      await downloadSvgPlot(svgSelector, `${filenameBase}.${format}`, format);
      updateDownloadNotice(id, { status: "done", message: "Download ready" });
      window.setTimeout(() => dismissDownloadNotice(id), 4500);
    } catch (err) {
      updateDownloadNotice(id, {
        status: "failed",
        message: err?.message || "Plot download failed",
      });
    }
  }

  function scrollToResults() {
    window.requestAnimationFrame(() => {
      resultPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  async function runAnalysis() {
    if (isCombinedMode) {
      const normalizedA = geneInputTokens(effectiveSignatureAInput).join(", ");
      const normalizedB = geneInputTokens(effectiveSignatureBInput).join(", ");
      if (!uniqueGeneSymbols(normalizedA).length || !uniqueGeneSymbols(normalizedB).length) {
        setError("Enter genes for both signatures before running the combined analysis.");
        return;
      }

      setLoading(true);
      setError("");
      setAnalysisResults([]);
      scrollToResults();
      setCombinedGeneQueries({ a: "", b: "" });
      setForm((current) => ({
        ...current,
        combined_signature: {
          ...current.combined_signature,
          signature_a: { ...current.combined_signature.signature_a, gene_symbol: normalizedA },
          signature_b: { ...current.combined_signature.signature_b, gene_symbol: normalizedB },
        },
      }));
      try {
        const payload = buildCombinedAnalysisPayload(form, normalizedA, normalizedB);
        const result = await createCombinedAnalysis(payload);
        setAnalysisResults([result]);
      } catch (err) {
        setError(formatError(err));
      } finally {
        setLoading(false);
      }
      return;
    }

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
            className={activePage === "pancancer" ? "selected" : ""}
            onClick={() => setActivePage("pancancer")}
          >
            <Network size={16} />
            Pan-cancer
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
              {activePage === "analysis"
                ? "Kaplan-Meier analysis"
                : activePage === "compare"
                  ? "Compare analyses"
                  : activePage === "pancancer"
                    ? "Pan-cancer survival concordance"
                    : "Dataset summary"}
            </p>
            <h1>
              {activePage === "analysis"
                ? "Gene expression survival explorer"
                : activePage === "compare"
                  ? "Gene and cutpoint comparison"
                  : activePage === "pancancer"
                    ? "Cross-cancer outcome concordance"
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

            <PanelHeader
              icon={<Activity size={18} />}
              title="Gene analysis"
              description="Choose a single gene/signature analysis or cross two independent signatures into combined groups."
            />

            <div className="axis-control two-options">
              <span>Analysis design</span>
              <div>
                {[
                  ["single_signature", "One signature"],
                  ["combined_signatures", "Two signatures"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={form.analysis_kind === value ? "selected" : ""}
                    onClick={() => updateForm("analysis_kind", value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {!isCombinedMode ? (
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
            ) : (
              <CombinedSignatureBuilder
                value={form.combined_signature}
                onSignatureChange={updateCombinedSignature}
                queries={combinedGeneQueries}
                setQuery={updateCombinedGeneQuery}
                suggestions={combinedGeneSuggestions}
              />
            )}

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

            {!isCombinedMode && (
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
            )}

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

            {!isCombinedMode ? (
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
            ) : (
              <div className="method-grid compact two">
                {[
                  { value: "median", label: "Median x median", help: "Four combined groups: Low_Low through High_High" },
                  { value: "tertiles", label: "Tertiles x tertiles", help: "Up to nine combined Low/Mid/High groups" },
                ].map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={form.combined_signature.grouping_method === item.value ? "selected" : ""}
                    onClick={() => updateCombinedGroupingMethod(item.value)}
                  >
                    <strong>{item.label}</strong>
                    <span>{item.help}</span>
                  </button>
                ))}
              </div>
            )}

            {!isCombinedMode && form.cutpoint_method === "maxstat" && (
              <div className="method-note">
                Maxstat optimizes the cutpoint against survival separation. Treat it as exploratory
                and validate important findings externally.
              </div>
            )}

            {!isCombinedMode && form.cutpoint_method === "percentile" && (
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
              title="Grade"
              values={filters?.grades || []}
              selected={form.filters.grades}
              onToggle={(value) => toggleFilterValue("grades", value)}
              onClear={() => clearFilter("grades")}
              showWhenEmpty
              emptyLabel="No grade metadata for this cohort"
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

            <PlotOutputControls
              form={form}
              updateForm={updateForm}
              updatePlotStyle={updatePlotStyle}
              updatePaletteColor={updatePaletteColor}
              plotTitlePlaceholder={`${plotCancerName} overall survival`}
            />

            <div className="run-summary">
              <div>
                <span>Ready request</span>
                <strong>
                  {selectedCancerName} / {isCombinedMode ? "2 signatures" : runCount ? `${runCount} gene${runCount === 1 ? "" : "s"}` : "GENE"}
                </strong>
                <small>
                  {isCombinedMode
                    ? `${form.combined_signature.grouping_method === "tertiles" ? "Tertile" : "Median"} crossed groups`
                    : form.signature_method === "single" ? "Separate KM plot per gene" : "Combined signature plot"}; {selectedEndpoint.label}; {selectedExpressionScale.label}
                </small>
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
                analysisKind={form.analysis_kind}
                signatureMethod={form.signature_method}
                geneCount={runCount}
                endpoint={selectedEndpoint}
                expressionScale={selectedExpressionScale}
                cutpoint={previewCutpoint}
                activeFilterCount={activeFilterCount}
              />
            )}

            {loading && (
              <LoadingState
                cohort={form.cohort}
                gene={isCombinedMode ? `${form.combined_signature.signature_a.name} x ${form.combined_signature.signature_b.name}` : form.gene_symbol}
                analysisKind={form.analysis_kind}
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
            cohorts={cohorts}
            visibleCohorts={visibleCohorts}
            selectedCohort={selectedCohort}
            selectedCohortId={form.cohort}
            cohortQuery={cohortQuery}
            setCohortQuery={setCohortQuery}
            cohortPickerOpen={cohortPickerOpen}
            setCohortPickerOpen={setCohortPickerOpen}
            onSelectCohort={selectCohort}
            endpointOptions={endpointOptions}
            selectedEndpoint={selectedEndpoint}
            onSelectEndpoint={(value) => updateForm("endpoint", value)}
            updateForm={updateForm}
            updatePlotStyle={updatePlotStyle}
            updatePaletteColor={updatePaletteColor}
            expressionScales={expressionScales}
            filters={filters}
            activeFilterCount={activeFilterCount}
            updateFilters={updateFilters}
            toggleFilterValue={toggleFilterValue}
            clearFilter={clearFilter}
            compare={compare}
            setCompare={setCompare}
            cutpoints={CUTPOINTS}
            expressionScale={selectedExpressionScale}
            suggestionCohort={geneSuggestionCohort}
            canRun={Boolean(form.cohort && selectedEndpoint.available)}
            onDownload={startDownload}
          />
        ) : activePage === "pancancer" ? (
          <PanCancerSurvival
            state={panCancer}
            setState={setPanCancer}
            updateState={updatePanCancer}
            cohorts={cohorts}
            form={form}
            endpointOptions={endpointOptions}
            expressionScales={expressionScales}
            onDownload={startDownload}
            onPlotDownload={startPlotDownload}
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

function FilterGroup({ title, values, selected, onToggle, onClear, showWhenEmpty = false, emptyLabel = "No values available" }) {
  if (!values.length && !showWhenEmpty) return null;
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
        {values.length ? (
          values.slice(0, 14).map((value) => (
            <button
              key={value}
              type="button"
              className={selected.includes(value) ? "selected" : ""}
              onClick={() => onToggle(value)}
            >
              {value}
            </button>
          ))
        ) : (
          <span className="filter-empty">{emptyLabel}</span>
        )}
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

function CombinedSignatureBuilder({
  value,
  onSignatureChange,
  queries,
  setQuery,
  suggestions,
}) {
  return (
    <div className="combined-signature-builder">
      {[
        ["signature_a", "a", "Signature A"],
        ["signature_b", "b", "Signature B"],
      ].map(([signatureKey, queryKey, fallbackName]) => {
        const signature = value[signatureKey];
        return (
          <div className="combined-signature-card" key={signatureKey}>
            <label className="field">
              <span>{fallbackName} name</span>
              <input
                value={signature.name}
                onChange={(event) => onSignatureChange(signatureKey, { name: event.target.value })}
                placeholder={fallbackName}
              />
            </label>
            <GeneSelector
              label={`${signature.name || fallbackName} genes`}
              value={signature.gene_symbol}
              onChange={(gene_symbol) => onSignatureChange(signatureKey, { gene_symbol })}
              draft={queries[queryKey]}
              setDraft={(draft) => setQuery(queryKey, draft)}
              suggestions={suggestions[queryKey]}
              placeholder="Type IFNG, CXCL9, GZMB..."
              help="Select genes for this signature. Weighted mode accepts GENE:weight."
            />
            <div className="axis-control">
              <span>Score method</span>
              <div>
                {[
                  ["single", "Single"],
                  ["mean", "Mean"],
                  ["zscore", "Z-score"],
                  ["weighted", "Weighted"],
                ].map(([method, label]) => (
                  <button
                    key={method}
                    type="button"
                    className={signature.signature_method === method ? "selected" : ""}
                    onClick={() => onSignatureChange(signatureKey, { signature_method: method })}
                    title={signatureHelp(method)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PlotOutputControls({
  form,
  updateForm,
  updatePlotStyle,
  updatePaletteColor,
  plotTitlePlaceholder,
  showOutputHeader = false,
}) {
  return (
    <div className="plot-output-controls">
      {showOutputHeader && (
        <PanelHeader
          icon={<Image size={18} />}
          title="Plot output"
          description="Set the time axis, risk table and plot appearance for all comparison runs."
        />
      )}

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
        <div className="axis-control two-options">
          <span>Plot shape</span>
          <div>
            {[
              { value: "rectangular", label: "Rectangular" },
              { value: "square", label: "Square" },
            ].map((shape) => (
              <button
                key={shape.value}
                type="button"
                className={form.plot_style.plot_aspect === shape.value ? "selected" : ""}
                onClick={() => updatePlotStyle("plot_aspect", shape.value)}
              >
                {shape.label}
              </button>
            ))}
          </div>
        </div>
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
              placeholder={plotTitlePlaceholder}
            />
          </label>
        )}
      </div>
    </div>
  );
}

function CompareAnalyses({
  form,
  cohorts,
  visibleCohorts,
  selectedCohort,
  selectedCohortId,
  cohortQuery,
  setCohortQuery,
  cohortPickerOpen,
  setCohortPickerOpen,
  onSelectCohort,
  endpointOptions,
  selectedEndpoint,
  onSelectEndpoint,
  updateForm,
  updatePlotStyle,
  updatePaletteColor,
  expressionScales,
  filters,
  activeFilterCount,
  updateFilters,
  toggleFilterValue,
  clearFilter,
  compare,
  setCompare,
  cutpoints,
  expressionScale,
  suggestionCohort,
  canRun,
  onDownload,
}) {
  const selectedMethods = compare.methods;
  const [compareGeneQuery, setCompareGeneQuery] = useState("");
  const [compareGeneSuggestions, setCompareGeneSuggestions] = useState([]);
  const effectiveCompareInput = compareGeneQuery.trim() ? addGeneToken(compare.genes, compareGeneQuery) : compare.genes;
  const genes = uniqueGeneSymbols(effectiveCompareInput);
  const adjusted = useMemo(() => adjustCompareResults(compare.results), [compare.results]);
  const selectedCutpoints = cutpoints.filter((item) => selectedMethods.includes(item.value));
  const missingRequirements = [];
  if (!form.cohort) missingRequirements.push("select a cancer cohort");
  if (form.cohort && !canRun) missingRequirements.push("select an available survival endpoint");
  if (!genes.length) missingRequirements.push("add at least one gene");
  if (!selectedMethods.length) missingRequirements.push("select at least one method");
  const canRunSelectedMethods = canRun && genes.length > 0 && selectedMethods.length > 0 && !compare.running;
  const canRunAllDichotomizations = canRun && genes.length > 0 && !compare.running;
  const selectedDichotomizationCount = selectedMethods.filter((method) => DICHOTOMIZATION_METHODS.includes(method)).length;

  useEffect(() => {
    const searchTerm = currentGeneSearchTerm(compareGeneQuery);
    if (!suggestionCohort || searchTerm.length < 1) {
      setCompareGeneSuggestions([]);
      return;
    }
    const handle = setTimeout(() => {
      searchGenes(suggestionCohort, searchTerm)
        .then((payload) => setCompareGeneSuggestions(payload.genes))
        .catch(() => setCompareGeneSuggestions([]));
    }, 220);
    return () => clearTimeout(handle);
  }, [suggestionCohort, compareGeneQuery]);

  function toggleMethod(method) {
    setCompare((current) => ({
      ...current,
      methods: current.methods.includes(method)
        ? current.methods.filter((item) => item !== method)
        : [...current.methods, method],
    }));
  }

  async function runCompare(methodOverride = null) {
    const methodsToRun = methodOverride || selectedMethods;
    if (!canRun || !genes.length || !methodsToRun.length) {
      setCompare((current) => ({
        ...current,
        error: `Cannot run comparison: ${missingRequirements.join(", ") || "check inputs"}.`,
      }));
      return;
    }
    const normalizedGenes = uniqueGeneSymbols(effectiveCompareInput);
    setCompareGeneQuery("");
    setCompare((current) => ({
      ...current,
      methods: methodsToRun,
      genes: normalizedGenes.join(", "),
      running: true,
      error: "",
      results: [],
    }));
    try {
      const jobs = normalizedGenes.flatMap((gene) =>
        methodsToRun.map((method) => {
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
      <div className="compare-controls" aria-label="Comparison controls">
        <div className="compare-main-flow">
          <section className="compare-section">
            <PanelHeader
              icon={<Database size={18} />}
              title="1. Dataset and endpoint"
              description="Shared cohort, outcome and expression scale for every matrix cell."
            />
            <div className="compare-control-grid">
              <div className="compare-control-block">
                <div className="compare-control-label">
                  <span>Cohort</span>
                </div>
                <CohortPicker
                  cohorts={cohorts}
                  visibleCohorts={visibleCohorts}
                  selectedCohort={selectedCohort}
                  selectedCohortId={selectedCohortId}
                  query={cohortQuery}
                  setQuery={setCohortQuery}
                  open={cohortPickerOpen}
                  setOpen={setCohortPickerOpen}
                  onSelect={onSelectCohort}
                />
              </div>
              <div className="compare-control-block">
                <div className="compare-control-label">
                  <span>Survival endpoint</span>
                  <strong>{selectedEndpoint.available ? "Available" : "Unavailable"}</strong>
                </div>
                <EndpointSelector
                  endpoints={endpointOptions}
                  selected={form.endpoint}
                  onSelect={onSelectEndpoint}
                />
              </div>
              <div className="compare-control-block wide">
                <div className="compare-control-label">
                  <span>RNA expression scale</span>
                  <strong>{expressionScale.label}</strong>
                </div>
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
              </div>
            </div>
          </section>

          <section className="compare-section">
            <PanelHeader
              icon={<Dna size={18} />}
              title="2. Markers and cutpoints"
              description="Genes define rows; cutpoint methods define columns."
            />
            <div className="compare-control-grid compare-marker-grid">
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
              <div className="compare-method-panel">
                <div className="compare-control-label">
                  <span>Cutpoint methods</span>
                  <strong>{selectedMethods.length} selected / {selectedDichotomizationCount} dichotomizing</strong>
                </div>
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
                <label className="field compare-percentile-field">
                  <span>Percentile threshold</span>
                  <input
                    type="number"
                    min="1"
                    max="99"
                    value={form.custom_percentile}
                    onChange={(event) => updateForm("custom_percentile", event.target.value)}
                  />
                </label>
              </div>
            </div>
          </section>

          <section className="compare-section">
            <details className="compare-disclosure" defaultOpen={activeFilterCount > 0}>
              <summary>
                <span>3. Clinical filters</span>
                <strong>{activeFilterCount ? `${activeFilterCount} active` : "All eligible patients"}</strong>
              </summary>
              <div className="compare-filter-grid">
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
                  title="Grade"
                  values={filters?.grades || []}
                  selected={form.filters.grades}
                  onToggle={(value) => toggleFilterValue("grades", value)}
                  onClear={() => clearFilter("grades")}
                  showWhenEmpty
                  emptyLabel="No grade metadata for this cohort"
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
              </div>
            </details>
          </section>

          <section className="compare-section">
            <details className="compare-disclosure compare-plot-disclosure">
              <summary>
                <span>4. Plot output</span>
                <strong>{form.time_unit}, {form.plot_style.plot_aspect}, risk table {form.show_risk_table ? "on" : "off"}</strong>
              </summary>
              <PlotOutputControls
                form={form}
                updateForm={updateForm}
                updatePlotStyle={updatePlotStyle}
                updatePaletteColor={updatePaletteColor}
                plotTitlePlaceholder={`${selectedCohort ? getCohortName(selectedCohort.id) : "Cancer"} comparison`}
              />
            </details>
          </section>
        </div>

        <aside className="compare-run-panel" aria-label="Run comparison">
          <div className="run-summary static">
            <div>
              <span>Run setup</span>
              <strong>{genes.length || 0} genes x {selectedMethods.length} methods</strong>
              <div className="compare-run-facts">
                <div><span>Cohort</span><strong>{form.cohort || "..."}</strong></div>
                <div><span>Endpoint</span><strong>{selectedEndpoint.label}</strong></div>
                <div><span>Scale</span><strong>{expressionScale.label}</strong></div>
                <div><span>Parallel jobs</span><strong>{ANALYSIS_BATCH_CONCURRENCY}</strong></div>
              </div>
              <small>BH and Bonferroni adjustment are applied across completed comparisons.</small>
              {missingRequirements.length ? (
                <small className="input-requirement">Required: {missingRequirements.join(", ")}.</small>
              ) : (
                <small className="input-requirement">Ready for {form.cohort}, {selectedEndpoint.label}; robustness runs maxstat, median, upper quartile, outer quartiles and percentile.</small>
              )}
            </div>
            <button className="primary-button" onClick={() => runCompare()} disabled={!canRunSelectedMethods}>
              {compare.running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              Run selected methods
            </button>
            <button
              className="secondary-button"
              onClick={() => runCompare(DICHOTOMIZATION_METHODS)}
              disabled={!canRunAllDichotomizations}
              title="Run all five two-group cutpoint methods: maxstat, median, upper quartile, outer quartiles and the selected custom percentile."
            >
              {compare.running ? <Loader2 className="spin" size={18} /> : <SlidersHorizontal size={18} />}
              Run all 5 cutpoint methods
            </button>
          </div>
        </aside>
      </div>
      {compare.error && <div className="error-box"><AlertCircle size={18} /><span>{compare.error}</span></div>}
      <ComparePlotMatrix
        rows={adjusted}
        genes={genes}
        methods={selectedCutpoints}
        running={compare.running}
        onDownload={onDownload}
      />
      <CutpointRobustnessSummary rows={adjusted} methods={cutpoints} />
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
      <div className="method-note">
        Not reached means the Kaplan-Meier curve did not fall below 50% during follow-up.
      </div>
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
        <span>RMST Δ {formatRmstDelta(metrics.rmst)}</span>
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

function CutpointRobustnessSummary({ rows, methods }) {
  const completed = rows.filter((row) => row.result?.metrics && DICHOTOMIZATION_METHODS.includes(row.method));
  if (!completed.length) return null;
  const methodLabels = Object.fromEntries(methods.map((method) => [method.value, method.label]));
  const summarized = completed.map((row) => ({
    ...row,
    robustness: cutpointRobustness(row),
  }));
  const survived = summarized.filter((row) => row.robustness.survives);
  const genes = Array.from(new Set(summarized.map((row) => row.gene)));
  return (
    <div className="detail-section robustness-summary">
      <h3>Cutpoint robustness</h3>
      <div className="robustness-headline">
        <div>
          <span>Surviving dichotomizations</span>
          <strong>{survived.length} / {summarized.length}</strong>
        </div>
        <div>
          <span>Genes evaluated</span>
          <strong>{genes.length}</strong>
        </div>
        <div>
          <span>Decision rule</span>
          <strong>BH + Cox + adjusted Cox + RMST + PH</strong>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>Gene</th>
            <th>Method</th>
            <th>Patients</th>
            <th>Events</th>
            <th>BH log-rank</th>
            <th>Cox p</th>
            <th>Adjusted p</th>
            <th>RMST delta</th>
            <th>RMST p</th>
            <th>PH global p</th>
            <th>Direction</th>
            <th>Survives</th>
          </tr>
        </thead>
        <tbody>
          {summarized.map((row) => {
            const metrics = row.result.metrics || {};
            const robustness = row.robustness;
            const univariable = findCoxModel(metrics.cox_models, "univariable");
            const adjustedModel = downstreamAdjustedModel(metrics.cox_models);
            return (
              <tr key={`${row.gene}-${row.method}`}>
                <td>{row.gene}</td>
                <td>{methodLabels[row.method] || formatLabel(row.method)}</td>
                <td>{formatInteger(metrics.n_patients)}</td>
                <td>{formatInteger(metrics.n_events)}</td>
                <td className={robustness.bhPass ? "pass-cell" : "fail-cell"}>{formatP(row.bh)}</td>
                <td className={robustness.coxPass ? "pass-cell" : "fail-cell"}>{formatP(univariable?.p_value)}</td>
                <td className={robustness.adjustedPass ? "pass-cell" : "fail-cell"}>{formatP(adjustedModel?.p_value)}</td>
                <td>{formatRmstDelta(metrics.rmst)}</td>
                <td className={robustness.rmstPass ? "pass-cell" : "fail-cell"}>{formatP(metrics.rmst?.difference?.p_value)}</td>
                <td className={robustness.phOk ? "pass-cell" : "fail-cell"}>{formatP(adjustedModel?.ph_global_p_value)}</td>
                <td>{robustness.direction}</td>
                <td>
                  <span className={`survival-badge ${robustness.survives ? "survives" : "does-not-survive"}`}>
                    {robustness.survives ? "Survives" : robustness.reason}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="method-note">
        {`A dichotomization survives when BH-adjusted log-rank p, univariable Cox p, the strongest available adjusted Cox p and RMST p are all <= ${ROBUSTNESS_ALPHA}, and the adjusted PH global test is not flagged.`}
      </div>
    </div>
  );
}

function PanCancerSurvival({ state, setState, updateState, cohorts, form, expressionScales, onDownload, onPlotDownload }) {
  const effectiveGeneInput = state.geneQuery.trim() ? addGeneToken(state.gene_symbol, state.geneQuery) : state.gene_symbol;
  const genes = uniqueGeneSymbols(effectiveGeneInput);
  const indexCohort = state.index_cohort || form.cohort || cohorts[0]?.id || "";
  const selectedExpressionScale =
    expressionScales.find((item) => item.value === state.expression_scale) || EXPRESSION_SCALE_FALLBACK[0];
  const selectedEndpointMode =
    PANCANCER_ENDPOINT_MODES.find((item) => item.value === state.endpoint_mode) || PANCANCER_ENDPOINT_MODES[0];
  const canRun = Boolean(indexCohort && genes.length === 1 && !state.running);

  function useCurrentKmInputs() {
    setState((current) => ({
      ...current,
      gene_symbol: geneInputTokens(form.gene_symbol).slice(0, 1).join(", "),
      geneQuery: "",
      index_cohort: form.cohort || current.index_cohort,
      endpoint: form.endpoint || current.endpoint,
      expression_scale: form.expression_scale || current.expression_scale,
      result: null,
      error: "",
    }));
  }

  async function runScan() {
    if (!canRun) return;
    setState((current) => ({
      ...current,
      gene_symbol: genes[0],
      geneQuery: "",
      running: true,
      result: null,
      error: "",
    }));
    try {
      const payload = {
        gene_symbol: genes[0],
        index_cohort: indexCohort,
        endpoint: state.endpoint,
        endpoint_mode: state.endpoint_mode,
        expression_scale: state.expression_scale,
        min_patients: Number(state.min_patients) || 10,
        min_events: Number(state.min_events) || 5,
        fdr_threshold: Number(state.fdr_threshold) || 0.1,
        filters: {
          sample_types: [],
          stages: [],
          grades: [],
          genders: [],
          races: [],
          age_min: null,
          age_max: null,
          max_time_days: null,
        },
      };
      const result = await createPanCancerSurvival(payload);
      setState((current) => ({ ...current, result, error: "" }));
    } catch (err) {
      setState((current) => ({ ...current, error: formatError(err) }));
    } finally {
      setState((current) => ({ ...current, running: false }));
    }
  }

  return (
    <section className="pancancer-page">
      <ImmunePanCancerAtlas
        screen={state.immuneScreen}
        loading={state.immuneScreenLoading}
        error={state.immuneScreenError}
        onDownload={onDownload}
        onPlotDownload={onPlotDownload}
      />

      <div className="pancancer-controls">
        <div className="pancancer-control-panel">
          <PanelHeader
            icon={<Network size={18} />}
            title="Pan-cancer query"
            description="Run one continuous Cox model per TCGA cancer using expression z-scored inside each cohort."
          />
          <div className="download-row">
            <button type="button" onClick={useCurrentKmInputs}>
              Use current KM inputs
            </button>
          </div>
          <label className="field">
            <span>Index cancer</span>
            <select value={indexCohort} onChange={(event) => updateState("index_cohort", event.target.value)}>
              {cohorts.map((cohort) => (
                <option key={cohort.id} value={cohort.id}>
                  {getCohortLabel(cohort.id)}
                </option>
              ))}
            </select>
          </label>
          <GeneSelector
            label="Gene symbol"
            value={state.gene_symbol}
            onChange={(value) => updateState("gene_symbol", value)}
            draft={state.geneQuery}
            setDraft={(value) => updateState("geneQuery", value)}
            suggestions={state.geneSuggestions}
            placeholder="Type TP53, KRAS, EGFR..."
            help="Use exactly one gene for a cross-cancer concordance scan."
          />
          {genes.length > 1 && (
            <div className="method-note">Pan-cancer concordance currently accepts one gene per scan.</div>
          )}
        </div>

        <div className="pancancer-control-panel">
          <PanelHeader
            icon={<Activity size={18} />}
            title="Outcome model"
            description="Select the reference endpoint and how similar endpoints are allowed across cohorts."
          />
          <div className="range-grid">
            <label className="field">
              <span>Reference endpoint</span>
              <select value={state.endpoint} onChange={(event) => updateState("endpoint", event.target.value)}>
                {PANCANCER_ENDPOINTS.map((endpoint) => (
                  <option key={endpoint.value} value={endpoint.value}>
                    {endpoint.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Expression scale</span>
              <select value={state.expression_scale} onChange={(event) => updateState("expression_scale", event.target.value)}>
                {expressionScales.map((scale) => (
                  <option key={scale.value} value={scale.value}>
                    {scale.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="method-grid compact">
            {PANCANCER_ENDPOINT_MODES.map((item) => (
              <button
                key={item.value}
                type="button"
                className={state.endpoint_mode === item.value ? "selected" : ""}
                onClick={() => updateState("endpoint_mode", item.value)}
              >
                <strong>{item.label}</strong>
                <span>{item.help}</span>
              </button>
            ))}
          </div>
          <div className="range-grid">
            <label className="field">
              <span>Min patients</span>
              <input
                type="number"
                min="10"
                value={state.min_patients}
                onChange={(event) => updateState("min_patients", event.target.value)}
              />
            </label>
            <label className="field">
              <span>Min events</span>
              <input
                type="number"
                min="5"
                value={state.min_events}
                onChange={(event) => updateState("min_events", event.target.value)}
              />
            </label>
            <label className="field wide">
              <span>FDR threshold</span>
              <input
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={state.fdr_threshold}
                onChange={(event) => updateState("fdr_threshold", event.target.value)}
              />
            </label>
          </div>
          <div className="run-summary static">
            <div>
              <span>Scan scope</span>
              <strong>{genes.length === 1 ? `${genes[0]} across ${formatInteger(cohorts.length)} cancers` : "One gene required"}</strong>
              <small>{selectedEndpointMode.label}; {selectedExpressionScale.label}; Cox HR per +1 SD expression.</small>
            </div>
            <button className="primary-button" onClick={runScan} disabled={!canRun}>
              {state.running ? <Loader2 className="spin" size={18} /> : <Play size={18} />}
              Run pan-cancer scan
            </button>
          </div>
        </div>
      </div>

      {state.error && <div className="error-box"><AlertCircle size={18} /><span>{state.error}</span></div>}
      {state.running && (
        <div className="loading-state compact">
          <Loader2 className="spin" size={34} />
          <div>
            <p className="eyebrow">Running pan-cancer Cox scan</p>
            <h2>{genes[0] || state.gene_symbol || "Gene"} across TCGA cohorts</h2>
            <span>Preparing one patient-level model per cancer, then adjusting p-values and summarizing concordance.</span>
          </div>
        </div>
      )}
      {!state.running && !state.result && !state.error && (
        <div className="empty-plot">
          <Network size={38} />
          <p>Pan-cancer concordance results will appear here after running a single-gene scan.</p>
        </div>
      )}
      {state.result && <PanCancerResults result={state.result} onDownload={onDownload} onPlotDownload={onPlotDownload} />}
    </section>
  );
}

function PanCancerResults({ result, onDownload, onPlotDownload }) {
  const summary = result.summary || {};
  const randomEffect = result.meta_analysis?.random_effect || {};
  const heterogeneity = result.meta_analysis?.heterogeneity || {};
  return (
    <div className="pancancer-results">
      <div className="analysis-result">
        <div className="result-header">
          <div>
            <p className="eyebrow">{result.scan_id} {result.cached ? "/ cached" : ""}</p>
            <h2>{result.gene_symbol} pan-cancer survival concordance</h2>
          </div>
          <div className="download-row">
            <DownloadLink href={result.downloads?.csv} icon={<FileSpreadsheet size={16} />} label="CSV" onDownload={onDownload} />
          </div>
        </div>
        <div className="metric-strip pancancer-kpis">
          <Metric label="Completed" value={`${formatInteger(summary.completed)} / ${formatInteger(summary.total_cohorts)}`} />
          <Metric label="FDR hits" value={formatInteger(summary.significant)} />
          <Metric label="Pooled HR" value={randomEffect.hazard_ratio ? formatHrValues(randomEffect) : "..."} />
          <Metric label="I2" value={formatPercent(heterogeneity.i_squared)} />
        </div>
        {!!result.warnings?.length && (
          <div className="warning-list">
            {result.warnings.map((warning) => <div key={warning}>{warning}</div>)}
          </div>
        )}
      </div>

      <div className="pancancer-layout">
        <section className="summary-panel">
          <PanelHeader
            icon={<BarChart3 size={18} />}
            title="Forest plot"
            description="Hazard ratio per +1 SD expression; confidence intervals are from per-cohort Cox models."
          />
          <PlotDownloadButtons
            svgSelector=".pancancer-forest"
            filenameBase={`${result.scan_id}.forest`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerForestPlot rows={result.results || []} metaAnalysis={result.meta_analysis} />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            icon={<PieChart size={18} />}
            title="Concordance map"
            description="Interactive cohort-level concordance, evidence strength and model-readiness relative to the selected index cancer."
          />
          <PanCancerConcordanceMap
            rows={result.results || []}
            summary={summary}
            reference={result.reference}
            fdrThreshold={result.fdr_threshold}
          />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            icon={<Activity size={18} />}
            title="Evidence landscape"
            description="Each cohort is positioned by effect size and FDR evidence; the horizontal line marks the selected FDR threshold."
          />
          <PlotDownloadButtons
            svgSelector=".pancancer-landscape"
            filenameBase={`${result.scan_id}.evidence_landscape`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerEvidenceLandscape rows={result.results || []} fdrThreshold={result.fdr_threshold} />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            icon={<SlidersHorizontal size={18} />}
            title="Power and precision map"
            description="Cohorts farther right and higher have more survival events and tighter Cox estimates."
          />
          <PlotDownloadButtons
            svgSelector=".pancancer-power"
            filenameBase={`${result.scan_id}.power_precision`}
            onPlotDownload={onPlotDownload}
          />
          <PanCancerPowerPrecision rows={result.results || []} />
        </section>
        <section className="summary-panel wide">
          <PanelHeader
            icon={<Table2 size={18} />}
            title="Cohort results"
            description="Skipped rows preserve endpoint and power limitations instead of hiding unevaluable cancers."
          />
          <PanCancerTable rows={result.results || []} />
        </section>
      </div>
    </div>
  );
}

function ImmunePanCancerAtlas({ screen, loading, error, onDownload, onPlotDownload }) {
  if (loading) {
    return (
      <div className="immune-atlas loading-state compact">
        <Loader2 className="spin" size={28} />
        <div>
          <p className="eyebrow">Immune pan-cancer atlas</p>
          <h2>Loading immune screen summary</h2>
        </div>
      </div>
    );
  }
  if (error) {
    return <div className="error-box"><AlertCircle size={18} /><span>{error}</span></div>;
  }
  if (!screen) return null;

  const headline = screen.headline || {};
  const downloads = screen.downloads || {};
  const directions = screen.direction_counts_global_fdr || {};
  const recurrence = screen.recurrence || {};
  return (
    <div className="immune-atlas analysis-result">
      <div className="result-header immune-atlas-header">
        <div>
          <p className="eyebrow">{screen.screen_id}</p>
          <h2>Immune pan-cancer atlas</h2>
        </div>
        <div className="download-row">
          <DownloadLink href={downloads.genes} icon={<FileSpreadsheet size={16} />} label="Genes" onDownload={onDownload} />
          <DownloadLink href={downloads.cohorts} icon={<Table2 size={16} />} label="Cohorts" onDownload={onDownload} />
          <DownloadLink href={downloads.terms} icon={<Network size={16} />} label="Terms" onDownload={onDownload} />
          <DownloadLink href={downloads.methodology} icon={<FileText size={16} />} label="Method TXT" onDownload={onDownload} />
        </div>
      </div>

      <div className="metric-strip immune-kpis">
        <Metric label="Immune genes" value={formatInteger(headline.immune_genes)} />
        <Metric label="Cox models" value={formatInteger(headline.completed_gene_cohort_models)} />
        <Metric label="Global FDR hits" value={formatInteger(headline.global_fdr_hits)} />
        <Metric label="Meta-FDR genes" value={formatInteger(headline.meta_fdr_gene_hits)} />
        <Metric label="Harmful hits" value={formatInteger(directions.harmful || 0)} />
        <Metric label="Protective hits" value={formatInteger(directions.protective || 0)} />
      </div>

      <div className="immune-atlas-grid">
        <section className="immune-panel recurrence">
          <PanelHeader
            icon={<SlidersHorizontal size={18} />}
            title="Recurrence by prognosis"
            description="How often each immune gene is a global-FDR hit with HR > 1 or HR < 1 across cancers."
          />
          <PlotDownloadButtons
            svgSelector=".immune-recurrence-svg"
            filenameBase={`${screen.screen_id}.immune_recurrence`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneRecurrencePlot recurrence={recurrence} />
        </section>
        <section className="immune-panel frequency">
          <PanelHeader
            icon={<BarChart3 size={18} />}
            title="Rare versus recurrent"
            description="Genes appearing in one cancer are context-specific; genes appearing in many cancers are pan-cancer patterns."
          />
          <PlotDownloadButtons
            svgSelector=".immune-frequency-svg"
            filenameBase={`${screen.screen_id}.immune_frequency`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneFrequencyDistribution recurrence={recurrence} />
        </section>
        <section className="immune-panel spectrum">
          <PanelHeader
            icon={<Activity size={18} />}
            title="Meta-behavior"
            description="Random-effects gene signal across evaluable cancers; point size follows cohort-level FDR hits."
          />
          <PlotDownloadButtons
            svgSelector=".immune-spectrum-svg"
            filenameBase={`${screen.screen_id}.immune_meta_spectrum`}
            onPlotDownload={onPlotDownload}
          />
          <ImmuneMetaSpectrum genes={screen.top_genes || []} />
        </section>
        <section className="immune-panel burden">
          <PanelHeader
            icon={<BarChart3 size={18} />}
            title="Cancer burden"
            description="Cancers with the densest immune-gene survival signal under global FDR control."
          />
          <ImmuneCohortBurden cohorts={screen.top_cohorts || []} />
        </section>
        <section className="immune-panel terms">
          <PanelHeader
            icon={<Network size={18} />}
            title="Immune programs"
            description="Open ImmPort GO/Reactome terms represented among strongest pan-cancer signals."
          />
          <ImmuneTermList terms={screen.top_terms || []} />
        </section>
        <section className="immune-panel rare">
          <PanelHeader
            icon={<Search size={18} />}
            title="Context-specific extremes"
            description="Strongest one-cancer signals; useful for tissue-specific follow-up rather than pan-cancer claims."
          />
          <ImmuneRareSignals recurrence={recurrence} />
        </section>
      </div>
    </div>
  );
}

function ImmuneRecurrencePlot({ recurrence }) {
  const harmful = (recurrence.top_harmful || []).slice(0, 12);
  const protective = (recurrence.top_protective || []).slice(0, 12);
  const rowCount = Math.max(harmful.length, protective.length);
  if (!rowCount) return <div className="empty-inline">No recurrence summary available.</div>;

  const width = 900;
  const rowHeight = 29;
  const height = 64 + rowCount * rowHeight;
  const plot = { left: 170, right: 170, top: 34, bottom: 30 };
  const center = width / 2;
  const maxCount = Math.max(
    1,
    ...harmful.map((row) => Number(row.harmful_cancer_count || 0)),
    ...protective.map((row) => Number(row.protective_cancer_count || 0)),
  );
  const maxSpan = center - plot.left;
  const scale = (value) => (Number(value || 0) / maxCount) * maxSpan;
  const ticks = uniqueNumbers([0, Math.ceil(maxCount / 2), maxCount]);

  return (
    <div className="immune-recurrence-wrap">
      <svg className="immune-recurrence-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene recurrence by prognosis">
        <line className="recurrence-center" x1={center} x2={center} y1={plot.top - 14} y2={height - plot.bottom + 4} />
        {ticks.map((tick) => (
          <g key={tick} className="recurrence-axis">
            <line x1={center - scale(tick)} x2={center - scale(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
            <line x1={center + scale(tick)} x2={center + scale(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
            <text x={center - scale(tick)} y={height - 8}>{tick}</text>
            {tick !== 0 && <text x={center + scale(tick)} y={height - 8}>{tick}</text>}
          </g>
        ))}
        <text className="recurrence-side-label protective" x={plot.left} y="18">More frequent better prognosis</text>
        <text className="recurrence-side-label harmful" x={width - plot.right} y="18">More frequent worse prognosis</text>
        {Array.from({ length: rowCount }).map((_, index) => {
          const y = plot.top + index * rowHeight;
          const better = protective[index];
          const worse = harmful[index];
          const betterCount = Number(better?.protective_cancer_count || 0);
          const worseCount = Number(worse?.harmful_cancer_count || 0);
          const betterX = center - scale(betterCount);
          const worseX = center + scale(worseCount);
          return (
            <g key={index} className="recurrence-row">
              <line className="recurrence-guide" x1={plot.left - 12} x2={width - plot.right + 12} y1={y} y2={y} />
              {better && (
                <g className="recurrence-lollipop protective">
                  <line x1={center} x2={betterX} y1={y} y2={y} />
                  <circle cx={betterX} cy={y} r={5.5} />
                  <text className="gene-label" x={betterX - 10} y={y + 4} textAnchor="end">{better.gene_symbol}</text>
                  <text className="count-label" x={center - 10} y={y + 4} textAnchor="end">{betterCount}</text>
                  <title>{`${better.gene_symbol}: protective in ${betterCount} cancers; best FDR ${formatP(better.min_protective_fdr)}; top cohort ${better.top_protective_cohort}`}</title>
                </g>
              )}
              {worse && (
                <g className="recurrence-lollipop harmful">
                  <line x1={center} x2={worseX} y1={y} y2={y} />
                  <circle cx={worseX} cy={y} r={5.5} />
                  <text className="gene-label" x={worseX + 10} y={y + 4}>{worse.gene_symbol}</text>
                  <text className="count-label" x={center + 10} y={y + 4}>{worseCount}</text>
                  <title>{`${worse.gene_symbol}: harmful in ${worseCount} cancers; best FDR ${formatP(worse.min_harmful_fdr)}; top cohort ${worse.top_harmful_cohort}`}</title>
                </g>
              )}
            </g>
          );
        })}
      </svg>
      <div className="pancancer-figure-legend">
        <span><i className="protective" /> HR &lt; 1, better prognosis</span>
        <span><i className="harmful" /> HR &gt; 1, worse prognosis</span>
      </div>
    </div>
  );
}

function ImmuneFrequencyDistribution({ recurrence }) {
  const data = (recurrence.frequency_distribution || [])
    .map((row) => ({
      cancerCount: Number(row.cancer_count || 0),
      harmful: Number(row.harmful_genes || 0),
      protective: Number(row.protective_genes || 0),
    }))
    .filter((row) => row.cancerCount > 0);
  if (!data.length) return <div className="empty-inline">No frequency distribution available.</div>;

  const width = 720;
  const height = 260;
  const plot = { left: 58, right: 24, top: 22, bottom: 50 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxX = Math.max(...data.map((row) => row.cancerCount));
  const maxY = Math.max(1, ...data.flatMap((row) => [row.harmful, row.protective]));
  const scaleX = (value) => plot.left + ((value - 1) / Math.max(1, maxX - 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / maxY) * innerHeight;
  const linePoints = (key) => data.map((row) => `${scaleX(row.cancerCount)},${scaleY(row[key])}`).join(" ");
  const xTicks = uniqueNumbers([1, 2, 4, 6, 8, 10, maxX].filter((tick) => tick <= maxX));
  const yTicks = niceTicks(maxY, 4);
  const summary = recurrence.summary || {};

  return (
    <div className="immune-frequency-wrap">
      <svg className="immune-frequency-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene rare versus recurrent distribution">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 17}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{formatInteger(Math.round(tick))}</text>
          </g>
        ))}
        <polyline className="frequency-line harmful" points={linePoints("harmful")} />
        <polyline className="frequency-line protective" points={linePoints("protective")} />
        {data.map((row) => (
          <g key={row.cancerCount}>
            <circle className="frequency-point harmful" cx={scaleX(row.cancerCount)} cy={scaleY(row.harmful)} r={4.5}>
              <title>{`${formatInteger(row.harmful)} genes harmful in ${row.cancerCount} cancer(s)`}</title>
            </circle>
            <circle className="frequency-point protective" cx={scaleX(row.cancerCount)} cy={scaleY(row.protective)} r={4.5}>
              <title>{`${formatInteger(row.protective)} genes protective in ${row.cancerCount} cancer(s)`}</title>
            </circle>
          </g>
        ))}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 4}>Number of cancer types with FDR hit</text>
        <text className="chart-axis-label y" x="14" y={plot.top + 16}>Genes</text>
      </svg>
      <div className="immune-frequency-notes">
        <span><strong>{formatInteger(summary.recurrent_harmful_genes_ge5)}</strong> harmful genes recur in 5+ cancers</span>
        <span><strong>{formatInteger(summary.recurrent_protective_genes_ge5)}</strong> protective genes recur in 5+ cancers</span>
        <span><strong>{formatInteger(summary.one_cancer_protective_genes)}</strong> protective genes appear in one cancer</span>
      </div>
    </div>
  );
}

function ImmuneMetaSpectrum({ genes }) {
  const points = genes
    .map((gene) => {
      const hr = finiteNumber(gene.meta_hr);
      const fdr = finiteNumber(gene.meta_fdr);
      if (!hr || !fdr) return null;
      return {
        gene,
        x: Math.log2(hr),
        y: -Math.log10(Math.max(fdr, 1e-300)),
        hits: finiteNumber(gene.global_fdr_hits) || 0,
        i2: finiteNumber(gene.meta_i_squared) || 0,
        direction: hr >= 1 ? "harmful" : "protective",
      };
    })
    .filter(Boolean);
  if (!points.length) return <div className="empty-inline">No immune gene summary available.</div>;

  const width = 760;
  const height = 320;
  const plot = { left: 52, right: 34, top: 20, bottom: 52 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const absX = Math.max(0.25, ...points.map((point) => Math.abs(point.x))) * 1.15;
  const yMax = Math.max(2, ...points.map((point) => point.y)) * 1.08;
  const scaleX = (value) => plot.left + ((value + absX) / (2 * absX || 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / (yMax || 1)) * innerHeight;
  const labels = points.slice(0, 9);
  const xTicks = [-0.5, -0.25, 0, 0.25, 0.5].filter((tick) => Math.abs(tick) <= absX);
  const yTicks = niceTicks(yMax, 4);

  return (
    <div className="immune-spectrum-wrap">
      <svg className="immune-spectrum-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Immune gene meta-analysis spectrum">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        <line className="chart-reference" x1={scaleX(0)} x2={scaleX(0)} y1={plot.top} y2={plot.top + innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 16}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(0)}</text>
          </g>
        ))}
        {points.map((point) => (
          <circle
            key={point.gene.gene_symbol}
            className={`immune-spectrum-dot ${point.direction}`}
            cx={scaleX(point.x)}
            cy={scaleY(point.y)}
            r={5 + Math.min(8, Math.sqrt(point.hits || 1) * 1.6)}
            opacity={0.72 + Math.min(0.24, point.i2 / 350)}
          >
            <title>{`${point.gene.gene_symbol}: meta HR ${formatCompactNumber(point.gene.meta_hr)}, meta FDR ${formatP(point.gene.meta_fdr)}, I2 ${formatPercent(point.gene.meta_i_squared)}`}</title>
          </circle>
        ))}
        {labels.map((point) => (
          <text key={`label-${point.gene.gene_symbol}`} className="chart-point-label" x={scaleX(point.x) + (point.x >= 0 ? 10 : -10)} y={scaleY(point.y) + 4} textAnchor={point.x >= 0 ? "start" : "end"}>
            {point.gene.gene_symbol}
          </text>
        ))}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 3}>log2(meta HR)</text>
        <text className="chart-axis-label y" x="14" y={plot.top + 16}>-log10(meta FDR)</text>
      </svg>
      <div className="pancancer-figure-legend">
        <span><i className="harmful" /> Higher expression worse</span>
        <span><i className="protective" /> Higher expression better</span>
      </div>
    </div>
  );
}

function ImmuneRareSignals({ recurrence }) {
  const harmful = (recurrence.rare_harmful || []).slice(0, 8);
  const protective = (recurrence.rare_protective || []).slice(0, 8);
  if (!harmful.length && !protective.length) return <div className="empty-inline">No rare signal summary available.</div>;
  return (
    <div className="immune-rare-grid">
      <div className="immune-rare-lane harmful">
        <span>Worse in one cancer</span>
        {harmful.map((row) => (
          <div key={row.gene_symbol}>
            <strong>{row.gene_symbol}</strong>
            <em>{row.top_harmful_cohort?.replace("TCGA-", "")}</em>
            <small>FDR {formatP(row.min_harmful_fdr)}</small>
          </div>
        ))}
      </div>
      <div className="immune-rare-lane protective">
        <span>Better in one cancer</span>
        {protective.map((row) => (
          <div key={row.gene_symbol}>
            <strong>{row.gene_symbol}</strong>
            <em>{row.top_protective_cohort?.replace("TCGA-", "")}</em>
            <small>FDR {formatP(row.min_protective_fdr)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

function ImmuneCohortBurden({ cohorts }) {
  const ordered = [...cohorts]
    .sort((a, b) => Number(b.global_fdr_hits || 0) - Number(a.global_fdr_hits || 0))
    .slice(0, 12);
  const maxHits = Math.max(1, ...ordered.map((cohort) => Number(cohort.global_fdr_hits || 0)));
  if (!ordered.length) return <div className="empty-inline">No cohort summary available.</div>;
  return (
    <div className="immune-burden-list">
      {ordered.map((cohort) => {
        const hits = Number(cohort.global_fdr_hits || 0);
        const harmful = Number(cohort.harmful_global_fdr_hits || 0);
        const protective = Number(cohort.protective_global_fdr_hits || 0);
        const harmfulWidth = hits ? (harmful / hits) * 100 : 0;
        const protectiveWidth = hits ? (protective / hits) * 100 : 0;
        return (
          <div key={cohort.cohort} className="immune-burden-row">
            <div>
              <strong>{cohort.cohort.replace("TCGA-", "")}</strong>
              <span>{cohort.top_gene || "..."}</span>
            </div>
            <div className="immune-burden-track" style={{ "--burden-width": `${(hits / maxHits) * 100}%` }}>
              <i className="harmful" style={{ width: `${harmfulWidth}%` }} />
              <i className="protective" style={{ width: `${protectiveWidth}%` }} />
            </div>
            <em>{formatInteger(hits)}</em>
          </div>
        );
      })}
    </div>
  );
}

function ImmuneTermList({ terms }) {
  const ordered = terms.slice(0, 10);
  const maxHits = Math.max(1, ...ordered.map((term) => Number(term.cohort_level_global_fdr_hits || 0)));
  if (!ordered.length) return <div className="empty-inline">No immune term summary available.</div>;
  return (
    <div className="immune-term-list">
      {ordered.map((term) => (
        <div key={term.term_id} className={`immune-term-row ${String(term.source || "").toLowerCase()}`}>
          <div>
            <strong>{term.term_name}</strong>
            <span>{term.source} / {formatInteger(term.panel_genes)} genes / best {term.best_gene || "..."}</span>
          </div>
          <b>{formatInteger(term.cohort_level_global_fdr_hits)}</b>
          <i style={{ width: `${(Number(term.cohort_level_global_fdr_hits || 0) / maxHits) * 100}%` }} />
        </div>
      ))}
    </div>
  );
}

function PanCancerForestPlot({ rows, metaAnalysis }) {
  const completed = rows.filter((row) => row.status === "completed" && Number.isFinite(Number(row.hazard_ratio)));
  if (!completed.length) return <div className="empty-inline">No completed Cox models available for the forest plot.</div>;
  const ordered = [...completed].sort((a, b) => Number(a.hazard_ratio) - Number(b.hazard_ratio));
  const pooled = metaAnalysis?.available ? metaAnalysis.random_effect : null;
  const width = 900;
  const rowHeight = 28;
  const pooledHeight = pooled?.hazard_ratio ? 40 : 0;
  const height = 78 + ordered.length * rowHeight + pooledHeight;
  const plot = { left: 124, right: 184, top: 28, bottom: 46 };
  const values = ordered.flatMap((row) => [row.hr_conf_low, row.hazard_ratio, row.hr_conf_high].map((value) => Number(value)).filter(Number.isFinite));
  if (pooled?.hazard_ratio) {
    values.push(...[pooled.hr_conf_low, pooled.hazard_ratio, pooled.hr_conf_high].map((value) => Number(value)).filter(Number.isFinite));
  }
  const logMin = Math.min(Math.log(0.25), ...values.map((value) => Math.log(Math.max(value, 0.001))));
  const logMax = Math.max(Math.log(4), ...values.map((value) => Math.log(Math.max(value, 0.001))));
  const scaleX = (value) => {
    const logValue = Math.log(Math.max(Number(value), 0.001));
    return plot.left + ((logValue - logMin) / (logMax - logMin || 1)) * (width - plot.left - plot.right);
  };
  const axisTicks = [0.25, 0.5, 1, 2, 4].filter((tick) => Math.log(tick) >= logMin && Math.log(tick) <= logMax);
  return (
    <div className="pancancer-forest-scroll">
      <svg className="pancancer-forest" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pan-cancer Cox forest plot">
        <line className="forest-reference" x1={scaleX(1)} x2={scaleX(1)} y1={plot.top - 8} y2={height - plot.bottom} />
        {axisTicks.map((tick) => (
          <g key={tick} className="forest-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={height - plot.bottom} y2={height - plot.bottom + 5} />
            <text x={scaleX(tick)} y={height - 8}>{tick}</text>
          </g>
        ))}
        <text className="forest-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 24}>Hazard ratio per +1 SD expression</text>
        {ordered.map((row, index) => {
          const y = plot.top + index * rowHeight;
          const effectClass = row.effect_category || "neutral";
          return (
            <g key={row.cohort} className={`forest-row ${effectClass}`}>
              <rect className="forest-row-band" x="0" y={y - 13} width={width} height={rowHeight} />
              <text x="8" y={y + 5}>{row.cohort}</text>
              <line x1={scaleX(row.hr_conf_low)} x2={scaleX(row.hr_conf_high)} y1={y} y2={y} />
              <circle cx={scaleX(row.hazard_ratio)} cy={y} r={row.significant ? 5 : 4} />
              <text className="forest-hr-label" x={width - plot.right + 18} y={y + 5}>{formatHrValues(row)}</text>
              <title>{`${row.cohort}: ${panCancerRowTooltip(row)}`}</title>
            </g>
          );
        })}
        {pooled?.hazard_ratio && (
          <g className="forest-pooled-row">
            <line x1="0" x2={width} y1={plot.top + ordered.length * rowHeight + 4} y2={plot.top + ordered.length * rowHeight + 4} />
            <text x="8" y={plot.top + ordered.length * rowHeight + 30}>Random effects</text>
            <polygon points={forestDiamondPoints(scaleX, pooled, plot.top + ordered.length * rowHeight + 25)} />
            <text x={width - plot.right + 18} y={plot.top + ordered.length * rowHeight + 30}>{formatHrValues(pooled)}</text>
            <title>{`Random-effects pooled HR: ${formatHrValues(pooled)}`}</title>
          </g>
        )}
      </svg>
    </div>
  );
}

function PanCancerEvidenceLandscape({ rows, fdrThreshold }) {
  const completed = pancancerCompletedRows(rows)
    .map((row) => {
      const logHr = finiteNumber(row.log_hr) ?? Math.log(finiteNumber(row.hazard_ratio) || 1);
      const fdr = finiteNumber(row.fdr);
      const pValue = finiteNumber(row.p_value);
      const evidenceValue = fdr ?? pValue;
      return {
        row,
        x: logHr / Math.log(2),
        y: evidenceValue ? -Math.log10(Math.max(evidenceValue, 1e-300)) : 0,
        evidenceValue,
        events: finiteNumber(row.n_events) || 0,
      };
    })
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (!completed.length) return <div className="empty-inline">No completed Cox models available for the evidence landscape.</div>;

  const width = 820;
  const height = 360;
  const plot = { left: 58, right: 34, top: 24, bottom: 58 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const fdrLine = fdrThreshold ? -Math.log10(Math.max(Number(fdrThreshold), 1e-12)) : null;
  const absX = Math.max(0.75, ...completed.map((point) => Math.abs(point.x))) * 1.08;
  const yMax = Math.max(1.4, fdrLine || 0, ...completed.map((point) => point.y)) * 1.08;
  const scaleX = (value) => plot.left + ((value + absX) / (2 * absX || 1)) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / (yMax || 1)) * innerHeight;
  const xTicks = [-2, -1, -0.5, 0, 0.5, 1, 2].filter((tick) => Math.abs(tick) <= absX);
  const yTicks = uniqueNumbers([0, fdrLine, Math.ceil(yMax / 2), Math.floor(yMax)].filter((value) => value !== null && value <= yMax));
  const labeled = evidenceLabels(completed);

  return (
    <div className="pancancer-chart-wrap">
      <svg className="pancancer-landscape" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pan-cancer evidence landscape">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        <line className="chart-reference" x1={scaleX(0)} x2={scaleX(0)} y1={plot.top} y2={plot.top + innerHeight} />
        {fdrLine !== null && (
          <g className="chart-threshold">
            <line x1={plot.left} x2={width - plot.right} y1={scaleY(fdrLine)} y2={scaleY(fdrLine)} />
            <text x={width - plot.right - 4} y={scaleY(fdrLine) - 7}>FDR {Number(fdrThreshold).toFixed(2)}</text>
          </g>
        )}
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 18}>{tick}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(tick < 1 ? 1 : 0)}</text>
          </g>
        ))}
        {completed.map((point) => {
          const radius = 4 + Math.min(5, Math.sqrt(point.events) / 7);
          return (
            <circle
              key={point.row.cohort}
              className={`landscape-dot ${point.row.effect_category || point.row.direction || "neutral"} ${point.row.significant ? "significant" : ""}`}
              cx={scaleX(point.x)}
              cy={scaleY(point.y)}
              r={radius}
            >
              <title>{`${point.row.cohort}: log2(HR) ${point.x.toFixed(2)}, FDR ${formatP(point.row.fdr)}, events ${formatInteger(point.row.n_events)}`}</title>
            </circle>
          );
        })}
        {labeled.map((point) => {
          const anchor = point.x >= 0 ? "start" : "end";
          const dx = point.x >= 0 ? 9 : -9;
          return (
            <text key={`label-${point.row.cohort}`} className="chart-point-label" x={scaleX(point.x) + dx} y={scaleY(point.y) + 4} textAnchor={anchor}>
              {point.row.cohort.replace("TCGA-", "")}
            </text>
          );
        })}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 4}>log2(HR): lower to higher hazard</text>
        <text className="chart-axis-label y" x="16" y={plot.top + 18}>-log10(FDR)</text>
      </svg>
      <PanCancerFigureLegend />
    </div>
  );
}

function PanCancerPowerPrecision({ rows }) {
  const points = pancancerCompletedRows(rows)
    .map((row) => ({
      row,
      events: finiteNumber(row.n_events),
      patients: finiteNumber(row.n_patients),
      precision: finiteNumber(row.standard_error) ? 1 / finiteNumber(row.standard_error) : null,
    }))
    .filter((point) => point.events !== null && point.patients !== null && point.precision !== null);
  if (!points.length) return <div className="empty-inline">No completed Cox models available for the power and precision map.</div>;

  const width = 820;
  const height = 350;
  const plot = { left: 60, right: 34, top: 24, bottom: 58 };
  const innerWidth = width - plot.left - plot.right;
  const innerHeight = height - plot.top - plot.bottom;
  const maxEvents = Math.max(10, ...points.map((point) => point.events)) * 1.05;
  const maxPrecision = Math.max(1, ...points.map((point) => point.precision)) * 1.08;
  const scaleX = (value) => plot.left + (value / maxEvents) * innerWidth;
  const scaleY = (value) => plot.top + innerHeight - (value / maxPrecision) * innerHeight;
  const xTicks = niceTicks(maxEvents, 4);
  const yTicks = niceTicks(maxPrecision, 4);
  const labeled = powerPrecisionLabels(points);

  return (
    <div className="pancancer-chart-wrap">
      <svg className="pancancer-power" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Pan-cancer power and precision map">
        <rect className="chart-frame" x={plot.left} y={plot.top} width={innerWidth} height={innerHeight} />
        {xTicks.map((tick) => (
          <g key={`x-${tick}`} className="chart-axis-tick">
            <line x1={scaleX(tick)} x2={scaleX(tick)} y1={plot.top + innerHeight} y2={plot.top + innerHeight + 5} />
            <text x={scaleX(tick)} y={height - 18}>{formatInteger(Math.round(tick))}</text>
          </g>
        ))}
        {yTicks.map((tick) => (
          <g key={`y-${tick}`} className="chart-axis-tick">
            <line x1={plot.left - 5} x2={plot.left} y1={scaleY(tick)} y2={scaleY(tick)} />
            <text className="chart-y-tick-label" x={plot.left - 10} y={scaleY(tick) + 4}>{tick.toFixed(tick >= 10 ? 0 : 1)}</text>
          </g>
        ))}
        {points.map((point) => {
          const radius = 4 + Math.min(8, Math.sqrt(point.patients) / 9);
          return (
            <circle
              key={point.row.cohort}
              className={`power-dot ${point.row.effect_category || point.row.direction || "neutral"} ${point.row.significant ? "significant" : ""}`}
              cx={scaleX(point.events)}
              cy={scaleY(point.precision)}
              r={radius}
            >
              <title>{`${point.row.cohort}: ${formatInteger(point.events)} events, ${formatInteger(point.patients)} patients, Cox SE ${Number(point.row.standard_error).toFixed(3)}`}</title>
            </circle>
          );
        })}
        {labeled.map((point) => {
          const anchor = point.events > maxEvents * 0.78 ? "end" : "start";
          const dx = anchor === "start" ? 9 : -9;
          return (
            <text key={`label-${point.row.cohort}`} className="chart-point-label" x={scaleX(point.events) + dx} y={scaleY(point.precision) + 4} textAnchor={anchor}>
              {point.row.cohort.replace("TCGA-", "")}
            </text>
          );
        })}
        <text className="chart-axis-label" x={(plot.left + width - plot.right) / 2} y={height - 4}>Survival events</text>
        <text className="chart-axis-label y" x="14" y={plot.top + 18}>Precision: 1 / Cox SE</text>
      </svg>
      <PanCancerFigureLegend />
    </div>
  );
}

function PanCancerFigureLegend() {
  return (
    <div className="pancancer-figure-legend" aria-label="Pan-cancer figure legend">
      <span><i className="harmful" /> FDR hit, HR &gt; 1</span>
      <span><i className="protective" /> FDR hit, HR &lt; 1</span>
      <span><i className="neutral" /> Not FDR-significant</span>
    </div>
  );
}

function PanCancerConcordanceMap({ rows, summary, reference, fdrThreshold }) {
  const [filter, setFilter] = useState("all");
  const [sortMode, setSortMode] = useState("evidence");
  const [query, setQuery] = useState("");
  const [selectedCohort, setSelectedCohort] = useState(reference?.cohort || "");
  const enriched = useMemo(() => rows.map((row) => enrichConcordanceRow(row)), [rows]);
  const counts = useMemo(() => concordanceFilterCounts(enriched), [enriched]);
  const referenceRow = enriched.find((row) => row.cohort === reference?.cohort);
  const filtered = useMemo(
    () => sortConcordanceRows(filterConcordanceRows(enriched, filter, query), sortMode),
    [enriched, filter, query, sortMode],
  );
  const selected =
    enriched.find((row) => row.cohort === selectedCohort) ||
    filtered[0] ||
    referenceRow ||
    enriched.find((row) => row.status === "completed") ||
    enriched[0];

  if (!rows.length) return <div className="empty-inline">No cohorts to display.</div>;

  return (
    <div className="concordance-explorer">
      <div className="concordance-toolbar">
        <div className="concordance-filter-set" aria-label="Concordance filters">
          {[
            ["all", "All", counts.all],
            ["hits", "FDR hits", counts.hits],
            ["same", "Same direction", counts.same],
            ["opposite", "Opposite", counts.opposite],
            ["qc", "QC review", counts.qc],
          ].map(([value, label, count]) => (
            <button key={value} type="button" className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>
              <span>{label}</span>
              <strong>{formatInteger(count)}</strong>
            </button>
          ))}
        </div>
        <label className="concordance-search">
          <Search size={15} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find cohort or site" />
        </label>
        <label className="concordance-sort">
          <span>Order</span>
          <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
            <option value="evidence">Evidence first</option>
            <option value="effect">Effect magnitude</option>
            <option value="precision">Precision</option>
            <option value="events">Events</option>
            <option value="cohort">Cohort code</option>
          </select>
        </label>
      </div>

      <div className="concordance-summary-strip">
        <div>
          <span>Index signal</span>
          <strong>{referenceRow ? `${referenceRow.shortCode} / ${formatDirectionToken(referenceRow)}` : "Unavailable"}</strong>
          <small>{referenceRow?.status === "completed" ? formatHrValues(referenceRow) : "No completed index model"}</small>
        </div>
        <div>
          <span>FDR threshold</span>
          <strong>{formatP(fdrThreshold)}</strong>
          <small>{formatInteger(summary?.significant || 0)} cohort-level hits</small>
        </div>
        <div>
          <span>Same vs opposite</span>
          <strong>{formatInteger(counts.same)} / {formatInteger(counts.opposite)}</strong>
          <ConcordanceBalance counts={counts} />
        </div>
        <div>
          <span>QC review</span>
          <strong>{formatInteger(counts.qc)}</strong>
          <small>Skipped, failed or PH flag</small>
        </div>
      </div>
      <div className="concordance-glyph-key" aria-label="Concordance glyph legend">
        <span><i className="key-axis" /> HR direction</span>
        <span><i className="key-ring" /> FDR evidence</span>
        <span><i className="key-halo" /> Event fraction</span>
        <span><i className="key-hit" /> FDR hit</span>
        <span><i className="key-qc" /> QC flag</span>
      </div>

      <div className="concordance-workspace">
        <div className="concordance-node-grid" role="list" aria-label="Interactive pan-cancer concordance cohorts">
          {filtered.map((row) => (
            <button
              key={row.cohort}
              type="button"
              role="listitem"
              className={`concordance-glyph-node ${row.effectClass} ${row.concordanceClass} ${row.status !== "completed" ? "not-completed" : ""} ${row.significant ? "fdr-hit" : ""} ${row.qcFlag ? "qc-flag" : ""} ${selected?.cohort === row.cohort ? "selected" : ""}`}
              onClick={() => setSelectedCohort(row.cohort)}
              title={`${row.cohort}: ${panCancerRowTooltip(row)}`}
              style={{
                "--glyph-x": `${row.glyphPosition}%`,
                "--glyph-size": `${row.glyphSize}px`,
                "--evidence-deg": `${row.evidenceDegrees}deg`,
                "--event-rate": row.eventRateRatio,
              }}
            >
              <span className="glyph-stage" aria-hidden="true">
                <span className="glyph-axis" />
                <span className="glyph-event-halo" />
                <span className="glyph-evidence-ring" />
                <span className="glyph-dot" />
                {row.concordance === "reference" && <span className="glyph-reference-mark" />}
                {row.significant && <span className="glyph-hit-mark" />}
                {row.qcFlag && <span className="glyph-qc-mark" />}
              </span>
              <span className="glyph-copy">
                <span className="glyph-topline">
                  <strong>{row.shortCode}</strong>
                  <i>{row.status === "completed" ? formatDirectionToken(row) : row.status}</i>
                </span>
                <span className="glyph-values">
                  <b>{row.status === "completed" ? `HR ${formatCompactNumber(row.hazardRatio)}` : row.code || "Not evaluable"}</b>
                  <em>FDR {formatP(row.fdr)}</em>
                </span>
                <span className="glyph-context">{formatInteger(row.nEvents)} / {formatInteger(row.nPatients)} events</span>
              </span>
            </button>
          ))}
          {!filtered.length && <div className="empty-inline">No cohorts match the active filter.</div>}
        </div>
        <PanCancerConcordanceDetail row={selected} referenceRow={referenceRow} fdrThreshold={fdrThreshold} />
      </div>
    </div>
  );
}

function ConcordanceBalance({ counts }) {
  const total = Math.max((counts.same || 0) + (counts.opposite || 0), 1);
  return (
    <span className="concordance-balance" aria-hidden="true">
      <i className="same" style={{ width: `${((counts.same || 0) / total) * 100}%` }} />
      <i className="opposite" style={{ width: `${((counts.opposite || 0) / total) * 100}%` }} />
    </span>
  );
}

function PanCancerConcordanceDetail({ row, referenceRow, fdrThreshold }) {
  if (!row) return <div className="concordance-detail empty-inline">Select a cohort to inspect concordance evidence.</div>;
  const interpretation = concordanceInterpretation(row, referenceRow, fdrThreshold);
  return (
    <aside className="concordance-detail" aria-label={`${row.cohort} concordance details`}>
      <div className="concordance-detail-header">
        <div>
          <p className="eyebrow">{row.cohort}</p>
          <h3>{getCohortName(row.cohort)}</h3>
        </div>
        <span className={`detail-badge ${row.effectClass}`}>{row.status === "completed" ? formatEffectLabel(row.effect_category) : row.status}</span>
      </div>

      <div className="concordance-detail-grid">
        <div><span>Concordance</span><strong>{formatConcordance(row.concordance)}</strong></div>
        <div><span>Endpoint</span><strong>{row.endpoint || "..."}</strong><small>{formatSourceLabel(row.endpoint_source)}</small></div>
        <div><span>HR per SD</span><strong>{row.status === "completed" ? formatHrValues(row) : "..."}</strong></div>
        <div><span>Evidence</span><strong>p {formatP(row.p_value)} / FDR {formatP(row.fdr)}</strong></div>
        <div><span>Information</span><strong>{formatInteger(row.nEvents)} events</strong><small>{formatInteger(row.nPatients)} patients, {formatPercent((row.eventRate || 0) * 100)} event rate</small></div>
        <div><span>Model QC</span><strong>{row.phPValue === null ? "PH not available" : `PH p ${formatP(row.phPValue)}`}</strong><small>{row.standardError ? `SE ${row.standardError.toFixed(3)}, precision ${formatCompactNumber(row.precision)}` : "SE unavailable"}</small></div>
      </div>

      <div className="concordance-interpretation">
        <strong>{interpretation.title}</strong>
        <span>{interpretation.body}</span>
      </div>

      {!!row.warnings?.length && (
        <div className="concordance-warning-list">
          {row.warnings.slice(0, 3).map((warning) => <span key={warning}>{warning}</span>)}
        </div>
      )}
    </aside>
  );
}

function PanCancerHeatmap({ rows }) {
  if (!rows.length) return <div className="empty-inline">No cohorts to display.</div>;
  return (
    <div className="pancancer-heatmap">
      {rows.map((row) => (
        <div key={row.cohort} className={`pancancer-tile ${row.effect_category || row.status}`} title={`${row.cohort}: ${panCancerRowTooltip(row)}`}>
          <strong>{row.cohort.replace("TCGA-", "")}</strong>
          <span>{shortEffectLabel(row)}</span>
        </div>
      ))}
    </div>
  );
}

function PanCancerSummaryCounts({ summary }) {
  const effects = summary.effect_counts || {};
  const concordance = summary.concordance_counts || {};
  return (
    <div className="pancancer-counts">
      <div><span>Harmful FDR hits</span><strong>{formatInteger(effects.harmful || 0)}</strong></div>
      <div><span>Protective FDR hits</span><strong>{formatInteger(effects.protective || 0)}</strong></div>
      <div><span>Same direction</span><strong>{formatInteger((concordance.same_direction_significant || 0) + (concordance.same_direction_not_significant || 0))}</strong></div>
      <div><span>Opposite direction</span><strong>{formatInteger((concordance.opposite_direction_significant || 0) + (concordance.opposite_direction_not_significant || 0))}</strong></div>
    </div>
  );
}

function PanCancerTable({ rows }) {
  const ordered = [...rows].sort((a, b) => {
    const aFdr = Number.isFinite(Number(a.fdr)) ? Number(a.fdr) : Number.POSITIVE_INFINITY;
    const bFdr = Number.isFinite(Number(b.fdr)) ? Number(b.fdr) : Number.POSITIVE_INFINITY;
    return aFdr - bFdr || String(a.cohort).localeCompare(String(b.cohort));
  });
  return (
    <div className="table-scroll pancancer-table-scroll">
      <table>
        <thead>
          <tr>
            <th>Cohort</th>
            <th>Endpoint</th>
            <th>Patients</th>
            <th>Events</th>
            <th>HR per SD</th>
            <th>p</th>
            <th>FDR</th>
            <th>Concordance</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((row) => (
            <tr key={row.cohort}>
              <td><strong>{row.cohort}</strong><br /><span>{getCohortName(row.cohort)}</span></td>
              <td>{row.endpoint || "..."}<br /><span>{formatSourceLabel(row.endpoint_source)}</span></td>
              <td>{formatInteger(row.n_patients)}</td>
              <td>{formatInteger(row.n_events)}</td>
              <td>{row.status === "completed" ? formatHrValues(row) : "..."}</td>
              <td>{formatP(row.p_value)}</td>
              <td>{formatP(row.fdr)}</td>
              <td>{formatConcordance(row.concordance)}</td>
              <td>{row.status === "completed" ? formatEffectLabel(row.effect_category) : row.reason || row.code}</td>
            </tr>
          ))}
        </tbody>
      </table>
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

function PreviewState({ cohort, analysisKind, signatureMethod, geneCount, endpoint, expressionScale, cutpoint, activeFilterCount }) {
  const isSingleMode = signatureMethod === "single";
  const isCombinedMode = analysisKind === "combined_signatures";
  return (
    <div className="preview-state">
      <div className="preview-header">
        <CheckCircle2 size={28} />
        <div>
          <p className="eyebrow">Ready to run</p>
          <h2>
            {geneCount
              ? isCombinedMode
                ? "Combined two-signature survival plot"
                : isSingleMode
                ? `${geneCount} separate survival plot${geneCount === 1 ? "" : "s"}`
                : "Combined signature survival plot"
              : isCombinedMode ? "Select genes for both signatures" : "Select one or more genes"}
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
        <PreviewItem label="Gene mode" value={isCombinedMode ? "Two signatures" : isSingleMode ? "Separate plots" : "Combined signature"} />
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

function LoadingState({ cohort, gene, analysisKind, signatureMethod, geneCount, completedCount, endpoint, expressionScale }) {
  const isSingleMode = signatureMethod === "single";
  const isCombinedMode = analysisKind === "combined_signatures";
  return (
    <div className="loading-state">
      <Loader2 className="spin" size={42} />
      <div>
        <p className="eyebrow">Running R survival analysis</p>
        <h2>
          {getCohortName(cohort)} / {isCombinedMode ? gene : isSingleMode ? `${completedCount} of ${geneCount} genes completed` : gene.trim().toUpperCase()}
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
  const combinedSignature = metrics.combined_signature;
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
          <DownloadLink href={downloads.cox_png} icon={<BarChart3 size={16} />} label="Cox PNG" onDownload={onDownload} />
          <DownloadLink href={downloads.cox_svg} icon={<ArrowDownToLine size={16} />} label="Cox SVG" onDownload={onDownload} />
          <DownloadLink href={downloads.json} icon={<FileText size={16} />} label="Metrics JSON" onDownload={onDownload} />
          <DownloadLink href={downloads.txt} icon={<FileText size={16} />} label="Method TXT" onDownload={onDownload} />
          <DownloadLink href={downloads.audit_json} icon={<ClipboardList size={16} />} label="Audit JSON" onDownload={onDownload} />
          <DownloadLink href={downloads.audit_html} icon={<ClipboardList size={16} />} label="Audit HTML" onDownload={onDownload} />
          <DownloadLink href={downloads.zip} icon={<Archive size={16} />} label="ZIP" onDownload={onDownload} />
        </div>
      </div>

      <div className="metric-strip">
        <Metric label="Patients" value={metrics.n_patients} />
        <Metric label="Events" value={metrics.n_events} />
        <Metric label="Log-rank p" value={formatP(metrics.logrank_p_value)} />
        <Metric label="Hazard ratio" value={formatHr(metrics)} />
        <Metric label="RMST delta" value={formatRmstDelta(metrics.rmst)} />
      </div>

      <div className="result-details">
        <GroupTable metrics={metrics} />
        <CutpointSummary details={metrics.cutpoint_details} />
      </div>

      <CoxModelTable models={metrics.cox_models} />
      <RmstTable rmst={metrics.rmst} />
      <AuditSummary audit={metrics.audit_report} />

      {combinedSignature && <CombinedSignatureSummary combined={combinedSignature} />}
      <SignatureInteractionCoxTable models={metrics.signature_interaction_cox_models} />

      {combinedSignature ? (
        <div className="result-details">
          <ExpressionDistribution
            title={`${combinedSignature.signature_a?.name || "Signature A"} score distribution`}
            distribution={metrics.expression_distribution_a}
            cutpointDetails={signatureCutpointDetails(metrics.cutpoint_details, "signature_a")}
          />
          <ExpressionDistribution
            title={`${combinedSignature.signature_b?.name || "Signature B"} score distribution`}
            distribution={metrics.expression_distribution_b}
            cutpointDetails={signatureCutpointDetails(metrics.cutpoint_details, "signature_b")}
          />
        </div>
      ) : (
        <div className="result-details">
          <ExpressionDistribution distribution={metrics.expression_distribution} cutpointDetails={metrics.cutpoint_details} />
          <QualitySummary quality={metrics.quality} />
        </div>
      )}

      {combinedSignature && (
        <div className="result-details single">
          <QualitySummary quality={metrics.quality} />
        </div>
      )}

      <img className="km-plot" src={apiUrl(downloads.png)} alt="Kaplan-Meier plot" />
      {downloads.cox_png && (
        <>
          <div className="plot-download-row">
            <span>Cox forest plot</span>
            <div className="download-row">
              <DownloadLink href={downloads.cox_png} icon={<Image size={16} />} label="PNG" onDownload={onDownload} />
              <DownloadLink href={downloads.cox_svg} icon={<ArrowDownToLine size={16} />} label="SVG" onDownload={onDownload} />
            </div>
          </div>
          <img className="cox-forest-plot" src={apiUrl(downloads.cox_png)} alt="Cox model forest plot" />
        </>
      )}

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

function CoxModelTable({ models }) {
  if (!models?.length) return null;
  return (
    <div className="detail-section cox-model-table">
      <h3>Cox models</h3>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Covariates</th>
            <th>Patients</th>
            <th>Events</th>
            <th>HR</th>
            <th>p</th>
            <th>PH global p</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.model || model.label}>
              <td>{model.label || formatLabel(model.model)}</td>
              <td>{formatCoxCovariates(model.covariates)}</td>
              <td>{formatInteger(model.n_patients)}</td>
              <td>{formatInteger(model.n_events)}</td>
              <td>{model.status === "completed" ? formatHrValues(model) : "..."}</td>
              <td>{model.status === "completed" ? formatP(model.p_value) : "..."}</td>
              <td>{model.status === "completed" ? formatP(model.ph_global_p_value) : "..."}</td>
              <td>{model.status === "completed" ? "Completed" : model.reason || formatLabel(model.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="method-note">
        Adjusted models use complete cases for the listed covariates; stage and grade are fitted as categorical terms.
      </div>
    </div>
  );
}

function RmstTable({ rmst }) {
  if (!rmst) return null;
  if (rmst.status === "skipped" && String(rmst.reason || "").includes("two expression groups")) {
    return null;
  }
  const completed = rmst.status === "completed";
  const groups = Object.entries(rmst.groups || {});
  return (
    <div className="detail-section rmst-table">
      <h3>Restricted mean survival time</h3>
      {completed ? (
        <>
          <div className="rmst-summary">
            <div>
              <span>Tau</span>
              <strong>{formatDays(rmst.tau_days)}</strong>
            </div>
            <div>
              <span>Comparison</span>
              <strong>{rmst.comparison_group} vs {rmst.reference_group}</strong>
            </div>
            <div>
              <span>RMST delta</span>
              <strong>{formatRmstDelta(rmst)}</strong>
            </div>
            <div>
              <span>RMST p</span>
              <strong>{formatP(rmst.difference?.p_value)}</strong>
            </div>
          </div>
          <table>
            <thead>
              <tr>
                <th>Group</th>
                <th>RMST days</th>
                <th>95% CI</th>
              </tr>
            </thead>
            <tbody>
              {groups.map(([group, item]) => (
                <tr key={group}>
                  <td>{group}</td>
                  <td>{formatDays(item?.rmst_days)}</td>
                  <td>{formatRmstCi(item)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="method-note">
            Tau is set to the smaller maximum follow-up time across the two expression groups.
          </div>
        </>
      ) : (
        <div className="method-note">RMST was not estimated: {rmst.reason || formatLabel(rmst.status)}.</div>
      )}
    </div>
  );
}

function SignatureInteractionCoxTable({ models }) {
  if (!models?.length) return null;
  return (
    <div className="detail-section interaction-cox-table">
      <h3>Two-signature interaction Cox</h3>
      <table>
        <thead>
          <tr>
            <th>Model</th>
            <th>Covariates</th>
            <th>Patients</th>
            <th>Events</th>
            <th>Signature A HR</th>
            <th>Signature B HR</th>
            <th>Interaction HR</th>
            <th>Interaction p</th>
            <th>PH global p</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => {
            const terms = Object.fromEntries((model.terms || []).map((term) => [term.term, term]));
            const interaction = model.interaction_term || terms["score_a_z:score_b_z"];
            return (
              <tr key={model.model || model.label}>
                <td>{model.label || formatLabel(model.model)}</td>
                <td>{formatCoxCovariates(model.covariates)}</td>
                <td>{formatInteger(model.n_patients)}</td>
                <td>{formatInteger(model.n_events)}</td>
                <td>{model.status === "completed" ? formatHrValues(terms.score_a_z) : "..."}</td>
                <td>{model.status === "completed" ? formatHrValues(terms.score_b_z) : "..."}</td>
                <td>{model.status === "completed" ? formatHrValues(interaction) : "..."}</td>
                <td>{model.status === "completed" ? formatP(interaction?.p_value) : "..."}</td>
                <td>{model.status === "completed" ? formatP(model.ph_global_p_value) : "..."}</td>
                <td>{model.status === "completed" ? "Completed" : model.reason || formatLabel(model.status)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="method-note">
        Continuous signature scores are z-scored within the analyzed patients; the interaction term tests whether the effect of one signature changes as the other signature increases.
      </div>
    </div>
  );
}

function AuditSummary({ audit }) {
  if (!audit?.reproducibility_hash) return null;
  return (
    <div className="detail-section audit-summary">
      <h3>Reproducibility audit</h3>
      <dl>
        <div>
          <dt>Schema</dt>
          <dd>{audit.schema_version || "..."}</dd>
        </div>
        <div>
          <dt>Generated</dt>
          <dd>{formatDateTime(audit.generated_at)}</dd>
        </div>
        <div>
          <dt>Analysis hash</dt>
          <dd><code>{audit.reproducibility_hash}</code></dd>
        </div>
        <div>
          <dt>Patient records hash</dt>
          <dd><code>{audit.patient_records_sha256 || "..."}</code></dd>
        </div>
      </dl>
      <div className="method-note">
        The audit report captures parameters, endpoint source, sample selection, patient records, Cox/QC outputs, software versions and artifact checksums.
      </div>
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

function CombinedSignatureSummary({ combined }) {
  const signatures = [
    ["Signature A", combined.signature_a],
    ["Signature B", combined.signature_b],
  ];
  return (
    <div className="detail-section combined-signature-summary">
      <h3>Combined signatures</h3>
      <table>
        <thead>
          <tr>
            <th>Signature</th>
            <th>Score method</th>
            <th>Genes</th>
          </tr>
        </thead>
        <tbody>
          {signatures.map(([fallback, signature]) => (
            <tr key={fallback}>
              <td>
                <strong>{signature?.name || fallback}</strong>
                <br />
                <span>{signature?.label || "..."}</span>
              </td>
              <td>{formatLabel(signature?.method || "...")}</td>
              <td>{signatureGenesLabel(signature?.genes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="method-note">
        {combined.method === "tertiles"
          ? "Each signature was split into Low, Mid and High before crossing labels."
          : "Each signature was split into Low and High before crossing labels."}
      </div>
    </div>
  );
}

function signatureGenesLabel(genes) {
  if (!genes?.length) return "...";
  return genes
    .map((gene) => {
      const symbol = gene.resolved_symbol || gene.query;
      return gene.weight !== undefined && Number(gene.weight) !== 1 ? `${symbol}:${gene.weight}` : symbol;
    })
    .join(", ");
}

function GroupTable({ metrics }) {
  const groups = Object.keys(metrics.group_counts || {});
  if (!groups.length) return null;
  const notReachedGroups = groups.filter((group) => isMedianNotReached(metrics.median_survival_days?.[group]));
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
              <td>{formatMedianSurvivalDays(metrics.median_survival_days?.[group])}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!!notReachedGroups.length && (
        <div className="method-note">
          Median survival is marked as not reached when the Kaplan-Meier curve stays above 50% survival for that group.
        </div>
      )}
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

function ExpressionDistribution({ distribution, cutpointDetails, title = "Expression distribution before cutpoint" }) {
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
      <h3>{title}</h3>
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

function signatureCutpointDetails(details, prefix) {
  if (!details || !prefix) return null;
  const scoped = {};
  [
    "threshold",
    "lower_tertile",
    "upper_tertile",
    "lower_quartile",
    "upper_quartile",
  ].forEach((key) => {
    const value = details[`${prefix}_${key}`];
    if (value !== undefined && value !== null) {
      scoped[key] = value;
    }
  });
  return Object.keys(scoped).length ? scoped : null;
}

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function pancancerCompletedRows(rows) {
  return (rows || []).filter((row) => row.status === "completed" && finiteNumber(row.hazard_ratio) !== null);
}

function forestDiamondPoints(scaleX, row, y) {
  const low = finiteNumber(row.hr_conf_low);
  const mid = finiteNumber(row.hazard_ratio);
  const high = finiteNumber(row.hr_conf_high);
  if (low === null || mid === null || high === null) return "";
  return `${scaleX(low)},${y} ${scaleX(mid)},${y - 8} ${scaleX(high)},${y} ${scaleX(mid)},${y + 8}`;
}

function evidenceLabels(points) {
  const significant = points
    .filter((point) => point.row.significant)
    .sort((a, b) => b.y - a.y)
    .slice(0, 8);
  if (significant.length) return significant;
  return [...points].sort((a, b) => b.y - a.y).slice(0, 3);
}

function powerPrecisionLabels(points) {
  const significant = points
    .filter((point) => point.row.significant)
    .sort((a, b) => b.precision - a.precision)
    .slice(0, 8);
  if (significant.length) return significant;
  return [...points].sort((a, b) => b.events - a.events).slice(0, 3);
}

function niceTicks(maxValue, count = 4) {
  const number = Number(maxValue);
  if (!Number.isFinite(number) || number <= 0) return [0];
  const rawStep = number / Math.max(count, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const step =
    residual > 5
      ? 10 * magnitude
      : residual > 2
        ? 5 * magnitude
        : residual > 1
          ? 2 * magnitude
          : magnitude;
  const ticks = [];
  for (let tick = 0; tick <= number + step * 0.5; tick += step) {
    ticks.push(Number(tick.toFixed(6)));
  }
  return uniqueNumbers(ticks);
}

function enrichConcordanceRow(row) {
  const hazardRatio = finiteNumber(row.hazard_ratio);
  const logHr = finiteNumber(row.log_hr) ?? (hazardRatio ? Math.log(hazardRatio) : null);
  const fdr = finiteNumber(row.fdr);
  const pValue = finiteNumber(row.p_value);
  const evidenceValue = fdr ?? pValue;
  const evidenceScore = evidenceValue ? -Math.log10(Math.max(evidenceValue, 1e-300)) : 0;
  const nPatients = finiteNumber(row.n_patients);
  const nEvents = finiteNumber(row.n_events);
  const standardError = finiteNumber(row.standard_error);
  const precision = standardError ? 1 / standardError : null;
  const phPValue = finiteNumber(row.ph_p_value);
  const eventRate = nPatients ? nEvents / nPatients : null;
  const direction = row.direction || (hazardRatio > 1 ? "harmful" : hazardRatio < 1 ? "protective" : "neutral");
  const glyphPosition = logHr === null ? 50 : 50 + Math.max(-1, Math.min(1, logHr / Math.log(4))) * 42;
  const glyphSize = 12 + Math.min(12, Math.sqrt(Math.max(nEvents || 0, 0)) / 2.6);
  const qcFlag = row.status !== "completed" || (phPValue !== null && phPValue < 0.05);
  return {
    ...row,
    hazardRatio,
    logHr,
    log2Hr: logHr === null ? null : logHr / Math.log(2),
    fdr,
    pValue,
    evidenceScore,
    evidenceRatio: Math.min(1, evidenceScore / 3),
    evidenceDegrees: Math.min(1, evidenceScore / 3) * 360,
    nPatients,
    nEvents,
    standardError,
    precision,
    phPValue,
    qcFlag,
    eventRate,
    eventRateRatio: Math.min(1, eventRate || 0),
    glyphPosition,
    glyphSize,
    direction,
    shortCode: String(row.cohort || "").replace("TCGA-", ""),
    effectClass: row.status === "completed" ? row.effect_category || direction || "neutral" : "not_evaluable",
    concordanceClass: row.concordance || "not_evaluable",
  };
}

function concordanceFilterCounts(rows) {
  return {
    all: rows.length,
    hits: rows.filter((row) => row.significant).length,
    same: rows.filter((row) => row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction")).length,
    opposite: rows.filter((row) => String(row.concordance || "").startsWith("opposite_direction")).length,
    qc: rows.filter((row) => row.status !== "completed" || (row.phPValue !== null && row.phPValue < 0.05)).length,
  };
}

function filterConcordanceRows(rows, filter, query) {
  const normalizedQuery = String(query || "").trim().toLowerCase();
  return rows.filter((row) => {
    const matchesFilter =
      filter === "hits"
        ? row.significant
        : filter === "same"
          ? row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction")
          : filter === "opposite"
            ? String(row.concordance || "").startsWith("opposite_direction")
            : filter === "qc"
              ? row.status !== "completed" || (row.phPValue !== null && row.phPValue < 0.05)
              : true;
    if (!matchesFilter) return false;
    if (!normalizedQuery) return true;
    return [row.cohort, row.shortCode, getCohortName(row.cohort), row.primary_site, row.endpoint, row.endpoint_source]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(normalizedQuery));
  });
}

function sortConcordanceRows(rows, sortMode) {
  const sorted = [...rows];
  const missingLast = (value) => (value === null || value === undefined ? Number.NEGATIVE_INFINITY : value);
  if (sortMode === "effect") {
    return sorted.sort((a, b) => Math.abs(missingLast(b.log2Hr)) - Math.abs(missingLast(a.log2Hr)) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "precision") {
    return sorted.sort((a, b) => missingLast(b.precision) - missingLast(a.precision) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "events") {
    return sorted.sort((a, b) => missingLast(b.nEvents) - missingLast(a.nEvents) || String(a.cohort).localeCompare(String(b.cohort)));
  }
  if (sortMode === "cohort") {
    return sorted.sort((a, b) => String(a.cohort).localeCompare(String(b.cohort)));
  }
  return sorted.sort((a, b) => {
    const aFdr = a.fdr ?? Number.POSITIVE_INFINITY;
    const bFdr = b.fdr ?? Number.POSITIVE_INFINITY;
    return aFdr - bFdr || Math.abs(missingLast(b.log2Hr)) - Math.abs(missingLast(a.log2Hr)) || String(a.cohort).localeCompare(String(b.cohort));
  });
}

function formatDirectionToken(row) {
  if (!row || row.status !== "completed") return "Not evaluable";
  if (row.hazardRatio > 1) return "HR > 1";
  if (row.hazardRatio < 1) return "HR < 1";
  return "HR = 1";
}

function formatCompactNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  if (Math.abs(number) < 0.01 && number !== 0) return number.toExponential(1);
  return number.toFixed(2);
}

function concordanceInterpretation(row, referenceRow, fdrThreshold) {
  if (row.status !== "completed") {
    return {
      title: "Not evaluable in this scan",
      body: row.reason || row.code || "This cohort did not pass endpoint, gene, patient-count or event-count requirements.",
    };
  }
  const direction = row.hazardRatio > 1 ? "higher hazard" : row.hazardRatio < 1 ? "lower hazard" : "no directional effect";
  const fdrHit = row.fdr !== null && fdrThreshold !== null && row.fdr <= Number(fdrThreshold);
  const sameDirection = row.concordance === "reference" || String(row.concordance || "").startsWith("same_direction");
  const oppositeDirection = String(row.concordance || "").startsWith("opposite_direction");
  const caveats = [];
  if (row.phPValue !== null && row.phPValue < 0.05) caveats.push("PH test is flagged; inspect time-varying effects before treating the Cox HR as stable.");
  if (row.nEvents !== null && row.nEvents < 20) caveats.push("Event count is low, so the confidence interval may be unstable.");
  if (row.standardError !== null && row.standardError > 0.25) caveats.push("The Cox standard error is wide relative to stronger cohorts.");

  if (!referenceRow) {
    return {
      title: fdrHit ? "FDR-significant cohort effect" : "Direction without index concordance",
      body: `Expression is associated with ${direction}; the selected index cancer was not evaluable, so same/opposite-direction labels should not drive interpretation.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (row.concordance === "reference") {
    return {
      title: "Index cancer reference",
      body: `This cohort defines the concordance direction for the scan. Expression is associated with ${direction}${fdrHit ? " and passes the selected FDR threshold" : " but does not pass the selected FDR threshold"}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (fdrHit && sameDirection) {
    return {
      title: "Concordant FDR hit",
      body: `This is the strongest cross-cancer support pattern: same direction as the index cancer and FDR <= ${formatP(fdrThreshold)}. Expression is associated with ${direction}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (fdrHit && oppositeDirection) {
    return {
      title: "Discordant FDR hit",
      body: `This cohort is statistically strong but directionally opposite to the index cancer. Treat it as biology worth follow-up, not noise. Expression is associated with ${direction}.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (sameDirection) {
    return {
      title: "Directional concordance only",
      body: `The HR direction matches the index cancer, but this cohort is not an FDR hit. Use it as weak directional support, especially if events or precision are limited.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  if (oppositeDirection) {
    return {
      title: "Opposite direction without FDR support",
      body: `The HR direction differs from the index cancer but does not pass FDR. This may reflect tissue context, endpoint noise or limited precision.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
    };
  }
  return {
    title: "No interpretable concordance label",
    body: `The cohort completed, but concordance is unavailable for this row.${caveats.length ? ` ${caveats.join(" ")}` : ""}`,
  };
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

function PlotDownloadButtons({ svgSelector, filenameBase, onPlotDownload }) {
  if (!onPlotDownload) return null;
  return (
    <div className="plot-download-row compact">
      <span>Download plot</span>
      <div className="download-row">
        <button type="button" onClick={() => onPlotDownload(svgSelector, filenameBase, "png")}>
          <Image size={16} />
          PNG
        </button>
        <button type="button" onClick={() => onPlotDownload(svgSelector, filenameBase, "svg")}>
          <ArrowDownToLine size={16} />
          SVG
        </button>
      </div>
    </div>
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

function formatHrValues(row) {
  if (row?.hazard_ratio === undefined || row?.hazard_ratio === null) return "...";
  return `${Number(row.hazard_ratio).toFixed(2)} (${Number(row.hr_conf_low).toFixed(2)}-${Number(row.hr_conf_high).toFixed(2)})`;
}

function formatCoxCovariates(value) {
  if (!value?.length) return "None";
  return value.map((item) => formatLabel(item)).join(", ");
}

function findCoxModel(models, modelId) {
  return (models || []).find((model) => model.model === modelId && model.status === "completed") || null;
}

function downstreamAdjustedModel(models) {
  return (
    findCoxModel(models, "stage_grade_adjusted") ||
    findCoxModel(models, "stage_adjusted") ||
    findCoxModel(models, "grade_adjusted")
  );
}

function cutpointRobustness(row) {
  const metrics = row.result?.metrics || {};
  const univariable = findCoxModel(metrics.cox_models, "univariable");
  const adjusted = downstreamAdjustedModel(metrics.cox_models);
  const bhPass = Number.isFinite(row.bh) && row.bh <= ROBUSTNESS_ALPHA;
  const coxPass = Number.isFinite(univariable?.p_value) && univariable.p_value <= ROBUSTNESS_ALPHA;
  const adjustedPass = Number.isFinite(adjusted?.p_value) && adjusted.p_value <= ROBUSTNESS_ALPHA;
  const rmstPValue = Number(metrics.rmst?.difference?.p_value);
  const rmstPass = metrics.rmst?.status === "completed" && Number.isFinite(rmstPValue) && rmstPValue <= ROBUSTNESS_ALPHA;
  const phValue = adjusted?.ph_global_p_value;
  const phOk = phValue === undefined || phValue === null || !Number.isFinite(Number(phValue)) || Number(phValue) >= ROBUSTNESS_ALPHA;
  const hr = Number(univariable?.hazard_ratio);
  const direction = Number.isFinite(hr) ? (hr < 1 ? "Protective" : hr > 1 ? "Harmful" : "Neutral") : "...";
  let reason = "Survives";
  if (!bhPass) reason = "Fails BH";
  else if (!coxPass) reason = "Fails Cox";
  else if (!adjustedPass) reason = "Fails adjusted";
  else if (!rmstPass) reason = "Fails RMST";
  else if (!phOk) reason = "PH flagged";
  return {
    survives: bhPass && coxPass && adjustedPass && rmstPass && phOk,
    reason,
    bhPass,
    coxPass,
    adjustedPass,
    rmstPass,
    phOk,
    direction,
  };
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  return `${number.toFixed(0)}%`;
}

function formatEffectLabel(value) {
  return {
    harmful: "Higher expression worse",
    protective: "Higher expression better",
    neutral: "Not FDR-significant",
    not_evaluable: "Not evaluable",
  }[value] || formatLabel(String(value || "..."));
}

function formatConcordance(value) {
  return {
    reference: "Index cancer",
    same_direction_significant: "Same direction / FDR hit",
    same_direction_not_significant: "Same direction",
    opposite_direction_significant: "Opposite / FDR hit",
    opposite_direction_not_significant: "Opposite direction",
    reference_unavailable: "No index effect",
    not_evaluable: "Not evaluable",
  }[value] || formatLabel(String(value || "..."));
}

function shortEffectLabel(row) {
  if (row.status !== "completed") return row.status === "failed" ? "Fail" : "Skip";
  if (row.effect_category === "harmful") return "Worse";
  if (row.effect_category === "protective") return "Better";
  return row.direction === "harmful" ? "HR > 1" : row.direction === "protective" ? "HR < 1" : "Neutral";
}

function panCancerRowTooltip(row) {
  if (row.status !== "completed") return row.reason || row.code || row.status;
  return `${formatHrValues(row)}, FDR ${formatP(row.fdr)}, ${formatConcordance(row.concordance)}`;
}

async function downloadSvgPlot(svgSelector, filename, format) {
  const svg = document.querySelector(svgSelector);
  if (!svg) throw new Error("Plot is not available.");
  const serialized = serializeSvgForDownload(svg);
  if (format === "svg") {
    downloadBlob(new Blob([serialized], { type: "image/svg+xml;charset=utf-8" }), filename);
    return;
  }
  if (format !== "png") {
    throw new Error("Unsupported plot format.");
  }
  const { width, height } = svgDimensions(svg);
  const scale = 2;
  const blob = new Blob([serialized], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  try {
    const image = await loadImage(url);
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const pngBlob = await new Promise((resolve, reject) => {
      canvas.toBlob((result) => (result ? resolve(result) : reject(new Error("PNG rendering failed."))), "image/png");
    });
    downloadBlob(pngBlob, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

function serializeSvgForDownload(svg) {
  const clone = svg.cloneNode(true);
  const { width, height } = svgDimensions(svg);
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  const styleText = collectStylesheetText();
  if (styleText) {
    const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent = styleText;
    clone.insertBefore(style, clone.firstChild);
  }
  return new XMLSerializer().serializeToString(clone);
}

function collectStylesheetText() {
  return Array.from(document.styleSheets)
    .map((sheet) => {
      try {
        return Array.from(sheet.cssRules || []).map((rule) => rule.cssText).join("\n");
      } catch {
        return "";
      }
    })
    .filter(Boolean)
    .join("\n");
}

function svgDimensions(svg) {
  const viewBox = svg.viewBox?.baseVal;
  if (viewBox && viewBox.width && viewBox.height) {
    return { width: viewBox.width, height: viewBox.height };
  }
  const rect = svg.getBoundingClientRect();
  return {
    width: rect.width || Number(svg.getAttribute("width")) || 900,
    height: rect.height || Number(svg.getAttribute("height")) || 500,
  };
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new window.Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not render SVG as PNG."));
    image.src = url;
  });
}

function downloadBlob(blob, filename) {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
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

function formatMedianSurvivalDays(value) {
  if (value === undefined || value === "") return "...";
  if (value === null) return "Not reached";
  const number = Number(value);
  if (!Number.isFinite(number)) return "Not reached";
  return Math.round(number).toLocaleString();
}

function formatDays(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "...";
  return Math.round(number).toLocaleString();
}

function formatRmstDelta(rmst) {
  if (rmst?.status !== "completed") return "...";
  const value = Number(rmst.difference?.estimate_days);
  if (!Number.isFinite(value)) return "...";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} days`;
}

function formatRmstCi(item) {
  const low = Number(item?.conf_low);
  const high = Number(item?.conf_high);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return "...";
  return `${Math.round(low).toLocaleString()}-${Math.round(high).toLocaleString()}`;
}

function isMedianNotReached(value) {
  if (value === undefined || value === "") return false;
  if (value === null) return true;
  return !Number.isFinite(Number(value));
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
