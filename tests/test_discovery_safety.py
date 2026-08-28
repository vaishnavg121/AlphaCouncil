from __future__ import annotations

"""Safety tests for discovery module - ensuring no mutation operations exist."""

import ast
from pathlib import Path


def get_discovery_source_files() -> list[Path]:
    """Get all Python files in the discovery module."""
    discovery_dir = Path(__file__).parent.parent / "backend" / "app" / "discovery"
    return list(discovery_dir.rglob("*.py"))


def get_diagnostic_source_files() -> list[Path]:
    """Get all diagnostic script files."""
    scripts_dir = Path(__file__).parent.parent / "scripts"
    return list(scripts_dir.rglob("check_discovery.py"))


class TestNoMutationMethodsInDiscoveryModule:
    """Ensure discovery module contains no order/position mutation methods."""

    MUTATION_KEYWORDS = {
        "submit_order",
        "cancel_order",
        "replace_order",
        "close_position",
        "close_all_positions",
        "liquidate",
        "exercise_option",
        "place_order",
        "create_order",
        "order_target",
        "order_target_percent",
        "order_target_value",
        "set_portfolio",
        "rebalance",
    }

    def test_no_mutation_methods_in_discovery_models(self) -> None:
        for file_path in get_discovery_source_files():
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name.lower()
                    for keyword in self.MUTATION_KEYWORDS:
                        assert keyword not in func_name, \
                            f"Mutation method '{func_name}' found in {file_path}"

                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        method_name = node.func.attr.lower()
                        for keyword in self.MUTATION_KEYWORDS:
                            assert keyword not in method_name, \
                                f"Mutation call '{method_name}' found in {file_path}"

    def test_no_mutation_methods_in_discovery_diagnostics(self) -> None:
        for file_path in get_diagnostic_source_files():
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        method_name = node.func.attr.lower()
                        for keyword in self.MUTATION_KEYWORDS:
                            assert keyword not in method_name, \
                                f"Mutation call '{method_name}' found in diagnostic {file_path}"


class TestNoLiveTradingInDiscoveryModule:
    """Ensure discovery module doesn't construct live trading clients."""

    def test_no_paper_false_in_discovery(self) -> None:
        for file_path in get_discovery_source_files():
            content = file_path.read_text()
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for paper=False in keyword arguments
                    for keyword in node.keywords:
                        if keyword.arg == "paper" and isinstance(keyword.value, ast.Constant):
                            assert keyword.value.value is not False, \
                                f"paper=False found in {file_path}"
                        if keyword.arg == "live" and isinstance(keyword.value, ast.Constant):
                            assert keyword.value.value is not True, \
                                f"live=True found in {file_path}"


class TestNoLLMDependenciesInDiscoveryModule:
    """Ensure discovery module doesn't depend on NVIDIA/LLM provider."""

    def test_no_llm_imports_in_discovery(self) -> None:
        for file_path in get_discovery_source_files():
            content = file_path.read_text()
            # Check imports don't include NVIDIA/LLM modules
            lines = content.split('\n')
            for line in lines:
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                    continue
                assert "nvidia" not in line.lower(), f"NVIDIA reference in {file_path}: {line}"
                if "import" in line.lower() or "from" in line.lower():
                    assert "llm" not in line.lower(), f"LLM import in {file_path}: {line}"

    def test_service_no_llm_dependency(self) -> None:
        service_file = Path(__file__).parent.parent / "backend" / "app" / "discovery" / "service.py"
        content = service_file.read_text()
        assert "nvidia" not in content.lower()
        assert "NvidiaLLMProvider" not in content
        assert "healthcheck" not in content.lower()


class TestDiscoveryDiagnosticReadOnly:
    """Ensure discovery diagnostic is read-only."""

    def test_check_discovery_no_order_submission(self) -> None:
        diag_file = Path(__file__).parent.parent / "scripts" / "check_discovery.py"
        content = diag_file.read_text()

        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            assert "submit_order" not in line
            assert "place_order" not in line
            assert "create_order" not in line
            assert "TradingClient" not in line  # Should use data client only

    def test_check_discovery_no_llm_calls(self) -> None:
        diag_file = Path(__file__).parent.parent / "scripts" / "check_discovery.py"
        content = diag_file.read_text()

        lines = content.split('\n')
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            assert "nvidia" not in line.lower()
            assert "NvidiaLLMProvider" not in line