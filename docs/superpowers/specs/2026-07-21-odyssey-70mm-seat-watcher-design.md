# Odyssey IMAX 70mm Seat Watcher — Design

**Date:** 2026-07-21
**Goal:** Continuously watch for 2 adjacent good seats for *The Odyssey* in IMAX 70mm at Cinemark Seven Bridges, and email when a qualifying pair opens up.

## Problem

The film is effectively sold out at this venue. A 2:40am showtime sampled on 2026-07-21 had **4 of 241 seats available**. Pairs open up only through cancellations and newly released showtimes, both of which appear without warning and disappear quickly. Manual checking cannot cover a three-week window.

## Target

| | |
|---|---|
| Theater | Cinemark Seven Bridges and IMAX, Woodridge, IL |
| `TheaterId` | `276` |
| Auditorium | 17 |
| Format label | `Imax 70mm` |

## Verified endpoint behavior

All of the following was confirmed live on 2026-07-21 via plain `curl` with a browser User-Agent. No authentication, no session, no JavaScript required — both pages are server-rendered.

### Listing page

```
GET https://www.cinemark.com/theatres/il-woodridge/cinemark-seven-bridges-and-imax?showDate=YYYY-MM-DD
```

`showDate` accepts future dates (verified 2026-07-25 and 2026-08-05, returning 2 and 5 IMAX 70mm showtimes respectively).

Each showtime is a `<div class="showtime">` carrying `data-print-type-name`, which is the format label (`Imax 70mm`, `Standard Format`, …). Within it, exactly one of three states:

| State | Markup |
|---|---|
| Past | `<p class="off past">` |
| Sold out | `<p class="off soldOut">` |
| Bookable | `<a class="showtime-link" href="/TicketSeatMap/?TheaterId=276&ShowtimeId=…&CinemarkMovieId=…&Showtime=…">` |

This is the key to the architecture: one request per date reveals which 70mm showtimes exist **and** which are sold out, without touching a single seat map.

### Seat map page

```
GET https://www.cinemark.com/TicketSeatMap/?TheaterId=276&ShowtimeId=<id>&CinemarkMovieId=<id>&Showtime=<iso8601>
```

Seats are server-rendered buttons:

```html
<button available="False" class="seatUnavailable seatBlock" id="row0col5"
        info="A,17,0,5,604612" seatType="seat" title="Unavailable Seat A17">
```

`info` is `ROW_LETTER,SEAT_NUMBER,PHYSICAL_ROW,PHYSICAL_COL,SHOWTIME_ID`.

Non-seat grid cells render as `<input class="seatBlank seatBlock">` and **occupy column indices**. This is load-bearing: because aisles consume columns, physical-column adjacency automatically excludes seats separated by an aisle.

### Auditorium 17 geometry (verified)

A uniform **27-column grid**, columns aligned across all rows, contiguous with no numbering gaps.

```
SCREEN
 A |.....XXXXXXXXXXXXXXXXX.....|
 B |...XXXXXXXXXXXXXXXXXXXX....|
 C |..XXXXXXXXXXXXXXXXXXXXXX...|
 D |..X    XXXXXXXXXXX  .  X...|   <- wheelchair/companion row
 E |...........................|   <- walkway spacer (all blanks)
 E |XXXXXXXXXXXXXXXXXXXXXXXXXXX|
 F |XXXXXXXXXXXXXXXXXXXXXXXXXXX|
 G |XXXXXXXXXXXXXXXXXXXXXXXXXXX|
 H |XXXXXXXXXXXXXXXXXXXXXXXXXXX|
 J |XXXXXXXXXXXXXXXXXXXXXXXXXXX|
 K |  X  .  XXXXXXXXXXXXXXXXXXX|
    012345678901234567890123456
```

Rows A–D form the narrow front section; E–K is full-width stadium seating. Row letters skip `I`.

**Screen orientation is verified, not assumed.** The markup renders `<div class="screenLabel">Screen</div>` above row A, so row A is nearest the screen and K is farthest. Rows F–K are therefore genuinely the back half. This was checked explicitly because inverting it would silently target the worst seats in the house.

**Three parsing hazards, all confirmed present in the fixtures:**

1. **Two rows are lettered `E`** — one is an all-blank walkway spacer. Row letter is therefore *not* a unique key; parsing must key on physical row index.
2. **Rows D and K contain gaps** and `seatType` values of `companion` and `wheelchair` alongside `seat`.
3. **BeautifulSoup lowercases attribute names.** `seatType` must be read as `seattype`, `showtimeId` as `showtimeid`. Reading the camelCase name returns `None` and silently yields zero seats.

**Only bookable showtimes carry a `ShowtimeId`.** Sold-out and past showtimes render as bare `<p>` elements with display text only. This is not a problem: the system never needs to act on them, and the moment one becomes bookable it gains an ID. Tier 1 counts them for sanity-checking only.

## Matching rule

A **seat** qualifies when all hold:

- `seatType == "seat"` (excludes `companion`, `wheelchair`)
- `available == "True"`
- row letter ∈ `{F, G, H, J, K}`

There is deliberately **no column restriction**. This release is close to fully sold out — both captured seat maps contain zero available seats anywhere in rows F–K — so narrowing to the center third would mean alerting on almost nothing. The entire back half is in scope, edge seats included. A skewed view from column 2 in row H beats not seeing the film in 70mm.

The column range remains a single config constant (`MIN_COL`/`MAX_COL`, currently `0`–`26`, the full grid width) so the zone can be tightened later without touching logic if alerts turn out to be plentiful rather than rare.

A **pair** qualifies when two qualifying seats share a physical row and their column indices differ by exactly 1.

A **showtime** qualifies when:

- format label is `Imax 70mm`
- start time falls within **11:00–19:00 inclusive**, `America/Chicago`
- date falls within **today → today + 21 days**, `America/Chicago`
- all days of the week are eligible

### Showtimes vary by day — nothing about the schedule is assumed

Observed on 2026-07-21: Jul 25 had 2 IMAX 70mm showtimes, Aug 5 had 5 (7:45am, 11:30am, 3:15pm, 7:00pm, 10:45pm), and today had 6. There is no repeating daily pattern.

The system therefore never models a schedule. Tier 1 fetches **each date's listing independently** and reads whatever showtimes are actually published for that date, applying the time filter per showtime. Consequences that follow, and which the implementation must preserve:

- No showtime list, count, or clock time is ever hardcoded or cached between dates.
- Weeks that have not been released yet simply return few or no showtimes; they populate on their own once Cinemark publishes them, with no code change and no redeploy.
- A showtime that appears mid-window is treated as new and gets its seat map checked on the very next scan.
- The time filter is applied to each showtime's own start time, so a day with only a 7:45am and a 10:45pm show correctly contributes nothing.

Timezone is explicit throughout. GitHub Actions runners are UTC while showtimes are Central; the sampled 2:40am showtime is exactly the date-boundary case that produces off-by-one errors.

## Architecture: two-tier polling

**Tier 1 — discovery (cheap).** For each of the 22 dates in the window, fetch the listing page and extract IMAX 70mm showtimes with their state. ~22 requests.

**Tier 2 — seat map (targeted).** Fetch seat maps **only** for showtimes that are bookable *and* pass the time/date filter. Sold-out and past showtimes cost nothing.

Because most showtimes are sold out for this release, a typical scan is ~25–35 requests total. The cost scales with availability, so the system naturally goes quiet when there is nothing to find and works hardest exactly when seats are opening. A sold-out show still gets noticed the moment it flips back to bookable, because tier 1 sees the state change.

Filtering is done on the `Imax 70mm` format label rather than a hardcoded `CinemarkMovieId`. Movie IDs churn as listings are re-published; the format label is stable.

## State model

`state.json` stores the set of qualifying pairs found in the **previous** scan, keyed by showtime. An alert fires for pairs present now but absent then.

This is deliberately *not* a permanent "already alerted" set. This is a cancellation watcher: a pair that opens, gets bought, and re-opens days later is precisely the event worth knowing about, and a permanent set would suppress it forever. Diff-against-previous re-alerts naturally and stays silent in steady state.

**First run seeds state without sending email**, so deployment does not dump every currently-open pair into the inbox.

Entries for showtimes now in the past are pruned each scan to keep the file bounded.

## Notification

One consolidated email per scan listing every newly-opened qualifying pair — not one email per pair. Each entry gives showtime, row, seat numbers, and a direct booking link.

Delivery is Gmail SMTP over SSL (port 465) to `you@example.com`, authenticated with a Google app password stored as the GitHub secret `GMAIL_APP_PASSWORD`. Requires 2FA on the Google account.

## Components

Parsing and matching are pure functions over strings and data, which keeps the fragile part (HTML parsing) and the fiddly part (geometry) independently testable without network access.

| File | Responsibility |
|---|---|
| `config.py` | theater ID, date window, time window, row/column rule |
| `fetch.py` | HTTP: browser UA, retries with backoff, inter-request delay |
| `parse.py` | listing HTML → showtimes; seatmap HTML → seats |
| `match.py` | pure: seats → qualifying pairs |
| `state.py` | load / save / diff / prune |
| `notify.py` | compose and send email |
| `main.py` | orchestration |

## Testing

Real HTML fixtures captured 2026-07-21 are committed to `tests/fixtures/`:

| Fixture | What it exercises |
|---|---|
| `seatmap_604612_nearly_sold_out.html` | 241 grid cells, 227 regular seats, **0 available regular seats**; the only 4 available cells are `wheelchair`. Both `E` rows present. The critical wheelchair-exclusion case. |
| `seatmap_601707_has_availability.html` | 19 available regular seats, all in rows A/B. Rows F–K fully taken, so it must yield **zero** qualifying pairs — the "available but wrong location" case. |
| `listing_today_with_soldout.html` | 6 IMAX 70mm showtimes: 1 bookable, 1 `soldOut`, 4 `past` |
| `listing_2026-08-05.html` | 5 bookable IMAX 70mm showtimes at 7:45am, 11:30am, 3:15pm, 7:00pm, 10:45pm — exercises the time filter, including 7:00pm as the inclusive upper boundary (3 of 5 must survive) |

Note that both seat map fixtures correctly yield zero qualifying pairs. That is an accurate reflection of the problem — this release is sold out, and a matcher that finds a pair in either fixture is wrong. Positive matching is tested in `match.py` against synthetic `Seat` lists rather than HTML, which keeps the geometry tests deterministic and independent of Cinemark's markup.

Matcher tests cover: adjacent pair in the back rows (must match), adjacent pair at the far edge of a back row (must match — no column restriction), adjacent pair in a front row (must not match), two available seats split by an aisle (must not match), a lone available seat, and wheelchair/companion exclusion.

Showtime-filter tests use `listing_2026-08-05.html` and assert exactly 3 of its 5 showtimes survive (11:30am, 3:15pm, 7:00pm), confirming both boundary inclusivity at 7:00pm and rejection of 7:45am/10:45pm. A separate test asserts the two listing fixtures yield *different* showtime counts, pinning the requirement that schedules are read per-date rather than assumed uniform.

## Scheduling

GitHub Actions scheduled workflow, `*/10 * * * *`, in a private repo. The job checks out, scans, emails on new matches, and commits the updated `state.json` back to the repo.

## Risks

**1. Cloudflare may block datacenter IPs. This is the one risk that can invalidate the hosting choice, so it is retired first.**

Every successful request during discovery originated from the user's Mac on a residential ISP. The site sits behind Cloudflare (`window.__CF` present in page source), and Cloudflare commonly admits residential traffic while challenging cloud provider ranges — which is exactly where GitHub Actions runs.

*Mitigation:* implementation step one is a throwaway workflow that curls the listing page from a runner and prints the HTTP status. `200` → proceed as designed. `403`/challenge → fall back to launchd on the Mac, accepting the gap while it sleeps. This is verified before any scanner code is written.

**2. GitHub Actions cron is best-effort.** `*/10` can lag 10–30 minutes or skip runs under platform load. For a resource where good seats vanish in minutes, this is a genuine limitation, not a formality. It remains substantially better than a laptop that sleeps.

**3. Markup drift.** Cinemark could restructure either page. Parser failures must be loud — a scan that parses zero showtimes across all 22 dates should error rather than silently report "no seats found," which is indistinguishable from working correctly.

## Rate limiting — discovered from the first live run (2026-07-22)

The plan's request estimates were wrong, and the live end-to-end dry run corrected them:

- **~52 showtimes are worth checking, not 3–10.** The film runs many daily 70mm showings; a full scan is ~74 requests (22 listings + ~52 seat maps), not 25–35.
- **Cinemark rate-limits at roughly 11 requests per burst.** Measured: 11 consecutive seat-map requests at 1s spacing succeed, the 12th returns `429 Too Many Requests`. It is a Cloudflare burst limit that refills within seconds, not a ban — a single request after ~20s idle returns 200. The 429 carried no `Retry-After` header in observation.

Two consequences, both addressed:

**1. `429` must be retried, not failed fast.** The original `fetch.get` treated every 4xx as fail-fast. That is correct for 403/404 but wrong for 429, which explicitly means "slow down and retry". Left unfixed, the dry run silently carried-forward 39 of 52 shows as failed — partial blindness the total-failure guard does not catch because 13 succeeded. `fetch.get` now retries 429 with a cooldown, honoring `Retry-After` when present and falling back to `RATE_LIMIT_COOLDOWN_S` when absent (the common case here), capped at `MAX_429_RETRIES`. This applies to listing requests too — 22 listings alone exceed the burst ceiling.

**2. Scans are tiered to reduce load.** With robust 429 backoff a full scan always *completes*, so tiering is a politeness/load optimization rather than a correctness requirement. Every 10-minute scan fetches all 22 listings plus seat maps for the **near window** (showtimes within `NEAR_WINDOW_DAYS` = 7 days), where last-minute cancellations cluster. Seat maps for the **far window** (days 8–21) are fetched once an hour.

The near/far split is driven by **which cron schedule fired** (`github.event.schedule`), not by wall-clock minute. Gating on the minute would collide with the already-documented GHA cron lag/skip risk: a skipped top-of-hour run would silently starve the far window while near dates kept reporting healthy. Two cron lines (`*/10 * * * *` and `5 * * * *`) let the workflow pass `include_far` only on the hourly one; a skipped hourly run simply self-heals the next hour, and nothing about far-scheduling touches `state.json`.

A deliberately-skipped far showtime becomes a **third** reason a showtime key can be absent from the current scan, alongside failed-and-carried-forward and genuinely-gone. It is handled like the fetch-failure case — the previous scan's entry is carried forward so it neither prunes nor spuriously re-alerts — and it is excluded from the total-failure guard's denominator, which fires only when seat maps were *attempted* this scan and none succeeded.

## Scope boundaries

Explicitly out of scope: automated purchasing, holding, or checkout of any kind. The system observes and notifies; a human buys. Request cadence stays polite and there is no attempt to evade rate limiting or bot detection.

## Open configuration defaults

| Setting | Value |
|---|---|
| Date window | today → +21 days |
| Scan cadence | every 10 minutes |
| Time window | 11:00–19:00 start, inclusive |
| Days | all |
| Rows | F, G, H, J, K |
| Columns | 0–26 (full width, no restriction) |
| Pair size | exactly 2, adjacent |

All live in `config.py` so they can be tuned without touching logic.
