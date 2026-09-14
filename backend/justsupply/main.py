from fastapi import FastAPI

from justsupply.api.routes import health, suppliers


def create_app() -> FastAPI:
    application = FastAPI(
        title="JustSupply API",
        description="Evidence-based supply-chain due diligence API.",
        version="0.1.0",
    )
    application.include_router(health.router)
    application.include_router(suppliers.router, prefix="/api/v1")
    return application


app = create_app()
