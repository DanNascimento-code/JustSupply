# JustSupply

JustSupply is an evidence-based due diligence platform for small vegan brands and ethical procurement teams. Its purpose is to help these organizations understand not only whether a product is vegan, but also what evidence exists about its supply chain and what information is still missing.

## Problem

A claim such as "vegan" does not, by itself, establish whether a supply chain respects women, workers, communities, animals, and ecosystems. Supplier documents may also be incomplete, outdated, contradictory, or supported only by unverified statements.

JustSupply will organize this information without producing an arbitrary ethical score. Every conclusion should identify its source, location within the document, evidence quality, freshness, and human review status.

## MVP

The first version will be **JustSupply Pro**, designed for small vegan brands, procurement teams, and organizations that conduct supplier due diligence.

The initial scope includes:

- cocoa and coffee as the first commodities;
- supplier document and certificate uploads;
- structured extraction of the information found;
- provenance tracking for every piece of evidence;
- identification of missing or contradictory information;
- human review of extracted information;
- supplier comparison based on evidence availability and quality;
- generation of evidence-based questions for suppliers.

The MVP will not issue legal verdicts, make automated accusations, or assign an overall "ethical" score to suppliers.

## Future vision

The evidence platform may eventually support two interfaces:

- **JustSupply Pro:** supplier documents, due diligence, and evidence review;
- **JustSupply Consumer:** product search, barcode scanning, and explanations based on consumer-selected priorities.

Both interfaces should use the same evidence base while preserving the distinction between product-level, brand-level, supplier-level, and commodity-region risk information.

## Planned architecture

- Backend: Python and FastAPI;
- Frontend: React with TypeScript;
- Database: PostgreSQL;
- Data validation: Pydantic;
- Persistence and migrations: SQLAlchemy and Alembic;
- Testing: pytest for the backend and React ecosystem testing tools for the frontend.

## Current capabilities

- API health check;
- create, list, retrieve, update, and delete suppliers;
- supplier input validation with Pydantic;
- PostgreSQL persistence with SQLAlchemy;
- versioned database migrations with Alembic;
- pgvector-enabled PostgreSQL container;
- in-memory repository used as an isolated test double;
- automated API tests, linting, formatting, and static type checking.

## Local development

Copy the local environment template:

```powershell
Copy-Item .env.example .env
```

Install the project and development tools inside the activated virtual environment:

```powershell
python -m pip install --editable ".[dev]"
```

Start PostgreSQL:

```powershell
docker compose up -d database
```

Apply the database migrations:

```powershell
python -m alembic upgrade head
```

Run the quality checks:

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy backend\justsupply
python -m pytest
```

Run the PostgreSQL integration test when the database is available:

```powershell
$env:RUN_DATABASE_TESTS = "1"
python -m pytest backend\tests\integration
Remove-Item Env:RUN_DATABASE_TESTS
```

Start the API:

```powershell
python -m uvicorn justsupply.main:app --reload
```

Open `http://127.0.0.1:8000/docs` to explore the API with Swagger UI.

The local database credentials in `compose.yaml` are intended only for development. Production
credentials must be supplied through environment variables and must never be committed.
