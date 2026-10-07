import React, { useEffect, useMemo, useState } from "react";

import { TraceIcon } from "../design/icons";
import {
  DATASET_ANALYSIS_FILTERS,
  availableDatasetModules,
  datasetCapability,
} from "../datasetCapabilities";
import { GUIDE_ANCHORS, GuideAnchor } from "../tutorials";
import { FieldWithHelp, SectionHelp, Term } from "../help";
import {
  REPOSITORY_PAGE_SIZE,
  activeRepositoryFilterCount,
  endpointCode,
  filterRepositoryCandidates,
  filterRepositoryDatasets,
  normalizeCatalogText,
  repositoryCatalogOptions,
  repositoryPage,
  sortedDatasetEndpoints,
  sourceProviderLabel,
} from "./catalog";

const CATALOG_STATE_KEY = "trace-repository-catalog-v3";

const DEFAULT_CATALOG_STATE = {
  view: "cancers",
  query: "",
  coverage: "available",
  cancerCode: "all",
  analysis: "all",
  endpoint: "all",
  source: "all",
  access: "all",
  minimumEvents: "0",
  sort: "catalog",
  page: 1,
  expandedCancer: "",
  expandedDataset: "",
};

function initialCatalogState() {
  try {
    const stored = JSON.parse(
      window.sessionStorage.getItem(CATALOG_STATE_KEY) || "{}",
    );
    return {
      ...DEFAULT_CATALOG_STATE,
      ...stored,
      page: Number(stored.page || 1),
    };
  } catch {
    return DEFAULT_CATALOG_STATE;
  }
}

function formatInteger(value) {
  const number = Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat("en-US").format(number)
    : "—";
}

function countLabel(value, singular, plural = `${singular}s`) {
  const numeric = Number(value || 0);
  return `${formatInteger(numeric)} ${numeric === 1 ? singular : plural}`;
}

function publicationYear(dataset) {
  const matches = String(dataset?.publication_citation || "").match(
    /\b(?:19|20)\d{2}\b/g,
  );
  return matches?.at(-1) || "";
}

function cancerSearchText(cancer) {
  return normalizeCatalogText([
    cancer.code,
    cancer.tcga_cohort,
    cancer.name,
    cancer.primary_site,
    cancer.search?.review_note,
    ...(cancer.search?.candidates || []).flatMap((candidate) => [
      candidate.accession,
      candidate.review_note,
    ]),
  ].join(" "));
}

function capabilityDecisionLabel(capability) {
  if (capability?.available || capability?.decision === "enabled") return "Ready";
  if (capability?.decision === "pending") return "Pending review";
  return "Not available";
}

function DatasetAnalysisBadges({ dataset }) {
  const modules = availableDatasetModules(dataset);
  if (!modules.length) {
    return <span className="repository-no-analysis">No analysis module available</span>;
  }
  return (
    <span className="repository-analysis-badges" aria-label="Available analyses">
      {modules.map((module) => (
        <span key={module.id}>{module.label}</span>
      ))}
    </span>
  );
}

function DatasetCapabilitySummary({ dataset }) {
  const uniqueCapabilities = [
    { id: "analysis", label: "Survival, Compare and Robustness" },
    { id: "expression", label: "Expression comparison" },
    { id: "gsea", label: "GSEA" },
  ];
  return (
    <section className="repository-capability-summary" aria-labelledby={`repository-capabilities-${dataset.id}`}>
      <p className="eyebrow" id={`repository-capabilities-${dataset.id}`}>Available analyses</p>
      <dl>
        {uniqueCapabilities.map(({ id, label }) => {
          const capability = datasetCapability(dataset, id);
          return (
            <div key={id} className={capability.available ? "is-ready" : "is-unavailable"}>
              <dt>
                <TraceIcon
                  role={capability.available ? "status.success" : "status.info"}
                  size="sm"
                  tone={capability.available ? "success" : "secondary"}
                />
                {label}
              </dt>
              <dd>
                <strong>{capability.available ? "Ready" : "Not available"}</strong>
                <span>{capability.reason}</span>
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

function RepositoryDownloadMenu({ dataset, onDownload }) {
  const files = [
    ["manifest", "Manifest", "file.audit"],
    ["qc", "QC report", "status.success"],
    ["license", "License", "file.text"],
    ...(dataset.redistribution_allowed
      ? [
          ["matrix", "Expression matrix", "data.expression"],
          ["matrix-metadata", "Matrix metadata", "file.audit"],
          ["genes", "Gene index", "data.table"],
        ]
      : []),
  ];

  return (
    <details className="repository-download-menu">
      <summary className="secondary-button">
        <TraceIcon role="action.download" size="sm" />
        Files & provenance
      </summary>
      <div>
        {files.map(([kind, label, iconRole]) => (
          <button
            key={kind}
            type="button"
            onClick={(event) => {
              event.currentTarget.closest("details")?.removeAttribute("open");
              onDownload(
                `/api/v1/datasets/${encodeURIComponent(dataset.id)}/download/${kind}?expression_layer_id=${encodeURIComponent(dataset.expression_layer?.layer_id || "")}`,
                `${dataset.id} ${label}`,
              );
            }}
          >
            <TraceIcon role={iconRole} size="sm" />
            {label}
          </button>
        ))}
      </div>
    </details>
  );
}

function RepositoryStudyDetails({ dataset, onDownload }) {
  const endpoints = sortedDatasetEndpoints(dataset);
  return (
    <div className="repository-study-detail">
      <div className="repository-decision-context">
        <section>
          <p className="eyebrow">Cohort context</p>
          <p>{dataset.cohort_context || dataset.description}</p>
        </section>
        <section>
          <p className="eyebrow">Expression used by TRACE</p>
          <strong>
            {dataset.expression_layer?.label || "Expression layer documented in release"}
          </strong>
          {dataset.expression_layer?.scale_note && (
            <p>{dataset.expression_layer.scale_note}</p>
          )}
        </section>
      </div>

      {endpoints.length ? (
        <div className="repository-endpoint-table" role="region" aria-label={`${dataset.name} survival endpoints`} tabIndex={0}>
          <table aria-label="External cohort endpoints">
            <thead>
              <tr>
                <th scope="col">Endpoint</th>
                <th scope="col">Patients</th>
                <th scope="col">Events</th>
                <th scope="col">Time origin</th>
                <th scope="col">Event definition</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((endpoint) => (
                <tr key={`${endpoint.value}-${endpoint.standard_code || ""}`}>
                  <td>
                    <strong>{endpointCode(endpoint)}</strong>
                    <span>{endpoint.label}</span>
                  </td>
                  <td>{formatInteger(endpoint.patient_count)}</td>
                  <td>{formatInteger(endpoint.event_count)}</td>
                  <td>{endpoint.time_origin || "Defined by the source release"}</td>
                  <td>{endpoint.event_definition || "Defined by the source release"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="repository-no-endpoint" role="note">
          <TraceIcon role="status.info" size="md" tone="secondary" />
          <div>
            <strong>No time-to-event endpoint</strong>
            <span>
              This release can still support the molecular analyses marked as ready below.
              Survival, Compare and Robustness are unavailable.
            </span>
          </div>
        </div>
      )}

      <DatasetCapabilitySummary dataset={dataset} />

      <dl className="repository-technical-summary">
        <div>
          <dt>RNA samples</dt>
          <dd>{formatInteger(dataset.sample_count)}</dd>
        </div>
        <div>
          <dt>Genes</dt>
          <dd>{formatInteger(dataset.gene_count)}</dd>
        </div>
        <div>
          <dt>License</dt>
          <dd>{dataset.license_id || "Source terms"}</dd>
        </div>
        <div>
          <dt>Matrix access</dt>
          <dd>
            {dataset.redistribution_allowed
              ? "Downloadable"
              : "Analyze in TRACE"}
          </dd>
        </div>
      </dl>

      <div className="repository-provenance">
        <div>
          <p>{dataset.publication_citation || "Source publication"}</p>
          <code title={dataset.manifest_hash}>
            {dataset.manifest_hash?.slice(0, 18)}…
          </code>
        </div>
        <div>
          <RepositoryDownloadMenu dataset={dataset} onDownload={onDownload} />
          <a
            className="repository-source-link"
            href={dataset.source_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Open source
            <TraceIcon role="action.next" size="sm" />
          </a>
        </div>
      </div>
    </div>
  );
}

function RepositoryStudyRow({
  dataset,
  expanded,
  onToggle,
  onOpenModule,
  onDownload,
}) {
  const endpoints = sortedDatasetEndpoints(dataset);
  const modules = availableDatasetModules(dataset);
  const year = publicationYear(dataset);
  const detailId = `repository-study-${dataset.id}`;
  return (
    <article className={`repository-study${expanded ? " is-expanded" : ""}`}>
      <div className="repository-study-summary">
        <button
          type="button"
          className="repository-study-identity"
          aria-expanded={expanded}
          aria-controls={expanded ? detailId : undefined}
          onClick={onToggle}
        >
          <span>
            {sourceProviderLabel(dataset.source_provider)}
            {" · "}
            {dataset.source_accession}
            {year ? ` · ${year}` : ""}
          </span>
          <strong>
            {dataset.name}
            <span className="repository-release-state is-ready">Ready</span>
          </strong>
          <small>{dataset.cohort_context || dataset.description}</small>
        </button>

        <dl className="repository-study-metrics">
          <div>
            <dt>Patients</dt>
            <dd>{formatInteger(dataset.patient_count)}</dd>
          </div>
          <div>
            <dt>Time-to-event</dt>
            <dd className="repository-endpoint-summary">
              {endpoints.slice(0, 2).map((endpoint) => (
                <span key={`${endpoint.value}-${endpoint.standard_code || ""}`}>
                  <b>{endpointCode(endpoint)}</b>
                  {formatInteger(endpoint.event_count)} events
                </span>
              ))}
              {endpoints.length > 2 && (
                <span>+{endpoints.length - 2} more</span>
              )}
              {!endpoints.length && <span>No time-to-event endpoint</span>}
            </dd>
          </div>
          <div>
            <dt>Available analyses</dt>
            <dd><DatasetAnalysisBadges dataset={dataset} /></dd>
          </div>
        </dl>

        <div className="repository-study-actions">
          <div className="repository-module-actions" aria-label={`Open ${dataset.name} in an analysis module`}>
            {modules.map((module, index) => (
              <button
                key={module.id}
                type="button"
                className={index === 0 ? "primary-button" : "secondary-button"}
                onClick={() => onOpenModule(dataset.id, module.id)}
                aria-label={`Open ${module.label} with ${dataset.name}`}
              >
                {index === 0 && <TraceIcon role="action.run" size="sm" />}
                {module.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="repository-detail-toggle"
            aria-expanded={expanded}
            aria-controls={expanded ? detailId : undefined}
            onClick={onToggle}
          >
            {expanded ? "Hide details" : "View details"}
            <TraceIcon role="action.expand" size="sm" />
          </button>
        </div>
      </div>
      {expanded && (
        <div id={detailId}>
          <RepositoryStudyDetails dataset={dataset} onDownload={onDownload} />
        </div>
      )}
    </article>
  );
}

function RepositoryCancerRow({
  cancer,
  datasets,
  expandedDataset,
  expanded,
  onToggle,
  onToggleDataset,
  onOpenModule,
  onDownload,
}) {
  const status = cancer.coverage_status;
  const isAvailable = status === "available";
  const detailId = `repository-cancer-${cancer.code}`;
  const candidates = (cancer.search?.candidates || [])
    .map((candidate) => candidate.accession)
    .filter(Boolean);

  return (
    <section className="repository-cancer-result">
      <button
        type="button"
        className="repository-cancer-row"
        aria-expanded={expanded}
        aria-controls={expanded ? detailId : undefined}
        onClick={onToggle}
      >
        <span className="repository-cancer-code">{cancer.code}</span>
        <span className="repository-cancer-name">
          <strong>{cancer.name}</strong>
          <small>{cancer.primary_site}</small>
        </span>
        <span className={`repository-coverage-label ${status}`}>
          {isAvailable
            ? `${datasets.length} ${datasets.length === 1 ? "cohort" : "cohorts"}`
            : status === "evidence_gap"
              ? "Evidence gap"
              : "Under review"}
        </span>
        <TraceIcon role="action.expand" size="sm" />
      </button>

      {expanded && (
        <div id={detailId} className="repository-cancer-detail">
          {isAvailable ? (
            <div className="repository-study-list">
              {datasets.map((dataset) => (
                <RepositoryStudyRow
                  key={dataset.id}
                  dataset={dataset}
                  expanded={expandedDataset === dataset.id}
                  onToggle={() => onToggleDataset(dataset.id)}
                  onOpenModule={onOpenModule}
                  onDownload={onDownload}
                />
              ))}
            </div>
          ) : (
            <div className="repository-gap-detail">
              <div>
                <p className="eyebrow">Search record</p>
                <p>
                  {cancer.search?.review_note
                    || "No public bulk RNA-seq cohort currently passes the expression and survival requirements."}
                </p>
              </div>
              {candidates.length > 0 && (
                <details>
                  <summary>
                    Reviewed candidates ({candidates.length})
                  </summary>
                  <p>{candidates.join(" · ")}</p>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function RepositoryCandidateRow({ candidate }) {
  const capabilities = [
    ["survival", "Survival"],
    ["expression_comparison", "Expression comparison"],
    ["gsea", "GSEA"],
  ];
  const source = candidate.source || {};
  const links = (candidate.links || []).filter((link) => link?.url);
  const controlledAccess = candidate.status === "access_required";
  const notEligible = candidate.status === "not_eligible";
  const stateLabel = controlledAccess
    ? "Access required"
    : notEligible
      ? "Not eligible"
      : "Under review";
  const blockers = (candidate.blockers || []).map((blocker) =>
    typeof blocker === "string"
      ? blocker
      : blocker?.detail || blocker?.code,
  ).filter(Boolean);
  return (
    <article className="repository-candidate">
      <header>
        <div className="repository-candidate-identity">
          <span>
            {sourceProviderLabel(source.repository)}
            {source.accession ? ` · ${source.accession}` : ""}
          </span>
          <strong>{candidate.label}</strong>
          <small>
            {candidate.tier ? `${candidate.tier} · ` : ""}
            {String(candidate.access_class || "public evidence").replaceAll("_", " ")}
          </small>
        </div>
        <span className={`repository-release-state ${controlledAccess ? "is-controlled" : notEligible ? "is-ineligible" : "is-review"}`}>
          {stateLabel}
        </span>
      </header>

      <div className="repository-candidate-capabilities" aria-label={`${candidate.label} review status by analysis`}>
        {capabilities.map(([capabilityId, label]) => {
          const capability = candidate.capabilities?.[capabilityId] || {};
          const decision = capabilityDecisionLabel(capability);
          return (
            <section key={capabilityId}>
              <div>
                <strong>{label}</strong>
                <span>{decision}</span>
              </div>
              <p>{capability.reason || "This cohort is still under review."}</p>
            </section>
          );
        })}
      </div>

      <footer>
        <div>
          <strong>
            {controlledAccess
              ? "Controlled data; not available in TRACE"
              : notEligible
                ? "Not eligible for TRACE"
                : "Not available for analysis"}
          </strong>
          <span>
            {blockers.length
              ? blockers.join(" · ")
              : controlledAccess
                ? "Request access from the source repository. TRACE does not proxy controlled patient data."
                : "Curation and quality checks must finish before you can analyze this cohort."}
          </span>
        </div>
        {links.slice(0, 2).map((link) => (
          <a
            key={`${link.url}-${link.label || link.kind || "source"}`}
            className="repository-source-link"
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {link.label || link.kind || "Open source"}
            <TraceIcon role="action.next" size="sm" />
          </a>
        ))}
      </footer>
    </article>
  );
}

function RepositoryCandidateCancerRow({
  disease,
  candidates,
  expanded,
  onToggle,
}) {
  const detailId = `repository-candidate-disease-${disease.id}`;
  const reviewedExclusions = candidates.every(
    (candidate) => candidate.status === "not_eligible",
  );
  return (
    <section className="repository-cancer-result">
      <button
        type="button"
        className="repository-cancer-row"
        aria-expanded={expanded}
        aria-controls={expanded ? detailId : undefined}
        onClick={onToggle}
      >
        <span className="repository-cancer-code">{disease.id}</span>
        <span className="repository-cancer-name">
          <strong>{disease.label}</strong>
          <small>
            {reviewedExclusions
              ? "Reviewed cohort excluded from TRACE"
              : "Candidate cohort; not yet ready in TRACE"}
          </small>
        </span>
        <span className={`repository-coverage-label ${reviewedExclusions ? "not_eligible" : "under_review"}`}>
          {candidates.length} {reviewedExclusions ? "excluded" : "not yet released"}
        </span>
        <TraceIcon role="action.expand" size="sm" />
      </button>
      {expanded && (
        <div id={detailId} className="repository-cancer-detail">
          <div className="repository-study-list">
            {candidates.map((candidate) => (
              <RepositoryCandidateRow key={candidate.id} candidate={candidate} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

export default function RepositoryCatalog({
  coverage,
  datasets,
  candidates = [],
  candidatesStatus = "idle",
  onOpenModule,
  onDownload,
}) {
  const [catalog, setCatalog] = useState(initialCatalogState);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const options = useMemo(
    () => repositoryCatalogOptions(datasets),
    [datasets],
  );
  const candidateOptions = useMemo(() => ({
    cancers: [...new Map((candidates || []).map((candidate) => [
      candidate.disease?.id,
      candidate.disease?.label,
    ]).filter(([value]) => value))]
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => left.value.localeCompare(right.value)),
    sources: [...new Set((candidates || []).map(
      (candidate) => candidate.source?.repository,
    ).filter(Boolean))]
      .map((value) => ({ value, label: sourceProviderLabel(value) }))
      .sort((left, right) => left.label.localeCompare(right.label)),
  }), [candidates]);
  const showingCandidates = ["under_review", "not_eligible"].includes(
    catalog.coverage,
  );
  const showingReviewedExclusions = catalog.coverage === "not_eligible";
  const visibleOptions = showingCandidates ? candidateOptions : options;
  const activeFilterCount = activeRepositoryFilterCount(catalog);
  const filteredDatasets = useMemo(
    () => filterRepositoryDatasets(datasets, catalog),
    [catalog, datasets],
  );
  const filteredCandidates = useMemo(
    () => filterRepositoryCandidates(candidates, catalog),
    [candidates, catalog],
  );
  const datasetsByCancer = useMemo(() => {
    const grouped = new Map();
    filteredDatasets.forEach((dataset) => {
      if (!grouped.has(dataset.cancer_code)) {
        grouped.set(dataset.cancer_code, []);
      }
      grouped.get(dataset.cancer_code).push(dataset);
    });
    return grouped;
  }, [filteredDatasets]);
  const candidatesByDisease = useMemo(() => {
    const grouped = new Map();
    filteredCandidates.forEach((candidate) => {
      const disease = candidate.disease || { id: "OTHER", label: "Other cancer" };
      if (!grouped.has(disease.id)) {
        grouped.set(disease.id, { disease, candidates: [] });
      }
      grouped.get(disease.id).candidates.push(candidate);
    });
    return grouped;
  }, [filteredCandidates]);
  const visibleCancers = useMemo(() => {
    const normalizedQuery = normalizeCatalogText(catalog.query);
    const datasetFiltersActive = activeFilterCount > 0;
    return (coverage?.cancers || []).filter((cancer) => {
      if (
        catalog.coverage !== "all"
        && cancer.coverage_status !== catalog.coverage
      ) {
        return false;
      }
      if (
        catalog.cancerCode !== "all"
        && cancer.code !== catalog.cancerCode
      ) {
        return false;
      }
      const matchingStudies = datasetsByCancer.get(cancer.code) || [];
      if (
        cancer.coverage_status === "available"
        && (datasetFiltersActive || normalizedQuery)
        && !matchingStudies.length
      ) {
        return false;
      }
      if (
        normalizedQuery
        && !matchingStudies.length
        && !cancerSearchText(cancer).includes(normalizedQuery)
      ) {
        return false;
      }
      return true;
    });
  }, [
    activeFilterCount,
    catalog.cancerCode,
    catalog.coverage,
    catalog.query,
    coverage?.cancers,
    datasetsByCancer,
  ]);
  const visibleCandidateDiseases = useMemo(
    () => [...candidatesByDisease.values()].sort((left, right) =>
      String(left.disease.id).localeCompare(String(right.disease.id)),
    ),
    [candidatesByDisease],
  );
  const pageRows = showingCandidates ? filteredCandidates : filteredDatasets;
  const page = repositoryPage(
    pageRows,
    catalog.page,
    REPOSITORY_PAGE_SIZE,
  );

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        CATALOG_STATE_KEY,
        JSON.stringify(catalog),
      );
    } catch {
      // Session storage may be disabled in privacy-restricted contexts.
    }
  }, [catalog]);

  useEffect(() => {
    if (page.page !== catalog.page) {
      setCatalog((current) => ({ ...current, page: page.page }));
    }
  }, [catalog.page, page.page]);

  function updateCatalog(patch, resetPage = true) {
    setCatalog((current) => ({
      ...current,
      ...patch,
      ...(resetPage ? { page: 1, expandedDataset: "" } : {}),
    }));
  }

  function clearFilters() {
    updateCatalog({
      query: "",
      cancerCode: "all",
      analysis: "all",
      endpoint: "all",
      source: "all",
      access: "all",
      minimumEvents: "0",
      sort: "catalog",
    });
  }

  function showCoverage(status, { preserveView = false } = {}) {
    setCatalog((current) => ({
      ...DEFAULT_CATALOG_STATE,
      view: preserveView ? current.view : "cancers",
      coverage: status,
      query: current.query,
      analysis: current.analysis,
      ...(["under_review", "not_eligible"].includes(status)
        ? { endpoint: "all", minimumEvents: "0", access: "all" }
        : {}),
      expandedCancer: current.coverage === status
        ? current.expandedCancer
        : "",
    }));
  }

  const studiesInVisibleCancers = visibleCancers.reduce(
    (total, cancer) => total + (datasetsByCancer.get(cancer.code)?.length || 0),
    0,
  );
  const readyCohortCount = coverage?.datasets ?? datasets.length;
  const readyCancerCount = coverage?.available_cancer_types
    ?? new Set(datasets.map((dataset) => dataset.cancer_code)).size;
  const reviewableCandidateCount = candidates.filter(
    (candidate) => ["under_review", "access_required"].includes(candidate.status),
  ).length;
  const reviewedExclusionCount = candidates.filter(
    (candidate) => candidate.status === "not_eligible",
  ).length;

  return (
    <div className="repository-page">
      <GuideAnchor
        anchor={GUIDE_ANCHORS.REPOSITORY_PROVENANCE}
        label="Repository coverage and provenance"
        className="repository-intro"
      >
        <div>
          <div className="panel-title-row">
            <p className="eyebrow">Curated external RNA-seq</p>
            <SectionHelp title="Curated external RNA-seq" helpId="repository.provenance" />
          </div>
          <p>
            Find a cohort for your question. Check which analyses it supports and review its
            <Term id="provenance">provenance</Term>.
          </p>
        </div>
        <p className="repository-inline-summary">
          <strong>{countLabel(readyCohortCount, "ready cohort")}</strong>
          {" across "}
          <button type="button" onClick={() => showCoverage("available")}>
            {countLabel(readyCancerCount, "cancer type")}
          </button>
          {reviewableCandidateCount > 0 && (
            <>
              {". "}
              <button type="button" onClick={() => showCoverage("under_review")}>
                {formatInteger(reviewableCandidateCount)} under review
              </button>
            </>
          )}
          {reviewedExclusionCount > 0 && (
            <>
              {". "}
              <button type="button" onClick={() => showCoverage("not_eligible")}>
                {formatInteger(reviewedExclusionCount)} reviewed exclusions
              </button>
            </>
          )}
          .
        </p>
      </GuideAnchor>

      <GuideAnchor
        anchor={GUIDE_ANCHORS.REPOSITORY_FINDER}
        labelledBy="repository-finder-title"
        className="repository-finder"
      >
        <header>
          <div>
            <div className="panel-title-row">
              <h2 id="repository-finder-title">Find a cohort</h2>
              <SectionHelp title="Find a cohort" helpId="repository.finder" />
            </div>
            <p>Search by cancer, accession, publication, source or analysis availability.</p>
          </div>
          <div className="repository-view-switch" aria-label="Catalog view">
            <button
              type="button"
              className={catalog.view === "cancers" ? "selected" : ""}
              aria-pressed={catalog.view === "cancers"}
              onClick={() => updateCatalog({ view: "cancers" })}
            >
              By cancer
            </button>
            <button
              type="button"
              className={catalog.view === "studies" ? "selected" : ""}
              aria-pressed={catalog.view === "studies"}
              onClick={() => updateCatalog({ view: "studies" })}
            >
              All studies
            </button>
          </div>
        </header>

        <div className="repository-search-row">
          <label className="repository-search">
            <TraceIcon role="action.search" size="sm" />
            <span className="sr-only">Search external cohorts</span>
            <input
              value={catalog.query}
              onChange={(event) => updateCatalog({ query: event.target.value })}
              placeholder="Cancer, study, accession or context"
            />
          </label>
          <button
            type="button"
            className="secondary-button repository-filter-toggle"
            aria-expanded={filtersOpen}
            aria-controls={filtersOpen ? "repository-filter-panel" : undefined}
            onClick={() => setFiltersOpen((current) => !current)}
          >
            <TraceIcon role="action.configure" size="sm" />
            {filtersOpen ? "Hide filters" : "More filters"}
            {activeFilterCount > 0 && <span>{activeFilterCount}</span>}
          </button>
          {(activeFilterCount > 0 || catalog.query) && (
            <button type="button" className="text-link" onClick={clearFilters}>
              Clear
            </button>
          )}
        </div>

        {filtersOpen && (
          <div id="repository-filter-panel" className="repository-filter-panel">
            <label>
              <span>Cancer type</span>
              <select
                value={catalog.cancerCode}
                onChange={(event) => updateCatalog({ cancerCode: event.target.value })}
              >
                <option value="all">All cancer types</option>
                {visibleOptions.cancers.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.value} · {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Available analyses</span>
              <select
                value={catalog.analysis}
                onChange={(event) => updateCatalog({ analysis: event.target.value })}
              >
                {DATASET_ANALYSIS_FILTERS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            {!showingCandidates && (
            <FieldWithHelp label="Survival endpoint" htmlFor="repository-endpoint" helpId="survivalEndpoint">
              <select
                id="repository-endpoint"
                value={catalog.endpoint}
                onChange={(event) => updateCatalog({ endpoint: event.target.value })}
              >
                <option value="all">Any endpoint</option>
                {options.endpoints.map((endpoint) => (
                  <option key={endpoint} value={endpoint}>{endpoint}</option>
                ))}
              </select>
            </FieldWithHelp>
            )}
            {!showingCandidates && (
            <FieldWithHelp label="Minimum events" htmlFor="repository-minimum-events" helpId="repository.eligibility">
              <select
                id="repository-minimum-events"
                value={catalog.minimumEvents}
                onChange={(event) => updateCatalog({ minimumEvents: event.target.value })}
              >
                <option value="0">Any event count</option>
                <option value="10">10 or more</option>
                <option value="25">25 or more</option>
                <option value="50">50 or more</option>
                <option value="100">100 or more</option>
              </select>
            </FieldWithHelp>
            )}
            <label>
              <span>Source</span>
              <select
                value={catalog.source}
                onChange={(event) => updateCatalog({ source: event.target.value })}
              >
                <option value="all">Any source</option>
                {visibleOptions.sources.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {!showingCandidates && (
            <FieldWithHelp label="Matrix access" htmlFor="repository-matrix-access" helpId="repository.eligibility">
              <select
                id="repository-matrix-access"
                value={catalog.access}
                onChange={(event) => updateCatalog({ access: event.target.value })}
              >
                <option value="all">Any access</option>
                <option value="downloadable">Downloadable matrix</option>
                <option value="server_only">Analyze in TRACE</option>
              </select>
            </FieldWithHelp>
            )}
            {catalog.view === "studies" && !showingCandidates && (
              <label>
                <span>Sort studies</span>
                <select
                  value={catalog.sort}
                  onChange={(event) => updateCatalog({ sort: event.target.value })}
                >
                  <option value="catalog">Cancer and study</option>
                  <option value="patients">Most patients</option>
                  <option value="events">Most events</option>
                </select>
              </label>
            )}
          </div>
        )}
      </GuideAnchor>

      {catalog.view === "cancers" ? (
        <GuideAnchor
          anchor={GUIDE_ANCHORS.REPOSITORY_INTERPRETATION}
          labelledBy="repository-cancer-results-title"
          className="repository-results"
        >
          <header className="repository-results-heading">
            <div>
              <h2 id="repository-cancer-results-title">
                {showingCandidates
                  ? showingReviewedExclusions
                    ? "Reviewed exclusions"
                    : "Candidate cohorts"
                  : catalog.coverage === "evidence_gap"
                  ? "Evidence gaps"
                  : catalog.coverage === "all"
                    ? "All cancer types"
                    : "Cancer types with ready cohorts"}
              </h2>
              <p>
                {showingCandidates
                  ? showingReviewedExclusions
                    ? `${countLabel(visibleCandidateDiseases.length, "cancer type")} · ${countLabel(filteredCandidates.length, "cohort")} reviewed and not eligible`
                    : `${countLabel(visibleCandidateDiseases.length, "cancer type")} · ${countLabel(filteredCandidates.length, "candidate")} under review or access-controlled`
                  : countLabel(visibleCancers.length, "cancer type")}
                {!showingCandidates && catalog.coverage === "available"
                  ? ` · ${countLabel(studiesInVisibleCancers, "matching cohort")}`
                  : ""}
              </p>
            </div>
            <div className="repository-coverage-switch" aria-label="Cancer coverage">
              {[
                ["available", "Ready"],
                ["under_review", "Under review"],
                ["not_eligible", "Reviewed exclusions"],
                ["evidence_gap", "Evidence gaps"],
                ["all", "All cancers"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={catalog.coverage === value}
                  className={catalog.coverage === value ? "selected" : ""}
                  onClick={() => showCoverage(value, { preserveView: true })}
                >
                  {label}
                </button>
              ))}
            </div>
          </header>
          <div className="repository-cancer-list">
            {showingCandidates ? visibleCandidateDiseases.map(({ disease, candidates: diseaseCandidates }) => (
              <RepositoryCandidateCancerRow
                key={disease.id}
                disease={disease}
                candidates={diseaseCandidates}
                expanded={catalog.expandedCancer === disease.id}
                onToggle={() => setCatalog((current) => ({
                  ...current,
                  expandedCancer: current.expandedCancer === disease.id
                    ? ""
                    : disease.id,
                }))}
              />
            )) : visibleCancers.map((cancer) => (
              <RepositoryCancerRow
                key={cancer.code}
                cancer={cancer}
                datasets={datasetsByCancer.get(cancer.code) || []}
                expanded={catalog.expandedCancer === cancer.code}
                expandedDataset={catalog.expandedDataset}
                onToggle={() => setCatalog((current) => ({
                  ...current,
                  expandedCancer: current.expandedCancer === cancer.code
                    ? ""
                    : cancer.code,
                  expandedDataset: "",
                }))}
                onToggleDataset={(datasetId) => setCatalog((current) => ({
                  ...current,
                  expandedDataset: current.expandedDataset === datasetId
                    ? ""
                    : datasetId,
                }))}
                onOpenModule={onOpenModule}
                onDownload={onDownload}
              />
            ))}
          </div>
          {showingCandidates && ["idle", "loading"].includes(candidatesStatus) && (
            <div className="repository-empty" role="status">
              <TraceIcon role="status.loading" size="md" tone="accent" className="spin" />
              <strong>Loading cohorts under review…</strong>
            </div>
          )}
          {showingCandidates && candidatesStatus === "unavailable" && (
            <div className="repository-empty" role="status">
              <TraceIcon role="status.info" size="md" tone="secondary" />
              <strong>The review registry is temporarily unavailable.</strong>
              <span>Ready cohorts remain available.</span>
            </div>
          )}
          {((showingCandidates
            ? !visibleCandidateDiseases.length && candidatesStatus === "ready"
            : !visibleCancers.length)) && (
            <div className="repository-empty">
              <TraceIcon role="status.info" size="md" tone="secondary" />
              <strong>
                {showingCandidates
                  ? "No candidate cohorts match these filters."
                  : "No cancer types match these filters."}
              </strong>
              <button type="button" className="text-link" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          )}
        </GuideAnchor>
      ) : (
        <GuideAnchor
          anchor={GUIDE_ANCHORS.REPOSITORY_INTERPRETATION}
          labelledBy="repository-study-results-title"
          className="repository-results"
        >
          <header className="repository-results-heading">
            <div>
              <h2 id="repository-study-results-title">
                {showingCandidates
                  ? showingReviewedExclusions
                    ? "All reviewed exclusions"
                    : "All candidate cohorts"
                  : "All ready cohorts"}
              </h2>
              <p>
                {pageRows.length
                  ? `Showing ${page.start + 1}–${page.end} of ${pageRows.length}`
                  : "No matching studies"}
              </p>
            </div>
            <div className="repository-coverage-switch" aria-label="Cohort release status">
              {[
                ["available", "Ready"],
                ["under_review", "Under review"],
                ["not_eligible", "Reviewed exclusions"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={catalog.coverage === value}
                  className={catalog.coverage === value ? "selected" : ""}
                  onClick={() => showCoverage(value, { preserveView: true })}
                >
                  {label}
                </button>
              ))}
            </div>
          </header>
          <div className="repository-study-list repository-all-studies">
            {showingCandidates ? page.rows.map((candidate) => (
              <RepositoryCandidateRow key={candidate.id} candidate={candidate} />
            )) : page.rows.map((dataset) => (
              <RepositoryStudyRow
                key={dataset.id}
                dataset={dataset}
                expanded={catalog.expandedDataset === dataset.id}
                onToggle={() => setCatalog((current) => ({
                  ...current,
                  expandedDataset: current.expandedDataset === dataset.id
                    ? ""
                    : dataset.id,
                }))}
                onOpenModule={onOpenModule}
                onDownload={onDownload}
              />
            ))}
          </div>
          {showingCandidates && ["idle", "loading"].includes(candidatesStatus) && (
            <div className="repository-empty" role="status">
              <TraceIcon role="status.loading" size="md" tone="accent" className="spin" />
              <strong>Loading candidate cohorts…</strong>
            </div>
          )}
          {showingCandidates && candidatesStatus === "unavailable" && (
            <div className="repository-empty" role="status">
              <TraceIcon role="status.info" size="md" tone="secondary" />
              <strong>The review registry is temporarily unavailable.</strong>
              <span>Ready cohorts remain available.</span>
            </div>
          )}
          {!page.rows.length && (!showingCandidates || candidatesStatus === "ready") && (
            <div className="repository-empty">
              <TraceIcon role="status.info" size="md" tone="secondary" />
              <strong>No studies match these filters.</strong>
              <button type="button" className="text-link" onClick={clearFilters}>
                Clear filters
              </button>
            </div>
          )}
          {page.pageCount > 1 && (
            <nav className="repository-pagination" aria-label="Study result pages">
              <button
                type="button"
                className="secondary-button"
                disabled={page.page === 1}
                onClick={() => updateCatalog({ page: page.page - 1 }, false)}
              >
                <TraceIcon role="action.back" size="sm" />
                Previous
              </button>
              <span>Page {page.page} of {page.pageCount}</span>
              <button
                type="button"
                className="secondary-button"
                disabled={page.page === page.pageCount}
                onClick={() => updateCatalog({ page: page.page + 1 }, false)}
              >
                Next
                <TraceIcon role="action.next" size="sm" />
              </button>
            </nav>
          )}
        </GuideAnchor>
      )}
    </div>
  );
}
