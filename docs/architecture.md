# Architecture

## Overview

The application follows a layered architecture that keeps website-specific scraping logic separate from business logic and the public API contract.

```text
Public Website
      │
      │ HTML
      ▼
WebsiteClient
      │
      ▼
WebsiteParser
      │
      ▼
Normalized Models
      │
      ▼
BookCatalogService
      │
      ▼
FastAPI Routes
      │
      ▼
JSON REST API
      │
      ├── API clients
      ├── scripts/demo.py
      └── OpenAPI documentation
```

The main architectural goal is to make the scraping layer replaceable.

If the website later provides an official API, the upstream client/parser can be replaced without requiring consumers of this project's API to change.

---

## Layer Responsibilities

| Layer       | File                       | Responsibility                                                                                    | Knows About HTML?   |
| ----------- | -------------------------- | ------------------------------------------------------------------------------------------------- | ------------------- |
| HTTP Client | `services/scraper.py`      | Allow-listed GET requests, timeout, spacing, retries, cache interaction, upstream failure mapping | No                  |
| Cache       | `services/cache.py`        | In-memory TTL cache of upstream page HTML                                                         | No                  |
| Parser      | `services/parser.py`       | HTML selectors, extraction, normalization into models                                             | **Yes — only here** |
| Catalog     | `services/catalog.py`      | Pagination mapping, category handling, search scanning, not-found translation                     | No                  |
| API         | `api/routes.py`, `main.py` | Request validation, rate limiting, error mapping, HTTP responses, OpenAPI                         | No                  |
| Contract    | `models/schemas.py`        | Public request/response data models                                                               | No                  |

The parser is deliberately the only component that depends directly on the website's HTML structure.

---

## Request Flow

### Example: `GET /api/v1/items/{id}`

```text
Client
  │
  ▼
FastAPI Route
  │
  ├── Request ID middleware
  │
  ├── Rate-limit check
  │
  └── Path validation
  │
  ▼
BookCatalogService
  │
  ▼
WebsiteClient
  │
  ├── Target host validation
  ├── Cache lookup
  ├── Request spacing
  ├── HTTP request
  └── Retry handling
  │
  ▼
HTML Response
  │
  ▼
WebsiteParser
  │
  ▼
BookDetail model
  │
  ▼
FastAPI JSON response
```

### Detailed Flow

1. Middleware assigns a request ID.
2. The route applies the per-client rate limit.
3. The book ID is validated against the expected pattern.
4. The catalog service constructs the product path.
5. The HTTP client validates the target host.
6. The cache is checked.
7. On a cache miss, the upstream request is throttled according to the configured minimum interval.
8. The HTTP client performs the request.
9. Retryable upstream failures are retried with bounded exponential backoff.
10. Successful HTML responses are cached.
11. The parser extracts and normalizes the book data.
12. The normalized model is returned through the API response model.
13. A structured request log is emitted without logging query strings.

---

## Search Flow

Search is different from item retrieval because the source website does not provide a conventional crawlable search endpoint.

```text
GET /api/v1/search?q=light
          │
          ▼
BookCatalogService
          │
          ▼
Scan listing pages
          │
          ├── Page 1
          ├── Page 2
          ├── ...
          └── Page N
          │
          ▼
Parse books
          │
          ▼
Filter titles
          │
          ▼
Return results
          │
          ├── scanned_pages
          └── partial
```

The number of pages scanned is bounded by:

```text
SEARCH_MAX_PAGES
```

This prevents a single search request from generating an unbounded number of upstream requests.

---

## Listing Pagination

The source website uses a fixed page size of 20 books.

The API exposes its own pagination interface:

```http
GET /api/v1/items?page=2&limit=10
```

The catalog service maps the API pagination model onto the site's fixed page structure.

This keeps consumers independent from the source website's pagination implementation.

---

## Component Details

### `services/scraper.py`

The HTTP client is responsible for:

* Building upstream requests.
* Enforcing the target-host allowlist.
* Setting request headers.
* Applying timeouts.
* Enforcing outbound spacing.
* Performing bounded retries.
* Mapping upstream failures into application-level errors.
* Reading/writing cached HTML.

It does not parse business fields from HTML.

---

### `services/cache.py`

The cache stores upstream page responses in memory.

Characteristics:

* TTL based.
* URL keyed.
* Bounded size.
* Per-process.
* Errors are not cached.

Default TTL:

```text
CACHE_TTL_SECONDS=300
```

For multiple production instances, a shared cache would be required.

---

### `services/parser.py`

The parser is the only component that knows the website's HTML selectors.

Responsibilities include:

* Extracting titles.
* Extracting prices.
* Extracting ratings.
* Extracting availability.
* Extracting categories.
* Extracting descriptions.
* Extracting UPC/tax/review information.
* Extracting image URLs.
* Normalizing relative URLs.
* Handling optional fields.

Keeping selectors in one location makes website markup changes easier to manage.

---

### `services/catalog.py`

The catalog service contains application-level behavior such as:

* Listing.
* Pagination mapping.
* Category filtering.
* Item retrieval.
* Search scanning.
* Not-found translation.

It does not contain HTML selectors.

---

### `api/routes.py`

The API layer is responsible for:

* HTTP routing.
* Input validation.
* Rate limiting.
* Response serialization.
* Error mapping.
* API documentation metadata.

It does not directly parse website HTML.

---

### `models/schemas.py`

The Pydantic schemas define the public API contract.

The API contract is intentionally independent from the HTML representation.

This means an API consumer receives a stable JSON structure even though the upstream source is an HTML website.

---

## Error Mapping

| Situation                        | Retried? | Result                             |
| -------------------------------- | -------: | ---------------------------------- |
| Invalid input                    |       No | `400 bad_request`                  |
| Target returns 404               |       No | `404 not_found`                    |
| Inbound rate limit exceeded      |       No | `429 rate_limited` + `Retry-After` |
| Timeout                          |      Yes | `503 upstream_unavailable`         |
| Connection error                 |      Yes | `503 upstream_unavailable`         |
| Target 429                       |      Yes | `503 upstream_unavailable`         |
| Target 502/503/504               |      Yes | `503 upstream_unavailable`         |
| Target 500                       |      Yes | `502 upstream_bad_response`        |
| Target 3xx/400/401/403           |       No | `502 upstream_bad_response`        |
| Non-HTML response                |       No | `502 upstream_bad_response`        |
| Empty response                   |       No | `502 upstream_bad_response`        |
| Missing expected HTML structure  |       No | `502 upstream_parse_error`         |
| Unexpected application exception |       No | `500 internal_error`               |

The distinction between `502` and `503` is intentional.

* `502` indicates an invalid or unexpected upstream response.
* `503` indicates that the upstream service could not currently be reached successfully.

---

## Rate Limiting

### Inbound

The API uses a sliding-window rate limiter.

Default:

```text
30 requests / 60 seconds / client
```

The client identity is based on the connection IP.

Proxy headers are not trusted automatically.

The purpose is to prevent consumers from using the API to generate excessive upstream traffic.

---

## Outbound Request Spacing

The upstream client enforces a minimum interval between requests.

Default:

```text
UPSTREAM_MIN_INTERVAL_SECONDS=0.2
```

This is deliberately conservative.

The goal is to keep traffic controlled rather than attempting to maximize scraping throughput.

---

## Caching

The application caches successful upstream HTML responses.

```text
URL
 │
 ▼
Cache lookup
 │
 ├── HIT  → return cached HTML
 │
 └── MISS
       │
       ▼
   upstream request
       │
       ▼
   cache response
```

Default:

```text
CACHE_TTL_SECONDS=300
```

The cache improves repeated-request performance and reduces unnecessary upstream traffic.

Production deployments with multiple application instances should use a shared cache such as Redis.

---

## Retry Strategy

Retries are limited to conditions that may reasonably succeed on a subsequent request.

Retryable:

* Timeouts.
* Connection errors.
* HTTP 429.
* HTTP 5xx.

Non-retryable:

* HTTP 400.
* HTTP 401.
* HTTP 403.
* HTTP 404.

Retries use bounded exponential backoff.

This avoids retrying known client errors and avoids creating unnecessary upstream traffic.

---

## Security

### SSRF Protection

The upstream target host is hard-coded and allow-listed.

There is no arbitrary URL parameter.

The API therefore cannot be used as a generic proxy such as:

```text
/api/fetch?url=https://internal-service/
```

### Redirect Handling

Automatic redirects are disabled for upstream requests.

This keeps requests within the intended target boundary.

### Input Validation

User-controlled identifiers and parameters have explicit length and pattern validation.

Only validated identifiers are incorporated into upstream paths.

### Information Leakage

The API does not return:

* Stack traces.
* Environment variables.
* Credentials.
* Internal exception details.

Logs contain operational information but avoid logging search query strings or client-provided sensitive data.

---

## Logging

Structured logging is used for operational visibility.

Useful fields include:

* Request ID.
* HTTP path.
* Response status.
* Request timing.
* Upstream URL.
* Upstream status.
* Cache hit/miss information.

Query strings are intentionally excluded from request logs.

The request ID allows an individual request to be followed through the application logs.

---

## Testing Architecture

The project separates deterministic tests from live integration tests.

### Deterministic Tests

Use local HTML fixtures and mocked HTTP behavior.

Benefits:

* No dependency on network availability.
* Fast execution.
* Repeatable results.
* Controlled failure scenarios.
* Safe CI execution.

The deterministic suite currently contains:

```text
72 passed
1 skipped
1 warning
```

### Live Integration

Live tests are opt-in.

They validate the real public website when network access is available.

The live demo also validates:

* Health.
* Search.
* Item retrieval.
* Validation errors.
* 404 behavior.

---

## Why This Architecture?

The main design decision is separation of concerns.

Without separation, the application could become:

```text
FastAPI Route
     │
     ├── HTTP request
     ├── HTML parsing
     ├── selector logic
     ├── retry logic
     ├── caching
     └── JSON response
```

That would make the system difficult to test and maintain.

Instead:

```text
FastAPI
   │
   ▼
Catalog Service
   │
   ▼
Website Client
   │
   ▼
Website Parser
```

Each layer has a focused responsibility.

---

## Production Evolution

The current architecture intentionally supports replacing the scraper.

### Current

```text
FastAPI
   │
   ▼
Catalog Service
   │
   ▼
WebsiteClient
   │
   ▼
HTML Parser
   │
   ▼
Public Website
```

### Preferred Production Architecture

```text
FastAPI
   │
   ▼
Catalog Service
   │
   ▼
Official API Adapter
   │
   ▼
Data Provider
```

The API contract can remain stable while the upstream adapter changes.

---

## Production Improvements

If this were deployed as a production integration, the following improvements would be appropriate:

* Official API/feed integration.
* Shared Redis cache.
* Distributed rate limiting.
* Background catalog synchronization.
* Search index/database for fast search.
* Centralized metrics.
* Distributed tracing.
* Alerting.
* Schema-drift monitoring.
* API authentication and authorization where required.
* API versioning.
* Health/readiness checks.
* Persistent storage for normalized catalog data.

These are intentionally outside the scope of the assignment implementation.

---

## Trade-offs

### FastAPI

Chosen for:

* Typed request/response models.
* Automatic OpenAPI documentation.
* Async I/O.
* Simple deployment.
* Good testing support.

### HTTPX

Chosen for:

* Async HTTP requests.
* Timeout support.
* Mockable transports.
* Straightforward error handling.

### BeautifulSoup

Chosen because:

* The target website is server-rendered HTML.
* The parser is lightweight.
* `html.parser` avoids additional native dependencies.

### Hand-Written Retry Logic

A small retry implementation was preferred over an additional dependency.

This keeps the project lightweight and makes the retry behavior explicit and easy to test.

### Separate Client / Parser / Service

This is the most important architectural trade-off.

The added separation creates a few more modules, but it makes the upstream integration replaceable and the system easier to test.

---

## Architectural Principle

The central principle of the project is:

> **Keep the public API contract stable and isolate the unstable upstream integration behind an adapter boundary.**

The current website parser is therefore an implementation detail rather than part of the consumer-facing API.
