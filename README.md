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

