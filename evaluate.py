#!/usr/bin/env python3
"""
FOCUS: FOA Intelligence Pipeline – Evaluation Module

This script evaluates the rule‑based semantic tagger against a small,
manually annotated "golden" dataset and reports micro‑averaged multi‑label
precision, recall, and F1‑score.
"""

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from main import RuleBasedTagger

console = Console()

# ---------------------------------------------------------------------------
# 1. Golden Dataset (Ground Truth)
#
# Each entry represents a synthetic FOA‑like example with:
#   - an identifier
#   - a title and short description
#   - expected tags for each ontology category
#
# This is intentionally small but diverse to exercise multiple branches of
# the rule‑based ontology without requiring any network calls.
# ---------------------------------------------------------------------------
GOLDEN_DATASET = [
    {
        "id": "NSF_GRFP",
        "title": "NSF Graduate Research Fellowship Program",
        "description": (
            "Supports outstanding graduate students in STEM disciplines "
            "pursuing research-based master's and doctoral degrees."
        ),
        "expected": {
            "research_domains": ["Education"],
            "methods": [],
            "populations": [],
            "themes": ["STEM Education", "Workforce Development"],
        },
    },
    {
        "id": "NIH_R01",
        "title": "Research Project Grant (Parent R01 Clinical Trial Required)",
        "description": (
            "Supports a discrete, specified, circumscribed project in areas "
            "representing the specific interests and competencies of the "
            "investigator, requiring human clinical trials."
        ),
        "expected": {
            "research_domains": ["Health & Medicine"],
            "methods": ["Clinical Trials"],
            "populations": [],
            "themes": [],
        },
    },
    {
        "id": "DOE_CLIMATE",
        "title": "Climate Resilience and Renewable Energy Research",
        "description": (
            "Funding for innovative mathematical models simulating climate "
            "change impacts on sustainable green energy infrastructure."
        ),
        "expected": {
            "research_domains": ["Mathematics", "Environmental Sciences"],
            "methods": ["Computational Modeling"],
            "populations": [],
            "themes": ["Climate & Sustainability"],
        },
    },
    {
        "id": "DOD_TECH",
        "title": "Advanced Machine Learning for Autonomous Vehicles",
        "description": (
            "Developing deep learning algorithms and artificial intelligence "
            "for military and veteran logistics."
        ),
        "expected": {
            "research_domains": ["Engineering & Technology"],
            "methods": ["Machine Learning"],
            "populations": ["Veterans"],
            "themes": [],
        },
    },
    {
        "id": "ED_UNDERSERVED",
        "title": "Community Health and Sociology Initiative",
        "description": (
            "A field study examining public healthcare access in marginalized "
            "and underserved communities."
        ),
        "expected": {
            "research_domains": ["Social Sciences", "Health & Medicine"],
            "methods": ["Field Studies"],
            "populations": ["Underserved Communities", "General Public"],
            "themes": [],
        },
    },
]


def calculate_metrics(expected_tags: list, predicted_tags: list) -> tuple[int, int, int]:
    """
    Compute true positives, false positives, and false negatives
    for a single FOA instance.

    Args:
        expected_tags: Flat list of ground‑truth tag labels.
        predicted_tags: Flat list of labels predicted by the tagger.

    Returns:
        Tuple (tp, fp, fn) as integer counts.
    """
    expected_set = set(expected_tags)
    predicted_set = set(predicted_tags)

    tp = len(expected_set.intersection(predicted_set))
    fp = len(predicted_set - expected_set)
    fn = len(expected_set - predicted_set)

    return tp, fp, fn


def main() -> None:
    """
    Run the evaluation against the golden dataset and render metrics.

    The script prints per‑example tag comparisons in a Rich table and then
    aggregates micro‑averaged precision, recall, and F1‑score across all
    examples.
    """
    console.print()
    console.print(
        Rule(
            "[bold cyan]FOCUS: Semantic Tagging Evaluation Framework"
            "[/bold cyan]",
            style="cyan",
        )
    )
    console.print()

    tagger = RuleBasedTagger()

    total_tp = 0
    total_fp = 0
    total_fn = 0

    # Visual table for individual FOA predictions vs ground truth.
    results_table = Table(
        show_header=True,
        header_style="bold magenta",
        expand=True,
    )
    results_table.add_column("FOA ID", style="cyan", width=15)
    results_table.add_column("Ground Truth (Expected)", style="green")
    results_table.add_column("Pipeline Prediction", style="yellow")

    for item in GOLDEN_DATASET:
        # Run the tagger on the synthetic FOA.
        predictions = tagger.tag(item["title"], item["description"])

        # Flatten the category -> list mapping into a single list of labels
        # so we can compute micro‑averaged metrics across all tags.
        expected_flat = [
            tag for category in item["expected"].values() for tag in category
        ]
        predicted_flat = [
            tag for category in predictions.values() for tag in category
        ]

        tp, fp, fn = calculate_metrics(expected_flat, predicted_flat)
        total_tp += tp
        total_fp += fp
        total_fn += fn

        expected_str = "\n".join(expected_flat) if expected_flat else "None"
        predicted_str = "\n".join(predicted_flat) if predicted_flat else "None"
        results_table.add_row(item["id"], expected_str, predicted_str)
        results_table.add_section()

    console.print(results_table)

    # -----------------------------------------------------------------------
    # 2. Global Metric Calculations (Micro‑Averaged)
    # -----------------------------------------------------------------------
    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    f1_score = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    # Compact Rich panel summarizing aggregate metrics.
    metrics_table = Table(show_header=False, box=None)
    metrics_table.add_column("Metric", style="cyan", width=20)
    metrics_table.add_column("Value", style="bold white")

    metrics_table.add_row(
        "Precision:",
        f"{precision:.2%} [dim](Accuracy of assigned tags)[/dim]",
    )
    metrics_table.add_row(
        "Recall:",
        f"{recall:.2%} [dim](Ability to find all relevant tags)[/dim]",
    )
    metrics_table.add_row(
        "F1-Score:",
        f"[bold green]{f1_score:.2%}[/bold green] "
        "[dim](Harmonic mean of precision & recall)[/dim]",
    )
    metrics_table.add_row("Total Evaluated:", str(len(GOLDEN_DATASET)))

    summary_panel = Panel(
        metrics_table,
        title="[bold green]📊 Baseline Accuracy Metrics (Multi-Label)[/bold green]",
        expand=False,
        border_style="green",
    )

    console.print()
    console.print(summary_panel)
    console.print()


if __name__ == "__main__":
    main()
