# 5:00 AM Eastern trigger

The Daily Curator Run should start near **5:00 AM America/New_York** every day, send the email once, and stay on that clock when daylight saving time starts and ends. November through early March that is 10:00 UTC. Mid-March through early November that is 09:00 UTC.

Two mechanisms do this. Only the first one is live when the workflow change is merged.

## What is live on merge

`.github/workflows/daily_run.yml` schedules four runs:

| Cron | Clock | Role |
| --- | --- | --- |
| `7 5 * * *` with `timezone: America/New_York` | 5:07 AM ET all year | Primary. Minute 7 stays off the top of the hour, which GitHub documents as the busiest time. |
| `17 6 * * *` with the same timezone | 6:17 AM ET | Catch-up if GitHub dropped the 5:07 run. |
| `37 8 * * *` with the same timezone | 8:37 AM ET | Last morning catch-up. |
| `7 10 * * *` with no timezone | 10:07 UTC | 5:07 AM EST, or 6:07 AM EDT. Safety net if GitHub ever ignored the timezone field and fired the other slots overnight. |

GitHub added the `timezone` field in March 2026. On the spring-forward Sunday, a schedule that falls in the skipped 2:00 AM hour moves forward. 5:07 AM is not in that hour, so the primary slot does not move.

This is still GitHub's scheduler. [GitHub's docs](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows) say a `schedule` run can start late when Actions is busy, and that a queued run can be dropped without a failed job. That is what happened at the end of October 2026: the Oct 31 run started around 10:35 AM ET instead of the old 6:00 AM EDT target, and the Nov 1 run had not started by about 6:44 AM ET. The new slots make a dropped 5:07 less likely to lose the whole morning. They do not make 5:00 AM punctual. The Cloudflare ping below is what does that, and it does nothing until you deploy it.

The pipeline job sets `TZ=America/New_York`, so the archive folder, the email date, and the commit subject use the Eastern calendar. At 5:00 AM that is the same date as UTC. It matters only if a catch-up is delivered after midnight UTC (8:00 PM EST / 9:00 PM EDT).

## What you still have to turn on

The Cloudflare Worker in `worker/morning/` is in the repo and is **not deployed**. Nothing calls GitHub at 5:00:00 AM until you do the steps below. Do them after this change is on `main`. Dispatching before that uses the old workflow, which has no same-morning guard.

You already have a Cloudflare account for the signup worker (`worker/`, name `cc-subscribe`). This is a second worker, `cc-morning-ping`, so a bad deploy cannot take the signup form down. Workers Free includes cron triggers: **5 per account**. This worker uses 3. The signup worker uses none. Two slots stay free. If a deploy says the cron limit is reached, stop and check the account before adding more.

Cloudflare cron is UTC-only. The worker fires at 09:00, 10:00, and 11:00 UTC and calls GitHub only when Eastern time is inside 4:50–8:00 AM:

| UTC cron | EST (winter) | EDT (summer) |
| --- | --- | --- |
| 09:00 | 4:00 AM, no dispatch | 5:00 AM, dispatch |
| 10:00 | 5:00 AM, dispatch | 6:00 AM, backup dispatch |
| 11:00 | 6:00 AM, backup dispatch | 7:00 AM, backup dispatch |

A backup dispatch the same morning no-ops in GitHub if the first one already published. There is no HTTP handler, so the `workers.dev` URL cannot start a run.

### 1. Create a fine-grained personal access token

GitHub → Settings → Developer settings → Fine-grained tokens → Generate.

- Resource owner: the account that can write to `tdaly678/christiancurator`
- Repository access: **only** `christiancurator`
- Permissions: **Actions → Read and write**. Nothing else. This can start a workflow. It cannot push commits.
- Expiration: 1 year is reasonable. Put a reminder on the calendar a week before it expires. When it expires the Cloudflare ping stops and the GitHub schedule is the only trigger again.

Do not use a classic token. The classic `workflow` scope is broader than this. Do not commit the token, do not put it in `wrangler.toml`, and do not paste it into a GitHub secret. It lives only as a Cloudflare secret.

### 2. Deploy the worker

From a checkout of `main` that contains `worker/morning/`:

```bash
cd worker/morning
npx wrangler login
npx wrangler secret put GITHUB_DISPATCH_TOKEN
npx wrangler deploy
```

`wrangler login` opens a browser. `secret put` prompts for the token and stores it encrypted on Cloudflare. Confirm the dashboard shows worker `cc-morning-ping` with cron triggers `0 9 * * *`, `0 10 * * *`, and `0 11 * * *`.

Run `npx wrangler deploy` from `worker/morning`, not from `worker/`. The parent directory is the signup worker.

### 3. Prove the ping without sending a second email

Wait until today's archive is already on main (`docs/archive/YYYY-MM-DD/index.html` for today's Eastern date). Then either:

- Actions → Daily Curator Run → Run workflow, set **morning** to true, leave the other boxes off, or
- let the next Cloudflare slot inside 4:50–8:00 AM ET fire.

The run should be green, the guard reason should be `already_published`, and the `run-pipeline` job should be skipped. You should not get another email.

Do not dispatch `morning=true` on a morning that has not published yet unless you want the real email to go out. The ping always takes the normal email path. `no_email` and `force_email` are ignored when `morning` is true, so a ping cannot suppress the send or force a duplicate.

## Same-morning guard

`scripts/morning_guard.py` runs before the pipeline. It fetches `origin/main` and looks for `docs/archive/<Eastern date>/index.html`. Concurrency group `daily-curator-morning` queues a second arrival instead of cancelling the one in progress (`cancel-in-progress: false`), so the second one sees the first one's commit.

| Arrival | Today's archive already on main | Result |
| --- | --- | --- |
| 5:07 AM ET schedule, or the 5:00 AM ping | no | Publish and send email (`on_time`) |
| Any later automatic arrival the same Eastern day | yes | No-op (`already_published`). No second publish, no second email. |
| Automatic arrival at or after 6:00 AM ET | no | Publish and send (`late_catchup`). The day is not dropped. |
| Automatic arrival before 4:50 AM ET | no | No-op (`too_early`). This is how an overnight UTC misfire is refused. |
| Actions button, both flags off | yes | No-op |
| Actions button, both flags off | no | Publish and send (`manual`) |
| `force_email` (morning left off) | yes or no | Publish and send again |
| `no_email` (morning left off) | yes or no | Republish, no email. Wins over `force_email`. |

A skip exits 0. The workflow is green and `run-pipeline` is skipped. That is a no-op, not a missed day. A missed day is no `decision=run` and no new `chore: daily curator run YYYY-MM-DD` commit.

The catch-up choice is deliberate. Oct 31's run showed up hours late. If that happens again and nothing has published for the Eastern date, the late run still sends the email. If the morning run already happened, the late run does not send another one. There is no afternoon cron. A slot that GitHub drops entirely never runs; a slot it only delays still does.

`force_email` from the Actions button, or from the dispatch API with `morning` left false, can still send a second email. That is the same power as the button. The token can do it too, because GitHub does not separate the UI from the API. The worker never sets that flag.

Residual gap: if a run sends email and then fails before the commit, the archive is not on `main` and a later arrival will send again. The guard's signal is the committed archive.

## How to confirm the next morning

1. Merge this change and leave the workflow alone. Do not dispatch it just to test, or you will send the email.
2. The next morning, open Actions → Daily Curator Run. You want one run whose guard log says `decision=run` and `reason=on_time`, with `eastern_date` equal to that Eastern morning. The job summary shows the same lines. The commit on `main` is `chore: daily curator run YYYY-MM-DD` for that date, and one email arrives.
3. Later slots the same morning (`6:17`, `8:37`, and in summer the `10:07` UTC run) should be green with `reason=already_published` and `run-pipeline` skipped. In winter, `7 10 * * *` UTC is the same instant as 5:07 AM ET, so it queues behind the primary and then no-ops. One extra short job at 5:07 AM EST is expected.
4. On the run, the workflow file on `main` should still show `timezone: "America/New_York"` on the 5:07 cron. If a run ever starts around 12:07–3:37 AM ET with reason `too_early`, the timezone field is not being honored and the 10:07 UTC slot is what publishes the morning (5:07 AM EST / 6:07 AM EDT).
5. After the worker is deployed, Cloudflare logs for `cc-morning-ping` should show `morning ping dispatched` around 5:00 AM ET (10:00 UTC in winter, 09:00 UTC in summer). The Actions run for that ping has event `workflow_dispatch` and input `morning=true`. The GitHub 5:07 schedule the same morning should no-op.

Check the clock logic locally without touching GitHub:

```bash
CC_EVENT_NAME=schedule CC_ALREADY_PUBLISHED=false python3 scripts/morning_guard.py --at 2026-11-15T10:07:00Z
# decision=run, reason=on_time, eastern_date=2026-11-15  (5:07 AM EST)

CC_EVENT_NAME=schedule CC_ALREADY_PUBLISHED=false python3 scripts/morning_guard.py --at 2026-07-15T09:07:00Z
# decision=run, reason=on_time  (5:07 AM EDT)

CC_EVENT_NAME=schedule CC_ALREADY_PUBLISHED=true python3 scripts/morning_guard.py --at 2026-10-31T14:35:00Z
# decision=skip, reason=already_published  (10:35 AM EDT, morning already ran)
```

Tests: `python3 -m unittest tests.test_morning_guard` and `node --test worker/morning/ping.test.js`.

## If the ping stops

An expired token, a failed `wrangler deploy`, or a Cloudflare error shows up as a failed cron invocation in the Cloudflare dashboard and no `workflow_dispatch` run at 5:00 AM. The GitHub 5:07 AM ET schedule still runs, then 6:17 and 8:37 if needed. Fix the token with `npx wrangler secret put GITHUB_DISPATCH_TOKEN` from `worker/morning` and redeploy only if the script changed.

To turn the ping off, delete the `cc-morning-ping` worker in the Cloudflare dashboard, or remove the `[triggers]` crons and deploy. Leave the GitHub workflow in place.
