import React, { useId } from "react";
import { FieldHelp, FieldWithHelp, LabelWithHelp, useHelpText } from "../help";
import { expressionCoverageLabel, expressionTissueLabel } from "./expressionDataContract";

export default function ExpressionDataSelector({ options, value, onChange, variant = "buttons", id }) {
  const generatedId = useId();
  const controlId = id || generatedId;
  const detailsId = `${controlId}-details`;
  const t = useHelpText();
  const selected = options.find((option) => option.value === value);
  const hasPaired = options.some((option) => option.transform === "paired_difference");
  const isPaired = selected?.transform === "paired_difference";
  const coverage = expressionCoverageLabel(selected);
  const sourceNote = selected?.scale_note || selected?.note;
  const helpId = isPaired
    ? ["expressionDataPaired", "expressionDataCoverage"]
    : coverage ? ["expressionScale", "expressionDataCoverage"] : "expressionScale";
  return (
    <div className="expression-data-selector">
      {variant === "select" ? (
        <FieldWithHelp label="Expression data" htmlFor={controlId} helpId={helpId}>
          <select id={controlId} value={value || ""} onChange={(event) => onChange(event.target.value)} aria-describedby={selected ? detailsId : undefined}>
            {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </FieldWithHelp>
      ) : (
        <>
          <LabelWithHelp label="Expression data" helpId={helpId} />
          <div className="scale-grid" role="group" aria-label="Expression data" aria-describedby={selected ? detailsId : undefined}>
            {options.map((option) => (
              <button key={option.value} type="button" aria-pressed={value === option.value}
                className={value === option.value ? "selected" : ""} onClick={() => onChange(option.value)}>
                <strong>{option.label}</strong>
                {hasPaired && <span>{t.entry(option.transform === "paired_difference" ? "expressionDataPaired" : "expressionDataSource").caption}</span>}
                {hasPaired && expressionCoverageLabel(option) && <small>{expressionCoverageLabel(option)}</small>}
              </button>
            ))}
          </div>
        </>
      )}
      {selected && (
        <div id={detailsId} className="expression-data-details" aria-live="polite" aria-atomic="true">
          {coverage && (!hasPaired || variant === "select") && <p className="expression-data-coverage"><strong>{coverage}</strong><FieldHelp helpId="expressionDataCoverage" /></p>}
          {isPaired ? (
            <>
              <p className="expression-data-formula">{selected.source_unit}<sub>tumor</sub> − {selected.source_unit}<sub>adjacent</sub></p>
              <p>{t.entry("expressionDataPaired").does}</p>
              <p>{t.entry("expressionDataPaired").changes}</p>
            </>
          ) : (
            <>
              {sourceNote && !hasPaired && <p>{sourceNote}</p>}
              {hasPaired && expressionTissueLabel(selected) && <p>{expressionTissueLabel(selected)}</p>}
              {hasPaired && <p>{t.entry("expressionDataSource").does}</p>}
            </>
          )}
        </div>
      )}
    </div>
  );
}
