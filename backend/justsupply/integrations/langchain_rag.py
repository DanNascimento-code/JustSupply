from dataclasses import dataclass
from typing import TypedDict

from langchain_core.runnables import Runnable, RunnableLambda

from justsupply.domain.research import GeneratedConsumerAnswer, RetrievedEvidence
from justsupply.integrations.ai import ConsumerAnswerGenerator


class ConsumerRagInput(TypedDict):
    question: str
    evidence: list[RetrievedEvidence]
    language: str


@dataclass(frozen=True)
class ConsumerRagResult:
    generated: GeneratedConsumerAnswer
    evidence: list[RetrievedEvidence]


class LangChainConsumerRag:
    def __init__(self, generator: ConsumerAnswerGenerator) -> None:
        self.generation_model = generator.model_name
        self.prompt_version = generator.prompt_version
        self._generator = generator
        self._chain: Runnable[ConsumerRagInput, ConsumerRagResult] = RunnableLambda(
            self._answer_stage
        )

    def answer(
        self,
        question: str,
        evidence: list[RetrievedEvidence],
        language: str,
    ) -> ConsumerRagResult:
        return self._chain.invoke(
            ConsumerRagInput(question=question, evidence=evidence, language=language)
        )

    def _answer_stage(self, state: ConsumerRagInput) -> ConsumerRagResult:
        if not state["evidence"]:
            generated = GeneratedConsumerAnswer(
                answer="No researched evidence is available for this product yet.",
                cited_evidence_numbers=[],
                insufficient_evidence=True,
            )
        else:
            generated = self._generator.generate(
                state["question"], state["evidence"], state["language"]
            )
        return ConsumerRagResult(generated=generated, evidence=state["evidence"])
