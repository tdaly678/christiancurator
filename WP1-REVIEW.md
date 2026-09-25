# WP-1 review packet

Branch `sprint/wp1-voice-triage`, rebuilt 2026-09-25 from the August spec after the
original branch was lost with the old account's sandbox. **Nothing is applied.** The
scripts are inert until run, and the branch is not merged. This file plus
`wp1-noindex-manifest.csv` is what needs your review.

## What it does

A voice page keeps its index slot only if it clears all three bars: at least 200 body
words, at least one Quick Facts item, at least one FAQ item. Everything else gets
`<meta name="robots" content="noindex, follow" />`. Pages stay live and navigable, so
internal links keep flowing to the topic pages. Nothing is deleted.

## The numbers

| | |
|---|---|
| Voice pages scanned | 1,192 |
| Stay indexed | **47** (39 people, 8 category hubs) |
| Noindexed | 1,143 |
| Left alone (hand placed robots tag) | 2 |
| `sitemap-voices.xml` | **1,192 URLs to 47** |

For scale, in August this was 1,028 pages and 55 keepers. The directory grew by 164
pages in seven weeks and all of them went straight into the sitemap.

## Decision 1: approve the keep list

The 39 people who stay indexed, longest first:

john-piper, john-mark-comer, doug-wilson, preston-sprinkle, wayne-grudem,
r-albert-mohler, kevin-deyoung, john-lennox, carl-trueman, os-guinness,
michael-gorman, sinclair-ferguson, thomas-jay-oord, paul-david-tripp, clark-pinnock,
o-palmer-robertson, andy-crouch, brian-mclaren, kay-warren, melissa-kruger,
michael-horton, roger-olson, joel-green, jonathan-leeman, alister-mcgrath,
andrew-wilson, ruth-haley-barton, timothy-paul-jones, sean-mcdowell, j-a-medders,
mathew-santhosh-thomas, alex-harris, david-garner, chris-brauns, katy-carl,
justin-n-poythress, mere-orthodoxy, blake-long, john-starke

**Scan this for names that should be there and are not.** The ones you will notice
missing are the WP-8 targets: tim-keller, russell-moore, r-albert-mohler-jr,
scot-mcknight, d-a-carson, mark-dever, john-macarthur. They all fail on Quick Facts
and FAQ, which is exactly the prominence to quality gap WP-8 exists to close. Tim
Keller is cited by 34 topic pages and has neither.

Two entries worth a second look, both your call and neither changed by me:

- `mere-orthodoxy` is a publication, not a person.
- `katy-carl` is Word on Fire and University of St. Thomas, which is Catholic.

And the four open theist and progressive names that clear the bar on structure alone:
thomas-jay-oord, brian-mclaren, clark-pinnock, roger-olson. They are real voices in the
conversation, so keeping them indexed is defensible. Flagging it because it is an
editorial call, not a threshold one.

## Decision 2: eight names I pre-flagged for you

`scripts/voice_index_overrides.txt` already carries eight force noindex lines, which is
why the keep list is 47 and not 55. All eight clear the bar only because the July
enrichment sweep handed them Quick Facts and FAQ markup:

aaron-boxerman, ben-hubbard, catie-edmondson, david-e-sanger, david-m-halbfinger,
elisabetta-povoledo, motoko-rich (all New York Times) and reem-nadeem (Pew Research).

That follows your July "evangelical only" call. Delete any line from the overrides file
to let that page stay indexed.

## Decision 3: the junk slugs got worse

The guard catches 19 junk byline slugs (the 18 from August plus
`damian-carrington-environment-editor` and `rowena-mason-whitehall-editor`, minus the
Stonestreet mashup which is two real people and must be split, not deleted).

**New finding:** there are **57 more** two reporter mashup slugs that the guard
deliberately leaves alone. 31 have an outright wire service affiliation, 22 have none
recorded, and 4 need a human look. Three of those are real evangelical pairs that want
splitting rather than deleting:

- `john-stonestreet-and-s-michael-craven`
- `john-stonestreet-and-thaddeus-williams`
- `rosaria-butterfield-and-jared-moore`

None of this is urgent, because all 57 are thin and get noindexed anyway. Deleting them
is cleanup you can approve separately with `scripts/prune_junk_voices.py --apply`.

## Verification performed

Run against all 1,192 live pages:

- `strip(add(x)) == x` byte exact on **1,192 of 1,192**. The August build failed this
  silently on 262 pages because it assumed `rel` came before `href` in the canonical
  link. Both orders are handled now, and the insert anchored on the canonical line for
  every single page.
- `add(add(x)) == add(x)` on all pages. Three consecutive `--apply` runs wrote 1,143
  files, then 0, then 0.
- `--revert` returned the tree to byte identical. `git status` came back empty.
- End to end: apply, then regenerate the sitemaps. `sitemap-voices.xml` went 1,192 to
  47, and the sitemap set equals the indexed set exactly, with nothing noindexed left in
  a sitemap and nothing indexed missing from one. Topic pages stayed at 70 and were not
  touched.

## Still open, not in this branch

- The Sproul canonical is backwards. `/voices/r-c-sproul/` is the stronger page (408
  words, enriched, 8 impressions) and it is the one carrying noindex and pointing its
  canonical at the thinner `rc-sproul`. Reversing it deserves its own revertable commit.
- `r-albert-mohler-jr` (16 topic citations) and `r-albert-mohler` (5 citations) need
  merging. The better page is again the less cited one, and under this branch the
  less cited one is the one that stays indexed.

## How to land it

```bash
cd ~/Projects/christiancurator
git checkout sprint/wp1-voice-triage
python3 scripts/apply_voice_noindex.py --dry-run --csv /tmp/check.csv   # confirm
git checkout main && git merge --no-ff sprint/wp1-voice-triage
git push origin main
```

The daily job then applies it every morning. To undo everything at any point:
`python3 scripts/apply_voice_noindex.py --revert`.

## Measurement

Impressions will fall by half or more. That is the intended result, not a regression.
Track indexed pages, average position of the 39 kept voices, "biblical literacy" rank,
clicks, and referring domains instead.
