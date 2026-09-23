from pathlib import Path

from justsupply.evaluation.benchmark import (
    BenchmarkCase,
    BenchmarkDocument,
    RetrievalBenchmark,
    RetrievalBenchmarkRunner,
    load_benchmark,
)

DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "backend" / "evaluation" / "rag_retrieval_v1.json"
)


class KeywordEmbeddingProvider:
    model_name = "keyword-test-embedding"
    dimensions = 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        normalized = text.casefold()
        if "women" in normalized or "leadership" in normalized:
            return [1.0, 0.0]
        return [0.0, 1.0]


def test_versioned_rag_benchmark_dataset_is_valid() -> None:
    benchmark = load_benchmark(DATASET_PATH)

    assert benchmark.version == "1.0.0"
    assert len(benchmark.documents) == 6
    assert len(benchmark.cases) == 12
    assert all(case.relevant_document_ids for case in benchmark.cases)


def test_benchmark_runner_reports_metrics_for_multiple_top_k_values() -> None:
    benchmark = RetrievalBenchmark(
        name="Test benchmark",
        version="1",
        description="A deterministic benchmark used by the unit test.",
        documents=[
            BenchmarkDocument(
                id="women-report",
                title="Women report",
                text=(
                    "Women completed a leadership program and received promotions. "
                    "The report includes workforce evidence and measurable outcomes."
                ),
            ),
            BenchmarkDocument(
                id="packaging-report",
                title="Packaging report",
                text=(
                    "Packaging used recycled paper and a lighter recyclable wrapper. "
                    "The environmental statement records material reductions."
                ),
            ),
        ],
        cases=[
            BenchmarkCase(
                id="women-question",
                question="What leadership evidence exists for women?",
                relevant_document_ids={"women-report"},
            ),
            BenchmarkCase(
                id="packaging-question",
                question="What does the packaging statement document?",
                relevant_document_ids={"packaging-report"},
            ),
        ],
    )
    runner = RetrievalBenchmarkRunner(
        KeywordEmbeddingProvider(),
        target_characters=500,
        overlap_characters=50,
    )

    report = runner.run(benchmark, top_ks=[2, 1, 2])

    assert [result.top_k for result in report.results] == [1, 2]
    assert report.results[0].hit_rate == 1.0
    assert report.results[0].mean_reciprocal_rank == 1.0
    assert report.results[0].mean_precision == 1.0
    assert report.results[0].mean_recall == 1.0
    assert report.results[1].mean_precision == 0.5
