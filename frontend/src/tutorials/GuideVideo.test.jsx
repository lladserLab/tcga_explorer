// @vitest-environment jsdom
import React from "react";
import { afterEach, beforeEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GuideVideo } from "./GuideVideo";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
});
afterEach(cleanup);

test("English video opens in a dialog, stops on close and restores focus", async () => {
  const user = userEvent.setup();
  const { container } = render(<GuideVideo guideId="quick-gsea" title="GSEA" />);
  expect(document.querySelector("video")).toBeNull();
  await user.click(screen.getByText("Watch video"));
  await waitFor(() => expect(document.querySelector("video")).not.toBeNull());
  const original = document.querySelector("video");
  expect(original.getAttribute("src")).toMatch(/05-gsea\/draft_v3_en\.mp4$/);
  expect(original.preload).toBe("none");
  expect(original.autoplay).toBe(false);
  expect(screen.queryByRole("combobox")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Close video" }));
  await waitFor(() => expect(document.querySelector("video")).toBeNull());
  expect(document.activeElement).toBe(screen.getByRole("button", { name: "Watch video" }));
});

test("failed media leaves a direct link and written-guide fallback", async () => {
  const { container } = render(<GuideVideo guideId="quick-analysis" title="Survival" />);
  await userEvent.click(screen.getByText("Watch video"));
  await waitFor(() => expect(document.querySelector("video")).not.toBeNull());
  fireEvent.error(document.querySelector("video"));
  expect(screen.getByRole("status").textContent).toContain("written guide");
  expect(screen.getByRole("link").getAttribute("href")).toMatch(/01-survival\/draft_v12_en\.mp4$/);
});

test("Home has no video", () => {
  const { container } = render(<GuideVideo guideId="quick-home" title="Home" />);
  expect(container.innerHTML).toBe("");
});
