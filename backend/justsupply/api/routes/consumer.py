from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID
from zipfile import BadZipFile, ZipFile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pydantic import HttpUrl

from justsupply.dependencies import get_consumer_research_service, get_consumer_service
from justsupply.integrations.ai import AiResearchError
from justsupply.integrations.open_food_facts import CatalogUnavailableError
from justsupply.repositories.consumer_evidence import (
    CommunityReportDocumentInput,
    EvidencePersistenceError,
    ProductNotFoundError,
)
from justsupply.schemas.consumer import (
    AssessmentDimension,
    CommunityReportAssessment,
    CommunityReportCreate,
    CommunityReportOutcome,
    CommunityReportRead,
    ConsumerAnswerResponse,
    ConsumerQuestionRequest,
    ConsumerSearchResponse,
    FoodCategory,
    ProductResearchResponse,
    PublicCommunityReportList,
    UserLocale,
)
from justsupply.services.consumer import (
    ConsumerProductNotFoundError,
    ConsumerResearchService,
    ConsumerService,
)

router = APIRouter(prefix="/consumer", tags=["consumer"])
MAX_LABEL_IMAGE_BYTES = 4_000_000
LABEL_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_REPORT_DOCUMENTS = 3
MAX_REPORT_DOCUMENT_BYTES = 8_000_000
REPORT_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}
ConsumerServiceDependency = Annotated[ConsumerService, Depends(get_consumer_service)]
ResearchServiceDependency = Annotated[
    ConsumerResearchService,
    Depends(get_consumer_research_service),
]
SearchQuery = Annotated[
    str,
    Query(
        min_length=2,
        max_length=120,
        description="A product name, brand name, or an 8-14 digit barcode.",
    ),
]


@router.get("/reports", response_model=PublicCommunityReportList)
def list_community_reports(
    service: ConsumerServiceDependency,
    barcode: Annotated[str | None, Query(pattern=r"^\d{8,14}$")] = None,
    product_name: Annotated[str | None, Query(min_length=2, max_length=300)] = None,
    category: FoodCategory | None = None,
    language: UserLocale = UserLocale.ENGLISH,
) -> PublicCommunityReportList:
    return service.list_public_community_reports(
        barcode=barcode,
        product_name=product_name,
        category=category,
        language=language,
    )


@router.post(
    "/reports",
    response_model=CommunityReportRead,
    status_code=status.HTTP_201_CREATED,
)
def submit_community_report(
    service: ConsumerServiceDependency,
    details: Annotated[str, Form(min_length=10, max_length=1500)],
    category: Annotated[FoodCategory, Form()],
    product_name: Annotated[str | None, Form(min_length=2, max_length=300)] = None,
    barcode: Annotated[
        str | None,
        Form(pattern=r"^\d{8,14}$"),
    ] = None,
    evidence_url: Annotated[HttpUrl | None, Form()] = None,
    vegan_composition: Annotated[CommunityReportOutcome | None, Form()] = None,
    environmental_impact: Annotated[CommunityReportOutcome | None, Form()] = None,
    women_workers: Annotated[CommunityReportOutcome | None, Form()] = None,
    minority_inclusion: Annotated[CommunityReportOutcome | None, Form()] = None,
    photo: Annotated[UploadFile | None, File()] = None,
    documents: Annotated[list[UploadFile] | None, File()] = None,
    language: UserLocale = UserLocale.ENGLISH,
) -> CommunityReportRead:
    if product_name is None and barcode is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide a product name or barcode.",
        )
    reported_outcomes = {
        AssessmentDimension.VEGAN_COMPOSITION: vegan_composition,
        AssessmentDimension.ENVIRONMENTAL_IMPACT: environmental_impact,
        AssessmentDimension.WOMEN_WORKERS: women_workers,
        AssessmentDimension.MINORITY_INCLUSION: minority_inclusion,
    }
    assessments = [
        CommunityReportAssessment(dimension=dimension, outcome=outcome)
        for dimension, outcome in reported_outcomes.items()
        if outcome is not None
    ]
    if not assessments:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Report a positive or negative outcome for at least one dimension.",
        )
    photo_data: bytes | None = None
    photo_mime_type: str | None = None
    if photo is not None:
        photo_mime_type = (photo.content_type or "").casefold()
        photo_data = photo.file.read(MAX_LABEL_IMAGE_BYTES + 1)
        if photo_mime_type not in LABEL_IMAGE_MIME_TYPES or not _matches_image_signature(
            photo_data,
            photo_mime_type,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Upload a valid JPEG, PNG, or WebP product photo.",
            )
        if len(photo_data) > MAX_LABEL_IMAGE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="The product photo must be 4 MB or smaller.",
            )
    document_inputs: list[CommunityReportDocumentInput] = []
    uploaded_documents = documents or []
    if len(uploaded_documents) > MAX_REPORT_DOCUMENTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Attach no more than {MAX_REPORT_DOCUMENTS} documents.",
        )
    for document in uploaded_documents:
        mime_type = (document.content_type or "").casefold()
        data = document.file.read(MAX_REPORT_DOCUMENT_BYTES + 1)
        if len(data) > MAX_REPORT_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="Each supporting document must be 8 MB or smaller.",
            )
        if mime_type not in REPORT_DOCUMENT_MIME_TYPES or not _matches_document(
            data,
            mime_type,
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Attach only valid PDF, DOCX, or plain-text documents.",
            )
        file_name = Path(document.filename or "supporting-document").name[:255]
        document_inputs.append(
            CommunityReportDocumentInput(
                file_name=file_name,
                mime_type=mime_type,
                data=data,
            )
        )
    try:
        return service.submit_community_report(
            CommunityReportCreate(
                product_name=product_name,
                barcode=barcode,
                category=category,
                assessments=assessments,
                details=details,
                evidence_url=evidence_url,
            ),
            photo_data=photo_data,
            photo_mime_type=photo_mime_type,
            documents=document_inputs,
            language=language,
        )
    except EvidencePersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.get("/reports/{report_id}/photo")
def read_community_report_photo(
    report_id: UUID,
    service: ConsumerServiceDependency,
) -> Response:
    photo = service.get_public_community_report_photo(report_id)
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found.")
    return Response(
        content=photo.data,
        media_type=photo.mime_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/reports/{report_id}/documents/{attachment_id}")
def download_community_report_document(
    report_id: UUID,
    attachment_id: UUID,
    service: ConsumerServiceDependency,
) -> Response:
    document = service.get_public_community_report_document(report_id, attachment_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    data, mime_type, file_name = document
    safe_name = "".join(
        character if character.isalnum() or character in {".", "-", "_"} else "_"
        for character in Path(file_name).name
    ) or "supporting-document"
    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/products", response_model=ConsumerSearchResponse)
def search_products(
    service: ConsumerServiceDependency,
    query: SearchQuery,
    language: UserLocale = UserLocale.ENGLISH,
) -> ConsumerSearchResponse:
    try:
        return service.search(query, language)
    except CatalogUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except EvidencePersistenceError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/products/{barcode}/research", response_model=ProductResearchResponse)
def research_product(
    barcode: str,
    service: ResearchServiceDependency,
    refresh: bool = False,
    language: UserLocale = UserLocale.ENGLISH,
) -> ProductResearchResponse:
    try:
        return service.research(barcode, refresh=refresh, language=language)
    except ConsumerProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CatalogUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (AiResearchError, EvidencePersistenceError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/products/{barcode}/research-label", response_model=ProductResearchResponse)
def research_product_label(
    barcode: str,
    service: ResearchServiceDependency,
    image: Annotated[UploadFile, File(description="A cropped ingredient-label image.")],
    language: UserLocale = UserLocale.ENGLISH,
) -> ProductResearchResponse:
    mime_type = (image.content_type or "").casefold()
    image_data = image.file.read(MAX_LABEL_IMAGE_BYTES + 1)
    if mime_type not in LABEL_IMAGE_MIME_TYPES or not _matches_image_signature(
        image_data, mime_type
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Upload a valid JPEG, PNG, or WebP label image.",
        )
    if len(image_data) > MAX_LABEL_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The label image must be 4 MB or smaller.",
        )
    try:
        return service.research_label(
            barcode,
            image_data,
            mime_type,
            language=language,
        )
    except ConsumerProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CatalogUnavailableError as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except (AiResearchError, EvidencePersistenceError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.get("/label-images/{image_id}")
def read_label_image(
    image_id: UUID,
    service: ResearchServiceDependency,
) -> Response:
    image = service.get_label_image(image_id)
    if image is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Label image not found.")
    return Response(
        content=image.data,
        media_type=image.mime_type,
        headers={
            "Cache-Control": "private, max-age=604800",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/products/{barcode}/ask", response_model=ConsumerAnswerResponse)
def ask_product_question(
    barcode: str,
    payload: ConsumerQuestionRequest,
    service: ResearchServiceDependency,
) -> ConsumerAnswerResponse:
    try:
        return service.ask(
            barcode,
            payload.question,
            top_k=payload.top_k,
            language=payload.language,
        )
    except ProductNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except AiResearchError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


def _matches_image_signature(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/webp":
        return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
    return False


def _matches_document(data: bytes, mime_type: str) -> bool:
    if mime_type == "application/pdf":
        return data.startswith(b"%PDF-")
    if mime_type == "text/plain":
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    if mime_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        try:
            with ZipFile(BytesIO(data)) as archive:
                names = set(archive.namelist())
        except (BadZipFile, OSError):
            return False
        return "[Content_Types].xml" in names and "word/document.xml" in names
    return False
