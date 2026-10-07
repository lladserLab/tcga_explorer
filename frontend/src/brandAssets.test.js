import { readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const publicPath = (relative) => fileURLToPath(new URL(`../public/${relative}`, import.meta.url));
const frontendPath = (relative) => fileURLToPath(new URL(`../${relative}`, import.meta.url));

function pngSize(relative) {
  const payload = readFileSync(publicPath(relative));
  expect(payload.subarray(1, 4).toString("ascii")).toBe("PNG");
  return {
    width: payload.readUInt32BE(16),
    height: payload.readUInt32BE(20),
  };
}

describe("TRACE Explorer brand assets", () => {
  it("keeps one simple, named SVG master mark", () => {
    const mark = readFileSync(publicPath("brand/trace-mark.svg"), "utf8");
    expect(mark).toContain("A T continuing into a stepped analytical trace");
    expect(mark).toContain('viewBox="0 0 64 64"');
    expect(mark.match(/<(?:path|rect|circle)\b/g)).toHaveLength(3);
    expect(mark).not.toMatch(/helix|dna/i);
  });

  it("ships correctly sized raster derivatives", () => {
    expect(pngSize("favicon-16x16.png")).toEqual({ width: 16, height: 16 });
    expect(pngSize("favicon-32x32.png")).toEqual({ width: 32, height: 32 });
    expect(pngSize("favicon-48x48.png")).toEqual({ width: 48, height: 48 });
    expect(pngSize("apple-touch-icon.png")).toEqual({ width: 180, height: 180 });
    expect(pngSize("icons/trace-icon-192.png")).toEqual({ width: 192, height: 192 });
    expect(pngSize("icons/trace-icon-512.png")).toEqual({ width: 512, height: 512 });
    expect(pngSize("icons/trace-maskable-512.png")).toEqual({ width: 512, height: 512 });
    expect(pngSize("brand/trace-thumbnail.png")).toEqual({ width: 512, height: 512 });
    expect(pngSize("social/trace-explorer-card-v1.png")).toEqual({ width: 1200, height: 630 });
    expect(readFileSync(publicPath("icons/trace-maskable-512.png"))).not.toEqual(
      readFileSync(publicPath("icons/trace-icon-512.png")),
    );
  });

  it("packages a multiframe favicon", () => {
    const icon = readFileSync(publicPath("favicon.ico"));
    expect(icon.readUInt16LE(0)).toBe(0);
    expect(icon.readUInt16LE(2)).toBe(1);
    expect(icon.readUInt16LE(4)).toBe(3);
    expect([icon[6], icon[22], icon[38]]).toEqual([16, 32, 48]);
    expect(statSync(publicPath("favicon.ico")).size).toBeGreaterThan(500);
  });

  it("keeps the install manifest scoped to the deployed base path", () => {
    const manifest = JSON.parse(readFileSync(publicPath("site.webmanifest"), "utf8"));
    expect(manifest.name).toBe("TRACE Explorer");
    expect(manifest.id).toBe("./");
    expect(manifest.start_url).toBe("./");
    expect(manifest.scope).toBe("./");
    expect(manifest.icons.map(({ sizes, purpose }) => [sizes, purpose])).toEqual([
      ["192x192", "any"],
      ["512x512", "any"],
      ["512x512", "maskable"],
    ]);
    manifest.icons.forEach(({ src }) => expect(statSync(publicPath(src)).isFile()).toBe(true));
  });

  it("binds every browser asset through Vite's base path", () => {
    const html = readFileSync(frontendPath("index.html"), "utf8");
    [
      "brand/trace-mark.svg",
      "favicon.ico",
      "apple-touch-icon.png",
      "site.webmanifest",
    ].forEach((asset) => expect(html).toContain(`%BASE_URL%${asset}`));
    expect(html).toContain("https://apps.cienciavida.org/tcga_explorer/social/trace-explorer-card-v1.png");
    expect(html).toContain('name="twitter:card" content="summary_large_image"');
  });
});
