import React, {
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { IconButton, ModuleIcon } from "../design/icons";
import {
  HELP_SLOTS,
  getGlossaryTerm,
  getHelpEntry,
  hasGlossaryTerm,
  hasHelpEntry,
} from "./registry";

const SLOT_LABELS = Object.freeze({
  does: "What it does",
  changes: "What changes",
  safeDefault: "How to use it",
});

const EXPLAIN_LABEL = "Explain";
const DEFINITION_LABEL = "Definition";

function toEntryIds(helpId) {
  if (!helpId) return [];
  return (Array.isArray(helpId) ? helpId : [helpId]).filter(Boolean);
}

/** Shared anchored help for controls and glossary terms, outside layout containers. */
export function HelpPopover({ label, className = "", term, children }) {
  const id = useId();
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const cardRef = useRef(null);
  const closeTimerRef = useRef(null);
  const pinnedRef = useRef(false);
  const dismissedRef = useRef(false);
  const [open, setOpen] = useState(false);

  function cancelClose() {
    clearTimeout(closeTimerRef.current);
  }
  function show() {
    cancelClose();
    if (dismissedRef.current) return;
    setOpen(true);
  }
  function close() {
    cancelClose();
    pinnedRef.current = false;
    dismissedRef.current = true;
    setOpen(false);
  }
  function scheduleClose() {
    cancelClose();
    closeTimerRef.current = setTimeout(() => {
      if (!rootRef.current?.matches(":hover") && !cardRef.current?.matches(":hover")) {
        dismissedRef.current = false;
      }
      if (!pinnedRef.current && !rootRef.current?.contains(document.activeElement)) {
        setOpen(false);
      }
    }, 180);
  }
  useEffect(() => () => clearTimeout(closeTimerRef.current), []);

  useLayoutEffect(() => {
    if (!open) return;
    function positionCard(event) {
      const card = cardRef.current;
      const trigger = triggerRef.current;
      if (!card || !trigger || card.contains(event?.target)) return;
      const margin = 12;
      const gap = 8;
      const anchor = trigger.getBoundingClientRect();
      card.style.maxHeight = `${Math.max(80, window.innerHeight - margin * 2)}px`;
      const width = card.offsetWidth;
      const height = card.offsetHeight;
      const left = Math.max(margin, Math.min(anchor.left, window.innerWidth - width - margin));
      const fitsBelow = anchor.bottom + gap + height <= window.innerHeight - margin;
      const fitsAbove = anchor.top - gap - height >= margin;
      const top = fitsBelow ? anchor.bottom + gap
        : fitsAbove ? anchor.top - gap - height
        : Math.max(margin, Math.min(anchor.bottom + gap, window.innerHeight - height - margin));
      card.style.left = `${left}px`;
      card.style.top = `${top}px`;
      card.style.setProperty("--popover-origin-x", `${Math.max(12, Math.min(width - 12, anchor.left + anchor.width / 2 - left))}px`);
    }
    positionCard();
    window.addEventListener("resize", positionCard);
    window.addEventListener("scroll", positionCard, true);
    const observer = typeof ResizeObserver === "function" ? new ResizeObserver(() => positionCard()) : null;
    observer?.observe(cardRef.current);
    return () => {
      window.removeEventListener("resize", positionCard);
      window.removeEventListener("scroll", positionCard, true);
      observer?.disconnect();
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function outside(event) {
      if (!rootRef.current?.contains(event.target) && !cardRef.current?.contains(event.target)) close();
    }
    function escape(event) {
      if (event.key === "Escape") close();
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const triggerProps = {
    ref: triggerRef,
    "aria-expanded": open,
    "aria-controls": open ? id : undefined,
    "aria-describedby": open ? id : undefined,
    onFocus: () => { dismissedRef.current = false; show(); },
    onBlur: close,
    onClick: (event) => {
      event.stopPropagation();
      if (pinnedRef.current) close();
      else { dismissedRef.current = false; pinnedRef.current = true; show(); }
    },
    onKeyDown: (event) => {
      if (event.key === "Escape") close();
      if (open && ["ArrowDown", "ArrowUp", "PageDown", "PageUp"].includes(event.key)) {
        event.preventDefault();
        const direction = event.key.endsWith("Down") ? 1 : -1;
        cardRef.current?.scrollBy?.({ top: direction * (event.key.startsWith("Page") ? 200 : 40) });
      }
    },
  };

  return (
    <span ref={rootRef}
      className={[term ? "trace-term" : "help-popover", className].filter(Boolean).join(" ")}
      onMouseEnter={show} onMouseLeave={scheduleClose}>
      {term ? <button type="button" className="trace-term-trigger" {...triggerProps}>{term}</button>
        : <IconButton iconRole="status.info" label={`${EXPLAIN_LABEL} ${label}`}
            tooltip={`${EXPLAIN_LABEL} ${label}`} iconSize="sm" size="md"
            className="help-trigger" {...triggerProps} />}
      {open && createPortal(
        <span ref={cardRef} id={id} role="tooltip"
          className={["help-card", "help-card-anchored", term ? "trace-term-card" : ""].filter(Boolean).join(" ")}
          data-open="true" onMouseEnter={cancelClose} onMouseLeave={scheduleClose}
          onPointerDown={(event) => event.preventDefault()}>
          {children}
        </span>, document.body,
      )}
    </span>
  );
}

/**
 * Structured body for one or more registry entries: what it does, what changes
 * and what to pick when unsure. Free text is still accepted for the few places
 * that compose a value-dependent sentence at render time.
 */
export function HelpBody({ helpId, children }) {
  const entryIds = toEntryIds(helpId);
  if (!entryIds.length) return children || null;
  return (
    <>
      {entryIds.map((entryId) => {
        const entry = getHelpEntry(entryId);
        return (
          <dl className="help-slots" key={entryId}>
            {HELP_SLOTS.filter((slot) => entry[slot]).map((slot) => (
              <div className="help-slot" key={slot} data-slot={slot}>
                <dt>{SLOT_LABELS[slot]}</dt>
                <dd>{entry[slot]}</dd>
              </div>
            ))}
          </dl>
        );
      })}
      {children ? <p className="help-extra">{children}</p> : null}
    </>
  );
}

/**
 * `helpId` is the supported form. `children` remains available for dynamic
 * copy that cannot live in the registry, such as a value-dependent note.
 */
export function HelpButton({ label, helpId, children }) {
  if (!toEntryIds(helpId).length && !children) return null;
  return (
    <HelpPopover label={label}>
      <HelpBody helpId={helpId}>{children}</HelpBody>
    </HelpPopover>
  );
}

export function LabelWithHelp({ label, helpId, help, children }) {
  return (
    <span className="label-with-help">
      <span>{label}</span>
      <HelpButton label={label} helpId={helpId}>
        {help || children}
      </HelpButton>
    </span>
  );
}

export function PanelHeader({
  iconRole,
  title,
  description,
  helpId,
  help,
  children,
}) {
  const body = help || children;
  return (
    <div className="panel-header">
      <ModuleIcon role={iconRole} />
      <div>
        <div className="panel-title-row">
          <h2>{title}</h2>
          {(toEntryIds(helpId).length || body) && (
            <HelpButton label={title} helpId={helpId}>{body}</HelpButton>
          )}
        </div>
        {description && <p>{description}</p>}
      </div>
    </div>
  );
}

/**
 * A labelled form field with in-place help. The trigger is a sibling of the
 * `<label>`, never a descendant: a button is a labelable element, so nesting it
 * inside a label would make the control association ambiguous.
 */
export function FieldWithHelp({
  label,
  htmlFor,
  helpId,
  help,
  className = "",
  children,
}) {
  return (
    <div className={["field-with-help", className].filter(Boolean).join(" ")}>
      <span className="field-with-help-head">
        <label htmlFor={htmlFor}>{label}</label>
        <HelpButton label={label} helpId={helpId}>{help}</HelpButton>
      </span>
      {children}
    </div>
  );
}

/**
 * Section heading used by the modules that render their own numbered setup
 * steps instead of `PanelHeader`.
 */
export function SectionHelp({ title, helpId, help }) {
  return <HelpButton label={title} helpId={helpId}>{help}</HelpButton>;
}

/**
 * A statistical term rendered in place, with its definition one interaction
 * away. This is the only path by which the glossary reaches the workspace.
 */
export function Term({ id, children, className = "" }) {
  if (!hasGlossaryTerm(id)) {
    throw new Error(`Unknown TRACE Explorer glossary term: ${id}`);
  }
  const concept = getGlossaryTerm(id);
  return (
    <HelpPopover label={concept.term} term={children || concept.term} className={className}>
      <span className="trace-term-kicker">{DEFINITION_LABEL}</span>
      <strong>{concept.term}</strong>
      <span>{concept.definition}</span>
    </HelpPopover>
  );
}

/** Inline note under a field, resolved from the registry. */
export function FieldHelp({ helpId, slot = "does" }) {
  if (!hasHelpEntry(helpId)) {
    throw new Error(`Unknown TRACE Explorer help entry: ${helpId}`);
  }
  const entry = getHelpEntry(helpId);
  const text = HELP_SLOTS.includes(slot)
    ? entry[slot]
    : HELP_SLOTS.map((key) => entry[key]).filter(Boolean).join(" ");
  if (!text) return null;
  return <small className="field-help">{text}</small>;
}
