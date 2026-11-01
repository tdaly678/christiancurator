import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { dispatchBody, dispatchMorningRun, shouldDispatch } from "./ping.js";

function at(iso) {
  return new Date(iso);
}

test("winter 10:00 UTC is 5:00 AM EST and dispatches", () => {
  assert.equal(shouldDispatch(at("2026-11-15T10:00:00Z")), true);
});

test("winter 09:00 UTC is 4:00 AM EST and does not dispatch", () => {
  assert.equal(shouldDispatch(at("2026-11-15T09:00:00Z")), false);
});

test("4:50 AM ET is inside the window, 4:49 is not", () => {
  assert.equal(shouldDispatch(at("2026-11-15T09:49:00Z")), false);
  assert.equal(shouldDispatch(at("2026-11-15T09:50:00Z")), true);
});

test("summer 09:00 UTC is 5:00 AM EDT and dispatches", () => {
  assert.equal(shouldDispatch(at("2026-07-15T09:00:00Z")), true);
});

test("a few seconds before 5:00 AM EDT still dispatches", () => {
  assert.equal(shouldDispatch(at("2026-07-15T08:59:30Z")), true);
});

test("summer backup hours dispatch, 8:00 AM does not", () => {
  assert.equal(shouldDispatch(at("2026-07-15T10:00:00Z")), true);
  assert.equal(shouldDispatch(at("2026-07-15T11:00:00Z")), true);
  assert.equal(shouldDispatch(at("2026-07-15T11:59:00Z")), true);
  assert.equal(shouldDispatch(at("2026-07-15T12:00:00Z")), false);
});

test("fall-back morning 2026-11-01 10:00 UTC is 5:00 AM EST", () => {
  assert.equal(shouldDispatch(at("2026-11-01T10:00:00Z")), true);
  assert.equal(shouldDispatch(at("2026-11-01T09:00:00Z")), false);
});

test("spring-forward morning 2027-03-14 09:00 UTC is 5:00 AM EDT", () => {
  assert.equal(shouldDispatch(at("2027-03-14T09:00:00Z")), true);
});

test("dispatch body is a morning ping and cannot force or skip email", () => {
  const body = dispatchBody();
  assert.equal(body.ref, "main");
  assert.deepEqual(body.inputs, {
    morning: "true",
    force_email: "false",
    no_email: "false",
  });
});

test("dispatch posts that body to the daily_run workflow", async () => {
  const calls = [];
  await dispatchMorningRun("test-token", async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 204, text: async () => "" };
  });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /daily_run\.yml\/dispatches$/);
  assert.equal(calls[0].options.method, "POST");
  assert.equal(calls[0].options.headers.Authorization, "Bearer test-token");
  assert.deepEqual(JSON.parse(calls[0].options.body), dispatchBody());
});

test("the worker has no HTTP handler and the crons are the three UTC slots", () => {
  const source = readFileSync(new URL("./ping.js", import.meta.url), "utf8");
  const toml = readFileSync(new URL("./wrangler.toml", import.meta.url), "utf8");
  assert.equal(source.includes("async fetch"), false);
  assert.match(toml, /"0 9 \* \* \*"/);
  assert.match(toml, /"0 10 \* \* \*"/);
  assert.match(toml, /"0 11 \* \* \*"/);
});

test("a failed dispatch throws and does not include the token in the error", async () => {
  await assert.rejects(
    () => dispatchMorningRun("super-secret-token", async () => ({
      ok: false,
      status: 401,
      text: async () => "Bad credentials",
    })),
    (error) => {
      assert.match(error.message, /401/);
      assert.equal(error.message.includes("super-secret-token"), false);
      return true;
    },
  );
});
