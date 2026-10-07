import React from "react";
import { TraceIcon } from "../design/icons";

/**
 * The section layer of the help system: a persistent, state-aware summary of
 * the design being built.
 *
 * It is deliberately not a dock and not a tour. It sits in the setup column,
 * never covers the controls it describes, has no steps, no progress and nothing
 * to complete. It answers what is decided, what is missing and what the result
 * will mean — and it says all three at every step, not only at the end.
 */
export function DesignLedger({
  title = "This analysis",
  ledger,
  requirementsId,
  className = "",
  compact = false,
}) {
  const { ready, decided, missing, estimand, cautions } = ledger;
  return (
    <aside
      className={["design-ledger", compact ? "design-ledger-compact" : "", className].filter(Boolean).join(" ")}
      aria-label={`${title} design summary`}
      data-ready={ready ? "true" : "false"}
    >
      <header className="design-ledger-header">
        <span className="result-family-label">{title}</span>
        <span className="design-ledger-state">
          <TraceIcon
            role={ready ? "status.success" : "status.info"}
            size="sm"
            tone={ready ? "success" : "secondary"}
          />
          {ready ? "Ready to run" : "Design incomplete"}
        </span>
      </header>

      <dl className="design-ledger-facts">
        {decided.filter((item) => !compact || ["marker", "endpoint", "adjustment"].includes(item.id)).map((item) => (
          <div key={item.id} data-fact={item.id} data-pending={item.pending ? "true" : undefined}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>

      {compact && ledger.compactEstimand && <p className="design-ledger-estimand">{ledger.compactEstimand}</p>}
      {compact && (
        <details className="design-ledger-details">
          <summary>All analysis settings</summary>
          <dl className="design-ledger-facts">
            {decided.filter((item) => !["marker", "endpoint", "adjustment"].includes(item.id)).map((item) => (
              <div key={item.id} data-fact={item.id} data-pending={item.pending ? "true" : undefined}>
                <dt>{item.label}</dt><dd>{item.value}</dd>
              </div>
            ))}
          </dl>
          <p className="design-ledger-estimand">{estimand}</p>
        </details>
      )}
      {!compact && estimand && (
        <p className="design-ledger-estimand">
          <strong>What this will estimate</strong>
          <span>{estimand}</span>
        </p>
      )}

      {!ready && (
        <div className="design-ledger-missing" role="status">
          <strong>Before you can run</strong>
          <ul id={requirementsId}>
            {missing.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}

      {!!cautions.length && (
        <ul className="design-ledger-cautions" aria-label={`${title} cautions`}>
          {cautions.map((item) => (
            <li key={item}>
              <TraceIcon role="status.caution" size="sm" tone="caution" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}

export default DesignLedger;
