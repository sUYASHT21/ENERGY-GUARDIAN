import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const USER = process.env.E2E_USER ?? "admin";
const PASSWORD = process.env.E2E_PASSWORD ?? "guardian-demo";

async function apiToken(request: APIRequestContext): Promise<string> {
  const r = await request.post("/api/v1/auth/login", { data: { username: USER, password: PASSWORD } });
  expect(r.ok()).toBeTruthy();
  return (await r.json()).access_token;
}

async function login(page: Page) {
  await page.goto("/");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Campus energy overview")).toBeVisible();
}

test.describe.configure({ mode: "serial" });

test("dashboard shows live backend data, labelled as simulated", async ({ page, request }) => {
  const token = await apiToken(request);
  const summary = await (await request.get("/api/v1/dashboard/summary", { headers: { Authorization: `Bearer ${token}` } })).json();
  await login(page);
  await expect(page.getByText("Simulation mode — data is synthetic")).toBeVisible();
  await expect(page.getByText("Hardware switching disabled")).toBeVisible();
  await expect(page.getByText("Live", { exact: true })).toBeVisible(); // websocket connected
  await expect(page.getByText(`${summary.rooms.occupied + summary.rooms.vacant + summary.rooms.unknown}`, { exact: false }).first()).toBeVisible();
  for (const room of ["CR-101 Lecture Hall", "LAB-202 Electronics Lab"]) {
    await expect(page.getByRole("link", { name: new RegExp(room) }).first()).toBeVisible();
  }
});

test("room page explains decisions with individual checks", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: /CR-102 Seminar Room/ }).first().click();
  await expect(page.getByRole("heading", { name: "CR-102 Seminar Room" })).toBeVisible();
  await page.getByRole("button", { name: /show decision checks for split ac/i }).click();
  await expect(page.getByText("Power data fresh").first()).toBeVisible();
  await expect(page.getByText("Not essential load").first()).toBeVisible();
});

test("sensor failure scenario raises a critical alert and blocks automation", async ({ page, request }) => {
  const token = await apiToken(request);
  const auth = { Authorization: `Bearer ${token}` };
  await login(page);
  await page.getByRole("link", { name: "Simulation" }).click();
  await page.getByLabel("Scenario for HST-A12 Hostel Room").selectOption("sensor_failure");
  await page.getByRole("link", { name: /^Alerts/ }).click();
  await expect(page.getByText("Occupancy sensor failure in HST-A12 Hostel Room").first()).toBeVisible({ timeout: 30_000 });
  const rooms = await (await request.get("/api/v1/rooms", { headers: auth })).json();
  const hst = rooms.find((r: { name: string }) => r.name.startsWith("HST-A12"));
  expect(hst.occupancy_state).toBe("unknown");
  // restore
  await request.post("/api/v1/simulation/scenario", { headers: auth, data: { room_id: hst.id, scenario: "normal" } });
});

test("auto mode sends simulated commands that are acknowledged", async ({ page, request }) => {
  const token = await apiToken(request);
  const auth = { Authorization: `Bearer ${token}` };
  const rooms = await (await request.get("/api/v1/rooms", { headers: auth })).json();
  const cr102 = rooms.find((r: { name: string }) => r.name.startsWith("CR-102"));
  // reset CR-102 to "vacant waste" so appliances are left on again
  await request.post("/api/v1/simulation/scenario", { headers: auth, data: { room_id: cr102.id, scenario: "vacant_waste" } });
  await request.put("/api/v1/settings", { headers: auth, data: { auto_command_cooldown_minutes: 0 } });
  await login(page);
  await page.getByRole("link", { name: "Settings" }).click();
  page.on("dialog", (d) => d.accept());
  await page.getByRole("radio", { name: /^Automatic/ }).check();
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Automation: auto")).toBeVisible();
  await page.getByRole("link", { name: "Commands" }).click();
  await expect(page.getByRole("cell", { name: "acknowledged" }).first()).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("cell", { name: "simulated" }).first()).toBeVisible();
  // restore safe defaults
  await request.put("/api/v1/settings", { headers: auth, data: { automation_mode: "dry_run", auto_command_cooldown_minutes: 5 } });
});
