import React, { useId, useMemo, useState } from "react";
import { TraceIcon } from "../design/icons";
import { GUIDE_ANCHORS, GuideAnchor } from "../tutorials";
import {
  filterSources,
  groupSources,
  sourceDisplayName,
  sourceIsReady,
  sourceProviderKey,
  sourceProviderMetadata,
  resolveSourceProviders,
  sourceStatusLabel,
  sourceTechnicalId,
  summarizeSources,
} from "./provenance";

function formatDate(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleDateString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  });
}

function formatDateTime(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

function plural(value, singular, pluralForm = `${singular}s`) {
  return `${value.toLocaleString()} ${value === 1 ? singular : pluralForm}`;
}

function SourceStatus({ source, compact = false }) {
  const ready = sourceIsReady(source);
  const label = compact && source.status === "ready"
    ? "Imported"
    : sourceStatusLabel(source.status);
  return (
    <span className={`source-ledger-status ${ready ? "ready" : "attention"}`}>
      <TraceIcon
        role={ready ? "status.success" : "status.caution"}
        size="sm"
        tone={ready ? "success" : "caution"}
      />
      <span>{label}</span>
    </span>
  );
}

function TechnicalRecord({ source }) {
  const metadata = source.metadata || {};
  const fields = [
    ["Technical source ID", sourceTechnicalId(source)],
    ["Internal status", source.status],
    ["Source system", sourceProviderMetadata(sourceProviderKey(source)).label],
    ["Import adapter", source.source_provider || metadata.source_provider],
    ["Dataset ID", metadata.dataset_id],
    ["Release ID", metadata.release_id],
    ["Manifest SHA-256", metadata.manifest_sha256 || metadata.manifest_hash],
    ["Data kind", source.kind],
    ["Source modified", source.source_file_modified_at ? formatDateTime(source.source_file_modified_at) : null],
    ["Redistribution", typeof metadata.redistribution_allowed === "boolean"
      ? (metadata.redistribution_allowed
          ? "Allowed by recorded terms"
          : "Not redistributed by TRACE; obtain files from the original source")
      : null],
    ["Description", metadata.description],
    ["Citation", metadata.citation],
  ].filter(([, value]) => value);

  if (!fields.length) return <span className="source-record-empty">No additional fields</span>;

  return (
    <details className="source-record-details">
      <summary>Technical record</summary>
      <dl>
        {fields.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function SourceGroup({ group, revealMatches }) {
  const [showAll, setShowAll] = useState(false);
  const allReady = group.ready === group.total;
  const visibleItems = showAll ? group.items : group.items.slice(0, 20);
  const hiddenCount = group.total - visibleItems.length;
  return (
    <details
      className="source-provider-group"
      open={revealMatches ? true : undefined}
    >
      <summary>
        <span className="source-provider-identity">
          <span className="source-provider-code" aria-hidden="true">{group.shortLabel}</span>
          <span>
            <strong>{group.label}</strong>
            <small>{plural(group.total, "source")}</small>
          </span>
        </span>
        <span className={`source-provider-health ${allReady ? "ready" : "attention"}`}>
          <TraceIcon
            role={allReady ? "status.success" : "status.caution"}
            size="sm"
            tone={allReady ? "success" : "caution"}
          />
          {group.ready.toLocaleString()} imported
        </span>
        <TraceIcon role="action.expand" size="sm" className="source-provider-chevron" />
      </summary>

      <div
        className="source-ledger-table-scroll"
        role="region"
        aria-label={`${group.label} source records`}
        tabIndex={0}
      >
        <table className="source-ledger-table">
          <caption className="sr-only">{group.label} source provenance</caption>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Status</th>
              <th scope="col">Imported</th>
              <th scope="col">License</th>
              <th scope="col"><span className="sr-only">Source record</span></th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.map((source) => {
              const metadata = source.metadata || {};
              return (
                <tr key={source.id}>
                  <td data-label="Source" className="source-ledger-name">
                    <strong>{sourceDisplayName(source)}</strong>
                    <small>{String(source.kind || "Source record").replaceAll("_", " ")}</small>
                  </td>
                  <td data-label="Status"><SourceStatus source={source} compact /></td>
                  <td data-label="Imported">
                    <time dateTime={source.imported_at || undefined}>
                      {formatDateTime(source.imported_at)}
                    </time>
                  </td>
                  <td data-label="License">
                    <span>{metadata.license_id || "Not specified"}</span>
                  </td>
                  <td data-label="Record" className="source-ledger-record">
                    <TechnicalRecord source={source} />
                    {source.source_url && (
                      <a
                        href={source.source_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Open original source for ${sourceDisplayName(source)} in a new tab`}
                      >
                        Original source <span aria-hidden="true">↗</span>
                      </a>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hiddenCount > 0 && (
        <div className="source-provider-more">
          <span>{plural(hiddenCount, "additional source")}</span>
          <button type="button" className="secondary-button" onClick={() => setShowAll(true)}>
            Show all {group.total.toLocaleString()}
          </button>
        </div>
      )}
    </details>
  );
}

export default function DatasetProvenance({
  dates = {},
  sources = [],
  repositoryDatasets = [],
  repositoryDatasetCount = 0,
}) {
  const queryId = useId();
  const providerId = useId();
  const statusId = useId();
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("all");
  const [status, setStatus] = useState("all");
  const [ledgerOpened, setLedgerOpened] = useState(false);

  const snapshotDate = dates.data_through_date
    || dates.source_latest_metadata_file
    || dates.source_summary_file;
  const snapshotLabel = dates.data_through_date
    ? "Latest TCGA source snapshot"
    : "Latest TCGA source file";
  const snapshotDescription = dates.data_through_date
    ? "Data included through this date"
    : "Source file modification date";
  const preparedDate = dates.rna_cache_generated_at || dates.database_imported_at;
  const preparedLabel = dates.rna_cache_generated_at ? "TCGA RNA analysis cache" : "Database import";
  const preparedDescription = dates.rna_cache_generated_at
    ? "Cache generated"
    : "Cohort records imported";
  const resolvedSources = useMemo(
    () => resolveSourceProviders(sources, repositoryDatasets),
    [repositoryDatasets, sources],
  );
  const summary = useMemo(() => summarizeSources(resolvedSources), [resolvedSources]);
  const filteredSources = useMemo(
    () => filterSources(resolvedSources, { query, provider, status }),
    [provider, query, resolvedSources, status],
  );
  const filteredGroups = useMemo(() => groupSources(filteredSources), [filteredSources]);
  const filtersActive = Boolean(query.trim() || provider !== "all" || status !== "all");
  const allReady = summary.total > 0 && summary.attention === 0;
  const coreSourceCount = resolvedSources.filter((source) => sourceProviderKey(source) === "tcga").length;
  const externalSourceCount = summary.total - coreSourceCount;

  function resetFilters() {
    setQuery("");
    setProvider("all");
    setStatus("all");
  }

  return (
    <GuideAnchor
      anchor={GUIDE_ANCHORS.DATASET_PROVENANCE}
      label="Dataset provenance and source status"
      className="dataset-provenance"
    >
      <header className="dataset-provenance-header">
        <div className="dataset-provenance-title">
          <TraceIcon role="data.cohort" size="md" />
          <div>
            <p className="eyebrow">Dataset lineage</p>
            <h2>Data provenance</h2>
            <p>Where each source came from and the exact record imported into TRACE.</p>
          </div>
        </div>
        <div
          className={`dataset-provenance-health ${allReady ? "ready" : "attention"}`}
          aria-label={summary.total
            ? `${summary.ready} of ${summary.total} source records imported`
            : "Source inventory unavailable"}
        >
          <TraceIcon
            role={allReady ? "status.success" : "status.caution"}
            size="md"
            tone={allReady ? "success" : "caution"}
          />
          <span>
            <strong>
              {summary.total
                ? `${summary.ready.toLocaleString()} of ${summary.total.toLocaleString()} records imported`
                : "Source inventory unavailable"}
            </strong>
            <small>
              {summary.total
                ? `${plural(coreSourceCount, "TCGA reference")} · ${plural(externalSourceCount, "external record")}`
                : "No source records were returned"}
            </small>
          </span>
        </div>
      </header>

      <ol className="dataset-provenance-timeline" aria-label="Dataset preparation timeline">
        <li>
          <span className="dataset-provenance-step">01</span>
          <span>
            <small>{snapshotLabel}</small>
            <strong><time dateTime={snapshotDate || undefined}>{formatDate(snapshotDate)}</time></strong>
            <em>{snapshotDescription}</em>
          </span>
        </li>
        <li>
          <span className="dataset-provenance-step">02</span>
          <span>
            <small>{preparedLabel}</small>
            <strong><time dateTime={preparedDate || undefined}>{formatDate(preparedDate)}</time></strong>
            <em>{preparedDescription}</em>
          </span>
        </li>
      </ol>

      <div className="dataset-provenance-note">
        <p>
          Each external cohort has its own release version. This source record also keeps
          imports no longer active in the cohort catalog. Open the source list to check
          imports, release manifests and licenses.
        </p>
        {(repositoryDatasetCount > 0 || repositoryDatasets.length > 0) && (
          <a href="?view=repository">
            Browse {plural(
              repositoryDatasetCount || repositoryDatasets.length,
              "active external cohort",
            )}
          </a>
        )}
      </div>

      <details
        className="source-ledger"
        onToggle={(event) => {
          if (event.currentTarget.open) setLedgerOpened(true);
        }}
      >
        <summary>
          <span>
            <TraceIcon role="data.table" size="md" />
            <span>
              <strong>Browse data sources</strong>
              <small>
                {summary.total
                  ? `${plural(summary.total, "source")} grouped by ${plural(summary.providerCount, "system")}`
                  : "No source records available"}
              </small>
            </span>
          </span>
          <span className="source-ledger-summary-action">
            <span className="source-ledger-action-label">Inspect sources</span>
            <TraceIcon role="action.expand" size="sm" />
          </span>
        </summary>

        {ledgerOpened && <div className="source-ledger-body">
          {summary.total > 0 ? (
            <>
          <div className="source-ledger-controls" role="search" aria-label="Filter data sources">
            <div className="source-ledger-search-field">
              <label htmlFor={queryId}>Search sources</label>
              <div className="source-ledger-search">
                <TraceIcon role="action.search" size="sm" />
                <input
                  id={queryId}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Study, accession, repository or license"
                />
              </div>
            </div>
            <label htmlFor={providerId}>
              <span>Source system</span>
              <select id={providerId} value={provider} onChange={(event) => setProvider(event.target.value)}>
                <option value="all">All systems</option>
                {summary.groups.map((group) => (
                  <option key={group.key} value={group.key}>
                    {group.shortLabel} ({group.total})
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={statusId}>
              <span>Status</span>
              <select id={statusId} value={status} onChange={(event) => setStatus(event.target.value)}>
                <option value="all">All statuses</option>
                <option value="ready">Imported</option>
                <option value="attention">Needs attention</option>
              </select>
            </label>
            {filtersActive && filteredSources.length > 0 && (
              <button type="button" className="text-link" onClick={resetFilters}>Clear filters</button>
            )}
          </div>

          <div className="source-ledger-result-line" role="status" aria-live="polite">
            <span>
              <strong>{filteredSources.length.toLocaleString()}</strong>
              {` of ${summary.total.toLocaleString()} sources`}
            </span>
            {filtersActive && <small>Matching the current filters</small>}
          </div>

          {filteredGroups.length ? (
            <div className="source-provider-groups">
              {filteredGroups.map((group) => (
                <SourceGroup
                  key={group.key}
                  group={group}
                  revealMatches={filtersActive && filteredGroups.length === 1}
                />
              ))}
            </div>
          ) : (
            <div className="source-ledger-empty">
              <TraceIcon role="action.search" size="md" />
              <strong>No sources match</strong>
              <p>Try a study name, accession, source system or license.</p>
              <button type="button" className="secondary-button" onClick={resetFilters}>Clear filters</button>
            </div>
          )}
            </>
          ) : (
            <div className="source-ledger-empty">
              <TraceIcon role="status.caution" size="md" tone="caution" />
              <strong>Source inventory unavailable</strong>
              <p>No source records were returned. Reload the page to try again.</p>
            </div>
          )}
        </div>}
      </details>
    </GuideAnchor>
  );
}
