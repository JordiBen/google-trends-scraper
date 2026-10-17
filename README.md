# Google Trends Scraper & API: Interest Over Time, Regions, Rising Queries and Trending Now

[![Run on Apify](https://img.shields.io/badge/Run%20on-Apify-1f6feb?logo=apify)](https://apify.com/manageable_gully/google-trends-scraper) [![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Run it in the cloud with no setup:** [Google Trends Scraper & API: Rising Queries, Regions, Compare on the Apify Store](https://apify.com/manageable_gully/google-trends-scraper).  
> Pay only per result, export to JSON/CSV/Excel, schedule runs and call it from the API.
<!-- Note: the Apify Store page goes live once the Actor is published. -->
<!-- AFFILIATE_LINK_PLACEHOLDER: replace the Apify links above with the affiliate link when available -->

Get **Google Trends data in bulk** without a Google account or the closed Trends API: **interest over time**, **interest by country, region, metro or city**, **top and rising related queries** (including "Breakout" terms) and related topics. Compare **up to 5 keywords on one 0-100 scale**, run **many countries in one go**, and optionally pull today's **Trending Now** searches per country. Every report comes back as one clean JSON row, ready for spreadsheets, dashboards or AI agents.

## What you can use it for
- **SEO and content planning:** find **rising and breakout queries** around your keywords before they peak.
- **E-commerce and product research:** check seasonality and 5-year trends for product ideas (use `searchProperty: shopping` for Google Shopping interest).
- **Market comparison:** compare up to 5 brands or products on one 0-100 scale, in 50 countries in one run.
- **Local marketing:** see which states, regions, metro areas or cities search for a term most.
- **News and social teams:** Trending Now searches per country, with approximate traffic and news links.
- **AI agents and dashboards:** stable JSON for every report, ready for an LLM or a BI tool.

## How to use it
1. Add keywords under **Search terms** (each analysed alone) and/or **Comparison groups** like `chatgpt, gemini, claude`.
2. Add the **countries / regions** (`US`, `GB`, `US-CA` ...) or leave empty for Worldwide.
3. Pick a **time range** (`past-12-months`, `past-5-years`, `2024-01-01 2024-12-31` ...).
4. Click **Start**. Each term or group in each geo becomes one report row.

## What you get in each report
| Section | Details |
|---|---|
| **Interest over time** | Timeline of 0-100 values per term (hourly, daily, weekly or monthly depending on the range), `isPartial` flag for the current period, and the average per term |
| **Interest by region** | Countries (Worldwide), states/regions (a country), or metros/cities, sorted by interest, with geo codes |
| **Related queries** | Top and rising searches per term with values like `+250%` and `Breakout` flags, plus links to open them in Google Trends |
| **Related topics** | Top and rising topics with topic type and Knowledge Graph id (single-term searches) |
| **Trending Now** | Trending searches per country with approximate traffic (`2,000+`), publish time, picture and news links |

Filters work like trends.google.com: time range (past hour to since 2004, or custom dates), category, and search type (web, images, news, Google Shopping, YouTube).

## Input examples
Rising queries and 12-month trend for a few keywords in the US:
```json
{ "searchTerms": ["air fryer", "standing desk", "protein powder"], "geos": ["US"], "timeRange": "past-12-months" }
```
Compare five AI assistants in five markets on one scale:
```json
{ "comparisonGroups": ["chatgpt, gemini, claude, copilot, perplexity"], "geos": ["", "US", "GB", "DE", "IN"], "timeRange": "past-90-days" }
```
YouTube search interest by US metro area for a custom date range:
```json
{ "searchTerms": ["minecraft"], "geos": ["US"], "timeRange": "2025-01-01 2025-12-31", "searchProperty": "youtube", "regionResolution": "DMA" }
```
Today's trending searches in three countries:
```json
{ "trendingNowGeos": ["US", "GB", "IL"], "maxTrendingPerGeo": 20 }
```

## Output
One row per term (or comparison group) and geo (shortened example):
```json
{
  "type": "keywordReport",
  "searchTerms": ["chatgpt", "gemini", "claude"],
  "isComparison": true,
  "geo": "US",
  "timeRange": "today 3-m",
  "averages": {"chatgpt": 66, "gemini": 27, "claude": 18},
  "interestOverTime": [
    {"date": "2026-07-17T00:00:00Z", "formattedTime": "Jul 17, 2026", "values": {"chatgpt": 62, "gemini": 23, "claude": 21}, "isPartial": false}
  ],
  "interestByRegion": [
    {"geoCode": "US-MS", "geoName": "Mississippi", "values": {"chatgpt": 73, "gemini": 19, "claude": 8}}
  ],
  "relatedQueries": {
    "claude": {
      "top": [{"query": "claude ai", "value": 100, "formattedValue": "100", "isBreakout": false, "link": "https://trends.google.com/trends/explore?q=claude+ai&date=today+3-m&geo=US"}],
      "rising": [{"query": "claude code", "value": 5000, "formattedValue": "Breakout", "isBreakout": true, "link": "https://trends.google.com/trends/explore?q=claude+code&date=today+3-m&geo=US"}]
    }
  },
  "hasData": true,
  "trendsUrl": "https://trends.google.com/trends/explore?q=chatgpt%2Cgemini%2Cclaude&date=today%203-m&geo=US",
  "charged": true,
  "scrapedAt": "2026-10-17T09:05:11Z"
}
```
Trending Now rows:
```json
{ "type": "trendingNow", "geo": "US", "rank": 1, "title": "hurricane trudy", "approxTraffic": "1000+", "approxTrafficNumber": 1000,
  "publishedAt": "2026-10-17T08:30:00Z", "news": [{"title": "...", "url": "https://...", "source": "..."}] }
```
Values are illustrative. Export as JSON, CSV or Excel, or read them from the API.

## Why this one
- **Reliable:** fresh sessions, backoff on HTTP 429 and an automatic residential-proxy fallback. Incomplete reports are returned with an `errors` field and **not charged**.
- **Cheap and fast:** plain HTTP (no browser), 256 MB memory, about 1 second per report. A comparison of 5 terms is still **one** report.
- **Bulk by design:** every term and comparison group runs in every geo you list, in parallel.
- **Stable schema** with ISO dates and per-term value maps, easy for spreadsheets, SQL and LLM agents.

## Limits
- Google Trends values are relative (0-100), not absolute search volumes.
- Google allows at most 5 terms per comparison. Very rare terms may have no data (`hasData: false`, free).
- Related topics are shown by Google only for single terms and are sometimes empty.
- Logged-out public data only. Google's Terms of Service restrict automated access; use the data responsibly. This Actor is not affiliated with Google.

## Pricing
Pay per event, no monthly rent: **$0.002 per keyword report** (**$2.00 per 1,000**).
- **$0.0005 per Trending Now search**

| Example | Cost |
|---|---|
| 100 keywords in one country | $0.20 |
| 1,000 reports | $2.00 |
| A 5-brand comparison in 50 countries (50 reports) | $0.10 |
| Trending Now for 10 countries x 50 searches | $0.25 |

You can set a **maximum cost per run** in the run options; the Actor stops cleanly when it is reached. New to Apify? The free plan includes $5 of platform credit every month, so you can try this Actor at no cost.

## API, integrations and AI agents (MCP)
Run it from your own code with the [Apify API](https://docs.apify.com/api/v2) and get the results in one call:
```bash
curl -X POST "https://api.apify.com/v2/acts/manageable_gully~google-trends-scraper/run-sync-get-dataset-items?token=<YOUR_APIFY_TOKEN>" \
  -H "Content-Type: application/json" -d @input.json
```
```python
from apify_client import ApifyClient
run = ApifyClient("<YOUR_APIFY_TOKEN>").actor("manageable_gully/google-trends-scraper").call(run_input={...})
```
- **No-code:** use the Apify app in **n8n, Make or Zapier** ("Run Actor", then "Get dataset items"), or send results to Google Sheets, Slack or a webhook.
- **AI agents (MCP):** add `https://mcp.apify.com?tools=manageable_gully/google-trends-scraper` to Claude, Cursor, VS Code or any MCP client and the agent can call this Actor as a tool.
- **Schedules:** run it hourly, daily or weekly from Apify Console.

## FAQ
**Is there an official Google Trends API?** Google offers a Trends API only to a small alpha group. This Actor reads the same public data that trends.google.com shows, without a Google account.

**Are the numbers search volumes?** No. Google Trends values are relative interest from 0 to 100 (100 = peak popularity for the selected terms, place and time). Terms in a comparison group share one scale.

**Why are related topics sometimes empty?** Google shows related topics only for single-term searches and omits them for low-volume terms. Related queries are usually available.

**What happens when Google rate-limits?** The Actor retries with fresh sessions and switches to residential proxies automatically. Reports that still fail come back with an `errors` field and are not charged.

**Do I pay for terms with no data?** No. Reports where Google has no data (`hasData: false`) are returned for transparency and not charged.

**Can AI agents use it?** Yes. It is available as a tool through the Apify MCP server (`https://mcp.apify.com?tools=manageable_gully/google-trends-scraper`) and the Apify API, and it returns structured JSON that agents can read directly.

## More tools from WebIntel Tools
- [SEO Audit & Domain Checker](https://apify.com/manageable_gully/website-health-audit): SEO, DNS, SSL and security-header audit for lists of domains
- [Lighthouse & PageSpeed Bulk Audit](https://apify.com/manageable_gully/lighthouse-bulk-audit): Lighthouse scores and Core Web Vitals for hundreds of URLs
- [RSS Feed Reader & Monitor](https://apify.com/manageable_gully/rss-feed-reader): read and monitor RSS, Atom and JSON feeds, only new items
- [Product Hunt Scraper](https://apify.com/manageable_gully/product-hunt-scraper): daily, weekly and monthly Product Hunt launches with websites

See [all WebIntel Tools Actors](https://apify.com/manageable_gully).

*Made by WebIntel Tools. This Actor was built and is maintained with AI assistance. Report issues on the Issues tab; they are monitored daily.*

## Run from source
This repository is the full source of the [Google Trends Scraper & API: Rising Queries, Regions, Compare](https://apify.com/manageable_gully/google-trends-scraper) Actor.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest
# run locally with the Apify CLI (https://docs.apify.com/cli):
apify run --input '{...}'
```

Deploy your own copy with `apify push`. The easiest way to use it is the hosted version on the [Apify Store](https://apify.com/manageable_gully/google-trends-scraper).

## License
MIT, see [LICENSE](LICENSE).
