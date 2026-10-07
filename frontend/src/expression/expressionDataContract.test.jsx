import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import ExpressionDataSelector from "./ExpressionDataSelector";
import { endpointsForExpressionLayer, expressionCoverageLabel } from "./expressionDataContract";

const endpoints = [{ value: "OS", available: true, patients: 135, events: 104 }];
const paired = { value: "delta", label: "Paired difference", transform: "paired_difference", source_unit: "log2(TPM + 1)",
  coverage: { patient_count: 66, sample_count: 66, observation_unit: "paired_contrast",
    endpoints: { OS: { patients: 66, events: 40, available: true } } } };
const source = { value: "source", label: "Source expression", transform: "identity",
  coverage: { patient_count: 135, sample_count: 201, observation_unit: "rna_profile" } };

describe("expression data selection", () => {
  test("counts patients, RNA profiles and paired contrasts separately", () => {
    expect(expressionCoverageLabel(source)).toBe("135 patients · 201 RNA profiles");
    expect(expressionCoverageLabel(paired)).toBe("66 patients · 66 paired contrasts");
    expect(expressionCoverageLabel({ sample_count: 66 })).toBe("");
  });
  test("projects only verified linked endpoint counts without mutating release totals", () => {
    expect(endpointsForExpressionLayer(endpoints, paired)[0]).toMatchObject({ patients: 66, events: 40, available: true });
    expect(endpoints[0].patients).toBe(135);
    expect(endpointsForExpressionLayer(endpoints, null)).toBe(endpoints);
  });
  test("does not enable a prohibited endpoint or invent missing coverage", () => {
    expect(endpointsForExpressionLayer([{ ...endpoints[0], available: false, reason: "Prohibited" }], paired)[0])
      .toMatchObject({ available: false, reason: "Prohibited" });
    expect(endpointsForExpressionLayer([{ value: "PFI", available: true }], paired)[0])
      .toMatchObject({ available: false, patients: 0, events: 0 });
  });
  test.each(["buttons", "select"])("%s explains paired direction and population", (variant) => {
    const html = renderToStaticMarkup(<ExpressionDataSelector options={[source, paired]} value="delta" onChange={() => {}} variant={variant} />);
    expect(html).toContain("Expression data");
    expect(html).toContain("66 patients · 66 paired contrasts");
    expect(html).toContain("Positive values mean higher expression in the tumor");
    expect(html).toContain("Only patients with both tissues");
    expect(html).toContain("not an independent healthy-control cohort");
    expect(html).toContain("<sub>tumor</sub>");
    expect(html).toContain('aria-describedby=');
  });
  test("TCGA and legacy choices do not acquire guessed coverage or paired guidance", () => {
    const html = renderToStaticMarkup(<ExpressionDataSelector options={[{ value: "tpm", label: "log2(TPM + 1)", note: "Source note" }]} value="tpm" onChange={() => {}} />);
    expect(html).toContain("Source note");
    expect(html).not.toContain("Only patients with both tissues");
    expect(html).not.toContain("RNA profiles");
  });
});
