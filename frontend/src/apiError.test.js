import { describe, expect, test } from "vitest";
import { formatApiError, validationErrorItems } from "./apiError";

describe("API validation errors", () => {
  test("turns a Pydantic percentile error into actionable copy", () => {
    const error = {
      code: "VALIDATION_ERROR",
      message: "The request did not match the documented API contract.",
      details: {
        errors: [{
          loc: ["body", "custom_percentile"],
          msg: "Input should be greater than or equal to 1",
        }],
      },
    };
    expect(formatApiError(error, { context: "Robustness" })).toBe(
      "Percentile threshold: Must be greater than or equal to 1.",
    );
  });

  test("names nested clinical-filter fields without exposing request syntax", () => {
    const items = validationErrorItems({
      details: {
        errors: [{
          loc: ["body", "filters", "custom_filters", 0, "levels"],
          msg: "List should have at least 1 item after validation, not 0",
        }],
      },
    });
    expect(items).toEqual([{
      field: "Selected levels",
      message: "List should have at least 1 item after validation, not 0.",
    }]);
  });

  test("uses a human fallback when an older server omits field details", () => {
    expect(formatApiError(
      { code: "VALIDATION_ERROR", message: "Invalid request." },
      { context: "Robustness" },
    )).toBe(
      "Robustness settings could not be validated. Review the current selections and try again.",
    );
  });

  test("does not prefix a human queue message with an internal error code", () => {
    expect(formatApiError({
      code: "HOURLY_LIMIT",
      message: "This network has reached the hourly limit. Try again in about 8 minutes.",
    })).toBe(
      "This network has reached the hourly limit. Try again in about 8 minutes.",
    );
  });

  test("preserves the selected-layer reason for rank capability errors", () => {
    const message = (
      "Rank-based scoring is unavailable because the selected expression "
      + "layer contains 7 missing or non-finite values. Use Mean, Z-score "
      + "or Weighted."
    );
    expect(formatApiError({
      code: "DATASET_CAPABILITY_UNAVAILABLE",
      message,
    })).toBe(message);
  });

  test("maps legacy rank errors to all supported non-rank alternatives", () => {
    const message = formatApiError({
      code: "INVALID_ANALYSIS",
      message: "A broad expression layer is required.",
    });
    expect(message).toMatch(/complete expression matrix/);
    expect(message).toMatch(/Mean, Z-score or Weighted/);
  });
});
