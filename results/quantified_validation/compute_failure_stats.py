#!/usr/bin/env python3
"""
Quantified Validation: Failure Mode Analysis for TestForge vs EvoTest.

Computes failure statistics from evaluation output files for the RQ1 case study.
Outputs a JSON summary and a human-readable report.

Usage:
    python compute_failure_stats.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
RESULTS_DIR = Path(__file__).resolve().parents[1]

EVOTEST_PATH = (
    RESULTS_DIR
    / "main_experiment"
    / "testgenevallite"
    / "EvoTest"
    / "eval"
    / "output.testgeneval.jsonl"
)

TESTFORGE_PATH = (
    RESULTS_DIR
    / "main_experiment"
    / "testgenevallite"
    / "TestForge"
    / "eval"
    / "output.testgeneval.jsonl"
)

OUTPUT_DIR = Path(__file__).resolve().parent


# ── Helpers ────────────────────────────────────────────────────────────────
def load_instances(path: Path) -> list[dict]:
    """Load all instances from a JSONL file."""
    instances = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                instances.append(json.loads(line))
    return instances


def classify_failure(instance: dict) -> str:
    """
    Classify a failing instance into one of:
        - "empty_generation": no test code produced
        - "import_error": ImportError / ModuleNotFoundError in test output
        - "syntax_error": SyntaxError / NameError in test output
        - "zero_tests_discovered": runner found 0 tests
        - "other": anything else
    """
    report = instance.get("test_result", {}).get("report", {})

    # 1. Empty generation
    if report.get("empty_generation", False):
        return "empty_generation"

    test_output = report.get("test_output", "")
    test_stats = report.get("test_stats", {})
    total_tests = test_stats.get("total_tests", 0) if test_stats else 0

    # 2. ImportError / ModuleNotFoundError
    if "ImportError" in test_output or "ModuleNotFoundError" in test_output:
        return "import_error"

    # 3. SyntaxError / NameError
    if "SyntaxError" in test_output or "NameError" in test_output:
        return "syntax_error"

    # 4. 0 tests discovered
    if total_tests == 0:
        return "zero_tests_discovered"

    # 5. Other
    return "other"


def compute_stats(instances: list[dict], label: str) -> dict:
    """Compute comprehensive statistics for a set of instances."""
    total = len(instances)

    # Basic counts
    any_pass_count = 0
    empty_gen_count = 0
    zero_tests_count = 0
    coverage_positive_count = 0
    coverage_sum = 0.0
    mutation_sum = 0.0
    coverage_count = 0
    mutation_count = 0
    error_eval_count = 0

    failing_instances = []
    failure_categories = Counter()

    for inst in instances:
        report = inst.get("test_result", {}).get("report", {})
        test_stats = report.get("test_stats", {})

        # Any Pass@1
        any_pass = test_stats.get("any_pass", False) if test_stats else False
        if any_pass:
            any_pass_count += 1

        # Empty generation
        if report.get("empty_generation", False):
            empty_gen_count += 1

        # 0 tests discovered
        total_tests = test_stats.get("total_tests", 0) if test_stats else 0
        if total_tests == 0:
            zero_tests_count += 1

        # Coverage
        cov = report.get("coverage")
        if cov is not None and cov > 0:
            coverage_positive_count += 1
        if cov is not None:
            coverage_sum += cov
            coverage_count += 1

        # Mutation
        mut = report.get("mutation_score")
        if mut is not None:
            mutation_sum += mut
            mutation_count += 1

        # error_eval
        if report.get("error_eval", False):
            error_eval_count += 1

        # Failing instances
        if not any_pass:
            category = classify_failure(inst)
            failure_categories[category] += 1
            failing_instances.append(
                {
                    "instance_id": inst.get("instance_id", "unknown"),
                    "failure_category": category,
                    "coverage": cov,
                    "total_tests": total_tests,
                }
            )

    avg_coverage = coverage_sum / coverage_count if coverage_count > 0 else 0.0
    avg_mutation = mutation_sum / mutation_count if mutation_count > 0 else 0.0

    return {
        "label": label,
        "total_instances": total,
        "any_pass_count": any_pass_count,
        "any_pass_rate": round(any_pass_count / total * 100, 2) if total > 0 else 0,
        "empty_generation_count": empty_gen_count,
        "empty_generation_rate": round(empty_gen_count / total * 100, 2) if total > 0 else 0,
        "zero_tests_count": zero_tests_count,
        "zero_tests_rate": round(zero_tests_count / total * 100, 2) if total > 0 else 0,
        "coverage_positive_count": coverage_positive_count,
        "coverage_positive_rate": round(coverage_positive_count / total * 100, 2) if total > 0 else 0,
        "average_coverage": round(avg_coverage, 2),
        "average_mutation": round(avg_mutation, 2),
        "error_eval_count": error_eval_count,
        "failing_count": total - any_pass_count,
        "failing_rate": round((total - any_pass_count) / total * 100, 2) if total > 0 else 0,
        "failure_categories": dict(failure_categories),
        "failing_instances": failing_instances,
    }


def format_report(evo_stats: dict, tf_stats: dict) -> str:
    """Format a human-readable comparison report."""
    lines = []
    lines.append("=" * 70)
    lines.append("Quantified Validation: TestForge vs EvoTest Failure Analysis")
    lines.append("=" * 70)
    lines.append("")

    # Overall table
    lines.append("Overall Statistics")
    lines.append("-" * 70)
    lines.append(f"{'Metric':<35} {'TestForge':>15} {'EvoTest':>15}")
    lines.append("-" * 70)
    lines.append(f"{'Total instances':<35} {tf_stats['total_instances']:>15} {evo_stats['total_instances']:>15}")
    lines.append(f"{'Any Pass@1':<35} {tf_stats['any_pass_count']:>10} ({tf_stats['any_pass_rate']:.1f}%) {evo_stats['any_pass_count']:>10} ({evo_stats['any_pass_rate']:.1f}%)")
    lines.append(f"{'Empty generation':<35} {tf_stats['empty_generation_count']:>10} ({tf_stats['empty_generation_rate']:.1f}%) {evo_stats['empty_generation_count']:>10} ({evo_stats['empty_generation_rate']:.1f}%)")
    lines.append(f"{'0 tests discovered':<35} {tf_stats['zero_tests_count']:>10} ({tf_stats['zero_tests_rate']:.1f}%) {evo_stats['zero_tests_count']:>10} ({evo_stats['zero_tests_rate']:.1f}%)")
    lines.append(f"{'Coverage > 0':<35} {tf_stats['coverage_positive_count']:>10} ({tf_stats['coverage_positive_rate']:.1f}%) {evo_stats['coverage_positive_count']:>10} ({evo_stats['coverage_positive_rate']:.1f}%)")
    lines.append(f"{'Average coverage':<35} {tf_stats['average_coverage']:>14.2f}% {evo_stats['average_coverage']:>14.2f}%")
    lines.append(f"{'Average mutation score':<35} {tf_stats['average_mutation']:>14.2f}% {evo_stats['average_mutation']:>14.2f}%")
    lines.append(f"{'Failing instances':<35} {tf_stats['failing_count']:>10} ({tf_stats['failing_rate']:.1f}%) {evo_stats['failing_count']:>10} ({evo_stats['failing_rate']:.1f}%)")
    lines.append("")

    # Failure categories
    lines.append("Failure Category Breakdown")
    lines.append("-" * 70)
    lines.append(f"{'Category':<35} {'TestForge':>15} {'EvoTest':>15}")
    lines.append("-" * 70)

    all_categories = sorted(
        set(list(tf_stats["failure_categories"].keys()) + list(evo_stats["failure_categories"].keys()))
    )
    for cat in all_categories:
        tf_count = tf_stats["failure_categories"].get(cat, 0)
        evo_count = evo_stats["failure_categories"].get(cat, 0)
        tf_pct = tf_count / tf_stats["total_instances"] * 100
        evo_pct = evo_count / evo_stats["total_instances"] * 100
        lines.append(f"{cat:<35} {tf_count:>10} ({tf_pct:.2f}%) {evo_count:>10} ({evo_pct:.2f}%)")

    lines.append("")

    # LaTeX table
    lines.append("LaTeX Table (for paper)")
    lines.append("-" * 70)
    tf_any = tf_stats["any_pass_rate"]
    evo_any = evo_stats["any_pass_rate"]
    tf_struct = tf_stats["failure_categories"].get("zero_tests_discovered", 0) + tf_stats["failure_categories"].get("syntax_error", 0)
    evo_struct = evo_stats["failure_categories"].get("zero_tests_discovered", 0) + evo_stats["failure_categories"].get("syntax_error", 0)
    tf_import = tf_stats["failure_categories"].get("import_error", 0)
    evo_import = evo_stats["failure_categories"].get("import_error", 0)

    tf_struct_pct = tf_struct / tf_stats["total_instances"] * 100
    evo_struct_pct = evo_struct / evo_stats["total_instances"] * 100
    tf_import_pct = tf_import / tf_stats["total_instances"] * 100
    evo_import_pct = evo_import / evo_stats["total_instances"] * 100

    lines.append("")
    lines.append(f"Structural failure (0 tests + syntax): TestForge={tf_struct} ({tf_struct_pct:.2f}%), EvoTest={evo_struct} ({evo_struct_pct:.2f}%)")
    lines.append(f"Import / execution failure:             TestForge={tf_import} ({tf_import_pct:.2f}%), EvoTest={evo_import} ({evo_import_pct:.2f}%)")
    lines.append(f"Any Pass@1:                             TestForge={tf_stats['any_pass_count']} ({tf_any:.2f}%), EvoTest={evo_stats['any_pass_count']} ({evo_any:.2f}%)")
    lines.append("")

    # Failing instance lists
    lines.append("TestForge Failing Instances")
    lines.append("-" * 70)
    for inst in tf_stats["failing_instances"]:
        lines.append(f"  {inst['instance_id']:<50} [{inst['failure_category']}]")
    lines.append("")

    lines.append("EvoTest Failing Instances")
    lines.append("-" * 70)
    for inst in evo_stats["failing_instances"]:
        lines.append(f"  {inst['instance_id']:<50} [{inst['failure_category']}]")
    lines.append("")

    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    print("Loading EvoTest results...")
    evo_instances = load_instances(EVOTEST_PATH)
    print(f"  Loaded {len(evo_instances)} instances")

    print("Loading TestForge results...")
    tf_instances = load_instances(TESTFORGE_PATH)
    print(f"  Loaded {len(tf_instances)} instances")

    print("\nComputing statistics...")
    evo_stats = compute_stats(evo_instances, "EvoTest")
    tf_stats = compute_stats(tf_instances, "TestForge")

    # Save JSON
    output = {
        "generated_at": "2026-06-26",
        "description": "Quantified validation: failure mode analysis for TestForge vs EvoTest",
        "data_sources": {
            "evotest": str(EVOTEST_PATH),
            "testforge": str(TESTFORGE_PATH),
        },
        "evotest": evo_stats,
        "testforge": tf_stats,
    }

    json_path = OUTPUT_DIR / "failure_stats.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nJSON saved to {json_path}")

    # Save report
    report = format_report(evo_stats, tf_stats)
    report_path = OUTPUT_DIR / "failure_stats_report.txt"
    with open(report_path, "w") as f:
        f.write(report)
    print(f"Report saved to {report_path}")

    # Print report
    print("\n" + report)


if __name__ == "__main__":
    main()
