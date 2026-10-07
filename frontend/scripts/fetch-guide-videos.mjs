import { createHash } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { readFile, mkdir, rename, rm, stat } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../public/tutorial-videos/", import.meta.url));
const base = "https://apps.cienciavida.org/tcga_explorer/tutorial-videos/";
const mode = process.argv[2] || "fetch";
if (!["fetch", "--check", "--list"].includes(mode) || process.argv.length > 3) {
  throw new Error("Usage: node scripts/fetch-guide-videos.mjs [--check|--list]");
}
const manifest = JSON.parse(await readFile(resolve(root, "manifest.json"), "utf8"));

async function matches(path, row) {
  try {
    if ((await stat(path)).size !== row.bytes) return false;
    const hash = createHash("sha256");
    for await (const chunk of createReadStream(path)) hash.update(chunk);
    return hash.digest("hex") === row.sha256;
  } catch (error) {
    if (error.code === "ENOENT") return false;
    throw error;
  }
}

let missing = 0;
for (const row of manifest) {
  const target = resolve(root, row.path);
  if (!target.startsWith(resolve(root) + sep) || !row.path.endsWith(".mp4") ||
      !Number.isSafeInteger(row.bytes) || row.bytes <= 0 ||
      !/^[a-f0-9]{64}$/.test(row.sha256)) {
    throw new Error("Invalid video manifest entry");
  }
  if (mode === "--list") {
    console.log(`${row.path} (${row.bytes} bytes)`);
    continue;
  }
  if (await matches(target, row)) {
    console.log(`Verified ${row.path}`);
    continue;
  }
  if (mode === "--check") {
    console.error(`Missing or mismatched: ${row.path}`);
    missing++;
    continue;
  }
  await mkdir(dirname(target), { recursive: true });
  const temporary = `${target}.part-${process.pid}`;
  try {
    const response = await fetch(new URL(row.path, base), { signal: AbortSignal.timeout(600_000) });
    if (!response.ok || !response.body || !response.url.startsWith("https://")) {
      throw new Error(`Video download failed: HTTP ${response.status}`);
    }
    let received = 0;
    const hash = createHash("sha256");
    const meter = new Transform({ transform(chunk, _encoding, done) {
      received += chunk.length;
      if (received > row.bytes) return done(new Error("Video exceeds manifest size"));
      hash.update(chunk);
      done(null, chunk);
    } });
    await pipeline(Readable.fromWeb(response.body), meter, createWriteStream(temporary, { flags: "wx" }));
    if (received !== row.bytes || hash.digest("hex") !== row.sha256) {
      throw new Error(`Size or checksum mismatch: ${row.path}`);
    }
    await rename(temporary, target);
    console.log(`Downloaded and verified ${row.path}`);
  } finally {
    await rm(temporary, { force: true });
  }
}
if (missing) process.exitCode = 1;
