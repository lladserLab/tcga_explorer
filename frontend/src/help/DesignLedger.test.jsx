// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { DesignLedger } from "./DesignLedger";
import { survivalDesignLedger } from "./designLedgerContract";

afterEach(cleanup);

const complete = {
  datasetLabel: "Kidney renal clear cell carcinoma",
  markerSummary: "CA9",
  markerCount: 1,
  endpointLabel: "Overall survival",
  patients: 512,
  events: 168,
  expressionScaleLabel: "log2(TPM + 1)",
  groupingLabel: "Median",
  adjustmentSummary: "Age",
  covariateCount: 1,
  requirements: [],
};

describe("design ledger panel", () => {
  test("compact setup keeps the question, blockers and expandable full design", () => {
    const { container } = render(<DesignLedger compact ledger={survivalDesignLedger({ ...complete, requirements: ["Wait for cohort details."] })} />);
    expect(screen.getByText("Survival association of the selected gene or signature.")).toBeTruthy();
    expect(screen.getByText("Wait for cohort details.")).toBeTruthy();
    expect(screen.getByText("All analysis settings")).toBeTruthy();
    expect(container.querySelector("details").open).toBe(false);
    expect(container.querySelector("details").textContent).toContain("log2(TPM + 1)");
  });
  test("an incomplete design shows what is missing and marks pending facts", () => {
    render(
      <DesignLedger
        ledger={survivalDesignLedger({
          ...complete,
          markerSummary: "",
          requirements: ["Add at least one gene or signature."],
        })}
        requirementsId="analysis-design-requirements"
      />,
    );

    const panel = screen.getByLabelText("This analysis design summary");
    expect(panel.dataset.ready).toBe("false");
    expect(within(panel).getByText("Design incomplete")).toBeTruthy();
    expect(within(panel).getByText("Add at least one gene or signature.")).toBeTruthy();
    expect(document.getElementById("analysis-design-requirements")).toBeTruthy();
  });

  test("a complete design states what the result will estimate", () => {
    render(<DesignLedger ledger={survivalDesignLedger(complete)} />);

    const panel = screen.getByLabelText("This analysis design summary");
    expect(panel.dataset.ready).toBe("true");
    expect(within(panel).getByText("Ready to run")).toBeTruthy();
    expect(within(panel).getByText("What this will estimate")).toBeTruthy();
    expect(within(panel).getByText(/one-standard-deviation increase/)).toBeTruthy();
    expect(within(panel).queryByText("Before you can run")).toBeNull();
  });

  test("the panel is a summary, not a tour: no steps, progress or dismissal", () => {
    const { container } = render(<DesignLedger ledger={survivalDesignLedger(complete)} />);
    expect(container.querySelectorAll("button")).toHaveLength(0);
    expect(container.querySelector("[data-lesson]")).toBeNull();
  });

  test("cautions surface beside the design rather than after the run", () => {
    render(
      <DesignLedger
        ledger={survivalDesignLedger({ ...complete, events: 12, covariateCount: 3 })}
      />,
    );
    const cautions = screen.getByLabelText("This analysis cautions");
    expect(within(cautions).getByText(/12 events/)).toBeTruthy();
  });

  test("the title names the section it summarizes", () => {
    render(<DesignLedger title="This Robustness analysis" ledger={survivalDesignLedger(complete)} />);
    expect(screen.getByLabelText("This Robustness analysis design summary")).toBeTruthy();
  });
});
