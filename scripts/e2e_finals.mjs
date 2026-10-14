// Rendered-browser check of the finals demo path. Usage:
//   [CHROMIUM_PATH=<chrome binary>] PLAYWRIGHT_PATH=<dir containing the playwright package> BASE_URL=http://127.0.0.1:3000 OUT=<dir> node scripts/e2e_finals.mjs
// Start the backend with COPILOT_STATE pointing at a scratch file so demo reviews are not touched.
import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_PATH ? path.join(process.env.PLAYWRIGHT_PATH, "playwright") : "playwright");
const BASE = process.env.BASE_URL ?? "http://127.0.0.1:3000";
const OUT = process.env.OUT ?? "e2e-output";
mkdirSync(OUT, { recursive: true });

const results = [];
const errors = [];
function check(name, ok, detail = "") {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` - ${detail}` : ""}`);
}

async function login(page, role) {
  await page.goto(`${BASE}/login`);
  await page.fill("#username", role);
  await page.fill("#password", `${role}-demo`);
  await page.click('button[type="submit"]');
  await page.waitForURL("**/overview", { waitUntil: "commit", timeout: 60000 });
}

async function shot(page, name) {
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true });
}

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
for (const viewport of [{ width: 1440, height: 1000, tag: "desktop" }, { width: 390, height: 844, tag: "mobile" }]) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${viewport.tag}: ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${viewport.tag}: ${e.message}`));
  const v = viewport.tag;

  await login(page, "supervisor");
  await page.getByRole("heading", { name: "Problems across all customers" }).waitFor({ timeout: 60000 });
  await page.getByText("Customers in hardship with no plan yet").waitFor();
  check(`${v}: overview shows portfolio checks`, await page.getByText("Cases close to write-off").isVisible());
  await page.getByText("Definition and SQL").first().click();
  check(`${v}: check SQL is viewable`, await page.locator("pre").first().isVisible());
  await shot(page, `${v}-overview`);
  if (v === "desktop") {
    await page.addStyleTag({ content: "header.sticky { position: static !important; }" });
    await page.getByRole("heading", { name: "Problems across all customers" }).scrollIntoViewIfNeeded();
    await page.locator("section", { has: page.getByRole("heading", { name: "Problems across all customers" }) }).screenshot({ path: path.join(OUT, "overview-checks.png") });
  }

  await page.goto(`${BASE}/queue`);
  const queueRows = page.locator(v === "mobile" ? 'ol[aria-label="Work queue in urgency order"] > li' : "tbody tr");
  await queueRows.first().waitFor({ timeout: 60000 });
  const rows = await queueRows.count();
  check(`${v}: queue renders rows`, rows > 10, `${rows} rows`);
  check(`${v}: queue shows tier rule`, await page.getByText("Promise due soon").first().isVisible());
  const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  check(`${v}: no horizontal page scroll on queue`, noHScroll);
  await shot(page, `${v}-queue`);
  if (v === "desktop") await page.screenshot({ path: path.join(OUT, "queue-viewport.png") });

  for (const [cid, expected] of [
    ["JEV-1240", "Offer one of these hardship programmes first"],
    ["SAV-6847", "Ask for the payment, timed to their payday"],
    ["HAC-4447", "Don't contact this customer"],
  ]) {
    await page.goto(`${BASE}/briefs?customer=${cid}`);
    await page.getByRole("button", { name: "Prepare brief" }).click();
    await page.getByText("What to do, in order").waitFor({ timeout: 60000 });
    check(`${v}: brief ${cid} headline`, await page.getByText(expected).first().isVisible(), expected);
    if (cid === "SAV-6847") check(`${v}: holiday shown for ${cid}`, await page.getByText(/statutory holiday/).first().isVisible());
    if (v === "desktop") {
      // Element shots for the deck: the plan card alone, without the sticky sidebar.
      await page.addStyleTag({ content: "header.sticky { position: static !important; }" });
      const card = page.locator('[data-slot="card"]', { has: page.getByText("What to do, in order") }).first();
      await card.screenshot({ path: path.join(OUT, `plan-${cid}.png`) });
    }
    if (cid === "JEV-1240") check(`${v}: programmes listed for ${cid}`, await page.getByText("3-month reduced payment").first().isVisible());
    await shot(page, `${v}-brief-${cid}`);
  }

  await page.goto(`${BASE}/reviews`);
  await page.getByText(/Step-by-step plan/).first().waitFor({ timeout: 60000 });
  check(`${v}: review shows plan toggle`, true);
  await shot(page, `${v}-reviews`);

  await context.clearCookies();
  await page.evaluate(() => sessionStorage.clear());
  await login(page, "agent");
  await page.goto(`${BASE}/queue`);
  await page.getByText("Promise due soon").first().waitFor({ timeout: 60000 });
  check(`${v}: agent sees own queue without agent picker`, (await page.locator("#queue-agent").count()) === 0);
  check(`${v}: agent overview hides portfolio checks`, (await page.getByText("Problems across all customers").count()) === 0);
  await context.close();
}
await browser.close();

check("no console or page errors", errors.length === 0, errors.slice(0, 5).join(" | "));
writeFileSync(path.join(OUT, "results.json"), JSON.stringify({ results, errors }, null, 2));
process.exit(results.every((r) => r.ok) ? 0 : 1);
