# Books Catalog API

A REST API built by reverse-engineering the public HTML catalog at [Books to Scrape](https://books.toscrape.com/), a sandbox e-commerce website intentionally designed for scraping practice.

This project demonstrates how a public website without a public API can be transformed into a structured, documented REST API while adding validation, caching, rate limiting, retries, error handling, testing, and security controls.

---

## Assignment Summary

**Task:** Reverse-engineer an API for a website that does not expose a public API.

**Selected website:** `https://books.toscrape.com/`

**Approach:** Read publicly accessible HTML pages, parse the catalog data, normalize it into typed models, and expose the data through a FastAPI-based REST API.

The implementation uses only publicly accessible website information. It does not require authentication, credentials, private data, or access-control bypasses.

---

## Why This Website?

Books to Scrape is a public sandbox website specifically designed for scraping practice.

| Requirement                                       | Result                                |
| ------------------------------------------------- | ------------------------------------- |
| No public API                                     | ✔ HTML-only catalog                   |
| Public access                                     | ✔ No login required                   |
| No CAPTCHA                                        | ✔                                     |
| Simple, stable HTML structure                     | ✔                                     |
| Enough data for testing                           | ✔ 1,000 books across 50 listing pages |
| No personal/customer data                         | ✔                                     |
| Suitable for a controlled technical demonstration | ✔                                     |

The website provides enough public catalog data to demonstrate listing, searching, category browsing, and individual book retrieval.

---

## What the API Provides

The API converts the website's HTML catalog into structured JSON.

For each book, the API can expose:

* Title
* Price
* Currency
* Star rating
* Availability / stock
* Category
* Description
* UPC
* Tax
* Tax percentage
* Review count
* Image URL
* Product URL

The API acts as an abstraction layer between the original HTML website and API consumers.

Instead of requiring clients to understand the website's HTML structure, clients interact with a stable REST interface.

---

## API Endpoints

### Health

```http
GET /health
```

Returns the API health status.

---

### List Books

```http
GET /api/v1/items
```

Supports pagination and category filtering.

Example:

```http
GET /api/v1/items?limit=10&offset=0
```

---

### Get Book

```http
GET /api/v1/items/{book_id}
```

Example:

```http
GET /api/v1/items/a-light-in-the-attic_1000
```

---

### Search Books

```http
GET /api/v1/search?q=light
```

Search is implemented by scanning public catalog listing pages and filtering book titles.

Because search requires scanning upstream listing pages, the number of pages scanned is bounded by the `SEARCH_MAX_PAGES` configuration.

The response indicates whether the search was partial.

---

### List Categories

```http
GET /api/v1/categories
```

Returns available book categories.

---

## Architecture

```text
                 Public Website
                books.toscrape.com
                         │
                         ▼
                  WebsiteClient
                         │
                         ▼
                    TTL Cache
                         │
                         ▼
                   HTML Parser
                         │
                         ▼
              Normalized Pydantic Models
                         │
                         ▼
                Book Catalog Service
                         │
                         ▼
                    FastAPI
                         │
                         ▼
                  REST JSON API
                         │
                         ▼
                API Consumer / Client
```

### Main Components

**WebsiteClient**

Responsible for communicating with the upstream website.

Responsibilities:

* HTTP requests
* Timeouts
* Retries
* Upstream status handling
* Request headers
* Target-host validation

**TTL Cache**

Reduces repeated upstream requests and avoids unnecessary traffic.

**WebsiteParser**

Converts HTML pages into structured application data.

**Pydantic Models**

Provide typed and validated API responses.

**BookCatalogService**

Contains the application-level catalog and search logic.

**FastAPI Routes**

Expose the catalog functionality through REST endpoints.

---

## Project Structure

```text
books-catalog-api/
│
├── app/
│   ├── api/
│   │   └── routes/
│   ├── models/
│   ├── services/
│   ├── utils/
│   └── main.py
│
├── docs/
│   ├── architecture.md
│   ├── api-design.md
│   └── limitations.md
│
├── scripts/
│   └── demo.py
│
├── tests/
│   ├── fixtures/
│   ├── test_api.py
│   ├── test_client.py
│   ├── test_parser.py
│   ├── test_security.py
│   └── test_live.py
│
├── .env.example
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Key Features

### REST API

Built using FastAPI with automatically generated OpenAPI documentation.

Available documentation:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
http://127.0.0.1:8000/openapi.json
```

### Input Validation

Invalid query parameters and request values return appropriate HTTP errors instead of being silently accepted.

Example:

```http
GET /api/v1/items?limit=0
```

Returns:

```http
400 Bad Request
```

### Error Handling

The API handles:

* Invalid requests
* Missing books
* Invalid upstream responses
* Upstream service failures
* Connection failures
* Timeouts
* Malformed HTML
* Unexpected application errors

The API does not expose internal exception details to clients.

### Caching

A TTL-based cache reduces repeated requests to the upstream website.

This improves response performance and reduces unnecessary upstream traffic.

### Rate Limiting

The API includes request rate limiting to prevent excessive client requests.

### Upstream Politeness

The upstream client includes:

* Request timeouts
* Retry handling
* Bounded search scanning
* Caching
* Controlled request behavior

The implementation is intentionally designed to avoid aggressive scraping behavior.

### Security

The project includes safeguards such as:

* Target-host allowlisting
* No arbitrary URL fetching
* No credentials
* No private data
* No authentication bypass
* No access-control bypass
* Protection against path traversal
* No generic proxy/fetch endpoint

Only the intended public website is accessed by the application.

### Structured Logging

Application activity includes structured logs for easier debugging and operational visibility.

---

## Technology Stack

* Python 3.11+
* FastAPI
* Uvicorn
* HTTPX
* BeautifulSoup4
* Pydantic
* Pytest
* python-dotenv

---

## Installation

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd books-catalog-api
```

### 2. Create a virtual environment

#### Windows

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell execution policy prevents activation, you can run:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run the API

Start the development server:

```bash
uvicorn app.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Open the interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Running the Demo

### Offline Demo

The offline demo uses local fixtures and does not make live requests.

```bash
python scripts/demo.py --offline
```

This validates:

* API health
* Search
* Book retrieval
* Invalid request handling
* Not-found handling

### Live Demo

The live demo communicates with the public Books to Scrape website.

```bash
python scripts/demo.py
```

The live demonstration validates:

* API health
* Search
* Book retrieval
* Input validation
* 404 handling
* Real upstream communication

---

## Testing

Run the deterministic test suite:

```bash
pytest -v
```

The test suite covers:

* API routes
* Request validation
* Book retrieval
* Search
* Category handling
* HTML parsing
* Cache behavior
* Rate limiting
* Retry behavior
* Timeout handling
* Upstream errors
* Connection failures
* Security controls
* Path traversal protection
* Host allowlisting
* Error response handling
* OpenAPI availability
* Request IDs
* Offline fixtures

### Current Test Result

```text
72 passed
1 skipped
1 warning
```

The skipped test is the optional live integration test, which requires explicit opt-in.

---

## Live Integration Tests

Live tests are disabled by default so that the normal test suite remains deterministic and does not depend on external network availability.

### Windows PowerShell

```powershell
$env:RUN_LIVE_TESTS="1"
pytest -m live -v
```

### Linux / macOS

```bash
RUN_LIVE_TESTS=1 pytest -m live -v
```

Live tests communicate with the public Books to Scrape website.

---

## Example Requests

### Health

```bash
curl http://127.0.0.1:8000/health
```

### List Books

```bash
curl "http://127.0.0.1:8000/api/v1/items?limit=10&offset=0"
```

### Search

```bash
curl "http://127.0.0.1:8000/api/v1/search?q=light&limit=5"
```

### Get a Book

```bash
curl "http://127.0.0.1:8000/api/v1/items/a-light-in-the-attic_1000"
```

### Categories

```bash
curl "http://127.0.0.1:8000/api/v1/categories"
```

---

## Example Search Response

```json
{
  "query": "light",
  "items": [
    {
      "id": "a-light-in-the-attic_1000",
      "title": "A Light in the Attic",
      "price": 51.77,
      "currency": "GBP",
      "rating": 3,
      "availability": "In stock",
      "stock": 22,
      "category": "Poetry"
    }
  ],
  "count": 1,
  "scanned_pages": 10,
  "partial": true
}
```

The `partial` field indicates whether the search was bounded by the configured maximum number of pages.

---

## Caching Strategy

The API uses a TTL cache for upstream website responses.

The purpose is to:

1. Reduce repeated upstream requests.
2. Improve API response time.
3. Reduce unnecessary traffic to the source website.
4. Make repeated requests more efficient.

Cache expiration is configurable.

---

## Rate Limiting Strategy

The API applies a configurable rate limit to incoming requests.

The purpose is to prevent clients from generating excessive request traffic.

The upstream scraper also uses bounded scanning, timeouts, retries, and caching.

---

## Search Design

The original website does not expose a search API.

Therefore, the API implements search by:

1. Starting from the public catalog listing pages.
2. Fetching listing pages within a configured maximum.
3. Extracting book information.
4. Filtering titles against the requested search query.
5. Returning normalized results.
6. Indicating whether the search was partial.

This approach is appropriate for a reverse-engineering demonstration, but it would not be the ideal architecture for a production-scale integration.

---

## Limitations

This implementation intentionally mirrors a public HTML website rather than integrating with a first-party API.

Potential limitations include:

* HTML structure can change.
* CSS selectors may become invalid.
* Search requires scanning listing pages.
* Search results may be partial when the configured page limit is reached.
* The upstream website may become unavailable.
* Response times depend partly on upstream availability.
* The source website does not provide an official API contract.
* Scraping is inherently more fragile than a supported API integration.

For these reasons, the project treats the website parser as an adapter that could later be replaced by a supported upstream integration.

See:

```text
docs/limitations.md
```

for the detailed limitations and long-term integration approach.

---

## Long-Term Production Approach

For a real production integration, scraping should not be the preferred long-term solution when a supported integration is available.

A production implementation should use, in order of preference:

1. An official API from the data provider.
2. An official feed/export mechanism.
3. A licensed or documented integration.
4. A controlled scraping adapter only when permitted and necessary.

The current architecture intentionally separates the upstream client/parser from the API and service layers so that the scraping implementation can be replaced without changing the public API contract.

For example:

```text
Current:

FastAPI
   │
   ▼
Catalog Service
   │
   ▼
HTML Scraper
   │
   ▼
Books to Scrape


Potential Production Version:

FastAPI
   │
   ▼
Catalog Service
   │
   ▼
Official API / Feed
   │
   ▼
Data Provider
```

This separation is the main architectural reason for keeping the scraper behind a dedicated client/service layer.

---

## Before Pointing This Project at a Real Website

This project is demonstrated against Books to Scrape, a public sandbox.

Before adapting the implementation to another website:

* Review the website's `robots.txt`.
* Review its terms and usage policies.
* Confirm that automated access is permitted.
* Avoid authentication-protected content.
* Do not collect personal or sensitive information.
* Respect rate limits.
* Keep request volume controlled.
* Prefer an official API or feed when available.

---

## Assignment Coverage

This project covers the requested reverse-engineering assignment deliverables:

* ✔ Public website without a public API
* ✔ Publicly accessible information only
* ✔ REST API abstraction over website data
* ✔ Book listing endpoint
* ✔ Book retrieval endpoint
* ✔ Search endpoint
* ✔ Category endpoint
* ✔ Working demonstration script
* ✔ Offline test/demo mode
* ✔ Live integration validation
* ✔ Input validation
* ✔ Error handling
* ✔ Retry and timeout handling
* ✔ Caching
* ✔ Rate limiting
* ✔ Security controls
* ✔ Deterministic automated tests
* ✔ Documented limitations
* ✔ Documented long-term production approach
* ✔ No credentials or private customer data

---

## Verification Status

The implementation has been validated through both deterministic tests and live integration.

* ✔ 72 deterministic tests passed.
* ✔ Optional live integration validated successfully against Books to Scrape.
* ✔ Offline demo completed successfully.
* ✔ Live demo completed successfully.
* ✔ API server boots successfully.
* ✔ `/health` returns successfully.
* ✔ `/docs` is available.
* ✔ `/redoc` is available.
* ✔ `/openapi.json` is available.
* ✔ Live search was validated.
* ✔ Live book retrieval was validated.
* ✔ Validation errors were validated.
* ✔ 404 handling was validated.
* ✔ Upstream error handling is covered by tests.
* ✔ Security protections are covered by tests.

---

## Demo Result

Example live flow:

```text
Start API
   ↓
GET /health
   ↓
Search for "light"
   ↓
Retrieve "A Light in the Attic"
   ↓
Test invalid request
   ↓
Test missing book
   ↓
Complete
```

The complete flow is available through:

```bash
python scripts/demo.py
```

---

## API Documentation

Once the application is running:

**Swagger UI**

```text
http://127.0.0.1:8000/docs
```

**ReDoc**

```text
http://127.0.0.1:8000/redoc
```

**OpenAPI JSON**

```text
http://127.0.0.1:8000/openapi.json
```

---

## Conclusion

This project demonstrates how to build a REST API abstraction over a website that does not expose a public API.

The implementation goes beyond simply scraping HTML by adding:

* A clean API contract
* Typed data models
* Input validation
* Error handling
* Caching
* Rate limiting
* Retry and timeout handling
* Security controls
* Automated tests
* Offline fixtures
* Live integration validation
* API documentation
* A documented migration path toward a supported production integration

The scraper is intentionally isolated behind an adapter-style architecture so the upstream implementation can be replaced later without redesigning the API layer.
