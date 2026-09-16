from dataclasses import dataclass
from typing import TypedDict
from uuid import UUID

from langchain_core.runnables import Runnable, RunnableLambda

from justsupply.domain.rag import GeneratedAnswer, RetrievedChunk
from justsupply.services.rag import AnswerGenerator, RagRetriever


class RagPipelineInput(TypedDict):
    brand_id: UUID
    question: str
    top_k: int


class RetrievalState(TypedDict):
    question: str
    chunks: list[RetrievedChunk]


@dataclass(frozen=True)
class RagPipelineResult:
    generated: GeneratedAnswer
    chunks: list[RetrievedChunk]


class LangChainRagOrchestrator:
    def __init__(
        self,
        retriever: RagRetriever,
        generator: AnswerGenerator,
    ) -> None:
        self.generation_model = generator.model_name
        self.prompt_version = generator.prompt_version
        self._retriever = retriever
        self._generator = generator
        self._chain: Runnable[RagPipelineInput, RagPipelineResult] = RunnableLambda(
            self._retrieve_stage
        ) | RunnableLambda(self._generate_stage)

    def answer(
        self,
        brand_id: UUID,
        question: str,
        *,
        top_k: int,
    ) -> tuple[GeneratedAnswer, list[RetrievedChunk]]:
        result = self._chain.invoke(
            RagPipelineInput(
                brand_id=brand_id,
                question=question,
                top_k=top_k,
            )
        )
        return result.generated, result.chunks

    def _retrieve_stage(self, payload: RagPipelineInput) -> RetrievalState:
        return RetrievalState(
            question=payload["question"],
            chunks=self._retriever.retrieve(
                payload["brand_id"],
                payload["question"],
                top_k=payload["top_k"],
            ),
        )

    def _generate_stage(self, state: RetrievalState) -> RagPipelineResult:
        if not state["chunks"]:
            generated = GeneratedAnswer(
                answer="No indexed evidence was retrieved.",
                cited_chunk_numbers=[],
                insufficient_evidence=True,
            )
        else:
            generated = self._generator.generate(state["question"], state["chunks"])
        return RagPipelineResult(generated=generated, chunks=state["chunks"])
