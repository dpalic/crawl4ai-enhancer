# Crawl4AI Enhancer

Crawl4AI Enhancer is a microservice that sits in front of Crawl4AI as a proxy and enriches every crawl for easier AI-ready ingestion. It is shipping with Docker/Compose for quick deployment. Crawl4AI Enhancer is adding following missing features:
- Link enrichment: collects all outgoing page links (anchors, hrefs) so you can queue the next URLs.
- HTML snapshots: stores the raw HTML (.html) for reproducing or re-parsing pages later.
- Media extraction: pulls media URLs and content for images (.png/.jpg/.jpeg/.gif/.webp), video (.mp4/.webm), and audio (.mp3/.wav).
- PDF extraction: captures PDF URLs and content (.pdf) when present.
- Network traces: records network requests/responses so you can debug missing assets or blocked resources.

## Backward compatibility to Crawl4AI

You can use all your previous code used with Crawl4AI, as Crawl4AI Enhancer is a man in the middle between your client and the Crawl4AI. So the only change is, that you change the URL of your Crawl4AI URL to the Crawl4AI Enhancer URL and your previous code is working as before.
If you want to use it consider this architecture.

```
  +---------+           HTTP (to 11234)          +-------------------+     HTTP (to 11235)       +-------------+
  | Client  | ---------------------------------> | Crawl4AI Enhancer | ------------------------> |  Crawl4AI   |
  |         | <--------------------------------- |      (proxy)      | <------------------------ |  Upstream   |
  +---------+       returns enriched JSON        |  - hooks: enrich  |      results JSON         |             |                  
                                                 |  - enhanced_media |                           +-------------+
                                                 |  - CSS fetch/parse|
                                                 +-------------------+
```

  Task polling (ports shown):

```
  +---------+   GET /task/{id} (to 11234)   +-------------------+   GET /task/{id} (to 11235)   +-------------+
  | Client  | ----------------------------> | Crawl4AI Enhancer | ----------------------------> |  Crawl4AI   |
  |         | <---------------------------- |  (proxy)          | <---------------------------- |  Upstream   |
  +---------+      results passthru         +-------------------+       results JSON            +-------------+
```


# How to run Crawl4AI Enhancer?

## Quickstart (Docker)
- Copy `.env.example` to `.env`
- edit `.env` and adjust values (set IMAGE_OWNER/IMAGE_NAME/IMAGE_TAG if pulling from your GHCR).
- Pull and run (default): `docker compose up -d` — pulls `ghcr.io/${IMAGE_OWNER}/${IMAGE_NAME}:${IMAGE_TAG}`.
- Local build instead: `docker compose -f docker-compose.yml -f docker-compose.build.yml up --build`.
- API: http://localhost:11234/docs

## Local development _without_ Docker
- `python -m venv .venv && source .venv/bin/activate`
- `pip install -r requirements-dev.txt`
- now start the application with:
   - best used with auto-creates venv, installs deps, loads .env   
         `./run.sh`
   - with other log level   
      `LOG_LEVEL=debug ./run.sh`   
      `LOG_LEVEL=trace ./run.sh`
   - or the standard way:   
      `uvicorn app.main:app --reload --env-file .env`


## Logging

If you are new to log levels be aware that the log level defines the highest details you want to see. So if you define CRITICAL you will only see CRITICAL errors, which are only in very very few environments helpful.
If you use the default log level INFO, it will include INFO, WARNING, ERROR and CRITICAL!
If you want to use more detail, use DEBUG, and if you want to be even more verbose use TRACE level.

By default log level is set to INFO. You can use the logging levels: 
- CRITICAL
- ERROR
- WARNING
- INFO (default)
- DEBUG. 
- TRACE (project custom level TRACE (python value=5) is also available; per-file CSS fetch details are logged at TRACE. Summary lines (e.g., “Files fetching summary…”) are INFO. Set `LOG_LEVEL=TRACE` to see per-file fetch URLs/paths; use `LOG_LEVEL=INFO` to see only summaries.


## Environment variables
- APP_NAME: display name (default "Crawl4AI Enhancer")
- APP_ID: identifier slug (default "crawl4ai-enhancer")
- VERSION: API version string (default 0.1.0)
- DATA_DIR: in-container path for persisted files (default /data)
- DB_URL: SQLAlchemy URL (default sqlite:////data/app.db)
- UPSTREAM_BASE_URL: Crawl4AI server base URL to proxy (default http://localhost:11235)
- UPSTREAM_AUTH_HEADER: Optional Authorization header value for upstream calls (default empty)
- UPSTREAM_TIMEOUT_SECONDS: Upstream HTTP timeout for enhancer→Crawl4AI calls (default 300 seconds)

## Enhancer request options
When calling `/crawl`, you can include an optional `crawl4ai_enhancer_options` block to control proxy-side enrichment:
```json
{
  "urls": ["https://example.com"],
    "include_html": true,
    "include_links": true,
    "capture_network_requests": true,
    "crawl4ai_enhancer_options": {
      "timeout_seconds": 300,            // optional per-request override of enhancer→upstream HTTP timeout
      "log_snippet": false,              // optionally include a short content snippet in the response for visibility
      "client_uuid": "abc123",           // optional client correlation; generated if omitted
      "media_extraction": {
        "extraction_media_enabled": true,     // master switch: extract media from HTML into enhanced_media
        "extract_media_from_css": true,      // parse captured CSS (from network_requests) for url(...) and add to enhanced_media
        "extract_media_from_network_requests": false, // parse network_requests for direct media assets (images/videos/audios)
        "media_exclude_patterns": [],        // optional list of substrings/regex to drop matching media (matched against URL path)
        "css_media_save_local": false,       // if true, save fetched CSS to disk (default: do not persist)
        "extraction_media_images": true,     // include images in enhanced_media (ignored when master is false)
        "extraction_media_videos": true,     // include videos in enhanced_media (ignored when master is false)
        "extraction_media_audios": true,     // include audios in enhanced_media (ignored when master is false)
        "extraction_media_pdfs": true       // include PDFs in enhanced_media (ignored when master is false)
      }
    }
}
```

Example curl:
```bash
curl -X POST http://localhost:11234/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://example.com"],
    "include_html": true,
    "include_links": true,
    "capture_network_requests": true,
    "crawl4ai_enhancer_options": {
      "timeout_seconds": 300,
      "log_snippet": false,
      "client_uuid": "abc123",
      "media_extraction": {
        "extraction_media_enabled": true,
        "extract_media_from_css": true,
        "extract_media_from_network_requests": false,
        "media_exclude_patterns": ["tracking", ".*pixel.*", "wp-content/plugins"],
        "css_media_save_local": false,
        "extraction_media_images": true,
        "extraction_media_videos": true,
        "extraction_media_audios": true,
        "extraction_media_pdfs": false
      },
      "priority": 10
    }
  }'
```

## Layout
- app/: application code (api routes, config, db helpers)
- data/: persisted volume mounted at /data in the container
- tests/: basic health check
- Dockerfile, docker-compose.yml (pull from GHCR), docker-compose.build.yml (local build override): containerization assets
- requirements*.txt: dependencies
- .env.example: dependencies and config defaults
- scripts/build-push-ghcr.sh: helper to build/push the image to GHCR

## Notes
- SQLite lives at /data/app.db by default. The data directory is a Docker volume so the DB survives rebuilds.
- Switch to PostgreSQL/MySQL in DB_URL for production multi-replica deployments.
- Logging levels: CRITICAL/ERROR/WARNING/INFO/DEBUG. A custom TRACE (5) is also available; per-file CSS fetch details are logged at TRACE. Summary lines (e.g., “Files fetching summary…”) are INFO. Set `LOG_LEVEL=TRACE` to see per-file fetch URLs/paths; use `LOG_LEVEL=INFO` to see only summaries.

## Publishing the Docker image to GHCR

You can publish the enhancer image to GitHub Container Registry with the helper script:

1. Create a token with `write:packages` (classic PAT is simplest) and log in:
   ```bash
   echo "$GHCR_TOKEN" | docker login ghcr.io -u YOUR_GH_USERNAME --password-stdin
   ```
2. (Optional) set defaults in `.env_publish`:
   - `GHCR_OWNER`: e.g., `dpalic`
   - `GHCR_IMAGE_NAME`: e.g., `crawl4ai-enhancer`
   - `GHCR_TOKEN`: your GHCR token (or set via env at run time)
   - Leave the tag out of `.env_publish`; you must pass it when running.
3. Run the script with an explicit tag:
   ```bash
   ./scripts/build-push-ghcr.sh --owner=dpalic --name=crawl4ai-enhancer --tag=0.1.0
   ```
   You can also set `GHCR_IMAGE_TAG` in the environment instead of `--tag`. By default the script also pushes `latest`; disable with `--push-latest=false`.
