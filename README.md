# GIS Route Analysis Architecture Backend

This repository contains the backend architecture for the GIS Route Analysis project. It manages the storage, analysis, and API layer for street survey data and AI-based urban morphology estimations.

## System Architecture

The tech stack comprises:
- **FastAPI**: Main web framework for high-performance API endpoints.
- **SQLAlchemy & GeoAlchemy2**: Database ORM with PostGIS spatial capability.
- **PostgreSQL + PostGIS**: Robust relational database handling spatial features.
- **Alembic**: Database schema migrations.
- **Google Gemini**: Integration for visual AI morphology analysis.

## Directory Structure

- `app/` / `main.py` - Application entry point. Follows modular architecture for route and analysis management.
- `dao/` - Data Access Object layer for database interactions (CRUD).
- `models/` - SQLAlchemy models dictating database tables and relationships (`route`, `analysis`).
- `schemas/` - Pydantic models for request validation and response formatting.
- `routers/` - FastAPI router endpoints definitions.
- `services/` - Business logic and external service integrations (Gemini AI, Storage, Google Street View).
- `scripts/` - Maintenance and utility scripts (`backup.py`, `upload.py`, `import_data.py`, `rebuild_db.py`).
- `alembic/` - Migration state definitions.

## Setup Instructions

1. **Environment Config**:
   Copy `.env.example` to `.env` and fill in DB credentials and API keys.
2. **Virtual Environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Database Migration**:
   ```bash
   alembic upgrade head
   ```
4. **Run Application**:
   ```bash
   uvicorn main:app --reload
   ```

## Development and Scripts

- Add newly analyzed route geometries or bulk data using `scripts/upload.py`.
- Refresh or backup metadata utilizing `scripts/backup.py` and `scripts/import_data.py`.
- **Warning**: Do not commit bulk image sets or `.env` files. Ensure you periodically clean development artifacts.