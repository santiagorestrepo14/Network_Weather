import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage, QImageReader
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from network_weather.compact_history import compact_points
from network_weather.desktop import ExpandedPanel, WeatherScene, WeatherWidget
from network_weather.history import HistorySeries, LatencyBin, WeatherPoint
from network_weather.models import (
    MeasurementRound,
    ProbeKind,
    ProbeResult,
    ProbeStatus,
    WifiSnapshot,
)
from network_weather.weather import Classification, Weather


def test_custom_weather_image_is_copied_and_persisted(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    source = tmp_path / "original.png"
    image = QImage(128, 128, QImage.Format.Format_RGB32)
    image.fill(QColor("#123456"))
    assert image.save(str(source))
    monkeypatch.setattr("network_weather.desktop.default_data_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(source), ""))
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.StandardButton.Apply)

    panel._choose_image(Weather.RAINY)
    saved = settings.value("image/rainy")
    assert saved != str(source)
    assert os.path.isfile(saved)
    assert source.is_file()
    assert QImage(saved).pixelColor(0, 0) == QColor("#123456")
    panel._reset_image(Weather.RAINY)
    assert settings.value("image/rainy") is None
    assert source.is_file()
    panel.close()
    widget.hide()
    app.processEvents()


def test_each_weather_has_a_readable_default_image(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    scene = WeatherScene(settings)
    scene.timer.stop()
    scene.resize(440, 210)
    scene.show()
    asset_dir = Path(__file__).parents[1] / "src" / "network_weather" / "assets"
    for weather in Weather:
        assert QImageReader(str(asset_dir / f"{weather.value}.png")).canRead()
        scene.set_weather(weather)
        app.processEvents()
        assert not scene.grab().isNull()
        assert not scene._cached_image.isNull()
    scene.hide()


def test_history_panel_filters_and_renders_observed_series(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    panel.nav.setCurrentRow(2)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    series = HistorySeries(
        start, start + timedelta(hours=1),
        (WeatherPoint(start, Weather.SUNNY),),
        (LatencyBin(start, start + timedelta(minutes=1), 42.0, 2),),
        ("one.example",), 120.0, False,
    )
    panel.show_history(series, [])
    assert panel.history_list.count() == 1
    assert panel.history_destination.count() == 2
    assert "2 muestras" in panel.history_status.text()
    assert panel.history_chart.series is series
    panel.history_range.setCurrentIndex(4)
    panel.history_start.setDateTime(start)
    panel.history_end.setDateTime(start + timedelta(hours=1))
    selected_start, selected_end, _ = panel.selected_history_range()
    assert selected_end - selected_start == timedelta(hours=1)
    panel.close()
    widget.hide()
    app.processEvents()


def test_incident_selection_shows_persisted_evidence(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    empty = HistorySeries(now, now + timedelta(hours=1), (), (), (), 120.0, False)
    incident = {
        "id": 1, "started_at": now.isoformat(),
        "ended_at": (now + timedelta(minutes=2)).isoformat(),
        "weather": Weather.RAINY.value, "severity": 0.5,
        "evidence": [{"code": "response_failures", "detail": "Failures",
                      "observed": 0.4, "threshold": 0.2}],
    }
    panel.show_history(empty, [incident])
    assert panel.incident_list.currentRow() == 0
    assert "40% de pruebas" in panel.incident_detail.toPlainText()
    assert "2 min" in panel.incident_detail.toPlainText()
    panel.close()
    widget.hide()
    app.processEvents()


def test_english_ui_uses_saved_language_for_widget_history_and_incidents(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    assert widget.weather_label.text() == "Unknown"
    assert panel.nav.item(0).text() == "Overview"
    assert panel.history_range.itemText(0) == "Last hour"
    assert panel.history_chart.language == "en"
    now = datetime(2026, 1, 1, tzinfo=UTC)
    empty = HistorySeries(now, now + timedelta(hours=1), (), (), (), 120.0, False)
    panel.show_history(empty, [{
        "id": 1, "started_at": now.isoformat(), "ended_at": None,
        "weather": Weather.RAINY.value, "severity": 0.5,
        "evidence": [{"code": "response_failures", "detail": "Response failures",
                      "observed": 0.4, "threshold": 0.2}],
    }])
    assert "valid TCP samples" in panel.history_status.text()
    assert "Cause: undetermined" in panel.incident_detail.toPlainText()
    assert "40% of probes" in panel.incident_detail.toPlainText()
    panel.close()
    widget.hide()
    app.processEvents()


def test_language_choice_persists_for_next_launch(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    panel.language_input.setCurrentIndex(panel.language_input.findData("en"))
    assert settings.value("language") == "en"
    panel.close()
    widget.hide()
    restarted_widget = WeatherWidget(settings)
    restarted_panel = ExpandedPanel(settings, restarted_widget)
    assert restarted_panel.nav.item(4).text() == "Settings"
    restarted_panel.close()
    restarted_widget.hide()
    app.processEvents()


def test_diagnostics_show_observed_wifi_without_claiming_it_is_the_route(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    at = datetime(2026, 1, 1, tzinfo=UTC)
    round_ = MeasurementRound(at, at, (), wifi=(WifiSnapshot("Test radio", 68, -66, 44),))
    result = Classification(Weather.UNKNOWN, (), 0, 0, (), 1)
    panel.update_measurement(round_, result)
    diagnostic = panel.diagnostic_label.text()
    assert "Test radio" in diagnostic
    assert "Signal quality: 68%" in diagnostic
    assert "RSSI: -66 dBm" in diagnostic
    assert "Channel: 44" in diagnostic
    assert "route not confirmed" in diagnostic
    panel.close()
    widget.hide()
    app.processEvents()


def test_compact_metric_selection_and_observed_history_persist(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    at = datetime(2026, 11, 22, tzinfo=UTC)
    rounds = [MeasurementRound(
        at + timedelta(seconds=offset), at + timedelta(seconds=offset),
        (ProbeResult(at + timedelta(seconds=offset), "example.test", ProbeKind.TCP,
                     ProbeStatus.SUCCESS, latency),),
    ) for offset, latency in ((0, 20.0), (30, 35.0))]
    widget.update_history(compact_points(rounds))
    assert widget.cards["jitter"].value.text() == "15 ms"
    assert widget.sparkline.points[-1].at == at + timedelta(seconds=30)
    widget.metric_select.setCurrentIndex(widget.metric_select.findData("variation"))
    assert settings.value("compact_metric") == "variation"
    assert widget.sparkline.chart_metric == "variation"
    widget.show()
    app.processEvents()
    assert not widget.sparkline.grab().isNull()
    widget.hide()
    restarted = WeatherWidget(settings)
    assert restarted.metric_select.currentData() == "variation"
    restarted.hide()
    app.processEvents()
