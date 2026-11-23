"""Categorical weather and observed latency charts for the history panel."""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from network_weather.history import HistorySeries
from network_weather.i18n import normalize_language, translate
from network_weather.weather import Weather

PALETTE = {
    Weather.SUNNY: "#ffca74", Weather.CLOUDY: "#aebcf4",
    Weather.WINDY: "#bd89ff", Weather.RAINY: "#75b8ff",
    Weather.FOGGY: "#b8c6d4", Weather.STORMY: "#f48cdd",
    Weather.OFFLINE: "#f77897", Weather.UNKNOWN: "#72728d",
}


def weather_segments(series: HistorySeries) -> list[tuple[datetime, datetime, Weather]]:
    """Only carry a state through its expected observation interval."""
    points = series.weather
    segments = []
    hold_seconds = min(series.gap_threshold_seconds,
                       max(1.0, series.typical_interval_seconds * 1.5))
    for index, point in enumerate(points):
        end = min(series.end, point.at + timedelta(seconds=hold_seconds))
        if index + 1 < len(points):
            end = min(end, points[index + 1].at)
        if end > point.at:
            segments.append((point.at, end, point.weather))
    return segments


class HistoryChart(QWidget):
    def __init__(self, parent: QWidget | None = None, language: str = "es") -> None:
        super().__init__(parent)
        self.language = normalize_language(language)
        self.series: HistorySeries | None = None
        self.setMinimumHeight(230)

    def set_series(self, series: HistorySeries) -> None:
        self.series = series
        self.update()

    def paintEvent(self, _event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#1a2145"))
        p.setPen(QColor("#e4e7ff"))
        p.drawText(16, 22, translate("Clima observado", self.language))
        p.drawText(16, 105, translate("Latencia TCP promedio por intervalo (ms)", self.language))
        left, right = 16.0, max(17.0, self.width() - 16.0)
        width = right - left
        p.fillRect(QRectF(left, 36, width, 34), QColor("#30354f"))
        p.fillRect(QRectF(left, 120, width, 75), QColor("#202846"))
        if self.series is None:
            p.drawText(16, 220, translate("Selecciona un periodo para consultar el historial",
                                          self.language))
            p.end()
            return
        series = self.series
        seconds = (series.end - series.start).total_seconds()
        if seconds <= 0:
            p.end()
            return

        def x(at: datetime) -> float:
            return left + width * (at - series.start).total_seconds() / seconds

        for start, end, weather in weather_segments(series):
            p.fillRect(QRectF(x(start), 36, max(1, x(end) - x(start)), 34),
                       QColor(PALETTE[weather]))
        max_latency = max((item.mean_ms for item in series.latency), default=0)
        if max_latency > 0:
            for item in series.latency:
                bar_height = item.mean_ms / max_latency * 70
                p.fillRect(QRectF(x(item.start), 195 - bar_height,
                                  max(2, x(item.end) - x(item.start) - 1), bar_height),
                           QColor("#ad8eff"))
            p.setPen(QColor("#c9c9f9"))
            maximum = "max." if self.language == "en" else "máx."
            p.drawText(int(right - 85), 118, f"{maximum} {max_latency:.0f} ms")
        p.setPen(QPen(QColor("#6f7aa7"), 1))
        p.drawLine(int(left), 195, int(right), 195)
        p.setPen(QColor("#b8c5ef"))
        stamp_format = "%m/%d %H:%M" if self.language == "en" else "%d/%m %H:%M"
        p.drawText(16, 217, series.start.astimezone().strftime(stamp_format))
        end_label = series.end.astimezone().strftime(stamp_format)
        p.drawText(QRectF(left, 201, width, 22),
                   Qt.AlignmentFlag.AlignRight, end_label)
        if not series.weather and not series.latency:
            p.drawText(16, 87, translate("Sin observaciones en este periodo", self.language))
        p.end()
