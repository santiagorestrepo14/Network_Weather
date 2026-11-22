import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QImage, QImageReader
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from network_weather.desktop import ExpandedPanel, WeatherScene, WeatherWidget
from network_weather.weather import Weather


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
