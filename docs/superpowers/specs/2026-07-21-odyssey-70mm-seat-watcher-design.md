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

**Two parsing hazards, both confirmed present in the fixtures:**

1. **Two rows are lettered `E`** — one is an all-blank walkway spacer. Row letter is therefore *not* a unique key; parsing must key on physical row index.
2. **Rows D and K contain gaps** and `seatType` values of `companion` and `wheelchair` alongside `seat`.

## Matching rule

A **seat** qualifies when all hold:

- `seatType == "seat"` (excludes `companion`, `wheelchair`)
- `available == "True"`
- row letter ∈ `{F, G, H, J, K}`
- physical column ∈ `[9, 17]` — the center third of the 27-column grid

A **pair** qualifies when two qualifying seats share a physical row and their column indices differ by exactly 1.

A **showtime** qualifies when:

- format label is `Imax 70mm`
- start time falls within **11:00–19:00 inclusive**, `America/Chicago`
- date falls within **today → today + 21 days**, `America/Chicago`
- all days of the week are eligible

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
| `seatmap_604612_nearly_sold_out.html` | 241 seats, 4 available, one genuine adjacent pair in row D; both `E` rows; wheelchair/companion types |
| `listing_today_with_soldout.html` | all three showtime states including a real `soldOut` |
| `listing_2026-08-05.html` | future-date listing, 5 IMAX 70mm showtimes |

Parser tests assert against these. Matcher tests use synthetic grids to cover: adjacent pair inside the zone, adjacent pair outside the zone, two available seats split by an aisle (must not match), a lone available seat, and companion/wheelchair exclusion.

## Scheduling

GitHub Actions scheduled workflow, `*/10 * * * *`, in a private repo. The job checks out, scans, emails on new matches, and commits the updated `state.json` back to the repo.

## Risks

**1. Cloudflare may block datacenter IPs. This is the one risk that can invalidate the hosting choice, so it is retired first.**

Every successful request during discovery originated from the user's Mac on a residential ISP. The site sits behind Cloudflare (`window.__CF` present in page source), and Cloudflare commonly admits residential traffic while challenging cloud provider ranges — which is exactly where GitHub Actions runs.

*Mitigation:* implementation step one is a throwaway workflow that curls the listing page from a runner and prints the HTTP status. `200` → proceed as designed. `403`/challenge → fall back to launchd on the Mac, accepting the gap while it sleeps. This is verified before any scanner code is written.

**2. GitHub Actions cron is best-effort.** `*/10` can lag 10–30 minutes or skip runs under platform load. For a resource where good seats vanish in minutes, this is a genuine limitation, not a formality. It remains substantially better than a laptop that sleeps.

**3. Markup drift.** Cinemark could restructure either page. Parser failures must be loud — a scan that parses zero showtimes across all 22 dates should error rather than silently report "no seats found," which is indistinguishable from working correctly.

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
| Columns | 9–17 |
| Pair size | exactly 2, adjacent |

All live in `config.py` so they can be tuned without touching logic.
