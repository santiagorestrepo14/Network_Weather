import ast
from pathlib import Path

from network_weather.i18n import (
    EN,
    classification_description,
    evidence_name,
    normalize_language,
    probe_status_name,
    weather_description,
    weather_name,
)
from network_weather.models import ProbeStatus
from network_weather.weather import Classification, Evidence, Weather


def test_catalog_covers_all_weather_and_probe_states():
    for language in ("es", "en"):
        for weather in Weather:
            assert weather_name(weather, language)
            assert weather_description(weather, language)
        for status in ProbeStatus:
            assert probe_status_name(status, language)
    assert probe_status_name(ProbeStatus.TIMEOUT, "es") == "tiempo agotado"
    assert normalize_language("unexpected") == "es"


def test_latency_evidence_retains_target_in_both_languages():
    for language in ("es", "en"):
        rendered = evidence_name(
            "high_latency", "TCP connection time elevated toward example.com", language,
        )
        assert "example.com" in rendered


def test_unknown_description_explains_measurement_progress_and_confirmation():
    gathering = Classification(
        Weather.UNKNOWN, (), 0.0, 0.0,
        (Evidence("insufficient_rounds", "At least three rounds are required", 2, 3),), 2,
    )
    assert classification_description(gathering, "es") == "Analizando la conexión (2/3 rondas)"
    assert classification_description(gathering, "en") == "Collecting measurements (2/3 rounds)"

    confirming = Classification(Weather.UNKNOWN, (), 0.5, 0.0, (), 3,
                                pending_weather=Weather.SUNNY)
    assert classification_description(confirming, "es") == (
        "Confirmando Soleado con otra medición")
    assert classification_description(confirming, "en") == (
        "Confirming Clear with another measurement")


def test_all_static_desktop_translation_calls_have_english_entries():
    root = Path(__file__).parents[1] / "src" / "network_weather"
    missing = set()
    for file in (root / "desktop.py", root / "history_chart.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if name in {"t", "translate", "_page"} and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str) and value not in EN:
                    missing.add(value)
    assert not missing
