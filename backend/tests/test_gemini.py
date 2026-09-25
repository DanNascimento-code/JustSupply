from types import SimpleNamespace

from justsupply.integrations.gemini import GeminiWebResearcher
from justsupply.schemas.consumer import AssessmentDimension, AssessmentStatus


class FakeModels:
    def __init__(self) -> None:
        self.responses: list[object] = []

    def generate_content(self, **kwargs: object) -> object:
        del kwargs
        return self.responses.pop(0)


class FakeClient:
    def __init__(self) -> None:
        self.models = FakeModels()


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
        '"es_latam":{"finding":"Afirmación sin respaldo.","limitations":null}}}]}'
    )


def test_gemini_research_extracts_sources_and_rejects_uncited_claims() -> None:
    client = FakeClient()
    metadata = SimpleNamespace(
        grounding_chunks=[
            SimpleNamespace(
                web=SimpleNamespace(
                    uri="https://example.org/certification",
                    title="Certification registry",
                    domain="example.org",
                )
            ),
            SimpleNamespace(
                web=SimpleNamespace(
                    uri="https://ngo.example/report",
                    title="Independent report",
                    domain="ngo.example",
                )
            ),
        ],
        grounding_supports=[
            SimpleNamespace(
                segment=SimpleNamespace(text="The product appears in a certification registry."),
                grounding_chunk_indices=[0],
            ),
            SimpleNamespace(
                segment=SimpleNamespace(text="The report describes a worker program."),
                grounding_chunk_indices=[1],
            ),
        ],
    )
    client.models.responses.extend(
        [
            SimpleNamespace(
                response_id="research-1",
                text="Grounded research text.",
                candidates=[SimpleNamespace(grounding_metadata=metadata)],
            ),
            SimpleNamespace(response_id="synthesis-1", parsed=None, text=_synthesis()),
        ]
    )
    researcher = GeminiWebResearcher("unused", "gemini-test", client=client)

    result = researcher.research("Example product", "Example brand", "7891000100103")

    assert len(result.sources) == 2
    assert result.sources[0].provider_name == "example.org"
    minority = next(
        item
        for item in result.assessments
        if item.dimension == AssessmentDimension.MINORITY_INCLUSION
    )
    assert minority.status == AssessmentStatus.NOT_DISCLOSED
    assert minority.source_numbers == []
