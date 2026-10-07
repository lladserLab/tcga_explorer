// @vitest-environment jsdom

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";

import ClinicalFilterControls, {
  ClinicalVariableProvenance,
  clinicalFilterSummary,
  filterableClinicalVariables,
} from "./ClinicalFilterControls";

afterEach(cleanup);

const VARIABLES = [
  {
    id: "stage",
    label: "Stage",
    category: "standardized",
    analysis_eligible: true,
  },
  {
    id: "ajcc_pathologic_n",
    label: "AJCC pathologic N",
    category: "clinical",
    value_type: "categorical",
    analysis_eligible: true,
    survival_eligible: true,
    patient_count: 1095,
    non_missing_count: 988,
    levels: [
      { value: "N0", label: "N0", count: 469 },
      { value: "N1", label: "N1", count: 358 },
    ],
  },
  {
    id: "paper_BRCA_Subtype_PAM50",
    label: "PAM50 intrinsic subtype",
    category: "tumor_specific",
    value_type: "categorical",
    analysis_eligible: true,
    survival_eligible: true,
    expression_derived: true,
    source: "TCGA marker-paper annotation",
    source_field: "paper_BRCA_Subtype_PAM50",
    provenance: {
      origin: "source_reported_molecular",
      label: "Published molecular call",
      reported_by: "TCGA marker-paper annotation",
      method_summary: "Author-provided PAM50 call; TRACE does not rerun it.",
      reference: {
        label: "TCGA Breast Cancer, Nature 2012",
        doi: "10.1038/nature11412",
        url: "https://doi.org/10.1038/nature11412",
      },
      expression_derived: true,
      recomputed_by_trace: false,
      comparability: "Do not assume cross-platform equivalence.",
    },
    patient_count: 1095,
    non_missing_count: 1083,
    levels: [
      { value: "LumA", label: "Luminal A (PAM50)", count: 562 },
      { value: "Basal", label: "Basal-like (PAM50)", count: 190 },
    ],
    analysis_note: "Expression comparisons may be circular.",
  },
  {
    id: "prior_treatment",
    label: "Treatment recorded before specimen collection",
    category: "clinical",
    value_type: "categorical",
    analysis_eligible: true,
    survival_eligible: false,
    survival_unavailable_reason: "Timing does not precede the endpoint origin.",
    levels: [{ value: "No", label: "No", count: 900 }],
  },
];

describe("Clinical filter controls", () => {
  test("offers curated BRCA variables without duplicating standardized controls", () => {
    const catalog = filterableClinicalVariables(VARIABLES, "survival");
    expect(catalog.map((variable) => variable.id)).toEqual([
      "ajcc_pathologic_n",
      "paper_BRCA_Subtype_PAM50",
      "prior_treatment",
    ]);
    expect(catalog.find((variable) => variable.id === "prior_treatment")).toMatchObject({
      available: false,
    });
  });

  test("renders an active PAM50 restriction with counts and circularity warning", () => {
    const markup = renderToStaticMarkup(
      <ClinicalFilterControls
        variables={VARIABLES}
        value={[
          {
            variable_id: "paper_BRCA_Subtype_PAM50",
            categorical_levels: ["LumA"],
          },
        ]}
        onChange={() => {}}
        analysisContext="expression"
        excludeVariableIds={["ajcc_pathologic_n"]}
      />,
    );

    expect(markup).toContain("Additional patient restrictions");
    expect(markup).toContain("must meet");
    expect(markup).toContain("PAM50 intrinsic subtype");
    expect(markup).toContain("Luminal A (PAM50)");
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).toContain("1,083 / 1,095 observed");
    expect(markup).toContain("Published molecular call");
    expect(markup).toContain("Not recalculated by TRACE");
    expect(markup).toContain("Expression comparisons may be circular.");
  });

  test("adds two different parameters while retaining multiple levels in the first", async () => {
    const user = userEvent.setup();

    function Harness() {
      const [filters, setFilters] = React.useState([]);
      return (
        <>
          <ClinicalFilterControls
            variables={VARIABLES}
            value={filters}
            onChange={setFilters}
            analysisContext="expression"
          />
          <output data-testid="filter-state">{JSON.stringify(filters)}</output>
        </>
      );
    }

    render(<Harness />);
    await user.selectOptions(
      screen.getByLabelText("Add a parameter"),
      "paper_BRCA_Subtype_PAM50",
    );
    const pam50Levels = screen.getByLabelText("PAM50 intrinsic subtype levels");
    await user.click(within(pam50Levels).getByRole("button", { name: /Luminal A/ }));
    await user.click(within(pam50Levels).getByRole("button", { name: /Basal-like/ }));

    await user.selectOptions(
      screen.getByLabelText("Add another parameter"),
      "ajcc_pathologic_n",
    );
    await user.click(
      within(screen.getByLabelText("AJCC pathologic N levels")).getByRole(
        "button",
        { name: /^N0/ },
      ),
    );

    expect(JSON.parse(screen.getByTestId("filter-state").textContent)).toEqual([
      {
        variable_id: "paper_BRCA_Subtype_PAM50",
        categorical_levels: ["LumA", "Basal"],
        numeric_min: null,
        numeric_max: null,
      },
      {
        variable_id: "ajcc_pathologic_n",
        categorical_levels: ["N0"],
        numeric_min: null,
        numeric_max: null,
      },
    ]);
    expect(screen.getByText("2 of 10 parameters")).toBeTruthy();
  });

  test("shows method, reference and comparability for a selected subtype", () => {
    const markup = renderToStaticMarkup(
      <ClinicalVariableProvenance variable={VARIABLES[2]} />,
    );

    expect(markup).toContain("Author-provided PAM50 call");
    expect(markup).toContain("TCGA Breast Cancer, Nature 2012");
    expect(markup).toContain("10.1038/nature11412");
    expect(markup).toContain("Do not assume cross-platform equivalence.");
  });

  test("summarizes filters with human labels instead of internal IDs", () => {
    expect(
      clinicalFilterSummary(
        [
          {
            variable_id: "paper_BRCA_Subtype_PAM50",
            categorical_levels: ["LumA"],
          },
        ],
        VARIABLES,
      ),
    ).toEqual(["PAM50 intrinsic subtype: Luminal A (PAM50)"]);
  });
});
