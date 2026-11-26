// Runs the frontend unit tests: each src/*.test.ts is bundled with esbuild and run by Node's test runner.
import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const out = join(root, ".test-build");
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });

const files = readdirSync(join(root, "src")).filter((f) => f.endsWith(".test.ts"));
for (const f of files) {
  await build({
    entryPoints: [join(root, "src", f)],
    bundle: true,
    platform: "node",
    format: "esm",
    outfile: join(out, f.replace(/\.ts$/, ".mjs")),
    logLevel: "warning",
  });
}
execFileSync(process.execPath, ["--test", ...files.map((f) => join(out, f.replace(/\.ts$/, ".mjs")))], { stdio: "inherit" });
