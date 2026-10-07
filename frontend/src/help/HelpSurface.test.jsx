// @vitest-environment jsdom

import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test } from "vitest";

import { FieldHelp, FieldWithHelp, HelpButton, LabelWithHelp, Term } from "./HelpSurface";

afterEach(cleanup);

describe("in-place help surface", () => {
  test("Escape stays dismissed when removing the panel exposes its hovered trigger", async () => {
    const user = userEvent.setup();
    render(<HelpButton label="Dataset" helpId="dataset" />);
    const trigger = screen.getByRole("button", { name: "Explain Dataset" });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    fireEvent.mouseOver(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("tooltip")).toBeNull();
    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
  });
  test("click pins help; another click or Escape dismisses it", async () => {
    const user = userEvent.setup();
    render(<HelpButton label="Dataset" helpId="dataset" />);
    const trigger = screen.getByRole("button", { name: "Explain Dataset" });
    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    await user.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  test("help is rendered outside the form and closes on an outside click", async () => {
    const user = userEvent.setup();
    const { container } = render(<div><HelpButton label="Dataset" helpId="dataset" /><button>Other action</button></div>);
    await user.click(screen.getByRole("button", { name: "Explain Dataset" }));
    const card = screen.getByRole("tooltip");
    expect(container.contains(card)).toBe(false);
    await user.click(screen.getByRole("button", { name: "Other action" }));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  test("single-gene guidance renders without describing a combined score", () => {
    render(<FieldHelp helpId="survivalSingleGenes" />);
    expect(screen.getByText(/Each gene gets its own survival analysis, not a combined score/)).toBeTruthy();
    expect(screen.queryByText(/changes the score of every patient/)).toBeNull();
  });
  test("a control explains what it does, what changes and what is safe", async () => {
    const user = userEvent.setup();
    render(<LabelWithHelp label="Stratification" helpId="stratification" />);

    await user.click(screen.getByRole("button", { name: /Explain Stratification/ }));

    expect(screen.getByText("What it does")).toBeTruthy();
    expect(screen.getByText("What changes")).toBeTruthy();
    expect(screen.getByText("How to use it")).toBeTruthy();
    expect(
      screen.getByText(/Start with the median for a reproducible split/),
    ).toBeTruthy();
  });

  test("several entries can be combined without duplicating their copy", async () => {
    const user = userEvent.setup();
    render(
      <HelpButton label="Clinical design" helpId={["clinicalFilters", "clinicalAdjustment"]} />,
    );

    await user.click(screen.getByRole("button", { name: /Explain Clinical design/ }));

    expect(screen.getAllByText("What it does")).toHaveLength(2);
    expect(screen.getByText(/Filters choose who enters the analysis/)).toBeTruthy();
    expect(screen.getByText(/Add clinical variables to estimate the marker association/)).toBeTruthy();
  });

  test("a statistical term carries its definition where it is read", async () => {
    const user = userEvent.setup();
    render(<p>Positive <Term id="nes">NES</Term> favors group B.</p>);

    const trigger = screen.getByRole("button", { name: "NES" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    await user.click(trigger);

    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Definition")).toBeTruthy();
    expect(screen.getByRole("tooltip").textContent).toMatch(/normalized enrichment/i);
  });

  test("an unknown term fails loudly rather than rendering an empty popover", () => {
    expect(() => render(<Term id="not-a-concept">x</Term>)).toThrow(
      /Unknown TRACE Explorer glossary term/,
    );
  });

  test("a field associates its label with the control and keeps help outside it", () => {
    const { container } = render(
      <FieldWithHelp label="Expression scale" htmlFor="scale" helpId="expressionScale">
        <select id="scale"><option>log2(TPM + 1)</option></select>
      </FieldWithHelp>,
    );

    const label = container.querySelector("label");
    expect(label.getAttribute("for")).toBe("scale");
    expect(label.querySelector("button")).toBeNull();
    expect(screen.getByLabelText("Expression scale").tagName).toBe("SELECT");
  });

  test("Compare percentile help does not steal the input label", async () => {
    const user = userEvent.setup();
    const { container } = render(<FieldWithHelp label="Percentile threshold" htmlFor="compare-percentile" helpId="cutpoint.percentile">
      <input id="compare-percentile" type="number" />
    </FieldWithHelp>);
    expect(screen.getByLabelText("Percentile threshold").tagName).toBe("INPUT");
    expect(container.querySelector("label button")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Explain Percentile threshold" }));
    expect(screen.getByRole("tooltip")).toBeTruthy();
  });
});
