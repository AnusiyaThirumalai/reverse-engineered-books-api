# Limitations and the appropriate long-term fix

## Limitations

1. **HTML dependency.** The parser is bound to the site's current markup. If classes or structure change,
   extraction breaks. Mitigations built in: all selectors in one dictionary, structural validation that
   fails loudly (`502 upstream_parse_error`) instead of returning bad data, fixture-based tests, and an
   opt-in live smoke test to detect drift quickly. Mitigation not built: automated drift monitoring.
2. **Performance.** Every uncached request waits on the target site. Search is the worst case: up to
   `SEARCH_MAX_PAGES` (default 10) sequential, spaced page fetches on a cold cache (a few seconds); warm
   searches are instant. Spacing is deliberate (politeness) and is the trade-off against latency.
3. **Search coverage.** Search is title-only and scans a bounded number of listing pages. With the default,
   only the first 200 of ~1,000 books are searched; the response says so (`partial: true`). Scanning all
   50 pages is possible by configuration but multiplies upstream load.
4. **Availability.** If the target is down, this API is down for uncached data. It returns `503`/`502`
   quickly rather than hanging (timeouts, bounded retries).
5. **Rate limits.** The limiter and request spacing exist to *respect* the target, not to evade anything.
   Both are in-memory and per-process; with several instances the effective limits multiply.
6. **Data freshness.** Cached pages can be up to `CACHE_TTL_SECONDS` stale (default 5 min). Stock/price
   shown may lag the site.
7. **Pagination.** The site paginates at a fixed 20 items, so `limit` is capped at 20 and a request can
   cost two upstream pages. Deep `page` values beyond the end return an empty list.
8. **Identity & semantics.** `id` is the site's URL slug; if the site renames a slug the id changes.
   Prices/ratings on this particular site are randomly assigned demo data.
9. **Live verification.** The selectors were manually validated against the public site during the
   assignment run. The automated live smoke test remains opt-in because CI or reviewer environments
   may not have network access to the target site.
10. **Legal / terms.** This sandbox site invites scraping, so the exercise is low-risk. For any real
    site, production use should be reviewed against that site's terms of use, `robots.txt`, applicable
    law, and any official integration options. This document makes no legal claims beyond that.

## Appropriate long-term solution

Scraping is a bridge, not a destination. The durable fix is to stop depending on presentation HTML:

```
Official API  →  Authentication  →  Stable API contract  →  Our integration layer  →  Agent / application
```

**If the website owner provides (or will provide) an official API / feed**, replace `WebsiteClient` +
`WebsiteParser` with an adapter to it and keep this project's `schemas.py` contract unchanged.
Advantages: a stable, versioned contract; authentication and attributable access; predictable schemas;
real rate-limit semantics (`429` with quotas instead of guessing); support channel and deprecation
notices; no breakage from cosmetic HTML changes; freshness via webhooks or ETags instead of TTL guesses.

**If no official API exists**, a production integration should require:

- **Permission** from the site owner and a **documented integration agreement** (allowed volume, purpose)
- A **stable data contract** (this repo's schemas are the start) agreed with downstream consumers
- **Monitoring**: parse-failure rate, upstream error/latency, schema-drift canary hitting known pages
- **Retry & backoff** policy agreed with the owner; **caching** and shared rate limiting (Redis/gateway)
- **Observability**: structured logs → central store, metrics, alerting, request-id tracing
- **Versioning** of our own API so consumers survive parser changes

Scraping should not be presented as equivalent to an official API: it has no contract, no support, and
can be withdrawn or broken at any time.
