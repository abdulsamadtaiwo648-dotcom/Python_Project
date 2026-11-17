// Run with: node cloudflare/worker.test.mjs
import assert from "node:assert/strict";
import worker from "./worker.js";

const calls = [];
globalThis.fetch = async (input, init = {}) => {
  const url = typeof input === "string" ? input : input.url;
  calls.push({ url, init });
  if (url.endsWith("/site/glow")) return new Response("<h1>Glow</h1>", { status: 200, headers: { "Set-Cookie": "x=1" } });
  if (url.endsWith("/site/nope")) return new Response("missing", { status: 404 });
  if (url.includes("/media/")) return new Response("img", { status: 200, headers: { "Content-Type": "image/png" } });
  return new Response("passthrough:" + url, { status: 200 });
};
const get = (u, init) => worker.fetch(new Request(u, init));

let r = await get("https://glow.solobiz.dev/");
assert.equal(r.status, 200); assert.equal(await r.text(), "<h1>Glow</h1>");
assert.equal(calls.at(-1).url, "https://solobiz.dev/site/glow");
assert.equal(r.headers.get("set-cookie"), null, "cookies are stripped");

calls.length = 0;
await get("https://glow.solobiz.dev/", { headers: { Cookie: "session=secret" } });
assert.equal(calls[0].init.headers.Cookie, undefined, "request cookies are not forwarded");

r = await get("https://glow.solobiz.dev/media/abcdefghijklmnopqrstu");
assert.equal(calls.at(-1).url, "https://solobiz.dev/media/abcdefghijklmnopqrstu");

for (const path of ["/login", "/dashboard", "/api/expenses", "/site/glow"]) {
  r = await get("https://glow.solobiz.dev" + path);
  assert.equal(r.status, 404, path + " is not served on a business address");
}
r = await get("https://glow.solobiz.dev/", { method: "POST" });
assert.equal(r.status, 404);

r = await get("https://nope.solobiz.dev/"); assert.equal(r.status, 404);
r = await get("https://nope.solobiz.dev/sitemap.xml"); assert.equal(r.status, 404);
r = await get("https://glow.solobiz.dev/sitemap.xml"); assert.match(await r.text(), /glow\.solobiz\.dev\//);
r = await get("https://glow.solobiz.dev/robots.txt"); assert.match(await r.text(), /Sitemap: https:\/\/glow\.solobiz\.dev\/sitemap\.xml/);

r = await get("https://www.solobiz.dev/login"); assert.equal(await r.text(), "passthrough:https://www.solobiz.dev/login");
r = await get("https://admin.solobiz.dev/"); assert.match(await r.text(), /^passthrough:/);
r = await get("https://solobiz.dev/"); assert.match(await r.text(), /^passthrough:/);
r = await get("https://-bad-.solobiz.dev/"); assert.equal(r.status, 404);
console.log("worker tests passed");
