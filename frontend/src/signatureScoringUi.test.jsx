// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import {
  SignatureInputSummary,
  SignatureScoringCollectionSummary,
  SignatureScoringSummary,
} from "./signatureScoringUi";

afterEach(cleanup);

describe("signature scoring UI", () => {
  test("states rank direction without promising cross-study comparability", () => {
    render(
      <SignatureInputSummary
        method="singscore"
        value="IFNG, GZMB, TGFB1:-1"
      />,
    );
    expect(screen.getByText(/2 up · 1 down/)).toBeTruthy();
    expect(screen.getByText(/Rank methods use direction/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Method details" }).getAttribute("href"))
      .toMatch(/methods\/signature-scoring\/$/);
  });

  test("renders coverage, fixed parameters and engine provenance", () => {
    render(
      <SignatureScoringSummary
        signature={{
          method: "ssgsea",
          genes: [
            { resolved_symbol: "IFNG", direction: "up" },
            { resolved_symbol: "GZMB", direction: "up" },
          ],
          coverage: {
            requested_n: 3,
            mapped_n: 3,
            unique_resolved_n: 2,
            fraction: 1,
          },
          scoring_parameters: { alpha: 0.25, normalize: false },
          gene_universe: { gene_count: 18000, expression_layer: "log2_tpm" },
          engine: { package: "GSVA", version: "2.0.7" },
          scoring_population: {
            timing: "before_clinical_filters",
            canonical_barcode_count: 531,
            returned_barcode_count: 510,
          },
        }}
      />,
    );
    expect(screen.getAllByText(/2 resolved genes from 3 requested entries/)).toHaveLength(2);
    expect(screen.getByText(/3 mapped requests/)).toBeTruthy();
    expect(screen.getByText("GSVA 2.0.7")).toBeTruthy();
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.getByText("No")).toBeTruthy();
  });

  test("keeps cohort scoring contracts compact and inspectable", () => {
    render(
      <SignatureScoringCollectionSummary
        title="Cohort-specific signature scoring"
        description="The score varies by cohort universe."
        items={[
          {
            id: "TCGA-KIRC",
            label: "Kidney clear cell · OS",
            signature: {
              method: "singscore",
              genes: [{ resolved_symbol: "CA9", direction: "up" }],
              coverage: { requested_n: 1, unique_resolved_n: 1 },
              gene_universe: { gene_count: 18000 },
              engine: { package: "singscore", version: "1.26.0" },
            },
          },
          {
            id: "TCGA-LUAD",
            label: "Lung adenocarcinoma · OS",
            signature: {
              method: "ssgsea",
              genes: [
                { resolved_symbol: "CA9", direction: "up" },
                { resolved_symbol: "VEGFA", direction: "up" },
              ],
              coverage: { requested_n: 2, unique_resolved_n: 2 },
              gene_universe: { gene_count: 17500 },
              engine: { package: "GSVA", version: "2.0.7" },
            },
          },
        ]}
      />,
    );

    expect(screen.getByText("The score varies by cohort universe.")).toBeTruthy();
    expect(screen.getByText("singscore 1.26.0")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Inspect"), {
      target: { value: "TCGA-LUAD" },
    });
    expect(screen.getByText("GSVA 2.0.7")).toBeTruthy();
    expect(screen.getAllByText("Lung adenocarcinoma · OS")).toHaveLength(2);
  });
});
