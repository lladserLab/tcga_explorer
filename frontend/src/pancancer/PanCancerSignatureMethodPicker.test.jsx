// @vitest-environment jsdom

import React from "react";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import PanCancerSignatureMethodPicker from "./PanCancerSignatureMethodPicker";

afterEach(cleanup);

describe("TCGA reference signature method picker", () => {
  test("offers every supported method and changes the selected contract", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <PanCancerSignatureMethodPicker
        method="single"
        geneInput="IFNG, GZMB"
        onChange={onChange}
      />,
    );

    const group = screen.getByRole("group", { name: "Pan-cancer score method" });
    expect(group.querySelectorAll("button")).toHaveLength(7);
    await user.click(screen.getByRole("button", { name: "ssGSEA" }));
    expect(onChange).toHaveBeenCalledWith("ssgsea");
  });

  test("shows directional validation and disables rank methods when unavailable", () => {
    render(
      <PanCancerSignatureMethodPicker
        method="singscore"
        geneInput="IFNG, TGFB1:-1"
        rankScoring={{ available: false, reason: "Broad expression is unavailable." }}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole("note").textContent).toContain("1 up · 1 down");
    expect(screen.getByRole("button", { name: "singscore" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "ssGSEA" }).disabled).toBe(true);
    expect(screen.getByRole("button", { name: "AUCell" }).disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("Broad expression");
  });
});
