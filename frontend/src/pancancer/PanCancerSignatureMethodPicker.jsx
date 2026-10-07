import React from "react";

import { LabelWithHelp, useHelpText } from "../help";
import {
  SIGNATURE_METHOD_OPTIONS,
  signatureMethodUsesDirection,
} from "../signatureScoring";
import { SignatureInputSummary } from "../signatureScoringUi";

export default function PanCancerSignatureMethodPicker({
  method = "single",
  geneInput = "",
  rankScoring = { available: true, reason: "" },
  onChange,
}) {
  const t = useHelpText();

  return (
    <div className="pancancer-signature-method">
      <div className="axis-control">
        <LabelWithHelp label="Score method" helpId={`score.${method}`} />
        <div role="group" aria-label="Pan-cancer score method">
          {SIGNATURE_METHOD_OPTIONS.map((option) => {
            const rankUnavailable = signatureMethodUsesDirection(option.value)
              && !rankScoring.available;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={method === option.value}
                className={method === option.value ? "selected" : ""}
                disabled={rankUnavailable}
                title={rankUnavailable
                  ? rankScoring.reason
                  : t.entry(`score.${option.value}`).does}
                onClick={() => onChange(option.value)}
              >
                {option.shortLabel}
              </button>
            );
          })}
        </div>
      </div>
      {method !== "single" && (
        <SignatureInputSummary method={method} value={geneInput} />
      )}
      {signatureMethodUsesDirection(method) && !rankScoring.available && (
        <p className="signature-rank-unavailable" role="alert">
          {rankScoring.reason}
        </p>
      )}
    </div>
  );
}
