/**
 * Cloudflare cron ping for the Daily Curator Run.
 *
 * Cloudflare cron is UTC-only. Three triggers cover 5:00, 6:00, and 7:00 AM
 * America/New_York across EST and EDT. This module dispatches GitHub
 * workflow_dispatch only inside 4:50–8:00 AM Eastern. There is no fetch
 * handler: the workers.dev URL must not be able to start a run.
 *
 * Setup (one time, after the workflow on main accepts the `morning` input):
 * .github/morning-trigger.md
 */

const DISPATCH_URL =
  "https://api.github.com/repos/tdaly678/christiancurator/actions/workflows/daily_run.yml/dispatches";

// 4:50 AM inclusive, 8:00 AM exclusive. A few seconds of cron earliness still
// falls inside the window; the winter 4:00 AM UTC slot does not.
const WINDOW_START = 4 * 60 + 50;
const WINDOW_END = 8 * 60;

export function etMinutes(now) {
  const fmt = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(
    fmt.formatToParts(now).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]),
  );
  let hour = Number(parts.hour);
  const minute = Number(parts.minute);
  if (hour === 24) hour = 0;
  if (!Number.isInteger(hour) || !Number.isInteger(minute)) {
    throw new Error(`could not read America/New_York time from ${now.toISOString()}`);
  }
  return hour * 60 + minute;
}

export function shouldDispatch(now) {
  const minute = etMinutes(now);
  return minute >= WINDOW_START && minute < WINDOW_END;
}

export function dispatchBody() {
  return {
    ref: "main",
    inputs: {
      morning: "true",
      force_email: "false",
      no_email: "false",
    },
  };
}

export async function dispatchMorningRun(token, fetchImpl = fetch) {
  const response = await fetchImpl(DISPATCH_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "Content-Type": "application/json",
      "User-Agent": "christian-curator-morning-ping",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(dispatchBody()),
  });
  if (!response.ok) {
    const text = typeof response.text === "function" ? await response.text() : "";
    throw new Error(`GitHub dispatch failed: ${response.status} ${String(text).slice(0, 300)}`);
  }
}

export default {
  async scheduled(_event, env) {
    const now = new Date();
    if (!shouldDispatch(now)) {
      console.log("morning ping skipped: outside 4:50–8:00 AM America/New_York");
      return;
    }
    if (!env || !env.GITHUB_DISPATCH_TOKEN) {
      throw new Error("GITHUB_DISPATCH_TOKEN is not set");
    }
    await dispatchMorningRun(env.GITHUB_DISPATCH_TOKEN);
    console.log("morning ping dispatched workflow_dispatch morning=true");
  },
};
