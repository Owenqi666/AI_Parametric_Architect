"""Command-line entry point for detached planning benchmarks."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ai_parametric_architect.benchmark.data import (
    BenchmarkDataError,
    load_benchmark_annotations,
    load_benchmark_dataset,
)
from ai_parametric_architect.benchmark.models import BenchmarkBudget
from ai_parametric_architect.composition import (
    create_cp_sat_benchmark_system,
    create_openai_cp_sat_benchmark_system,
    create_planning_benchmark_runner,
    create_rule_spatial_benchmark_system,
)
from ai_parametric_architect.domain import PlanningError
from ai_parametric_architect.infrastructure import OpenAIProviderConfig
from ai_parametric_architect.planning import PlanningRules

_CLI_BUDGET = BenchmarkBudget(
    max_cases=16,
    max_systems=3,
    max_trials=4,
    max_attempts=192,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-architect-benchmark",
        description=(
            "Compare detached rule-based and CP-SAT floor-plan proposals. "
            "A real OpenAI intent system is included only when --openai-model is supplied."
        ),
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("annotations", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument(
        "--openai-model",
        help=(
            "explicitly enable the network OpenAI intent adapter; "
            "credentials come from the environment"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        _require_output_target(
            arguments.output,
            inputs=(arguments.dataset, arguments.annotations),
        )
        dataset = load_benchmark_dataset(arguments.dataset)
        annotations = load_benchmark_annotations(arguments.annotations, dataset=dataset)
        rules = PlanningRules()
        runner = create_planning_benchmark_runner(rules=rules, budget=_CLI_BUDGET)
        systems = [
            create_rule_spatial_benchmark_system(),
            create_cp_sat_benchmark_system(rules=rules),
        ]
        if arguments.openai_model is not None:
            systems.append(
                create_openai_cp_sat_benchmark_system(
                    OpenAIProviderConfig(model=arguments.openai_model),
                    rules=rules,
                )
            )
        report = runner.run(
            dataset,
            annotations,
            tuple(systems),
            trials=arguments.trials,
        )
        encoded = json.dumps(
            report.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        arguments.output.write_text(f"{encoded}\n", encoding="utf-8")
    except (BenchmarkDataError, PlanningError, OSError, ValueError) as error:
        print(_safe_error(error), file=sys.stderr)
        return 2
    return 0


def _require_output_target(output: Path, *, inputs: tuple[Path, ...]) -> None:
    resolved_output = output.resolve(strict=False)
    if any(resolved_output == path.resolve(strict=False) for path in inputs):
        raise OSError("Benchmark output must not overwrite an input artifact.")
    if not output.parent.is_dir():
        raise OSError("Benchmark output parent directory does not exist.")
    if output.exists() and not output.is_file():
        raise OSError("Benchmark output target must be a regular file path.")


def _safe_error(error: Exception) -> str:
    if isinstance(error, BenchmarkDataError):
        return json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True)
    if isinstance(error, PlanningError):
        return json.dumps(error.to_dict(), ensure_ascii=False, sort_keys=True)
    return str(error)


if __name__ == "__main__":
    raise SystemExit(main())
