import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../../functions/api/dashboard-read-api.js", import.meta.url), "utf8");
const moduleUrl = "data:text/javascript;base64," + Buffer.from(source).toString("base64");
const { handleDashboardRequest } = await import(moduleUrl);
const origin = "https://crypto-market-intelligence.bool.so";

test("rejects non-dashboard origins", async () => {
  const response = await handleDashboardRequest(
    new Request("https://proxy.example/api/dashboard-read-api", {
      headers: { Origin: "https://attacker.example" },
    }),
    {},
    async () => { throw new Error("must_not_call_upstream"); },
  );
  assert.equal(response.status, 403);
  assert.equal((await response.json()).error, "ORIGIN_NOT_ALLOWED");
});

test("fails closed when server-side secrets are not configured", async () => {
  const response = await handleDashboardRequest(
    new Request("https://proxy.example/api/dashboard-read-api", {
      headers: { Origin: origin },
    }),
    {},
    async () => { throw new Error("must_not_call_upstream"); },
  );
  assert.equal(response.status, 503);
  assert.equal((await response.json()).error, "SERVER_PROXY_NOT_CONFIGURED");
});

test("forwards the server-side key and returns upstream response", async () => {
  let observed;
  const response = await handleDashboardRequest(
    new Request("https://proxy.example/api/dashboard-read-api", {
      headers: { Origin: origin, Accept: "application/json" },
    }),
    {
      ACTIVEPIECES_DASHBOARD_WEBHOOK_URL: "https://example.activepieces.test/sync",
      ACTIVEPIECES_DASHBOARD_API_KEY: "a".repeat(48),
    },
    async (url, options) => {
      observed = { url, options };
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    },
  );
  assert.equal(observed.url, "https://example.activepieces.test/sync");
  assert.equal(observed.options.headers["X-Api-Key"], "a".repeat(48));
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true });
  assert.equal(response.headers.get("Access-Control-Allow-Origin"), origin);
});

test("does not require or accept a browser-supplied API key", async () => {
  let observed;
  const response = await handleDashboardRequest(
    new Request("https://proxy.example/api/dashboard-read-api", {
      headers: { Origin: origin },
    }),
    {
      ACTIVEPIECES_DASHBOARD_WEBHOOK_URL: "https://example.activepieces.test/sync",
      ACTIVEPIECES_DASHBOARD_API_KEY: "b".repeat(48),
    },
    async (_url, options) => {
      observed = options.headers["X-Api-Key"];
      return new Response("unauthorized", { status: 401 });
    },
  );
  assert.equal(observed, "b".repeat(48));
  assert.equal(response.status, 401);
});
