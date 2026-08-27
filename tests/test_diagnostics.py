from __future__ import annotations

from pathlib import Path


def test_alpaca_diagnostic_contains_no_order_mutation_calls() -> None:
    source = (Path(__file__).parents[1] / "scripts" / "check_alpaca.py").read_text(encoding="utf-8")
    forbidden_calls = (
        "submit_order(",
        "cancel_order(",
        "replace_order(",
        "close_position(",
        "close_all_positions(",
        "exercise_options(",
    )
    assert all(call not in source for call in forbidden_calls)


def test_no_m0_source_contains_alpaca_mutation_calls() -> None:
    source_root = Path(__file__).parents[1] / "backend" / "app"
    forbidden_calls = (
        "submit_order(",
        "cancel_order(",
        "replace_order(",
        "close_position(",
        "close_all_positions(",
        "exercise_options(",
    )
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_root.rglob("*.py"))
    assert all(call not in source for call in forbidden_calls)
