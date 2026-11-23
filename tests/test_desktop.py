import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QColor, QImage, QImageReader
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from network_weather.compact_history import compact_points
from network_weather.desktop import ExpandedPanel, WeatherScene, WeatherWidget
from network_weather.diagnostics import recent_diagnostics
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

    widget.scene.set_weather(Weather.RAINY)
    panel.overview_scene.set_weather(Weather.RAINY)
    widget.show()
    panel.show()
    app.processEvents()
    panel._choose_image(Weather.RAINY)
    saved = settings.value("image/rainy")
    assert saved != str(source)
    assert os.path.isfile(saved)
    assert source.is_file()
    assert QImage(saved).pixelColor(0, 0) == QColor("#123456")
    cover = widget.scene.grab().toImage()
    panel.overview_scene.grab()
    assert widget.scene._cached_image_path == saved
    assert panel.overview_scene._cached_image_path == saved
    panel.image_fit_input.setCurrentText("contain")
    app.processEvents()
    assert widget.scene.grab().toImage() != cover
    panel._reset_image(Weather.RAINY)
    assert settings.value("image/rainy") is None
    panel.overview_scene.grab()
    assert panel.overview_scene._cached_image_path.endswith("rainy.png")
    assert source.is_file()
    panel.close()
    widget.hide()
    app.processEvents()


def test_effects_and_reduced_motion_apply_to_visible_scenes_immediately(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    widget.scene.timer.stop()
    panel.overview_scene.timer.stop()
    for scene in (widget.scene, panel.overview_scene):
        scene.set_weather(Weather.RAINY)
        scene.phase = 1.0
    widget.show()
    panel.show()
    app.processEvents()
    widget.scene.timer.stop()
    panel.overview_scene.timer.stop()
    animated_widget = widget.scene.grab().toImage()
    animated_overview = panel.overview_scene.grab().toImage()
    panel.effects_checkbox.setChecked(False)
    app.processEvents()
    assert widget.scene.grab().toImage() != animated_widget
    assert panel.overview_scene.grab().toImage() != animated_overview
    panel.effects_checkbox.setChecked(True)
    panel.reduced_motion_checkbox.setChecked(True)
    app.processEvents()
    assert settings.value("reduced_motion", type=bool)
    assert widget.scene.grab().toImage() != animated_widget
    panel.close()
    widget.hide()
    app.processEvents()


def test_missing_or_disguised_image_is_rejected_without_changing_selection(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("invalid"))
    missing = tmp_path / "missing.png"
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(missing), ""))
    panel._choose_image(Weather.RAINY)
    disguised = tmp_path / "disguised.exe"
    image = QImage(128, 128, QImage.Format.Format_RGB32)
    image.fill(QColor("#123456"))
    assert image.save(str(disguised), "PNG")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(disguised), ""))
    panel._choose_image(Weather.RAINY)
    assert messages == ["invalid", "invalid"]
    assert settings.value("image/rainy") is None
    panel.close()
    widget.hide()
    app.processEvents()


def test_imported_weather_image_survives_new_settings_session(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.ini"
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    source = tmp_path / "wind.png"
    image = QImage(128, 128, QImage.Format.Format_RGB32)
    image.fill(QColor("#5874cc"))
    assert image.save(str(source))
    monkeypatch.setattr("network_weather.desktop.default_data_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args: (str(source), ""))
    monkeypatch.setattr(QMessageBox, "exec", lambda _self: QMessageBox.StandardButton.Apply)
    panel._choose_image(Weather.WINDY)
    saved = settings.value("image/windy")
    panel.close()
    widget.hide()
    reopened_settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    reopened = WeatherWidget(reopened_settings)
    reopened.scene.set_weather(Weather.WINDY)
    reopened.show()
    app.processEvents()
    reopened.scene.grab()
    assert reopened.scene._cached_image_path == saved
    assert source.is_file()
    reopened.hide()
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


def test_weather_animation_runs_only_when_visible_and_enabled(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    scene = WeatherScene(settings)
    scene.set_weather(Weather.RAINY)
    assert not scene.timer.isActive()
    scene.show()
    app.processEvents()
    assert scene.timer.isActive()
    scene.hide()
    assert not scene.timer.isActive()
    scene.show()
    assert scene.timer.isActive()
    settings.setValue("effects", False)
    scene.sync_animation()
    assert not scene.timer.isActive()
    settings.setValue("effects", True)
    scene.sync_animation()
    assert scene.timer.isActive()
    settings.setValue("reduced_motion", True)
    scene.sync_animation()
    assert not scene.timer.isActive()
    settings.setValue("reduced_motion", False)
    scene.set_weather(Weather.OFFLINE)
    assert scene.timer.isActive()
    scene._transition_started -= 1
    scene._tick()
    assert not scene.timer.isActive()
    scene.set_weather(Weather.SUNNY)
    assert scene.timer.isActive()
    scene.hide()


def test_sunny_and_cloudy_have_motion_but_previews_stay_static(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    scene = WeatherScene(settings, animated=False)
    scene.resize(440, 210)
    scene.show()
    app.processEvents()
    for weather in (Weather.SUNNY, Weather.CLOUDY):
        scene.set_weather(weather)
        scene.phase = 0
        first = scene.grab().toImage()
        scene.phase = 2
        assert scene.grab().toImage() != first
        assert not scene.timer.isActive()
    scene.hide()


def test_weather_change_crossfades_and_reduced_motion_skips_it(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    scene = WeatherScene(settings)
    scene.resize(440, 210)
    scene.set_weather(Weather.SUNNY)
    scene.show()
    app.processEvents()
    scene.timer.stop()
    sunny_frame = scene.grab().toImage()

    scene.set_weather(Weather.OFFLINE)
    assert not scene._transition_image.isNull()
    assert scene.timer.isActive()
    assert scene.timer.interval() == 50
    scene._transition_started -= 0.275
    midway_frame = scene.grab().toImage()
    scene._transition_started -= 1
    scene._tick()
    assert scene._transition_image.isNull()
    assert not scene.timer.isActive()
    offline_frame = scene.grab().toImage()
    assert midway_frame != sunny_frame
    assert midway_frame != offline_frame

    settings.setValue("reduced_motion", True)
    scene.set_weather(Weather.RAINY)
    assert scene._transition_image.isNull()
    assert not scene.timer.isActive()
    settings.setValue("reduced_motion", False)
    scene.set_weather(Weather.CLOUDY)
    assert not scene._transition_image.isNull()
    settings.setValue("effects", False)
    scene.sync_animation()
    assert scene._transition_image.isNull()
    assert not scene.timer.isActive()
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


def test_widget_restores_saved_position_on_an_available_screen(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("widget_position", QPoint(999999, 999999))
    widget = WeatherWidget(settings)
    widget.show()
    widget.ensure_visible()
    app.processEvents()
    assert any(screen.availableGeometry().contains(widget.geometry())
               for screen in app.screens())
    widget.hide()


def test_overview_cards_use_observed_probe_results(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    at = datetime(2026, 11, 22, tzinfo=UTC)
    probes = (
        ProbeResult(at, "a.example", ProbeKind.DNS, ProbeStatus.SUCCESS, 5.0),
        ProbeResult(at, "a.example", ProbeKind.TCP, ProbeStatus.TIMEOUT, None),
        ProbeResult(at, "a.example", ProbeKind.HTTPS, ProbeStatus.SUCCESS, 50.0),
        ProbeResult(at, "192.0.2.1", ProbeKind.ICMP, ProbeStatus.TIMEOUT, None),
    )
    round_ = MeasurementRound(at, at, probes)
    result = Classification(Weather.RAINY, (), 0.75, 0.5, (), 3)
    panel.update_measurement(round_, result)
    assert panel.overview_scene.weather == Weather.RAINY
    assert panel.overview_cards["latency"].value.text() == "—"
    assert panel.overview_cards["failures"].value.text() == "100%"
    assert panel.overview_cards["dns"].value.text() == "Healthy"
    assert panel.overview_cards["gateway"].value.text() == "No reply"
    assert panel.overview_cards["external"].value.text() == "Confirmed"
    assert panel.evidence_label.text() == "No conclusive evidence yet."
    series = HistorySeries(at - timedelta(hours=1), at, (), (), (), 120.0, False)
    panel.show_overview(series, [])
    assert panel.overview_chart.series is series
    assert panel.incident_summary_label.text() == "No active incidents."
    panel.close()
    widget.hide()
    app.processEvents()


def test_diagnostic_table_shows_samples_and_excludes_failed_latency(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("language", "en")
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    start = datetime(2026, 11, 22, tzinfo=UTC)
    rounds = []
    for offset, duration in ((0, 20.0), (30, None), (60, 45.0)):
        at = start + timedelta(seconds=offset)
        probe = ProbeResult(at, "example.com", ProbeKind.TCP,
                            ProbeStatus.SUCCESS if duration is not None else ProbeStatus.TIMEOUT,
                            duration)
        rounds.append(MeasurementRound(at, at, (probe,)))
    panel.update_diagnostics(recent_diagnostics(rounds, 30))
    assert panel.diagnostic_table.rowCount() == 1
    assert panel.diagnostic_table.item(0, 2).text() == "3"
    assert panel.diagnostic_table.item(0, 3).text() == "2"
    assert panel.diagnostic_table.item(0, 4).text() == "32.5 ms"
    assert panel.diagnostic_table.item(0, 5).text() == "45.0 ms"
    assert panel.diagnostic_table.item(0, 6).text() == "— (0)"
    assert panel.diagnostic_table.item(0, 7).text() == "33%"
    panel.close()
    widget.hide()
    app.processEvents()


def test_startup_checkbox_reflects_registry_and_reverts_failed_change(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("startup", True)  # obsolete preference must not override Windows
    registry = {"command": None, "fail": False}
    command = '"C:\\NetworkWeather\\NetworkWeather.exe"'

    monkeypatch.setattr("network_weather.desktop.read_startup_command",
                        lambda: registry["command"])
    monkeypatch.setattr("network_weather.desktop.startup_command",
                        lambda *_args, **_kwargs: command)

    def update(enabled, value):
        if registry["fail"]:
            raise OSError("Access denied")
        registry["command"] = value if enabled else None

    monkeypatch.setattr("network_weather.desktop.set_startup_enabled", update)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    assert not panel.startup_checkbox.isChecked()
    panel.startup_checkbox.setChecked(True)
    assert registry["command"] == command
    assert panel.startup_checkbox.isChecked()
    registry["command"] = '"C:\\OldNetworkWeather\\NetworkWeather.exe"'
    panel._refresh_startup_state()
    assert panel.startup_checkbox.isChecked()
    assert "otra instalación" in panel.startup_status.text()
    panel.startup_checkbox.setChecked(False)
    assert registry["command"] is None
    registry["fail"] = True
    panel.startup_checkbox.setChecked(True)
    assert not panel.startup_checkbox.isChecked()
    panel.close()
    widget.hide()
    app.processEvents()


def test_optional_direct_ip_setting_is_validated_and_persisted(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    messages = []
    monkeypatch.setattr(QMessageBox, "information", lambda *_args: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: messages.append("invalid"))
    panel.direct_ip_input.setText("192.168.1.1")
    panel._save_probe_settings()
    assert messages == ["invalid"]
    assert settings.value("direct_ip_target") is None
    panel.direct_ip_input.setText("1.1.1.1")
    panel._save_probe_settings()
    assert settings.value("direct_ip_target") == "1.1.1.1"
    panel.close()
    widget.hide()
    app.processEvents()


def test_direct_ip_failure_does_not_inflate_hostname_cards(tmp_path):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    widget = WeatherWidget(settings)
    panel = ExpandedPanel(settings, widget)
    at = datetime(2026, 11, 22, tzinfo=UTC)
    probes = (
        ProbeResult(at, "example.com", ProbeKind.DNS, ProbeStatus.SUCCESS, 3.0),
        ProbeResult(at, "example.com", ProbeKind.TCP, ProbeStatus.SUCCESS, 20.0),
        ProbeResult(at, "example.com", ProbeKind.HTTPS, ProbeStatus.SUCCESS, 35.0),
        ProbeResult(at, "1.1.1.1", ProbeKind.TCP, ProbeStatus.TIMEOUT, None),
    )
    round_ = MeasurementRound(at, at, probes)
    result = Classification(Weather.UNKNOWN, (), 0.5, 0, (), 1)
    widget.update_measurement(round_, result)
    panel.update_measurement(round_, result)
    assert widget.cards["loss"].value.text() == "0%"
    assert panel.overview_cards["failures"].value.text() == "0%"
    assert panel.overview_cards["external"].value.text() == "Confirmada"
    panel.close()
    widget.hide()
    app.processEvents()
