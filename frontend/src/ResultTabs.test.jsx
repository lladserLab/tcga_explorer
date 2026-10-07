// @vitest-environment jsdom
import React from "react";
import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import ResultTabs, { ResultSection } from "./ResultTabs";
afterEach(cleanup);
const views = <ResultTabs><ResultSection id="first" title="Model"><input aria-label="Local setting" defaultValue="original" /></ResultSection>{false}<ResultSection id="second" title="Groups">Group data</ResultSection></ResultTabs>;
test("shows one named pane, supports keyboard navigation and preserves pane state", () => {
  render(views);
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  const setting = screen.getByRole("textbox");
  fireEvent.change(setting, { target: { value: "edited" } });
  const first = screen.getByRole("tab", { name: "Model" });
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowRight" });
  const groups = screen.getByRole("tab", { name: "Groups" });
  expect(document.activeElement).toBe(groups);
  expect(groups.getAttribute("aria-selected")).toBe("true");
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
  fireEvent.keyDown(groups, { key: "Home" });
  expect(screen.getByRole("textbox").value).toBe("edited");
  expect(document.getElementById(first.getAttribute("aria-controls")).hidden).toBe(false);
});
test("falls back to an available view when a conditional section disappears", () => {
  const { rerender } = render(views);
  fireEvent.click(screen.getByRole("tab", { name: "Groups" }));
  rerender(<ResultTabs><ResultSection id="first" title="Model">Model data</ResultSection></ResultTabs>);
  expect(screen.getByRole("tab").getAttribute("aria-selected")).toBe("true");
  expect(screen.getAllByRole("tabpanel")).toHaveLength(1);
});
