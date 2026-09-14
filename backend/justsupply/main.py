from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from justsupply.api.routes import health, suppliers
from justsupply.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="JustSupply API",
        description="Evidence-based supply-chain due diligence API.",
        version="0.1.0",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health.router)
    application.include_router(suppliers.router, prefix="/api/v1")
    return application


app = create_app()
