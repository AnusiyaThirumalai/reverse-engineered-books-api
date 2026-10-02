# API Design and Reverse-Engineering Note

The website has **no public API**. This project builds one: an abstraction over the site's publicly accessible HTML.

The implementation uses only public pages. It does not use private or authenticated endpoints, bypass access controls, or attempt to access restricted data.

---

## Discovery

The website was reverse-engineered using publicly accessible pages and normal browser/view-source inspection.

### Public URL Patterns

| Need               | Public page              | URL pattern                                                          |
| ------------------ | ------------------------ | -------------------------------------------------------------------- |
| Browse all books   | Home / paged listing     | `/index.html`, `/catalogue/page-N.html`                              |
| Browse by category | Category listing         | `/catalogue/category/books/<slug>_<n>/index.html`, `.../page-N.html` |
| Book detail        | Product page             | `/catalogue/<slug>_<n>/index.html`                                   |
| Category names     | Sidebar on listing pages | `div.side_categories`                                                |

The catalog contains approximately 1,000 books distributed across listing pages, with 20 books per page.

The site's search box is JavaScript-driven and does not expose a crawlable search-results URL that can be used as an API.

Therefore, `/api/v1/search` is implemented by this project in the service layer by scanning bounded listing pages and filtering book titles.

The `<slug>_<n>` product identifier is used as the API `id`.

---

## Data Extraction

The parser keeps website-specific HTML selectors isolated inside the parser layer.

| Data          | Source in HTML                                         |
| ------------- | ------------------------------------------------------ |
| Full title    | Listing: `h3 a[title]`; product: `div.product_main h1` |
| Price         | `p.price_color`                                        |
| Rating        | Class word on `p.star-rating` (`One` through `Five`)   |
| Stock         | `p.availability`                                       |
| Category      | Breadcrumb, second-to-last `li`                        |
| Description   | Paragraph immediately after `#product_description`     |
| UPC           | `table.table-striped` row                              |
| Tax           | `table.table-striped` row                              |
| Reviews       | `table.table-striped` row                              |
| Image         | `div.image_container img` / `#product_gallery img`     |
| Next page     | `li.next a`                                            |
| Total results | First `<strong>` in `form.form-horizontal`             |

Optional fields are allowed to be missing.

Structural failures are treated differently from optional missing data. If the expected page structure is missing, the API returns an upstream parsing error instead of silently returning incorrect data.

---

## Normalization

Raw HTML values are converted into the API's normalized data model.

### Price

For example:

```text
£51.77
```

becomes:

```json
{
  "price": 51.77,
  "currency": "GBP"
}
```

The parser also handles the `Â£` encoding artifact that can occur when the source does not provide an explicit charset.

### Rating

Rating classes are converted into integers:

```text
One   → 1
Two   → 2
Three → 3
Four  → 4
Five  → 5
```

### Availability

Stock text such as:

```text
In stock (22 available)
```

is normalized into availability information such as:

```json
{
  "in_stock": true,
  "stock_count": 22
}
```

### URLs

Relative image and product URLs are converted into absolute URLs using the source page URL as the base.

### Missing Optional Fields

Optional fields are represented as `null` when unavailable.

Missing optional information does not cause the entire response to fail.

Missing structural markers are treated as parser failures and mapped to:

```text
502 upstream_parse_error
```

---

## API Contract

The website HTML is never exposed directly to API consumers.

The transformation is:

```text
Website HTML
     │
     ▼
HTML Element
     │
     ▼
Website Parser
     │
     ▼
Normalized Model
     │
     ▼
FastAPI Response Model
     │
     ▼
JSON API
```

This keeps the public API contract independent of the website's HTML representation.

---

## Endpoint Design

| Endpoint                 | Purpose                                           |
| ------------------------ | ------------------------------------------------- |
| `GET /health`            | Health/liveness check                             |
| `GET /api/v1/search`     | Search books by title                             |
| `GET /api/v1/items`      | List books with pagination and category filtering |
| `GET /api/v1/items/{id}` | Retrieve a normalized book detail record          |
| `GET /api/v1/categories` | Discover available categories                     |

---

## 1. Health

```http
GET /health
```

Used to determine whether the API process is running.

Example:

```json
{
  "status": "ok"
}
```

---

## 2. Search

```http
GET /api/v1/search?q=light&limit=5
```

Optional category filtering may also be applied where supported by the API contract.

Search is implemented by:

1. Starting from the catalog listing pages.
2. Fetching pages up to `SEARCH_MAX_PAGES`.
3. Parsing the books on each page.
4. Filtering titles against the requested query.
5. Returning normalized results.
6. Reporting the number of scanned pages.
7. Reporting whether the search was partial.

Example response shape:

```json
{
  "query": "light",
  "total": 3,
  "results": [
    {
      "id": "a-light-in-the-attic_1000",
      "title": "A Light in the Attic",
      "price": 51.77,
      "currency": "GBP",
      "rating": 3,
      "in_stock": true,
      "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
      "image_url": "https://books.toscrape.com/media/cache/..."
    }
  ],
  "scanned_pages": 10,
  "partial": true
}
```

`partial: true` means the configured search page limit was reached before the complete catalog could be scanned.

---

## 3. List Books

```http
GET /api/v1/items?page=1&limit=10
```

Optional category filtering:

```http
GET /api/v1/items?page=1&limit=10&category=poetry_23
```

The source website uses a fixed page size of 20 books.

The API provides its own `page` and `limit` abstraction and maps those values to the website's underlying pages.

A request can therefore require more than one upstream page.

For example:

```text
API request:
page=2
limit=20

        ↓

Upstream:
catalogue/page-2.html
```

For smaller API page sizes or offsets, the catalog service handles the required page mapping.

---

## 4. Get Book

```http
GET /api/v1/items/a-light-in-the-attic_1000
```

The ID corresponds to the product slug used by the website.

The service constructs the corresponding public product URL, retrieves the page, parses it, and returns a normalized detail record.

---

## 5. Categories

```http
GET /api/v1/categories
```

Returns the categories discovered from the public catalog structure.

Categories can then be used with the listing endpoint.

---

## Validation Limits

The API deliberately applies bounded input values.

Examples include:

| Input        | Limit                                  |
| ------------ | -------------------------------------- |
| Search query | Maximum 100 characters                 |
| Search limit | Maximum 100                            |
| List limit   | Maximum 20                             |
| Page         | Maximum 10,000                         |
| Book ID      | Explicit pattern and length validation |
| Category     | Explicit pattern validation            |

Invalid values are rejected before making an upstream request.

Example:

```http
GET /api/v1/items?limit=0
```

returns:

```text
400 Bad Request
```

The `/items` endpoint does not accept a free-text search query.

Search belongs to `/api/v1/search` because combining free-text search with a paginated listing endpoint would require a potentially expensive catalog scan.

---

## Error Contract

The API uses structured JSON error responses.

Example:

```json
{
  "error": "not_found",
  "message": "Book 'no-such-book_0' was not found.",
  "status_code": 404
}
```

### Error Mapping

| Situation                       | Retry | API result                         |
| ------------------------------- | ----: | ---------------------------------- |
| Invalid client input            |    No | `400 bad_request`                  |
| Target returns 404              |    No | `404 not_found`                    |
| API rate limit exceeded         |    No | `429 rate_limited` + `Retry-After` |
| Timeout / connection failure    |   Yes | `503 upstream_unavailable`         |
| Target 429                      |   Yes | `503 upstream_unavailable`         |
| Target 502/503/504              |   Yes | `503 upstream_unavailable`         |
| Target 500                      |   Yes | `502 upstream_bad_response`        |
| Target 3xx/400/401/403          |    No | `502 upstream_bad_response`        |
| Non-HTML response               |    No | `502 upstream_bad_response`        |
| Empty upstream body             |    No | `502 upstream_bad_response`        |
| Missing expected HTML structure |    No | `502 upstream_parse_error`         |
| Unexpected internal exception   |    No | `500 internal_error`               |

Internal stack traces and implementation details are not exposed to API consumers.

---

## Retry Strategy

Retries are intentionally limited.

Retryable conditions include:

* Connection errors
* Timeouts
* Upstream `429`
* Upstream `5xx`

Retries use bounded exponential backoff.

The implementation does **not** retry errors such as:

* `400`
* `401`
* `403`
* `404`

This avoids repeatedly requesting resources that are known to be invalid or inaccessible.

---

## Caching

Upstream HTML responses are cached using a TTL-based in-memory cache.

Default TTL:

```text
300 seconds
```

Caching reduces repeated upstream traffic and improves response latency for repeated requests.

Errors are not cached.

In a multi-instance production deployment, a shared cache such as Redis would be preferable.

---

## Rate Limiting

The API includes an inbound per-client rate limiter.

Default configuration:

```text
30 requests / 60 seconds
```

The purpose is to protect both the API and the upstream website.

The limiter is not designed to bypass or evade upstream rate limits.

Outbound requests also have a minimum spacing interval:

```text
UPSTREAM_MIN_INTERVAL_SECONDS
```

This keeps upstream request traffic controlled.

---

## Security

The implementation includes several security controls.

### Target Host Allowlist

The upstream target host is explicitly allow-listed.

There is no endpoint such as:

```http
GET /fetch?url=<arbitrary-url>
```

This prevents the service from becoming a generic HTTP proxy or SSRF primitive.

### Input Validation

User-controlled identifiers are validated using explicit patterns and bounds before being incorporated into upstream paths.

### Redirect Handling

Automatic redirects are disabled for the upstream client.

### Sensitive Information

The application does not require credentials or private customer information.

Error responses do not expose:

* Stack traces
* Environment variables
* Credentials
* Internal implementation details

Logs also avoid recording search query strings.

---

## Reverse-Engineering Boundary

The reverse-engineering work is limited to publicly accessible information.

The project does not:

* Bypass authentication.
* Circumvent CAPTCHA.
* Access private endpoints.
* Guess credentials.
* Access private customer information.
* Circumvent access controls.
* Attempt to evade rate limits.

The goal is to demonstrate API abstraction over public website data.

---

## Design Rationale

The architecture intentionally separates:

```text
HTTP Client
     ↓
HTML Parser
     ↓
Catalog Service
     ↓
FastAPI Routes
     ↓
API Contract
```

This separation allows the upstream integration to change without forcing API consumers to change.

For example, the current implementation could later replace:

```text
WebsiteClient + WebsiteParser
```

with:

```text
Official API Client
```

while keeping the normalized API contract stable.

---

## Production Direction

The current scraper is appropriate for the assignment and controlled demonstration.

For production, the preferred order is:

1. Official API.
2. Official data feed/export.
3. Licensed/documented integration.
4. Permitted scraping only when necessary and appropriately governed.

If an official API becomes available, the adapter can be replaced while preserving the API's normalized schemas and consumer-facing routes.

See `docs/limitations.md` for the detailed limitations and long-term production approach.
