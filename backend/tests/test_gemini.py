from types import SimpleNamespace

from justsupply.domain.research import (
    GroundedWebSource,
    OrganizationLookup,
    PublicWebSearchResult,
)
from justsupply.integrations.gemini import GeminiEvidenceResearcher
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus


class FakeModels:
    def __init__(self) -> None:
        self.responses: list[object] = []
        self.calls: list[dict[str, object]] = []

    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeClient:
    def __init__(self) -> None:
        self.models = FakeModels()


class FakeSearchProvider:
    provider_name = "Test Search"

    def search(
        self,
        product_name: str,
        brand: str | None,
        barcode: str,
        organization_names: tuple[str, ...] = (),
    ) -> PublicWebSearchResult:
        assert product_name == "Example product"
        assert brand == "Example brand"
        assert barcode == "7891000100103"
        assert organization_names == ("Example Group",)
        return PublicWebSearchResult(
            provider_response_id="search-1",
            sources=[
                GroundedWebSource(
                    number=1,
                    title="Certification registry",
                    provider_name="example.org",
                    url="https://example.org/certification",
                    cited_text="The product appears in a certification registry.",
                ),
                GroundedWebSource(
                    number=2,
                    title="Independent report",
                    provider_name="ngo.example",
                    url="https://ngo.example/report",
                    cited_text="The report describes a worker program.",
                ),
            ],
        )


class FakeOrganizationResolver:
    def resolve(self, brand: str | None, brand_owner: str | None) -> OrganizationLookup:
        assert brand == "Example brand"
        assert brand_owner == "Example Group"
        return OrganizationLookup(
            names=("Example Group",),
            source=GroundedWebSource(
                number=0,
                title="Example brand — organization record",
                provider_name="Wikidata",
                url="https://www.wikidata.org/wiki/Q1",
                cited_text="Example Group owns Example brand.",
                focus="organization",
                source_class="public_database",
            ),
        )


def _synthesis() -> str:
    return (
        '{"assessments":['
        '{"dimension":"vegan_composition","status":"supported","finding":"Certified vegan.",'
        '"evidence_scope":"product","source_numbers":[1],"limitations":null,'
        '"translations":{"pt_br":{"finding":"Vegano certificado.","limitations":null},'
        '"es_latam":{"finding":"Vegano certificado.","limitations":null}}},'
        '{"dimension":"environmental_impact","status":"mixed","finding":"Mixed reporting.",'
        '"evidence_scope":"brand","source_numbers":[1,2],"limitations":"Limited detail.",'
        '"translations":{"pt_br":{"finding":"Relatos divergentes.",'
        '"limitations":"Detalhes limitados."},'
        '"es_latam":{"finding":"Informes mixtos.","limitations":"Detalles limitados."}}},'
        '{"dimension":"women_workers","status":"supported","finding":"A program is reported.",'
        '"evidence_scope":"brand","source_numbers":[2],"limitations":null,'
        '"translations":{"pt_br":{"finding":"Um programa foi relatado.","limitations":null},'
        '"es_latam":{"finding":"Se informó un programa.","limitations":null}}},'
        '{"dimension":"minority_inclusion","status":"supported",'
        '"finding":"An unsupported model claim.","evidence_scope":"brand",'
        '"source_numbers":[99],"limitations":null,'
        '"translations":{"pt_br":{"finding":"Afirmação sem suporte.","limitations":null},'
        '"es_latam":{"finding":"Afirmación sin respaldo.","limitations":null}}}],'
        '"organization":{"legal_name":"Example Foods Ltd",'
        '"parent_company":"Example Group","jurisdiction":"United Kingdom",'
        '"source_numbers":[2]}}'
    )


def test_gemini_synthesizes_search_sources_and_rejects_uncited_claims() -> None:
    client = FakeClient()
    client.models.responses.append(
        SimpleNamespace(response_id="synthesis-1", parsed=None, text=_synthesis())
    )
    researcher = GeminiEvidenceResearcher(
        "unused",
        "gemini-test",
        FakeSearchProvider(),
        organization_resolver=FakeOrganizationResolver(),
        client=client,
    )

    result = researcher.research(
        "Example product",
        "Example brand",
        "7891000100103",
        brand_owner="Example Group",
    )

    assert len(result.sources) == 3
    assert result.sources[0].provider_name == "example.org"
    assert result.provider_response_id == "synthesis-1"
    assert result.organization is not None
    assert result.organization.parent_company == "Example Group"
    assert result.sources[2].number == 3
    assert result.sources[2].provider_name == "Wikidata"
    assert len(client.models.calls) == 1
    assert getattr(client.models.calls[0]["config"], "tools", None) is None
    minority = next(
        item
        for item in result.assessments
        if item.dimension == AssessmentDimension.MINORITY_INCLUSION
    )
    assert minority.status == AssessmentStatus.NOT_DISCLOSED
    assert minority.source_numbers == []
