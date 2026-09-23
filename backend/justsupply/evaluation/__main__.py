import argparse
from pathlib import Path

from justsupply.core.config import get_settings
from justsupply.dependencies import get_configured_embedding_provider
from justsupply.evaluation.benchmark import RetrievalBenchmarkRunner, load_benchmark

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3] / "backend" / "evaluation" / "rag_retrieval_v1.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the JustSupply RAG retrieval benchmark.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--top-k", type=int, nargs="+", default=[1, 3, 5])
    parser.add_argument("--target-characters", type=int)
    parser.add_argument("--overlap-characters", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    settings = get_settings()
    benchmark = load_benchmark(args.dataset)
    runner = RetrievalBenchmarkRunner(
        get_configured_embedding_provider(),
        target_characters=args.target_characters or settings.rag_chunk_target_characters,
        overlap_characters=(
            args.overlap_characters
            if args.overlap_characters is not None
            else settings.rag_chunk_overlap_characters
        ),
    )
    report = runner.run(benchmark, top_ks=args.top_k)

    print(f"Benchmark: {report.benchmark_name} v{report.benchmark_version}")
    print(f"Embedding model: {report.embedding_model} ({report.embedding_dimensions} dimensions)")
    print(f"Corpus: {report.document_count} documents, {report.chunk_count} chunks")
    print("top_k  hit_rate  mrr     precision  recall")
    for result in report.results:
        print(
            f"{result.top_k:>5}  {result.hit_rate:>8.3f}  "
            f"{result.mean_reciprocal_rank:>6.3f}  "
            f"{result.mean_precision:>9.3f}  {result.mean_recall:>6.3f}"
        )

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"Report written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
