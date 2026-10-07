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

describe("TRACE Explorer icon contract", () => {
  test("every registered glyph role renders through TraceIcon", () => {
    for (const role of TRACE_ICON_ROLES) {
      const markup = renderToStaticMarkup(<TraceIcon role={role} size="sm" />);
      expect(markup).toContain("trace-icon-size-sm");
      expect(markup).toContain('aria-hidden="true"');
    }
  });

  test("platform and source links have distinct decorative silhouettes", () => {
    const drawings = ["platform.windows", "platform.macos", "platform.linux", "resource.github"].map(role => {
      const markup = renderToStaticMarkup(<TraceIcon role={role} size="lg" />);
      expect(markup).toContain('aria-hidden="true"');
      return markup.match(/<path d="([^"]+)"/)[1];
    });
    expect(new Set(drawings).size).toBe(4);
  });

  test("every registered scientific role renders through ModuleIcon", () => {
    for (const role of MODULE_ICON_ROLES) {
      const markup = renderToStaticMarkup(<ModuleIcon role={role} />);
      expect(markup).toContain("scientific-icon");
      expect(markup).toContain("scientific-icon-core");
      expect(markup).toContain("scientific-icon-signal");
      expect(markup).not.toContain("scientific-icon-corner");
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

  test("GSEA uses one ranked-list enrichment drawing across module and navigation roles", () => {
    const moduleMarkup = renderToStaticMarkup(
      <ModuleIcon role="module.geneSetEnrichment" />,
    );
    const navigationMarkup = renderToStaticMarkup(
      <ModuleIcon role="navigation.gsea" frame="navigation" />,
    );
    expect(moduleMarkup).toContain("workflow-icon-gene-set-enrichment");
    expect(navigationMarkup).toContain("workflow-icon-gene-set-enrichment");
    expect(moduleMarkup).toContain("workflow-emphasis");
  });

  test("expression comparison uses one distribution drawing across module and navigation roles", () => {
    const moduleMarkup = renderToStaticMarkup(
      <ModuleIcon role="module.expressionComparison" />,
    );
    const navigationMarkup = renderToStaticMarkup(
      <ModuleIcon role="navigation.expressionComparison" frame="navigation" />,
    );
    expect(moduleMarkup).toContain("workflow-icon-expression-comparison");
    expect(navigationMarkup).toContain("workflow-icon-expression-comparison");
    expect(moduleMarkup).toContain("workflow-emphasis");
  });

  test("every scientific drawing stays inside the primitive budget", () => {
    // A framed glyph is drawn at 16 to 22 CSS pixels. Past about ten
    // primitives — every move command in every path plus every shape — the
    // strokes stop resolving and the icon reads as texture, which is what made
    // the previous set unreadable.
    const BUDGET = 10;

    expect(MODULE_ICON_ROLES.length).toBeGreaterThan(40);
    for (const role of MODULE_ICON_ROLES) {
      const markup = renderToStaticMarkup(
        <ModuleIcon role={role} frame="navigation" />,
      );
      const moveCommands = [...markup.matchAll(/\bd="([^"]*)"/g)].reduce(
        (total, [, commands]) => total + (commands.match(/[Mm]/g) || []).length,
        0,
      );
      const shapes = (markup.match(/<(circle|rect|ellipse|line|polyline|polygon)\b/g) || [])
        .length;
      const primitives = moveCommands + shapes;
      expect(primitives, `${role} draws ${primitives} primitives`).toBeLessThanOrEqual(
        BUDGET,
      );
    }
  });

  test("every navigation destination draws a distinct mark", () => {
    const navigationRoles = MODULE_ICON_ROLES.filter((role) =>
      role.startsWith("navigation."),
    );
    const drawings = navigationRoles.map((role) => {
      const markup = renderToStaticMarkup(<ModuleIcon role={role} frame="navigation" />);
      return markup.match(/workflow-icon-[a-z-]+/)[0];
    });

    // Two destinations that share a drawing cannot be told apart in the
    // sidebar, whatever their labels say.
    expect(new Set(drawings).size).toBe(drawings.length);
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
    ).toThrow("TRACE Explorer IconButton requires a specific accessible label");
  });

  test("unknown roles and arbitrary sizes fail loudly", () => {
    expect(() => renderToStaticMarkup(<TraceIcon role="action.unknown" />)).toThrow(
      "Unknown TRACE Explorer glyph icon role",
    );
    expect(() =>
      renderToStaticMarkup(<TraceIcon role="action.close" size="17" />),
    ).toThrow("Unsupported TRACE Explorer icon size");
    expect(() => renderToStaticMarkup(<ModuleIcon role="module.unknown" />)).toThrow(
      "Unknown TRACE Explorer module icon role",
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
