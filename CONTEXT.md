# Context Notes

- Purpose: FastAPI microservice skeleton with Docker; SQLite default persisted in /data volume.
- Key versions: FastAPI 0.127.0, uvicorn[standard], pydantic-settings 2.x, SQLAlchemy 2.x.
- Layout: app/ (main, core/config, api/routes/health, db/session), tests/test_health.py, data/.gitkeep, Dockerfile, docker-compose.yml, requirements*.txt, .env.example, README.md.
- Docker: VOLUME /data; docker-compose mounts named volume app_data:/data, exposes 8000; CMD uvicorn app.main:app --host 0.0.0.0 --port 8000.
- Config: env vars APP_NAME, VERSION, DATA_DIR (/data), DB_URL (sqlite:////data/app.db). Lifespan ensures data dir exists. DB session factory at app/db/session.py with SQLite check_same_thread False.
- Notes: Use .env for env vars; for local dev `uvicorn app.main:app --reload --env-file .env`; switch DB_URL to Postgres for multi-replica deployments. SQLite file lives under the data volume; backup by copying the db file (plus wal if enabled).
- Test: tests/test_health.py validates /api/health returns status ok.
