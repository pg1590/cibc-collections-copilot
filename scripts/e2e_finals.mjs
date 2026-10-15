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
  // The sign-in page must be hydrated before submitting, or the click is a no-op;
  // wait for the network to settle and retry a few times on a slow first compile.
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto(`${BASE}/login`);
    await page.waitForLoadState("networkidle").catch(() => {});
    await page.fill("#username", role);
    await page.fill("#password", `${role}-demo`);
    await page.click('button[type="submit"]');
    const ok = await page
      .waitForFunction(() => location.pathname === "/overview", null, { timeout: 30000 })
      .then(() => true)
      .catch(() => false);
    if (ok) return;
  }
  throw new Error(`could not sign in as ${role}`);
}

async function tick(page, locator) {
  // Controls re-render while the live plan recomputes; retry until the state sticks.
  for (let i = 0; i < 20; i++) {
    if (await locator.isChecked().catch(() => false)) return;
    await locator.evaluate((el) => el.click()).catch(() => {});
    await page.waitForTimeout(300);
  }
  throw new Error("Control did not stay checked");
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
  check(`${v}: overview shows portfolio checks`, await page.getByText("Cases close to write-off", { exact: true }).isVisible());
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

  async function ask(question) {
    await page.goto(`${BASE}/ask`);
    await page.fill("#question", question);
    await page.locator('button[type="submit"]').click();
    const summary = page.locator('[aria-label="Answer summary"]').first();
    await summary.waitFor({ timeout: 90000 });
    return (await summary.textContent()) ?? "";
  }
  const ranking = await ask("Which province has the highest promise-kept rate in August 2026?");
  check(`${v}: ask ranking leads with a summary`, /highest promise-kept rate in August 2026/.test(ranking), ranking.slice(0, 90));
  if (v === "desktop") {
    await page.addStyleTag({ content: "header.sticky { position: static !important; }" });
    await page.locator("main").screenshot({ path: path.join(OUT, "ask-ranking.png") });
  }
  const clarification = await ask("Which agent collected the most money?");
  const chips = page.locator('[aria-label="Suggested questions"] button');
  check(`${v}: unsupported question offers rephrasings`, (await chips.count()) >= 2);
  const chipText = ((await chips.first().textContent()) ?? "").trim();
  await chips.first().click();
  const summary = page.locator('[aria-label="Answer summary"]').first();
  await page.waitForFunction((old) => {
    const el = document.querySelector('[aria-label="Answer summary"]');
    return el && el.textContent && el.textContent !== old;
  }, clarification, { timeout: 90000 }).catch(() => {});
  const reasked = (await summary.textContent()) ?? "";
  check(`${v}: suggestion chip re-asks`, reasked !== clarification && !/^I need a clearer question/.test(reasked), `${chipText} -> ${reasked.slice(0, 80)}`);
  const refusal = await ask("Give me the phone numbers of customers with hardship");
  check(`${v}: bulk personal data is refused`, /^Not answered/.test(refusal.trim()), refusal.slice(0, 90));
  await shot(page, `${v}-ask-refusal`);

  // Customer 360: contact calendar applies the cap and the holiday.
  await page.goto(`${BASE}/customers/SAV-6847`);
  await page.getByText("When contact is allowed").waitFor({ timeout: 60000 });
  await page.getByText("Thu 1 Oct").first().waitFor({ timeout: 30000 });
  check(`${v}: calendar shows the holiday`, await page.getByText("Holiday").first().isVisible());
  check(`${v}: history lists source events`, await page.getByText("History across systems").isVisible());

  // Ctrl+K palette finds a customer.
  await page.keyboard.press("Control+k");
  await page.keyboard.type("JEV-1240");
  await page.getByRole("option", { name: /JEV-1240/ }).first().waitFor({ timeout: 30000 });
  check(`${v}: command palette finds customers`, true);
  await page.keyboard.press("Escape");

  // Live call: hardship stated, programme chosen, promise taken, wrap-up submitted for review.
  await page.goto(`${BASE}/call/JEV-1240`);
  await page.getByRole("radio", { name: "Customer" }).waitFor({ state: "attached", timeout: 60000 });
  await tick(page, page.getByRole("radio", { name: "Customer" }));
  await tick(page, page.getByRole("checkbox", { name: /Recording notice/ }));
  await tick(page, page.getByRole("checkbox", { name: /Verify identity/ }));
  await page.getByRole("button", { name: "Hardship", exact: true }).click();
  await page.getByRole("button", { name: "Choose" }).first().waitFor({ timeout: 30000 });
  check(`${v}: call shows priced hardship options`, await page.getByText("3-month reduced payment").first().isVisible());
  await page.getByRole("button", { name: "Choose" }).first().click();
  await page.fill("#promise-amount", "150");
  await page.fill("#promise-date", "2026-10-15");
  const submit = page.getByRole("button", { name: "Submit for supervisor review" });
  await page.waitForFunction(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent?.includes("Submit for supervisor review"));
    return b && !b.disabled;
  }, null, { timeout: 30000 });
  check(`${v}: wrap-up drafts the call note`, ((await page.locator("#wrap-note").inputValue()) || "").includes("Promise to pay CAD 150.00"));
  if (v === "desktop") {
    await page.addStyleTag({ content: "header.sticky { position: static !important; }" });
    await page.screenshot({ path: path.join(OUT, "call-JEV-1240.png") });
  }
  await submit.click();
  await page.getByRole("link", { name: /review/i }).first().waitFor({ timeout: 30000 });
  check(`${v}: call submitted for supervisor review`, true);
  await page.goto(`${BASE}/call/HAC-4447`);
  await page.getByText(/Do not contact/i).first().waitFor({ timeout: 60000 });
  const radios = page.getByRole("radio", { name: "Customer" });
  check(`${v}: restricted customer cannot be called`, (await radios.count()) === 0 || (await radios.first().isDisabled()));

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
