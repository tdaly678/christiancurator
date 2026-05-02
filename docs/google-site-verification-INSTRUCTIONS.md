# Google Search Console Verification

Private setup note for Tom. The site doesn't have a verified Search Console
property yet. Once verified, GSC unlocks indexing reports, "Request Indexing"
on individual URLs, and search-performance data — and it's a prerequisite
for submitting our sitemap.

A placeholder verification meta tag has already been added to the homepage:

    <meta name="google-site-verification" content="REPLACE_ME" />

It's in two places (so a homepage rebuild won't wipe it out):

  1. `frontend/template.html`  (source — the homepage is rendered from here)
  2. `docs/index.html`         (generated — what GitHub Pages actually serves)

Both need the same `content="..."` string after Google gives it to us.

---

## Two verification methods Google offers

When you add a property in Search Console, Google will offer several
verification methods. The two relevant ones for a static GitHub Pages site:

### A. HTML tag (recommended — what we've scaffolded)

Search Console gives you a single `<meta>` tag to drop into the homepage
`<head>`. It looks like:

    <meta name="google-site-verification" content="abc123XYZ_someLongOpaqueString" />

You replace the `REPLACE_ME` string in the two files above with the
`content="..."` value, commit and push, wait for the GitHub Pages build to
go live, then click **Verify** in Search Console.

### B. HTML file upload (alternative)

Search Console gives you a file like `google1234abcd5678.html` to upload
to the site root. For our setup that means dropping the file at
`docs/google1234abcd5678.html` and pushing — GitHub Pages will then serve
it at `https://www.christiancurator.com/google1234abcd5678.html`.

Either method works. We've scaffolded for method A.

---

## Step-by-step

1. Go to https://search.google.com/search-console.

2. Click **Add property**.

3. Choose the **URL prefix** option (not Domain, since we don't want to
   add a DNS TXT record). Enter:

       https://www.christiancurator.com

4. Repeat the Add-property flow a second time and add the apex domain
   variant as a separate property:

       https://christiancurator.com

   (Google treats `www` and apex as different properties under URL-prefix
   verification — verify both so reporting covers all traffic.)

5. For each property, choose **HTML tag** as the verification method.

6. Copy just the `content="..."` string from the meta tag Google shows
   you. (Don't paste the whole tag — we already have the wrapper.)

7. In `frontend/template.html` and `docs/index.html`, replace
   `REPLACE_ME` with that string. Both files must use the same string.

8. Commit and push. Wait ~1–2 minutes for the GitHub Pages build to
   deploy the change to the live site.

9. Confirm the tag is live — `curl -s https://www.christiancurator.com/ | grep google-site-verification` should show the new content string.

10. Back in Search Console, click **Verify**. If it says "Verification
    failed," double-check that the live homepage shows the new content
    string (step 9), then try again — sometimes there's a small CDN lag.

11. Once verified, submit the sitemap. Inside the property:

        Sitemaps → Add a new sitemap → sitemap.xml → Submit

    Full URL Google will fetch: `https://www.christiancurator.com/sitemap.xml`.
    (We're already serving a sitemap-index there, expanded in Round 1 to
    602 URLs.)

12. Use the **URL Inspection** tool to "Request Indexing" on the top 10
    topic pages. Suggested first batch:

        /topics/apologetics/
        /topics/biblical-inerrancy/
        /topics/eschatology/
        /topics/the-trinity/
        /topics/missions-and-evangelism/
        /topics/preaching/
        /topics/spiritual-abuse/
        /topics/justification-by-faith/
        /topics/atonement/
        /topics/christology/

    For each: paste the full URL into the URL Inspection bar at the top
    of GSC → wait for the live test → click **Request Indexing**. Google
    rate-limits this to ~10–20 requests per day per property.

---

## Important

- The placeholder string `REPLACE_ME` is **not** a valid token. The site
  will not verify until you replace it with the real string Google gives
  you. Don't ship a fake token; it'll just fail verification silently.

- Keep the apex and `www` properties both verified — links from other
  sites sometimes hit the apex even though our canonical is `www`.

- If Google ever rotates your verification string (rare, but possible
  if you remove and re-add a property), you'll need to repeat steps 6–10.
