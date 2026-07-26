import React from "react";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, test } from "vitest";
import {
  IconButton,
  MODULE_ICON_ROLES,
  ModuleIcon,
  TRACE_ICON_ROLES,
  TraceIcon,
} from "./icons";

describe("TCGA-TRACE icon contract", () => {
  test("every registered glyph role renders through TraceIcon", () => {
    for (const role of TRACE_ICON_ROLES) {
      const markup = renderToStaticMarkup(<TraceIcon role={role} size="sm" />);
      expect(markup).toContain("trace-icon-size-sm");
      expect(markup).toContain('aria-hidden="true"');
    }
  });

  test("every registered scientific role renders through ModuleIcon", () => {
    for (const role of MODULE_ICON_ROLES) {
      const markup = renderToStaticMarkup(<ModuleIcon role={role} />);
      expect(markup).toContain("scientific-icon");
      expect(markup).toContain("workflow-icon");
      expect(markup).toContain('aria-hidden="true"');
    }
  });

  test("session history has a dedicated scientific navigation drawing", () => {
    const markup = renderToStaticMarkup(
      <ModuleIcon role="navigation.session" frame="navigation" />,
    );
    expect(markup).toContain("workflow-icon-session-history");
    expect(markup).toContain("workflow-emphasis");
  });

  test("meaningful standalone icons receive one accessible name", () => {
    const markup = renderToStaticMarkup(
      <TraceIcon role="status.caution" label="Diagnostic caution" tone="caution" />,
    );
    expect(markup).toContain('role="img"');
    expect(markup).toContain('aria-label="Diagnostic caution"');
    expect(markup).not.toContain('aria-hidden="true"');
  });

  test("module icons can be named without exposing their internal SVG", () => {
    const markup = renderToStaticMarkup(
      <ModuleIcon role="module.survivalEndpoint" label="Survival endpoint" />,
    );
    expect(markup).toContain('role="img"');
    expect(markup).toContain('aria-label="Survival endpoint"');
    expect(markup).toContain('aria-hidden="true"');
  });

  test("IconButton always exposes a label and tooltip", () => {
    const markup = renderToStaticMarkup(
      <IconButton iconRole="action.close" label="Dismiss download status" />,
    );
    expect(markup).toContain('aria-label="Dismiss download status"');
    expect(markup).toContain('title="Dismiss download status"');
    expect(markup).toContain("trace-icon-button");
    expect(() =>
      renderToStaticMarkup(<IconButton iconRole="action.close" />),
    ).toThrow("TCGA-TRACE IconButton requires a specific accessible label");
  });

  test("unknown roles and arbitrary sizes fail loudly", () => {
    expect(() => renderToStaticMarkup(<TraceIcon role="action.unknown" />)).toThrow(
      "Unknown TCGA-TRACE glyph icon role",
    );
    expect(() =>
      renderToStaticMarkup(<TraceIcon role="action.close" size="17" />),
    ).toThrow("Unsupported TCGA-TRACE icon size");
    expect(() => renderToStaticMarkup(<ModuleIcon role="module.unknown" />)).toThrow(
      "Unknown TCGA-TRACE module icon role",
    );
  });

  test("literal icon roles used by the application belong to the registry", () => {
    const source = readFileSync(new URL("../main.jsx", import.meta.url), "utf8");
    const registered = new Set([...TRACE_ICON_ROLES, ...MODULE_ICON_ROLES]);
    const usages = [
      ...source.matchAll(/\biconRole="([^"]+)"/g),
      ...source.matchAll(/<TraceIcon[^>]*\brole="([^"]+)"/g),
    ].map((match) => match[1]);

    expect(usages.length).toBeGreaterThan(20);
    for (const role of usages) {
      expect(registered.has(role), `Unregistered icon role: ${role}`).toBe(true);
    }
  });
});
