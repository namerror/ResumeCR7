"""Pytest configuration for test suite."""
import os
import sys
import pytest


# Set environment variables BEFORE any app imports
os.environ["DEV_MODE"] = "true"
os.environ["SKILL_TOP_N"] = "10"
os.environ["SKILL_METHOD"] = "baseline"
os.environ["SKILL_BASELINE_FILTER"] = "false"
os.environ["PROJ_METHOD"] = "llm"
os.environ.pop("PROJ_TOP_N", None)
os.environ["LLM_PROVIDER"] = "openai"


def pytest_addoption(parser):
    parser.addoption(
        "--run-smoke",
        action="store_true",
        default=False,
        help="Run smoke tests that hit the real OpenAI API (requires OPENAI_API_KEY)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-smoke"):
        # --run-smoke given: only skip if key is missing
        skip_no_key = pytest.mark.skip(reason="OPENAI_API_KEY not set")
        for item in items:
            if "smoke" in item.keywords and not os.environ.get("OPENAI_API_KEY"):
                item.add_marker(skip_no_key)
    else:
        # No flag: skip all smoke tests
        skip_smoke = pytest.mark.skip(reason="need --run-smoke flag to run")
        for item in items:
            if "smoke" in item.keywords:
                item.add_marker(skip_smoke)


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: live API smoke tests (require --run-smoke and OPENAI_API_KEY)")


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment and reload modules with correct env vars."""
    # Reload the baseline module to pick up the new DEV_MODE value
    if "app.skill_selection.scoring.baseline" in sys.modules:
        import importlib
        import app.skill_selection.scoring.baseline
        importlib.reload(app.skill_selection.scoring.baseline)

    yield
