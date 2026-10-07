import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";

describe("tutorial manual print contract", () => {
  test("does not hide the application during ordinary result printing", () => {
    const css = readFileSync(new URL("./tutorials.css", import.meta.url), "utf8");
    expect(css).toContain('body[data-print-target="tutorial-manual"] *');
    expect(css).not.toMatch(/@media print\s*\{\s*body \*/);
  });
});
