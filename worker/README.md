# Christian Curator — Signup Worker

A Cloudflare Worker that verifies reCAPTCHA v3 tokens and subscribes verified
email addresses to a Brevo list. Replaces direct posts from the browser to
Brevo's hosted form URL, so we can enforce bot protection.

## Architecture

```
Browser (template.html / digest_template.html)
  │  POST JSON { email, token, honeypot }
  ▼
Cloudflare Worker (subscribe.js)
  ├── verify token via google.com/recaptcha/api/siteverify (checks score ≥ 0.5)
  └── POST to api.brevo.com/v3/contacts  (adds contact + list membership)
```

## One-time setup

### 1. Install Wrangler
```bash
npm install -g wrangler
wrangler login
```
Wrangler opens a browser tab → log in to your Cloudflare account (free tier is fine).

### 2. Deploy the Worker (from this directory)
```bash
cd christiancurator/worker
wrangler deploy
```
First deploy will create the Worker and give you a URL like:
`https://cc-subscribe.<your-account-subdomain>.workers.dev`

Note that URL — you'll need it for step 4.

### 3. Set the three secrets
Run each command and paste the value when prompted. Values are encrypted at
rest by Cloudflare; they are NOT stored in `wrangler.toml` or any file.

```bash
wrangler secret put RECAPTCHA_SECRET
# paste the reCAPTCHA v3 secret key (starts with 6L...)

wrangler secret put BREVO_API_KEY
# paste your Brevo API v3 key (from Brevo → SMTP & API → API Keys)

wrangler secret put BREVO_LIST_ID
# paste the numeric ID of your subscriber list
# find it at Brevo → Contacts → Lists → (click list) → check the URL, e.g. /contact/list/123  → list ID = 123
```

Optional:
```bash
wrangler secret put RECAPTCHA_THRESHOLD
# paste a float 0.0–1.0 (default 0.5). Lower = more permissive, higher = stricter.
```

### 4. Update the Worker URL in both templates
In both files:
- `christiancurator/frontend/template.html`
- `christiancurator/frontend/digest_template.html`

Find this line:
```js
var WORKER_URL = 'https://cc-subscribe.YOUR-CF-ACCOUNT.workers.dev/';
```
Replace `YOUR-CF-ACCOUNT` with your actual Cloudflare account subdomain (from
step 2).

### 5. Regenerate and deploy the site
The templates are used by the daily pipeline. Either:
- Wait for the next 6:00 AM UTC run, OR
- Run `/tmp/rerender_only.py` (the re-rendering helper documented in project memory) to rebuild `docs/` immediately, then commit & push.

---

## Optional: bind to a custom domain

If your DNS is on Cloudflare, you can expose the Worker at
`https://christiancurator.com/api/subscribe` instead of the `.workers.dev` URL.

1. Uncomment the `[[routes]]` block in `wrangler.toml`.
2. `wrangler deploy` again.
3. Update `WORKER_URL` in both templates to the new path.

Benefits: same-origin fetch (no CORS), nicer URL, no third-party domain
exposed in the HTML.

---

## Testing

### Local test with curl
Once deployed, confirm the Worker is reachable:
```bash
curl -X POST https://cc-subscribe.<account>.workers.dev/ \
  -H 'Content-Type: application/json' \
  -H 'Origin: https://christiancurator.com' \
  -d '{"email":"fake@example.com","token":"invalid","honeypot":""}'
```
Expected: `{"error":"We couldn't verify you aren't a bot. Please try again."}`
(400). This confirms the Worker is running and reaching Google.

### End-to-end test on the live site
1. Open christiancurator.com in an incognito window.
2. Scroll to the signup form, enter a real test email, click Subscribe.
3. Expected UX: button changes to "Subscribing…" → form replaced by success
   message within ~1 second.
4. Check Brevo → Contacts: the email should appear, assigned to your list.
5. Check Cloudflare Workers → cc-subscribe → Logs if anything failed; the
   Worker logs rejected attempts (score, error-codes, email domain).

### Tuning the score threshold
If legitimate users get rejected, check the Worker logs for the rejected
`score` values. If most are 0.3–0.5, lower `RECAPTCHA_THRESHOLD` to 0.3. If
bots are slipping through, raise it to 0.7.

---

## Rollback

If something breaks and you need to restore the old Brevo-hosted form quickly:
1. `git revert` the commit that modified `template.html` + `digest_template.html`.
2. Regenerate `docs/` and push.

The Worker can keep running; it's not in the request path once the templates
point back to Brevo's hosted URL.
