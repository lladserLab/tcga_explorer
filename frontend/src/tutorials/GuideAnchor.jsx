import React from "react";
import {
  guideAnchorDomId,
  isKnownGuideAnchor,
} from "./catalog";

export function clearGuideSpotlight(documentLike = globalThis.document) {
  if (!documentLike?.querySelectorAll) return;
  documentLike
    .querySelectorAll('[data-guide-spotlight="active"]')
    .forEach((element) => element.removeAttribute("data-guide-spotlight"));
}

export function spotlightGuideAnchor(anchor, documentLike = globalThis.document) {
  if (!documentLike || !isKnownGuideAnchor(anchor)) return false;
  const target = documentLike.getElementById(guideAnchorDomId(anchor));
  clearGuideSpotlight(documentLike);
  if (!target) return false;
  target.setAttribute("data-guide-spotlight", "active");
  return true;
}

export function focusGuideAnchor(anchor, documentLike = globalThis.document) {
  if (!documentLike || !isKnownGuideAnchor(anchor)) return false;
  const target = documentLike.getElementById(guideAnchorDomId(anchor));
  if (!target) return false;
  // Reveal the result pane before focusing a tutorial target inside it.
  const pane = target.closest?.('[role="tabpanel"][hidden]');
  if (pane) {
    const tab = documentLike.getElementById(pane.getAttribute("aria-labelledby"));
    if (!tab) return false;
    tab.click();
    globalThis.requestAnimationFrame?.(() => focusGuideAnchor(anchor, documentLike));
    return true;
  }
  spotlightGuideAnchor(anchor, documentLike);
  const reduceMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  target.scrollIntoView?.({
    block: "center",
    inline: "nearest",
    behavior: reduceMotion ? "auto" : "smooth",
  });
  try {
    target.focus({ preventScroll: true });
  } catch {
    target.focus?.();
  }
  return true;
}

/**
 * A stable, focusable landmark for tutorial steps. Visible/localized copy must
 * provide its accessible name; the semantic anchor ID never becomes UI copy.
 */
export function GuideAnchor({
  anchor,
  label,
  labelledBy,
  as: Component = "section",
  tabIndex = -1,
  className = "",
  children,
  ...props
}) {
  if (!isKnownGuideAnchor(anchor)) {
    throw new Error(`Unknown TRACE Explorer guide anchor: ${anchor}`);
  }
  if (!String(label || "").trim() && !String(labelledBy || "").trim()) {
    throw new Error("TRACE Explorer GuideAnchor requires label or labelledBy.");
  }
  return (
    <Component
      {...props}
      id={guideAnchorDomId(anchor)}
      data-guide-anchor={anchor}
      tabIndex={tabIndex}
      aria-label={label || undefined}
      aria-labelledby={labelledBy || undefined}
      className={["trace-guide-anchor", className].filter(Boolean).join(" ")}
    >
      {children}
    </Component>
  );
}

export default GuideAnchor;
