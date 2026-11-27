// End-to-end checks for the SoloBiz app, run in a real browser.
//
//   BASE_URL=http://localhost:8000 OWNER_EMAIL=owner@example.com OWNER_PASSWORD=... \
//     node e2e/app.e2e.mjs
//
// Needs Playwright (npm i -D playwright && npx playwright install chromium).
// Creates one staff account and one sale and one expense on the owner's business.

import { chromium } from "playwright";

const BASE = (process.env.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const OWNER = { email: process.env.OWNER_EMAIL, password: process.env.OWNER_PASSWORD };
if (!OWNER.email || !OWNER.password) {
  console.error("Set OWNER_EMAIL and OWNER_PASSWORD.");
  process.exit(2);
}

let failures = 0;
const check = (label, ok) => {
  console.log(ok ? "PASS" : "FAIL", label);
  if (!ok) failures++;
};

async function signIn(page, email, password) {
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button.login-submit");
  await page.waitForURL((u) => !u.toString().includes("/login"), { timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(500);
}

const browser = await chromium.launch();
const errors = [];
const watch = (page, who) => {
  page.on("pageerror", (e) => errors.push(`${who}: ${e.message}`));
};

try {
  // ---- owner -------------------------------------------------------------
  const ownerCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const owner = await ownerCtx.newPage();
  watch(owner, "owner");
  await signIn(owner, OWNER.email, OWNER.password);
  check("owner signs in", owner.url().includes("/dashboard"));

  await owner.goto(`${BASE}/team`, { waitUntil: "networkidle" });
  await owner.click('button:has-text("+ Add staff")');
  const staffEmail = `e2e.staff.${Date.now()}@example.com`;
  await owner.fill("#staff-name", "E2E Sales");
  await owner.fill("#staff-email", staffEmail);
  await owner.fill("#staff-password", "Staff1234");
  await owner.check("input[name=role][value=sales]");
  await owner.click(".sb-sheet-foot button[type=submit]");
  await owner.waitForTimeout(800);
  check("owner adds a sales staff member", (await owner.textContent(".sb-list-card")).includes("E2E Sales"));

  await owner.goto(`${BASE}/inventory`, { waitUntil: "networkidle" });
  await owner.click("#btn-manage-presets");
  const product = `E2E item ${Date.now() % 100000}`;
  await owner.fill("#inventory-edit-name", product);
  await owner.fill("#inventory-edit-price", "1500");
  await owner.fill("#inventory-edit-stock", "10");
  await owner.click(".sb-sheet-foot button[type=submit]");
  await owner.waitForTimeout(800);

  // ---- sales staff -------------------------------------------------------
  const staffCtx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const staff = await staffCtx.newPage();
  watch(staff, "staff");
  await signIn(staff, staffEmail, "Staff1234");
  check("sales staff lands on Sales", staff.url().endsWith("/sales"));
  for (const path of ["/inventory", "/team", "/plans", "/expenses"]) {
    await staff.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
    await staff.waitForTimeout(400);
    check(`sales staff cannot open ${path}`, staff.url().endsWith("/sales"));
  }
  await staff.goto(`${BASE}/sales`, { waitUntil: "networkidle" });
  await staff.waitForTimeout(500);
  check("sales staff has no Delete button", (await staff.locator("button.btn-delete-income").count()) === 0);

  await staff.click('button[aria-label="New sale"]').catch(() => {});
  await staff.waitForTimeout(400);
  await staff.click("#sales-product-open").catch(() => {});
  await staff.waitForTimeout(300);
  const options = await staff.$$eval("[data-product-id]", (o) => o.map((x) => [x.getAttribute("data-product-id"), x.textContent]));
  const pick = options.find((o) => o[1].includes(product));
  check("staff sees the owner's product", !!pick);
  if (pick) {
    await staff.click(`[data-product-id="${pick[0]}"]`);
    await staff.fill("#income-customer-name", "E2E Customer");
    await staff.click("#sale-entry-card button[type=submit]");
    await staff.waitForTimeout(1200);
    check("sales staff records a sale", (await staff.textContent("#income-list")).includes("E2E Customer"));
  }

  // ---- owner sees it and can delete it ----------------------------------
  await owner.goto(`${BASE}/sales`, { waitUntil: "networkidle" });
  await owner.waitForTimeout(600);
  check("owner sees the staff member's sale", (await owner.textContent("#income-list")).includes("E2E Customer"));
  check("owner has Delete buttons", (await owner.locator("button.btn-delete-income").count()) > 0);

  console.log(errors.length ? `Page errors: ${errors.join(" | ")}` : "No page errors.");
  if (errors.length) failures++;
} finally {
  await browser.close();
}
console.log(failures ? `${failures} check(s) failed.` : "All checks passed.");
process.exit(failures ? 1 : 0);
