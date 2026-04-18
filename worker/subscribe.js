/**
 * Christian Curator — email signup Cloudflare Worker
 *
 * Flow:
 *   Browser POSTs { email, token, honeypot } (JSON) →
 *   Worker verifies reCAPTCHA v3 token with Google →
 *   If score passes threshold, calls Brevo API to add contact to list →
 *   Returns { success: true } or { error: "..." }.
 *
 * Required secrets (set via `wrangler secret put <NAME>`):
 *   RECAPTCHA_SECRET    — Google reCAPTCHA v3 secret key
 *   BREVO_API_KEY       — Brevo API v3 key
 *   BREVO_LIST_ID       — Numeric Brevo list ID (as a string, we parseInt it)
 *
 * Optional secret:
 *   RECAPTCHA_THRESHOLD — Minimum score to accept (default "0.5")
 *
 * CORS: allows christiancurator.com, www.christiancurator.com, localhost for testing.
 */

const ALLOWED_ORIGINS = new Set([
  "https://christiancurator.com",
  "https://www.christiancurator.com",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
]);

const EXPECTED_ACTION = "subscribe";

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin") || "";
    const corsHeaders = buildCorsHeaders(origin);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return json({ error: "Method not allowed." }, 405, corsHeaders);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "Invalid request body." }, 400, corsHeaders);
    }

    const email = (body.email || "").trim().toLowerCase();
    const token = body.token || "";
    const honeypot = body.honeypot || "";

    // Honeypot: real users leave this empty; bots fill it
    if (honeypot) {
      // Pretend success to avoid tipping off the bot
      return json({ success: true }, 200, corsHeaders);
    }

    // Basic email sanity check
    if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email) || email.length > 254) {
      return json({ error: "Please enter a valid email address." }, 400, corsHeaders);
    }

    if (!token) {
      return json({ error: "Verification failed. Please refresh and try again." }, 400, corsHeaders);
    }

    // Verify reCAPTCHA v3 token with Google
    let verify;
    try {
      const r = await fetch("https://www.google.com/recaptcha/api/siteverify", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          secret: env.RECAPTCHA_SECRET,
          response: token,
        }),
      });
      verify = await r.json();
    } catch (err) {
      console.error("reCAPTCHA verify request failed:", err);
      return json({ error: "Verification service unavailable. Please try again." }, 502, corsHeaders);
    }

    const threshold = parseFloat(env.RECAPTCHA_THRESHOLD || "0.5");
    const score = typeof verify.score === "number" ? verify.score : 0;
    const actionOk = !verify.action || verify.action === EXPECTED_ACTION;

    if (!verify.success || score < threshold || !actionOk) {
      console.log("reCAPTCHA rejected:", {
        email_domain: email.split("@")[1],
        score,
        action: verify.action,
        errors: verify["error-codes"],
      });
      return json({ error: "We couldn't verify you aren't a bot. Please try again." }, 400, corsHeaders);
    }

    // Subscribe via Brevo API
    const listId = parseInt(env.BREVO_LIST_ID, 10);
    if (!Number.isFinite(listId)) {
      console.error("BREVO_LIST_ID is not configured correctly");
      return json({ error: "Signup is temporarily unavailable." }, 500, corsHeaders);
    }

    let brevoResp;
    try {
      brevoResp = await fetch("https://api.brevo.com/v3/contacts", {
        method: "POST",
        headers: {
          "api-key": env.BREVO_API_KEY,
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({
          email,
          listIds: [listId],
          updateEnabled: true, // if contact exists, just add to list (idempotent-ish)
        }),
      });
    } catch (err) {
      console.error("Brevo request failed:", err);
      return json({ error: "Signup failed. Please try again." }, 502, corsHeaders);
    }

    // Brevo returns 201 for new contact, 204 for existing (with updateEnabled).
    // Anything in 2xx is a win.
    if (!brevoResp.ok) {
      const errText = await brevoResp.text().catch(() => "");
      console.error("Brevo error:", brevoResp.status, errText);

      // 400 with code "duplicate_parameter" = already subscribed. Treat as success.
      if (brevoResp.status === 400 && errText.includes("duplicate_parameter")) {
        return json({ success: true, alreadySubscribed: true }, 200, corsHeaders);
      }
      return json({ error: "Signup failed. Please try again later." }, 500, corsHeaders);
    }

    return json({ success: true }, 200, corsHeaders);
  },
};

// ────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────

function buildCorsHeaders(origin) {
  const headers = {
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
  if (ALLOWED_ORIGINS.has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function json(data, status, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}
