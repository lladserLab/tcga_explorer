import { expect, test } from "vitest";
import { referenceCohortId, tcgaReferenceCohorts } from "./referenceCohorts";

test("TCGA reference counts and choices exclude external-only cancer categories", () => {
  const cohorts = [{ id: "EXT-ALCL" }, { id: "TCGA-KIRC" }, { id: "TCGA-LUAD" }];
  expect(tcgaReferenceCohorts(cohorts).map((row) => row.id)).toEqual(["TCGA-KIRC", "TCGA-LUAD"]);
  expect(referenceCohortId(cohorts, "EXT-ALCL", "TCGA-LUAD")).toBe("TCGA-LUAD");
  expect(referenceCohortId(cohorts, "EXT-ALCL")).toBe("TCGA-KIRC");
  expect(referenceCohortId([{ id: "EXT-ALCL" }])).toBe("");
});
