import json
import logging
import sys
import pytest
from app.logging_config import JsonFormatter, setup_logging


def make_record(msg="hello", level=logging.INFO, name="test", extra=None):
    logger = logging.getLogger(name)
    record = logger.makeRecord(
        name, level, fn="test.py", lno=1, msg=msg, args=(), exc_info=None
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


# === JsonFormatter tests ===

def test_format_returns_valid_json():
    record = make_record()
    output = JsonFormatter().format(record)
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_format_required_fields():
    record = make_record(msg="hi", name="mylogger")
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["msg"] == "hi"
    assert parsed["logger"] == "mylogger"
    assert parsed["level"] == "INFO"
    assert "ts" in parsed


def test_format_level_names():
    for level, name in [(logging.DEBUG, "DEBUG"), (logging.WARNING, "WARNING"), (logging.ERROR, "ERROR")]:
        record = make_record(level=level)
        parsed = json.loads(JsonFormatter().format(record))
        assert parsed["level"] == name


def test_format_includes_extra_fields():
    record = make_record(extra={"event": "select_skills", "role": "backend"})
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["event"] == "select_skills"
    assert parsed["role"] == "backend"


def test_format_excludes_internal_fields():
    record = make_record()
    parsed = json.loads(JsonFormatter().format(record))
    for field in ("args", "levelno", "pathname", "lineno", "thread", "process"):
        assert field not in parsed


def test_format_includes_exc_info():
    try:
        raise ValueError("boom")
    except ValueError:
        record = make_record()
        record.exc_info = sys.exc_info()
        parsed = json.loads(JsonFormatter().format(record))
        assert "exc_info" in parsed
        assert "ValueError" in parsed["exc_info"]
        assert "boom" in parsed["exc_info"]


def test_format_no_exc_info_by_default():
    record = make_record()
    parsed = json.loads(JsonFormatter().format(record))
    assert "exc_info" not in parsed


def test_format_ts_is_iso8601():
    from datetime import datetime
    record = make_record()
    parsed = json.loads(JsonFormatter().format(record))
    # Should parse without raising
    dt = datetime.fromisoformat(parsed["ts"])
    assert dt.tzinfo is not None  # timezone-aware


def test_format_unicode_safe():
    record = make_record(msg="résumé skills: 日本語")
    output = JsonFormatter().format(record)
    parsed = json.loads(output)
    assert parsed["msg"] == "résumé skills: 日本語"


# === setup_logging tests ===

def test_setup_logging_attaches_json_handler():
    setup_logging("INFO")
    root = logging.getLogger()
    assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)


def test_setup_logging_clears_previous_handlers():
    # Add a dummy handler, then setup_logging should replace it
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    count_before = len(root.handlers)
    setup_logging("INFO")
    # Should have exactly one handler after setup
    assert len(root.handlers) == 1


def test_setup_logging_can_attach_file_handler(tmp_path):
    log_path = tmp_path / "logs" / "resumecr7.log"

    setup_logging("INFO", log_path=log_path)
    logging.getLogger("test").info("hello")

    assert log_path.is_file()
    parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert parsed["msg"] == "hello"


def test_setup_logging_sets_level_info():
    setup_logging("INFO")
    assert logging.getLogger().level == logging.INFO


def test_setup_logging_sets_level_debug():
    setup_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_setup_logging_sets_level_warning():
    setup_logging("WARNING")
    assert logging.getLogger().level == logging.WARNING


def test_setup_logging_case_insensitive():
    setup_logging("debug")
    assert logging.getLogger().level == logging.DEBUG


@pytest.fixture(autouse=True)
def restore_root_logger():
    """Reset root logger state after each test."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.level = original_level
