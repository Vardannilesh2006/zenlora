# Zenlora Winning Product Hunting Tool (Real-Data Provenance Edition)

An evidence-led product research and unit-economics engine for the **Zenlora** Indian dropshipping store (`DeoDap` supplier catalog $\rightarrow$ `Google Trends India` & `Google Autosuggest` $\rightarrow$ `Polite Marketplace Price Check` $\rightarrow$ `Meta Ad Library & Instagram Manual/API Validation` $\rightarrow$ `Transparent 10-Criteria Scoring` $\rightarrow$ `Sample & Store Test Tracking`).

---

## Non-Negotiable Architecture Rules

1. **100% Real Data Only:** Zero fake, dummy, sample, random (`Math.random`, `faker`, `hash()`), or hardcoded lookup arrays exist anywhere in the codebase, seed files, or UI.
2. **Strict LLM Boundary:** Google Gemini (`pipeline/winning_engine/gemini_analyzer.py`) is **never** allowed to generate numbers, trends, prices, ad counts, view counts, or sales estimates. It may only classify or summarize visible product inputs, and its output is always labelled **`"AI opinion (not data)"`** (`method: "ai_opinion"`).
3. **Honest `null` States:** Whenever a field cannot be fetched or has not been manually entered yet, it is stored as `null` (`None` in Python) and displayed as **`"Data not available"`** with the exact reason.
4. **Full Provenance Metadata:** Every data point and scored criterion carries:
   - `source`: Human-readable data source name
   - `source_url`: Exact API endpoint, product URL, or search query used
   - `fetched_at`: ISO-8601 UTC timestamp
   - `method`: `api` | `scrape` | `manual_entry` | `rule_based` | `user_assumption` | `ai_opinion`
   - `is_stale`: Automatically flagged `true` when `fetched_at` is older than the configurable limit (default **7 days**).
5. **Transparent 10-Criteria Scoring (0–100):** Missing inputs are **never** silently scored as zero or average—they remain `null` and lower the **Confidence Badge** (`High` / `Medium` / `Low`) and **Data Coverage** counter.

---

## Data Sources, Feasibility & Limits

| Pipeline Step | Source | Method | What It Provides | Limits & Fallback |
| :--- | :--- | :--- | :--- | :--- |
| **1. Supplier Ingest** | **DeoDap Public Shopify JSON API** (`/collections/all/products.json`, `/search/suggest.json`, `/products/<handle>.json`) | `api` | Real product title, SKU, wholesale cost (`price`), `compare_at_price`, stock availability (`variant.available`), images, and `grams` (when non-zero). | DeoDap sets `grams: 0` on many items and does not expose per-product delivery days on product JSON. Missing weight/dimensions are stored as `null`. Store-wide shipping policy (`4–8 business days` from `/policies/shipping-policy`) is shown separately. Includes dual-stack IPv6 (`2620:127:f00f:e::`) + IPv4 support for Indian mobile networks. |
| **2a. Demand Check** | **Google Trends India (`pytrends`)** (`geo='IN'`, `timeframe='today 12-m'`) | `api` | 12-month Indian search interest (0–100), peak month, YoY change %, and Oct–Nov festive spike ratio vs baseline. | Google rate-limits rapid requests (`HTTP 429`). Results are cached in `data/trends_cache.json` with `fetched_at` timestamps. |
| **2b. Autocomplete** | **Google Autosuggest India API** (`suggestqueries.google.com/complete/search?client=firefox&gl=in`) | `api` | Real Indian buyer autocomplete queries and suggestion count. | Free public endpoint; cached in `data/trends_cache.json`. |
| **2c. Video Demand** | **YouTube Data API v3** (`googleapis.com/youtube/v3/search`, `regionCode='IN'`) | `api` | Real Indian YouTube video count and top video titles for the product keyword. | Requires `YOUTUBE_API_KEY` in `.env`. Without key, stores `null` (`"YOUTUBE_API_KEY not configured"`). |
| **3 & 6. Marketplace Price Check** | **Amazon.in, Flipkart, Meesho Public Search Pages** | `scrape` + `manual_entry` | Lowest visible competitor prices to benchmark Zenlora's selling price. | Flipkart and Meesho frequently enforce anti-bot JS challenges (`403`/`503`); Amazon.in works with polite headers and caching (`data/marketplace_cache.json`) but can present CAPTCHAs under heavy load. Whenever blocked, the tool stores `null` with the exact HTTP reason and provides 1-click search links + a Manual Price Entry form. |
| **4. Ads Validation** | **Meta Ad Library (India)** | `manual_entry` | Active ad count, longest-running ad days (`30+ days` signal), distinct creatives count, advertiser names. | Meta Ad Library API requires identity verification and an active token. The tool generates a direct India Ad Library search URL and provides a Manual Entry form (`"Ads not checked yet"` until filled). |
| **5. Social Validation** | **Instagram Graph API / Reels Manual Log** | `api` / `manual_entry` | Reel URL, view count, saves/shares, and `"price?" / "link?"` buying-intent comment count. | Uses Official Instagram Graph API if `INSTAGRAM_ACCESS_TOKEN` and `INSTAGRAM_USER_ID` are set in `.env`; otherwise uses the Manual Entry form (`"Data not available"` until filled). |
| **7 & 8. Sample & Store Tests** | **Zenlora Manual Operations Log** (`data/manual_entries.json`) | `manual_entry` | Sample lifecycle (`shortlisted` $\rightarrow$ `winner`/`killed`) and real store test metrics (`visits`, `ATC`, `orders`, `COD %`, `RTO %`, `ad_spend`, `revenue`). | Computes real delivered net profit and adjusts product ranking based on real test outcomes. |

---

## How to Configure API Keys (`.env`)

Create or edit `.env` in the project root (`e:\Zenlora\.env`):

```env
# Optional: For AI Opinion classification & Hinglish ad hooks (strictly labelled "AI opinion (not data)")
GEMINI_API_KEY=your_google_gemini_api_key_here

# Optional: For Step 2 YouTube India video demand check (YouTube Data API v3)
YOUTUBE_API_KEY=your_youtube_data_api_v3_key_here

# Optional: For Step 5 Official Instagram Graph API hashtag/media lookup
INSTAGRAM_ACCESS_TOKEN=your_instagram_graph_api_token_here
INSTAGRAM_USER_ID=your_instagram_business_user_id_here
```

*Note: The tool works out-of-the-box without any API keys using DeoDap's public JSON API, `pytrends` (India), Google Autosuggest (India), polite Amazon/Flipkart/Meesho scraping, and manual entry forms.*

---

## Running the App & Tests

### 1. Run Automated Real-Data Integrity Tests
```bash
python -m unittest discover -s tests -v
```
This test suite (`tests/test_real_data_only.py`) fails the build if:
- Any hardcoded sample product array, `Math.random()`, `faker`, or `hash()` score generator is found in source files.
- Any criterion in `winning_scorer.py` computes a score without `source`, `source_url`, `fetched_at`, and `method`.
- Missing inputs are silently scored as `0` instead of `None`.

### 2. Run the Flask Radar Dashboard Locally
```bash
python pipeline/web_app.py
```
Open `http://127.0.0.1:5000/radar` to:
- Click **"Scan DeoDap Winners"** (rotates cursor across live DeoDap catalog pages and search seeds on every click).
- Edit **Cost Assumptions ("My Assumptions")**, **10-Criteria Weights**, **Festival Calendar**, and **Restricted Keyword Rules** in the Settings Modal (all changes are recorded in `data/audit_log.json`).
- Open any product detail page (`/product/<handle>`) to trigger live Google Trends/Marketplace fetches or log Meta Ads, Instagram Reels, Sample status, and Store Test results.
