// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";

import DatasetProvenance from "./DatasetProvenance";

afterEach(cleanup);

const DATES = {
  source_latest_metadata_file: "2026-04-22T16:16:36+00:00",
  rna_cache_generated_at: "2026-08-05T14:16:28+00:00",
};

const SOURCES = [
  {
    id: "external:geo-brca-scanb-gse96058-2018",
    label: "SCAN-B breast cancer cohort",
    kind: "external_bulk_rna_seq",
    status: "ready",
    source_url: "https://example.org/GSE96058",
    imported_at: "2026-07-27T12:00:00+00:00",
    metadata: {
      dataset_id: "geo-brca-scanb-gse96058-2018",
      release_id: "geo-brca-scanb-gse96058-2018-release",
      manifest_hash: "a".repeat(64),
      license_id: "CC-BY-4.0",
      redistribution_allowed: true,
    },
  },
  {
    id: "external:cbioportal-skcm-gide-2019",
    label: "Melanoma immunotherapy cohort",
    kind: "external_bulk_rna_seq",
    status: "configured_no_survival",
    imported_at: "2026-07-28T12:00:00+00:00",
    metadata: {
      dataset_id: "cbioportal-skcm-gide-2019",
      license_id: "ODbL-1.0",
    },
  },
  {
    id: "tcga_cdr",
    label: "TCGA Clinical Data Resource",
    kind: "clinical_endpoint",
    status: "missing",
    imported_at: "2026-07-26T12:00:00+00:00",
    metadata: {},
  },
];

const DATASETS = [
  { id: "geo-brca-scanb-gse96058-2018", source_provider: "geo" },
  { id: "cbioportal-skcm-gide-2019", source_provider: "cbioportal" },
];

describe("DatasetProvenance", () => {
  test("shows a compact lineage summary while keeping the source ledger collapsed", () => {
    const { container } = render(
      <DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />,
    );

    expect(screen.getByRole("region", { name: "Dataset provenance and source status" })).toBeTruthy();
    expect(screen.getByText("2 of 3 records imported")).toBeTruthy();
    expect(screen.getByText("1 TCGA reference · 2 external records")).toBeTruthy();
    expect(container.querySelectorAll(".dataset-provenance-timeline time")).toHaveLength(2);
    expect(container.querySelector(".source-ledger").open).toBe(false);
  });

  test("labels a database fallback without presenting it as an RNA cache", () => {
    render(
      <DatasetProvenance
        dates={{ source_latest_metadata_file: DATES.source_latest_metadata_file, database_imported_at: DATES.rna_cache_generated_at }}
        sources={SOURCES}
        repositoryDatasets={DATASETS}
      />,
    );

    expect(screen.getByText("Database import")).toBeTruthy();
    expect(screen.getByText("Cohort records imported")).toBeTruthy();
  });

  test("shows an explicit unavailable state when no source inventory is returned", async () => {
    const user = userEvent.setup();
    render(<DatasetProvenance dates={DATES} sources={[]} repositoryDatasets={[]} />);

    expect(screen.getByLabelText("Source inventory unavailable")).toBeTruthy();
    expect(screen.getByText("No source records available")).toBeTruthy();
    await user.click(screen.getByText("Browse data sources"));
    expect(screen.getByText("No source records were returned. Reload the page to try again.")).toBeTruthy();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  test("searches human and technical metadata, opens matching groups and clears filters", async () => {
    const user = userEvent.setup();
    render(<DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />);

    await user.click(screen.getByText("Browse data sources"));
    await user.type(screen.getByRole("searchbox", { name: "Search sources" }), "GSE96058");

    expect(screen.getByRole("status").textContent).toMatch(/1 of 3 sources/);
    expect(screen.getByText("SCAN-B breast cancer cohort")).toBeTruthy();
    expect(screen.queryByText("Melanoma immunotherapy cohort")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("status").textContent).toMatch(/3 of 3 sources/);
  });

  test("filters attention states without relying on color and exposes source records", async () => {
    const user = userEvent.setup();
    render(<DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />);

    await user.click(screen.getByText("Browse data sources"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "attention");

    expect(screen.getByText("TCGA Clinical Data Resource")).toBeTruthy();
    expect(screen.getByText("Source files unavailable")).toBeTruthy();
    expect(screen.queryByText("SCAN-B breast cancer cohort")).toBeNull();
  });

  test("keeps an analysis limitation visible for expression-only records", async () => {
    const user = userEvent.setup();
    render(<DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />);

    await user.click(screen.getByText("Browse data sources"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Source system" }), "cbioportal");
    expect(screen.getByText("Expression available; survival unavailable")).toBeTruthy();
  });

  test("keeps broad status results collapsed and opens a single selected system", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />,
    );

    await user.click(screen.getByText("Browse data sources"));
    await user.selectOptions(screen.getByRole("combobox", { name: "Status" }), "ready");
    expect(container.querySelectorAll(".source-provider-group[open]")).toHaveLength(0);

    await user.selectOptions(screen.getByRole("combobox", { name: "Source system" }), "geo");
    expect(container.querySelectorAll(".source-provider-group[open]")).toHaveLength(1);
  });

  test("uses native disclosures and exposes visible technical provenance", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />,
    );

    await user.click(screen.getByText("Browse data sources"));
    const geoLabel = screen
      .getAllByText("Gene Expression Omnibus")
      .find((element) => element.matches(".source-provider-identity strong"));
    const geoDetails = geoLabel.closest("details");
    const geoSummary = geoDetails.querySelector(":scope > summary");
    await user.click(geoSummary);
    expect(geoDetails.open).toBe(true);

    expect(screen.getByText("external:geo-brca-scanb-gse96058-2018")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open original source for SCAN-B/i })).toBeTruthy();
    await user.click(within(geoDetails).getByText("Technical record"));
    expect(screen.getByText("geo-brca-scanb-gse96058-2018-release")).toBeTruthy();
    expect(container.textContent).toContain("CC-BY-4.0");
  });

  test("offers a recoverable empty result instead of a blank ledger", async () => {
    const user = userEvent.setup();
    render(<DatasetProvenance dates={DATES} sources={SOURCES} repositoryDatasets={DATASETS} />);

    await user.click(screen.getByText("Browse data sources"));
    await user.type(screen.getByRole("searchbox", { name: "Search sources" }), "not-a-study");
    expect(screen.getByText("No sources match")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("status").textContent).toMatch(/3 of 3 sources/);
  });
});
