from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from justsupply.database.session import get_database_session
from justsupply.main import app


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check_returns_ready_when_database_responds(client: TestClient) -> None:
    session = Mock(spec=Session)
    app.dependency_overrides[get_database_session] = lambda: session

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    session.execute.assert_called_once()


def test_readiness_check_returns_503_when_database_is_unavailable(
    client: TestClient,
) -> None:
    session = Mock(spec=Session)
    session.execute.side_effect = SQLAlchemyError("Database connection failed.")
    app.dependency_overrides[get_database_session] = lambda: session

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable."}
