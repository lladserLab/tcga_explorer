import { chromium } from "playwright";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicRoot = path.join(frontendRoot, "public");
const markSource = path.join(publicRoot, "brand", "trace-mark.svg");
const maskableSource = path.join(publicRoot, "brand", "trace-mark-maskable.svg");
const socialSource = path.join(publicRoot, "social", "trace-explorer-card-v1.svg");
const fontSource = path.join(
  frontendRoot,
  "node_modules",
  "@fontsource-variable",
  "ibm-plex-sans",
  "files",
  "ibm-plex-sans-latin-wght-normal.woff2",
);

const outputs = {
  favicon16: path.join(publicRoot, "favicon-16x16.png"),
  favicon32: path.join(publicRoot, "favicon-32x32.png"),
  favicon48: path.join(publicRoot, "favicon-48x48.png"),
  faviconIco: path.join(publicRoot, "favicon.ico"),
  apple: path.join(publicRoot, "apple-touch-icon.png"),
  icon192: path.join(publicRoot, "icons", "trace-icon-192.png"),
  icon512: path.join(publicRoot, "icons", "trace-icon-512.png"),
  maskable512: path.join(publicRoot, "icons", "trace-maskable-512.png"),
  thumbnail: path.join(publicRoot, "brand", "trace-thumbnail.png"),
  social: path.join(publicRoot, "social", "trace-explorer-card-v1.png"),
};

await mkdir(path.join(publicRoot, "icons"), { recursive: true });

const [markSvg, maskableSvg, socialSvg, fontBytes] = await Promise.all([
  readFile(markSource, "utf8"),
  readFile(maskableSource, "utf8"),
  readFile(socialSource, "utf8"),
  readFile(fontSource),
]);

const browser = await chromium.launch({ headless: true });

async function renderSvg(svg, width, height, output, { font = false } = {}) {
  const page = await browser.newPage({
    viewport: { width, height },
    deviceScaleFactor: 1,
  });
  const fontFace = font
    ? `@font-face{font-family:'IBM Plex Sans';src:url(data:font/woff2;base64,${fontBytes.toString("base64")}) format('woff2');font-style:normal;font-weight:100 900;font-display:block;}`
    : "";
  await page.setContent(`<!doctype html><html><head><style>${fontFace}*{box-sizing:border-box}html,body{margin:0;width:${width}px;height:${height}px;overflow:hidden}svg{display:block;width:${width}px;height:${height}px}</style></head><body>${svg}</body></html>`);
  if (font) await page.evaluate(() => document.fonts.ready);
  await page.locator("svg").screenshot({ path: output, omitBackground: false });
  await page.close();
}

try {
  await renderSvg(markSvg, 16, 16, outputs.favicon16);
  await renderSvg(markSvg, 32, 32, outputs.favicon32);
  await renderSvg(markSvg, 48, 48, outputs.favicon48);
  await renderSvg(markSvg, 180, 180, outputs.apple);
  await renderSvg(markSvg, 192, 192, outputs.icon192);
  await renderSvg(markSvg, 512, 512, outputs.icon512);
  await renderSvg(maskableSvg, 512, 512, outputs.maskable512);
  await renderSvg(markSvg, 512, 512, outputs.thumbnail);
  await renderSvg(socialSvg, 1200, 630, outputs.social, { font: true });
} finally {
  await browser.close();
}

function createIco(images) {
  const headerSize = 6;
  const directorySize = images.length * 16;
  let offset = headerSize + directorySize;
  const header = Buffer.alloc(headerSize);
  header.writeUInt16LE(0, 0);
  header.writeUInt16LE(1, 2);
  header.writeUInt16LE(images.length, 4);
  const entries = images.map(({ size, data }) => {
    const entry = Buffer.alloc(16);
    entry.writeUInt8(size === 256 ? 0 : size, 0);
    entry.writeUInt8(size === 256 ? 0 : size, 1);
    entry.writeUInt8(0, 2);
    entry.writeUInt8(0, 3);
    entry.writeUInt16LE(1, 4);
    entry.writeUInt16LE(32, 6);
    entry.writeUInt32LE(data.length, 8);
    entry.writeUInt32LE(offset, 12);
    offset += data.length;
    return entry;
  });
  return Buffer.concat([header, ...entries, ...images.map(({ data }) => data)]);
}

const icoImages = await Promise.all([
  [16, outputs.favicon16],
  [32, outputs.favicon32],
  [48, outputs.favicon48],
].map(async ([size, filename]) => ({ size, data: await readFile(filename) })));
await writeFile(outputs.faviconIco, createIco(icoImages));

console.log("TRACE Explorer brand assets generated.");
