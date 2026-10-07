import React, { Children, useId, useState } from "react";
import { getHelpEntry, SectionHelp } from "./help";

export function ResultSection({ children }) {
  return <>{children}</>;
}

/** Keep panes mounted so changing views never resets a result's controls. */
export default function ResultTabs({ children, label = "Result sections" }) {
  const sections = Children.toArray(children).filter((child) => React.isValidElement(child));
  const [selected, setSelected] = useState(null);
  const prefix = useId();
  const active = sections.some((section) => section.props.id === selected)
    ? selected : sections[0]?.props.id;
  function move(event, index) {
    const keys = ["ArrowRight", "ArrowLeft", "Home", "End"];
    if (!keys.includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? sections.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + sections.length) % sections.length;
    setSelected(sections[next].props.id);
    event.currentTarget.parentElement.children[next].focus();
  }
  return <div className="result-tabs">
    <div role="tablist" aria-label={label} className="result-tab-list">
      {sections.map(({ props }, index) => <button type="button" role="tab" key={props.id}
        id={`${prefix}-tab-${props.id}`} aria-controls={`${prefix}-pane-${props.id}`}
        aria-selected={active === props.id} tabIndex={active === props.id ? 0 : -1}
        onClick={() => setSelected(props.id)} onKeyDown={(event) => move(event, index)}>
        {props.title}
      </button>)}
    </div>
    {sections.map(({ props }) => <section key={props.id} role="tabpanel" tabIndex={0}
      id={`${prefix}-pane-${props.id}`} aria-labelledby={`${prefix}-tab-${props.id}`}
      hidden={active !== props.id} className="result-tab-panel">
      <div className="result-pane-heading">
        <h3>{props.title}</h3>
        {props.helpId && <SectionHelp title={props.title} helpId={props.helpId} />}
      </div>
      {(props.description || props.descriptionHelpId) && <p className="result-tab-description">{props.descriptionHelpId ? getHelpEntry(props.descriptionHelpId).does : props.description}</p>}
      {props.children}
    </section>)}
  </div>;
}
