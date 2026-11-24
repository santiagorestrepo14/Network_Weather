from datetime import UTC, datetime, timedelta

from network_weather.incident_view import format_incident


def test_incident_detail_shows_duration_evidence_and_uncertain_cause():
    started = datetime(2026, 1, 1, tzinfo=UTC)
    incident = {
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(minutes=23)).isoformat(),
        "weather": "stormy", "severity": 0.8,
        "evidence": [
            {"code": "high_latency", "detail": "TCP connection time is elevated",
             "observed": 230.4, "threshold": 150.0},
            {"code": "gateway_echo_unanswered", "detail": "Gateway did not answer ICMP",
             "observed": None, "threshold": None},
        ],
    }
    rendered = format_incident(incident)
    assert "23 min" in rendered
    assert "80%" in rendered
    assert "230.4 ms" in rendered
    assert "Causa: no determinada" in rendered
    assert "Confianza en causa: no establecida" in rendered
    assert "podría filtrar" in rendered


def test_active_incident_uses_observation_time():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    incident = {"started_at": start.isoformat(), "ended_at": None,
                "weather": "rainy", "severity": 0.5, "evidence": []}
    rendered = format_incident(incident, start + timedelta(minutes=5))
    assert "aún activo" in rendered
    assert "5 min" in rendered
    english = format_incident(incident, start + timedelta(minutes=5), language="en")
    assert "Weather: Rain" in english
    assert "Cause: undetermined" in english
    assert "Cause confidence: not established" in english
    assert "still active" in english
