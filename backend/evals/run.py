"""Usage from backend: python -m evals.run --report."""

import argparse
import shlex
from contextlib import contextmanager
from pathlib import Path

from app.ai import graph
from app.database.session import SessionLocal
from app.repositories.incident_history_repository import IncidentHistoryRepository
from evals.reporting import render
from evals.runner import load_scenarios, read, run, save

DIRECTORY = Path(__file__).parent


@contextmanager
def exclusive(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)
    lock = cache / "runner.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise RuntimeError(
            "Evaluation already running; remove stale runner.lock only after exit"
        ) from error
    try:
        with handle:
            handle.write("Sequential evaluator; do not run alongside the API LLM worker.\n")
        yield
    finally:
        lock.unlink()


def require_retrieval_history() -> None:
    with SessionLocal() as db:
        count = IncidentHistoryRepository(db).embedding_count()
    validate_history_count(count)


def validate_history_count(count: int) -> None:
    if count < 50:
        raise SystemExit(
            "Retrieval evaluation requires at least 50 resolved-history embeddings in the "
            "configured database. Index historical cases before running with --retrieval on."
        )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="Print and save the Markdown report")
    parser.add_argument("--report-only", action="store_true", help="Render saved results; no calls")
    parser.add_argument(
        "--limit", type=int, help="Evaluate only the first N cases; report stays partial"
    )
    parser.add_argument(
        "--retrieval",
        choices=("off", "on"),
        default="off",
        help="Disable history for the baseline or use resolved-history retrieval",
    )
    parser.add_argument("--scenarios", type=Path, default=DIRECTORY / "scenarios")
    parser.add_argument("--cache", type=Path, default=DIRECTORY / ".cache")
    parser.add_argument("--output", type=Path, default=DIRECTORY)
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.report_only:
        result = read(args.output / "results.json")
        if not result:
            parser.error("No saved results.json exists")
    else:
        scenarios = load_scenarios(args.scenarios)
        if len(scenarios) != 50:
            parser.error("The benchmark requires exactly 50 scenarios")
        if args.retrieval == "on":
            require_retrieval_history()
        # Validate credentials/model setup before charging any budget. No provider call.
        graph.get_llm()
        with exclusive(args.cache):
            result = run(scenarios, args.cache, limit=args.limit, retrieval=args.retrieval)
            command = ["python", "-m", "evals.run"]
            if args.report:
                command.append("--report")
            if args.limit is not None:
                command.extend(["--limit", str(args.limit)])
            if args.retrieval != "off":
                command.extend(["--retrieval", args.retrieval])
            if args.scenarios != DIRECTORY / "scenarios":
                command.extend(["--scenarios", str(args.scenarios)])
            if args.cache != DIRECTORY / ".cache":
                command.extend(["--cache", str(args.cache)])
            if args.output != DIRECTORY:
                command.extend(["--output", str(args.output)])
            result["command"] = shlex.join(command)
            save(args.output / "results.json", result)
    if args.report or args.report_only:
        report = render(result)
        args.output.mkdir(parents=True, exist_ok=True)
        (args.output / "RESULTS.md").write_text(report, encoding="utf-8")
        print(report)
    return 0 if all(row["status"] == "completed" for row in result["results"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
