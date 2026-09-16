from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient

from justsupply.dependencies import get_brand_evidence_service
from justsupply.main import app
from justsupply.schemas.brand_evidence import (
    BrandClaimListResponse,
    BrandClaimRead,
    BrandEvidenceCreate,
    BrandListResponse,
    BrandSummaryRead,
    ClaimReviewUpdate,
    ReviewStatus,
)
from justsupply.schemas.consumer import (
    AssessmentDimension,
    AssessmentSourceRead,
    AssessmentStatus,
)

BRAND_ID = UUID("9c39497c-d18e-42a1-845e-64cf1f7f52fc")
CLAIM_ID = UUID("854c9a26-89d3-46d5-b0a0-381d08534102")


def claim_response(review_status: ReviewStatus) -> BrandClaimRead:
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    return BrandClaimRead(
        id=CLAIM_ID,
        brand_id=BRAND_ID,
        brand_name="Example Foods",
        dimension=AssessmentDimension.WOMEN_WORKERS,
        status=AssessmentStatus.SUPPORTED,
        statement="The report documents a leadership program for women workers.",
        review_status=review_status,
        reviewed_at=now if review_status != ReviewStatus.PENDING else None,
        created_at=now,
        updated_at=now,
        sources=[
            AssessmentSourceRead(
                title="2025 Impact Report",
                provider_name="Example Organization",
                url="https://example.org/report",
                published_at=now,
                source_location="page 18",
            )
        ],
    )


class StubBrandEvidenceService:
    def list_brands(self) -> BrandListResponse:
        return BrandListResponse(
            items=[BrandSummaryRead(id=BRAND_ID, name="Example Foods")],
            total=1,
        )

    def list_claims(self, brand_id: UUID) -> BrandClaimListResponse:
        assert brand_id == BRAND_ID
        claim = claim_response(ReviewStatus.PENDING)
        return BrandClaimListResponse(items=[claim], total=1)

    def create_claim(
        self,
        brand_id: UUID,
        payload: BrandEvidenceCreate,
    ) -> BrandClaimRead:
        assert brand_id == BRAND_ID
        assert payload.dimension == AssessmentDimension.WOMEN_WORKERS
        return claim_response(ReviewStatus.PENDING)

    def review_claim(
        self,
        claim_id: UUID,
        payload: ClaimReviewUpdate,
    ) -> BrandClaimRead:
        assert claim_id == CLAIM_ID
        return claim_response(ReviewStatus(payload.decision.value))


def evidence_payload() -> dict[str, str]:
    return {
        "dimension": "women_workers",
        "status": "supported",
        "statement": "The report documents a leadership program for women workers.",
        "source_title": "2025 Impact Report",
        "source_provider": "Example Organization",
        "source_url": "https://example.org/report",
        "source_type": "corporate_report",
    }


def test_brand_evidence_routes(client: TestClient) -> None:
    service = StubBrandEvidenceService()
    app.dependency_overrides[get_brand_evidence_service] = lambda: service

    brands_response = client.get("/api/v1/evidence/brands")
    claims_response = client.get(f"/api/v1/evidence/brands/{BRAND_ID}/claims")
    create_response = client.post(
        f"/api/v1/evidence/brands/{BRAND_ID}/claims",
        json=evidence_payload(),
    )
    review_response = client.patch(
        f"/api/v1/evidence/claims/{CLAIM_ID}/review",
        json={"decision": "approved"},
    )

    assert brands_response.status_code == 200
    assert brands_response.json()["items"][0]["name"] == "Example Foods"
    assert claims_response.status_code == 200
    assert create_response.status_code == 201
    assert create_response.json()["review_status"] == "pending"
    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "approved"


def test_brand_evidence_rejects_non_social_dimensions(client: TestClient) -> None:
    service = StubBrandEvidenceService()
    app.dependency_overrides[get_brand_evidence_service] = lambda: service
    payload = evidence_payload()
    payload["dimension"] = "vegan_composition"

    response = client.post(
        f"/api/v1/evidence/brands/{BRAND_ID}/claims",
        json=payload,
    )

    assert response.status_code == 422
