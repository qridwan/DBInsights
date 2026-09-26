"""Dashboard backend: runs scans, stores their findings and view snapshots, serves them read-only.

Runs on the host (`uv run uvicorn api.dashboard.app:app --port 8710`), separate from the
collector service, because a scan needs the repository, `node` and the database.
"""
