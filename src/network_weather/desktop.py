"""Windows desktop widget and expanded view. All network work runs in MonitorThread."""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QPoint,
    QRect,
    QRectF,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedLayout,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from network_weather.compact_history import CompactPoint, compact_points, visible_segments
from network_weather.config import ProbeConfig, default_data_dir
from network_weather.diagnostics import DiagnosticSummary, recent_diagnostics
from network_weather.history import HistoryStore
from network_weather.history_chart import PALETTE, HistoryChart, weather_segments
from network_weather.i18n import (
    evidence_name,
    normalize_language,
    probe_status_name,
    translate,
    weather_description,
    weather_name,
)
from network_weather.incident_view import format_incident
from network_weather.models import MeasurementRound, ProbeKind
from network_weather.monitor import Monitor
from network_weather.weather import Classification, Weather
from network_weather.window_placement import visible_position
from network_weather.windows_startup import (
    read_startup_command,
    set_startup_enabled,
    startup_command,
)

COLORS = {
    Weather.SUNNY: ("#ffbf68", "#6d4ead"),
    Weather.CLOUDY: ("#b4c4f8", "#303d70"),
    Weather.WINDY: ("#d18cff", "#344bad"),
    Weather.RAINY: ("#82b9ff", "#50317e"),
    Weather.FOGGY: ("#b5c6da", "#444d72"),
    Weather.STORMY: ("#f790df", "#271d61"),
    Weather.OFFLINE: ("#fa7c9b", "#27263e"),
    Weather.UNKNOWN: ("#b9b8df", "#343159"),
}
def icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor("#7d67eb"))
    gradient.setColorAt(1, QColor("#1c3e83"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#a899ff"), 2))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    painter.setPen(QPen(QColor("#e1cbff"), 4))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(12, 16, 40, 28), 0, 180 * 16)
    painter.drawArc(QRectF(16, 33, 32, 22), 15 * 16, 150 * 16)
    painter.drawEllipse(QPoint(32, 53), 2, 2)
    painter.end()
    return QIcon(pixmap)


class WeatherScene(QWidget):
    """Procedural, redistributable scene with independent optional image/effects."""

    def __init__(self, settings: QSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.weather = Weather.UNKNOWN
        self.phase = 0.0
        self._cached_image_path = ""
        self._cached_image = QImage()
        self.setMinimumHeight(205)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)

    def _tick(self) -> None:
        if self.isVisible() and self.settings.value("effects", True, type=bool) and not self.settings.value("reduced_motion", False, type=bool):
            self.phase += 0.08
            self.update()

    def set_weather(self, weather: Weather) -> None:
        self.weather = weather
        self.update()

    def invalidate_image(self) -> None:
        self._cached_image_path = ""
        self._cached_image = QImage()
        self.update()

    def paintEvent(self, _event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        p.setClipPath(path)
        accent, base = COLORS[self.weather]
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#101d49"))
        gradient.setColorAt(0.52, QColor(base))
        gradient.setColorAt(1, QColor("#17142f"))
        p.fillRect(rect, gradient)
        default_path = Path(__file__).parent / "assets" / f"{self.weather.value}.png"
        image_path = self.settings.value(f"image/{self.weather.value}", "") or str(default_path)
        if image_path != self._cached_image_path:
            self._cached_image_path = image_path
            reader = QImageReader(image_path)
            if reader.canRead():
                native = reader.size()
                target_width = max(self.width()*2, 144)
                if native.width() > target_width:
                    ratio = target_width / native.width()
                    reader.setScaledSize(QSize(target_width, max(1, int(native.height()*ratio))))
                self._cached_image = reader.read()
            else:
                self._cached_image = QImage()
        image = self._cached_image
        if not image.isNull():
            mode = self.settings.value("image_fit", "cover")
            if mode == "contain":
                scaled = image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                target = QRectF((self.width() - scaled.width()) / 2,
                                (self.height() - scaled.height()) / 2,
                                scaled.width(), scaled.height())
                p.drawImage(target, scaled)
            elif mode == "center":
                p.drawImage(QPoint((self.width() - image.width()) // 2,
                                   (self.height() - image.height()) // 2), image)
            else:
                scaled = image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                      Qt.TransformationMode.SmoothTransformation)
                source = QRectF((scaled.width() - self.width()) / 2,
                                (scaled.height() - self.height()) / 2,
                                self.width(), self.height())
                p.drawImage(rect, scaled, source)
            p.fillRect(rect, QColor(10, 9, 34, 80))
        else:
            self._landscape(p, QColor(accent))
        if self.settings.value("effects", True, type=bool):
            self._effects(p, QColor(accent))
        p.end()

    def _landscape(self, p: QPainter, accent: QColor) -> None:
        w, h = self.width(), self.height()
        glow = QRadialGradient(w * 0.67, h * 0.39, w * 0.56)
        g = QColor(accent)
        g.setAlpha(130)
        glow.setColorAt(0, g)
        glow.setColorAt(1, QColor(20, 16, 50, 0))
        p.fillRect(self.rect(), glow)
        if self.weather in (Weather.WINDY, Weather.RAINY, Weather.STORMY):
            for offset, color in ((0, QColor(241, 86, 192, 85)),
                                  (15, QColor(100, 174, 255, 100)),
                                  (29, QColor(211, 113, 255, 55))):
                arc = QPainterPath(QPoint(-20, int(h*.73 + offset)))
                arc.cubicTo(w*.20, h*.22 + offset, w*.56, h*.08 + offset,
                            w+30, h*.47 + offset)
                p.setPen(QPen(color, 1.5))
                p.drawPath(arc)
        p.setPen(Qt.PenStyle.NoPen)
        if self.weather == Weather.SUNNY:
            sun = QRadialGradient(w * 0.72, h * 0.32, 75)
            sun.setColorAt(0, QColor("#fff6bc"))
            sun.setColorAt(0.35, QColor("#ffbd77"))
            sun.setColorAt(1, QColor(255, 150, 80, 0))
            p.setBrush(sun)
            p.drawEllipse(QPoint(int(w * 0.72), int(h * 0.32)), 75, 75)
        else:
            for x, y, rx, ry in ((.36, .56, .15, .20), (.43, .45, .15, .25),
                                 (.53, .38, .17, .28), (.63, .41, .18, .28),
                                 (.72, .43, .16, .25), (.82, .54, .14, .20)):
                cloud = QRadialGradient(w * x, h * y, w * rx)
                cloud.setColorAt(0, QColor("#aebaff"))
                cloud.setColorAt(.48, QColor("#6d74c5"))
                cloud.setColorAt(.82, QColor("#554394"))
                cloud.setColorAt(1, QColor(50, 42, 107, 0))
                p.setBrush(cloud)
                p.drawEllipse(QRectF(w * (x-rx), h * (y-ry), w * rx * 2, h * ry * 2))
            for i in range(9):
                x = w*(.38 + i*.052)
                y = h*(.62 + .04*math.sin(i*2.1))
                under = QRadialGradient(x, y, w*.10)
                under.setColorAt(0, QColor("#e484d9" if self.weather == Weather.STORMY else "#6c78c8"))
                under.setColorAt(1, QColor(39, 26, 89, 0))
                p.setBrush(under)
                p.drawEllipse(QRectF(x-w*.10, y-h*.16, w*.20, h*.32))
        p.setBrush(QColor("#171a43"))
        ground = QPainterPath()
        ground.moveTo(0, h)
        ground.lineTo(0, h * .81)
        ground.cubicTo(w*.2, h*.65, w*.34, h*.94, w*.53, h*.79)
        ground.cubicTo(w*.7, h*.65, w*.81, h*.87, w, h*.7)
        ground.lineTo(w, h)
        ground.closeSubpath()
        p.drawPath(ground)
        if self.weather in (Weather.STORMY, Weather.RAINY, Weather.WINDY):
            tower_x, tower_y = int(w*.90), int(h*.72)
            p.setPen(QPen(QColor("#201838"), 3))
            p.drawLine(tower_x, tower_y, tower_x-12, h)
            p.drawLine(tower_x, tower_y, tower_x+12, h)
            p.drawLine(tower_x-6, int(h*.87), tower_x+6, int(h*.87))
            p.setBrush(QColor("#ff76dd"))
            p.setPen(QPen(QColor(255, 115, 225, 100), 8))
            p.drawEllipse(QPoint(tower_x, tower_y), 2, 2)

    def _effects(self, p: QPainter, accent: QColor) -> None:
        w, h = self.width(), self.height()
        motion = 0 if self.settings.value("reduced_motion", False, type=bool) else self.phase
        if self.weather in (Weather.RAINY, Weather.STORMY):
            for i in range(45 if self.weather == Weather.STORMY else 25):
                x = (i * 67 + int(motion * 24)) % max(1, w)
                y = (i * 39 + int(motion * 70)) % max(1, h)
                p.setPen(QPen(QColor(159, 190, 255, 100 + i % 70), 1.3))
                p.drawLine(x, y, x - 7, y + 15)
            if self.weather == Weather.STORMY:
                alpha = 230 if int(motion * 2) % 17 == 2 else 105
                lightning = [QPoint(int(w*.65), int(h*.45)), QPoint(int(w*.61), int(h*.59)),
                             QPoint(int(w*.65), int(h*.59)), QPoint(int(w*.57), int(h*.84))]
                p.setPen(QPen(QColor(239, 110, 255, alpha//2), 10))
                p.drawPolyline(lightning)
                p.setPen(QPen(QColor(255, 219, 255, alpha), 2))
                p.drawPolyline(lightning)
        elif self.weather == Weather.WINDY:
            for i in range(8):
                y = int(h * (.24 + i*.08))
                x = int((i*71 + motion*30) % max(1, w))
                p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 130), 2))
                p.drawArc(QRect(x-80, y-10, 110, 32), 20*16, 135*16)
        elif self.weather == Weather.FOGGY:
            for i in range(5):
                y = int(h * (.27 + i*.15))
                fog = QColor("#d2d9f7")
                fog.setAlpha(18 + i*5)
                p.setPen(QPen(fog, 18))
                p.drawLine(int(-20 + math.sin(motion+i)*15), y, w+20, y)
        elif self.weather == Weather.OFFLINE:
            p.setPen(QPen(QColor("#fa8fae"), 4))
            p.drawLine(int(w*.70)-22, int(h*.36)-22, int(w*.70)+22, int(h*.36)+22)
            p.drawLine(int(w*.70)+22, int(h*.36)-22, int(w*.70)-22, int(h*.36)+22)


STYLE = """
QWidget { color: #eee9ff; font-family: 'Segoe UI'; font-size: 12px; }
QWidget#panelRoot { background: #111936; }
QWidget#panelPage { background: #111936; }
QFrame#panelHeader { background: #1b254d; border: 1px solid #5364a5; border-radius: 15px; }
QFrame#overviewSection { background: #22284f; border: 1px solid #625c99; border-radius: 15px; }
QFrame#overviewHero { background: #171e41; border: 1px solid #745ba9; border-radius: 16px; }
QFrame#overviewCard { background: #25294e; border: 1px solid #655a96; border-radius: 13px; }
QListWidget#panelNav { background: #19234b; border: 1px solid #5364a5; border-radius: 14px; padding: 8px; }
QFrame#shell { background: #1b1b3b; border: 1px solid #7665bf; border-radius: 22px; }
QFrame#card { background: #292849; border: 1px solid #554e82; border-radius: 13px; }
QPushButton { background: #35345e; border: 1px solid #665aa0; border-radius: 9px; padding: 6px 9px; }
QPushButton:hover { background: #514483; }
QListWidget { background: #1d2147; border: 1px solid #5b5792; border-radius: 12px; padding: 8px; }
QListWidget::item { padding: 10px; border-radius: 8px; }
QListWidget::item:selected { background: #6c47a6; }
QListWidget::item:focus { outline: none; }
QComboBox { background: #33335f; border: 1px solid #665aa0; padding: 5px; }
QScrollArea { background: transparent; border: none; }
QScrollArea QWidget#qt_scrollarea_viewport { background: transparent; }
"""


class MetricCard(QFrame):
    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        caption = QLabel(title)
        caption.setStyleSheet("color:#b9b0dc;font-size:11px")
        self.value = QLabel("—")
        self.value.setStyleSheet("color:#f9b0c7;font-size:19px;font-weight:700")
        layout.addWidget(caption)
        layout.addWidget(self.value)


class Sparkline(QWidget):
    def __init__(self, language: str = "es") -> None:
        super().__init__()
        self.language = normalize_language(language)
        self.points: tuple[CompactPoint, ...] = ()
        self.chart_metric = "latency"
        self.setMinimumHeight(78)

    def set_points(self, points: tuple[CompactPoint, ...]) -> None:
        self.points = points
        self.update()

    def set_metric(self, metric: str) -> None:
        if metric not in {"latency", "variation"}:
            raise ValueError("Unsupported compact metric")
        self.chart_metric = metric
        self.update()

    def paintEvent(self, _event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#27264c"))
        if not self.points:
            message = "No samples yet" if self.language == "en" else "Aún no hay muestras"
            p.setPen(QColor("#b9b0dc"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, message)
            p.end()
            return
        values = [value for point in self.points
                  if (value := point.value(self.chart_metric)) is not None]
        first, last = self.points[0].at, self.points[-1].at
        span = max(1.0, (last - first).total_seconds())
        left, width = 8, max(1, self.width() - 16)
        plot_top, plot_bottom = 15, max(16, self.height() - 23)

        def x(point: CompactPoint) -> int:
            return int(left + (point.at - first).total_seconds() / span * width)

        if values:
            low, high = min(values), max(values)
            margin = max(5.0, (high - low) * 0.15)
            low, high = max(0.0, low - margin), high + margin

            def y(value: float) -> int:
                return int(plot_bottom - (value - low) / max(1.0, high - low)
                           * (plot_bottom - plot_top))

            p.setPen(QPen(QColor("#ee79d1"), 2))
            for previous, current in visible_segments(self.points, self.chart_metric):
                p.drawLine(QPoint(x(previous), y(previous.value(self.chart_metric))),
                           QPoint(x(current), y(current.value(self.chart_metric))))
            p.setBrush(QColor("#ffc0ef"))
            for point in self.points:
                value = point.value(self.chart_metric)
                if value is not None:
                    p.drawEllipse(QPoint(x(point), y(value)), 2, 2)
            p.setPen(QColor("#d3c8f4"))
            p.drawText(8, 12, f"{max(values):.0f} ms")
        stamp_format = "%d/%m %H:%M" if (last - first).total_seconds() >= 86400 else "%H:%M"
        p.setPen(QColor("#b9b0dc"))
        p.drawText(left, self.height() - 4, first.astimezone().strftime(stamp_format))
        p.drawText(QRectF(left, self.height() - 19, width, 17),
                   Qt.AlignmentFlag.AlignRight, last.astimezone().strftime(stamp_format))
        p.end()


class MonitorThread(QThread):
    initial_history = Signal(object)
    measured = Signal(object, object, object)
    failed = Signal(str)

    def __init__(self, config: ProbeConfig, language: str = "es") -> None:
        super().__init__()
        self.config = config
        self.language = normalize_language(language)
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            with Monitor(self.config) as monitor:
                self.initial_history.emit(monitor.history.recent_rounds(30))
                while not self.stop_event.is_set():
                    try:
                        round_, result = monitor.measure()
                        self.measured.emit(round_, result, monitor.history.incidents(100))
                    except Exception as exc:  # noqa: BLE001 - report probe failures without killing UI
                        prefix = "Probe failed" if self.language == "en" else "No se pudo medir"
                        self.failed.emit(f"{prefix}: {exc}")
                    self.stop_event.wait(self.config.interval_seconds)
        except Exception as exc:  # noqa: BLE001 - show startup failures in the widget
            prefix = ("Could not start monitoring" if self.language == "en"
                      else "No se pudo iniciar el monitor")
            self.failed.emit(f"{prefix}: {exc}")

    def stop(self) -> None:
        self.stop_event.set()


class HistoryQueryThread(QThread):
    loaded = Signal(object, object)
    failed = Signal(str)

    def __init__(self, start: datetime, end: datetime, destination: str | None) -> None:
        super().__init__()
        self.start, self.end, self.destination = start, end, destination

    def run(self) -> None:
        try:
            with HistoryStore(default_data_dir() / "history.db") as store:
                self.loaded.emit(store.history_range(self.start, self.end, self.destination),
                                 store.incidents(100))
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.failed.emit(str(exc))


class WeatherWidget(QWidget):
    open_panel = Signal()
    hide_requested = Signal()

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
        self.language = normalize_language(settings.value("language", "es"))
        self.setWindowTitle("Network Weather")
        self.setWindowIcon(icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(440, 465)
        self._drag_origin: QPoint | None = None
        shell = QFrame(self)
        shell.setObjectName("shell")
        shell.setStyleSheet(STYLE)
        self.shell = shell
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.addWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        app_icon = QLabel()
        app_icon.setPixmap(icon().pixmap(30, 30))
        title = QLabel("Network Weather")
        title.setStyleSheet("font-size:16px;font-weight:600")
        self.pin_button = QPushButton("📌")
        self.pin_button.setToolTip(self.t("Fijar encima de otras ventanas"))
        self.pin_button.setFixedWidth(38)
        self.pin_button.clicked.connect(self.toggle_pin)
        panel_button = QPushButton("▣")
        panel_button.setToolTip(self.t("Abrir panel"))
        panel_button.setFixedWidth(38)
        panel_button.clicked.connect(self.open_panel.emit)
        hide_button = QPushButton("−")
        hide_button.setToolTip(self.t("Ocultar en la bandeja"))
        hide_button.setFixedWidth(38)
        hide_button.clicked.connect(self.hide_requested.emit)
        header.addWidget(app_icon)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.pin_button)
        header.addWidget(panel_button)
        header.addWidget(hide_button)
        layout.addLayout(header)
        self.scene = WeatherScene(settings)
        layout.addWidget(self.scene)
        self.weather_label = QLabel(weather_name(Weather.UNKNOWN, self.language))
        self.weather_label.setStyleSheet("font-size:27px;font-weight:700;color:#f5e9ff")
        self.description = QLabel(weather_description(Weather.UNKNOWN, self.language))
        self.description.setStyleSheet("color:#c7bfe1")
        self.monitoring = QLabel(self.t("●  Monitoreo activo"))
        self.monitoring.setStyleSheet("color:#6cf2bd;font-size:11px")
        layout.addWidget(self.weather_label)
        layout.addWidget(self.description)
        layout.addWidget(self.monitoring)
        metrics = QHBoxLayout()
        self.cards = {
            "latency": MetricCard(self.t("Latencia")),
            "jitter": MetricCard(self.t("Variación")),
            "loss": MetricCard(self.t("Fallos TCP")),
            "dns": MetricCard("DNS"),
        }
        for card in self.cards.values():
            metrics.addWidget(card)
        layout.addLayout(metrics)
        self.sparkline = Sparkline(self.language)
        history_row = QHBoxLayout()
        history_caption = QLabel(self.t("Historial TCP · muestras por ronda"))
        history_caption.setStyleSheet("color:#b9b0dc;font-size:10px")
        self.metric_select = QComboBox()
        self.metric_select.addItem(self.t("Latencia"), "latency")
        self.metric_select.addItem(self.t("Variación"), "variation")
        self.metric_select.setFixedWidth(112)
        saved_metric = settings.value("compact_metric", "latency")
        selected = self.metric_select.findData(saved_metric)
        self.metric_select.setCurrentIndex(max(0, selected))
        self.sparkline.set_metric(self.metric_select.currentData())
        self.metric_select.currentIndexChanged.connect(self._metric_changed)
        history_row.addWidget(history_caption)
        history_row.addStretch()
        history_row.addWidget(self.metric_select)
        layout.addLayout(history_row)
        layout.addWidget(self.sparkline)
        self._apply_pin()
        saved = settings.value("widget_position")
        screen = QApplication.primaryScreen().availableGeometry()
        requested = (saved if isinstance(saved, QPoint) else
                     QPoint(screen.right()-self.width()-25, screen.top()+25))
        self.move(visible_position(
            requested, self.size(),
            [item.availableGeometry() for item in QApplication.screens()], screen))

    def t(self, message: str) -> str:
        return translate(message, self.language)

    def _metric_changed(self, _index: int) -> None:
        metric = self.metric_select.currentData()
        self.sparkline.set_metric(metric)
        self.settings.setValue("compact_metric", metric)

    def update_history(self, points: tuple[CompactPoint, ...]) -> None:
        self.sparkline.set_points(points)
        variation = points[-1].variation_ms if points else None
        self.cards["jitter"].value.setText(
            f"{variation:.0f} ms" if variation is not None else "—")

    def _apply_pin(self) -> None:
        pinned = self.settings.value("pinned", False, type=bool)
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.pin_button.setStyleSheet("color:#e99bff" if pinned else "")

    def toggle_pin(self) -> None:
        self.settings.setValue("pinned", not self.settings.value("pinned", False, type=bool))
        position = self.pos()
        self._apply_pin()
        self.move(position)
        self.show()

    def ensure_visible(self) -> None:
        app = QApplication.instance()
        primary = app.primaryScreen().availableGeometry()
        self.move(visible_position(
            self.pos(), self.size(),
            [screen.availableGeometry() for screen in app.screens()], primary))

    def update_measurement(self, round_: MeasurementRound, result: Classification) -> None:
        self.scene.set_weather(result.weather)
        self.weather_label.setText(weather_name(result.weather, self.language))
        self.description.setText(weather_description(result.weather, self.language))
        self.monitoring.setText(self.t("●  Monitoreo activo · datos reales"))
        tcp = [p for p in round_.probes if p.kind == ProbeKind.TCP]
        dns = [p for p in round_.probes if p.kind == ProbeKind.DNS]
        times = [p.duration_ms for p in tcp if p.ok and p.duration_ms is not None]
        self.cards["latency"].value.setText(f"{sum(times)/len(times):.0f} ms" if times else "—")
        self.cards["loss"].value.setText(
            f"{100 * sum(not p.ok for p in tcp)/len(tcp):.0f}%" if tcp else "—"
        )
        self.cards["dns"].value.setText("OK" if dns and all(p.ok for p in dns)
                                        else self.t("Error") if dns else "—")

    def mousePressEvent(self, event: object) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 52:
            self._drag_origin = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: object) -> None:
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: object) -> None:
        if self._drag_origin is not None:
            self.settings.setValue("widget_position", self.pos())
            self._drag_origin = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event: object) -> None:
        self.hide_requested.emit()
        event.ignore()


class ExpandedPanel(QMainWindow):
    history_requested = Signal()

    def __init__(self, settings: QSettings, widget: WeatherWidget) -> None:
        super().__init__()
        self.settings = settings
        self.language = normalize_language(settings.value("language", "es"))
        self.widget_ref = widget
        self.setWindowTitle("Network Weather · " + self.t("Resumen"))
        self.setWindowIcon(icon())
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1060, max(1, available.width() - 40)),
                    min(780, max(1, available.height() - 40)))
        root = QWidget()
        root.setObjectName("panelRoot")
        root.setStyleSheet(STYLE)
        self.setCentralWidget(root)
        vertical = QVBoxLayout(root)
        vertical.setContentsMargins(14, 12, 14, 14)
        vertical.setSpacing(12)
        header = QFrame()
        header.setObjectName("panelHeader")
        header_row = QHBoxLayout(header)
        brand_icon = QLabel()
        brand_icon.setPixmap(icon().pixmap(38, 38))
        brand = QLabel("Network Weather")
        brand.setStyleSheet("font-size:19px;font-weight:700;color:#f5efff")
        self.panel_status = QLabel(self.t("Esperando las primeras mediciones…"))
        self.panel_status.setStyleSheet("color:#91eec7;font-size:11px")
        header_row.addWidget(brand_icon)
        header_row.addWidget(brand)
        header_row.addStretch()
        header_row.addWidget(self.panel_status)
        vertical.addWidget(header)
        horizontal = QHBoxLayout()
        horizontal.setSpacing(12)
        vertical.addLayout(horizontal, 1)
        self.nav = QListWidget()
        self.nav.setObjectName("panelNav")
        self.nav.addItems([self.t(item) for item in
                           ("Resumen", "Diagnóstico", "Historial", "Incidentes", "Configuración")])
        self.nav.setFixedWidth(175)
        horizontal.addWidget(self.nav)
        self.stack = QStackedWidget()
        horizontal.addWidget(self.stack)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.currentRowChanged.connect(self._navigation_changed)
        for page in (self._summary_page(), self._diagnostic_page(), self._history_page(),
                     self._incident_page(), self._settings_page()):
            self.stack.addWidget(page)
        self.nav.setCurrentRow(0)

    def t(self, message: str) -> str:
        return translate(message, self.language)

    def _page(self, heading: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("panelPage")
        layout = QVBoxLayout(page)
        title = QLabel(self.t(heading))
        title.setStyleSheet("font-size:24px;font-weight:700;color:#f5ddff")
        layout.addWidget(title)
        return page, layout

    def _summary_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("panelPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(10)
        hero = QFrame()
        hero.setObjectName("overviewHero")
        hero.setMinimumHeight(220)
        hero_stack = QStackedLayout(hero)
        hero_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        hero_stack.setContentsMargins(1, 1, 1, 1)
        self.overview_scene = WeatherScene(self.settings)
        hero_stack.addWidget(self.overview_scene)
        overlay = QWidget()
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        overlay_layout = QVBoxLayout(overlay)
        overlay_layout.setContentsMargins(22, 14, 22, 18)
        overlay_layout.addStretch()
        self.summary_label = QLabel(weather_name(Weather.UNKNOWN, self.language))
        self.summary_label.setStyleSheet(
            "font-size:34px;font-weight:750;color:#ffffff;background:transparent")
        self.summary_description = QLabel(weather_description(Weather.UNKNOWN, self.language))
        self.summary_description.setStyleSheet(
            "font-size:15px;color:#f2e9ff;background:transparent")
        self.confidence_label = QLabel(self.t("Confianza: —   Severidad: —"))
        self.confidence_label.setStyleSheet(
            "color:#c8f9e5;font-size:11px;background:transparent")
        overlay_layout.addWidget(self.summary_label)
        overlay_layout.addWidget(self.summary_description)
        overlay_layout.addWidget(self.confidence_label)
        hero_stack.addWidget(overlay)
        hero_stack.setCurrentWidget(overlay)
        layout.addWidget(hero)

        metrics = QHBoxLayout()
        metrics.setSpacing(8)
        self.overview_cards = {
            "latency": MetricCard(self.t("Latencia")),
            "variation": MetricCard(self.t("Variación")),
            "failures": MetricCard(self.t("Fallos TCP")),
            "dns": MetricCard("DNS"),
            "gateway": MetricCard(self.t("Puerta de enlace")),
            "external": MetricCard(self.t("Conectividad externa")),
        }
        for card in self.overview_cards.values():
            card.setObjectName("overviewCard")
            card.value.setStyleSheet("color:#e6d1ff;font-size:17px;font-weight:700")
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        chart_section = QFrame()
        chart_section.setObjectName("overviewSection")
        chart_layout = QVBoxLayout(chart_section)
        chart_layout.addWidget(QLabel(self.t("Historial de red · última hora")))
        self.overview_chart = HistoryChart(language=self.language)
        chart_layout.addWidget(self.overview_chart)
        layout.addWidget(chart_section)

        detail_row = QHBoxLayout()
        for title, name in (("Incidente activo", "incident_summary_label"),
                            ("Explicación técnica", "evidence_label")):
            section = QFrame()
            section.setObjectName("overviewSection")
            section_layout = QVBoxLayout(section)
            section_layout.addWidget(QLabel(self.t(title)))
            detail = QLabel(self.t("Sin datos observados todavía.") if name ==
                            "evidence_label" else self.t("Sin incidentes activos."))
            detail.setWordWrap(True)
            detail.setMinimumHeight(45)
            section_layout.addWidget(detail)
            setattr(self, name, detail)
            detail_row.addWidget(section, 1)
        layout.addLayout(detail_row)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _diagnostic_page(self) -> QWidget:
        page, layout = self._page("Diagnóstico técnico")
        self.diagnostic_window_label = QLabel(self.t("Esperando muestras comparables…"))
        self.diagnostic_window_label.setStyleSheet("color:#b9c4ed")
        layout.addWidget(self.diagnostic_window_label)
        self.diagnostic_table = QTableWidget(0, 8)
        self.diagnostic_table.setHorizontalHeaderLabels([
            self.t(item) for item in (
                "Destino", "Protocolo", "Intentos", "Éxitos", "Mediana",
                "P95", "Variación", "Fallos",
            )
        ])
        self.diagnostic_table.verticalHeader().hide()
        self.diagnostic_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diagnostic_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diagnostic_table.setAlternatingRowColors(True)
        self.diagnostic_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self.diagnostic_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.diagnostic_table.setMinimumHeight(260)
        self.diagnostic_table.setStyleSheet(
            "QTableWidget{background:#1c2449;alternate-background-color:#242d55;"
            "border:1px solid #5a639d;gridline-color:#3b4679;}"
            "QHeaderView::section{background:#303961;color:#f1e9ff;padding:6px;"
            "border:1px solid #5a639d;}"
        )
        layout.addWidget(self.diagnostic_table)
        note = QLabel(self.t(
            "P95: rango más cercano entre éxitos. Variación: diferencias entre tiempos consecutivos del mismo destino y protocolo; no es jitter unidireccional."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#b9c4ed;font-size:11px")
        layout.addWidget(note)
        context = QFrame()
        context.setObjectName("overviewSection")
        context_layout = QVBoxLayout(context)
        context_layout.addWidget(QLabel(self.t("Última ronda y contexto de red")))
        self.diagnostic_label = QLabel(self.t("Esperando pruebas DNS, TCP y HTTPS…"))
        self.diagnostic_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.diagnostic_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.diagnostic_label.setWordWrap(True)
        context_layout.addWidget(self.diagnostic_label)
        layout.addWidget(context)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _history_page(self) -> QWidget:
        page, layout = self._page("Historial observado")
        filters = QHBoxLayout()
        self.history_range = QComboBox()
        self.history_range.addItems([self.t(item) for item in
                                     ("Última hora", "24 horas", "7 días", "30 días", "Personalizado")])
        self.history_range.currentIndexChanged.connect(self._range_changed)
        self.history_start = QDateTimeEdit()
        self.history_end = QDateTimeEdit()
        for field in (self.history_start, self.history_end):
            field.setCalendarPopup(True)
            field.setDisplayFormat("yyyy-MM-dd HH:mm" if self.language == "en"
                                   else "dd/MM/yyyy HH:mm")
            field.hide()
        self.history_destination = QComboBox()
        self.history_destination.addItem(self.t("Todos los destinos"), None)
        self.history_destination.currentIndexChanged.connect(self.history_requested.emit)
        refresh = QPushButton(self.t("Actualizar"))
        refresh.clicked.connect(self.history_requested.emit)
        filters.addWidget(self.history_range)
        filters.addWidget(self.history_start)
        filters.addWidget(self.history_end)
        filters.addWidget(self.history_destination)
        filters.addWidget(refresh)
        layout.addLayout(filters)
        self.history_status = QLabel(self.t("Abre el historial para consultar los datos guardados."))
        layout.addWidget(self.history_status)
        self.history_chart = HistoryChart(language=self.language)
        layout.addWidget(self.history_chart)
        legend = QHBoxLayout()
        for weather in Weather:
            label = QLabel(f"● {weather_name(weather, self.language)}")
            label.setStyleSheet(f"color:{PALETTE[weather]}")
            legend.addWidget(label)
        legend.addStretch()
        layout.addLayout(legend)
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        return page

    def _navigation_changed(self, index: int) -> None:
        if index in (0, 2, 3):
            self.history_requested.emit()

    def _range_changed(self, _index: int) -> None:
        custom = self.history_range.currentIndex() == 4
        self.history_start.setVisible(custom)
        self.history_end.setVisible(custom)
        if custom:
            now = datetime.now().astimezone()
            self.history_start.setDateTime(now - timedelta(days=1))
            self.history_end.setDateTime(now)
        self.history_requested.emit()

    def selected_history_range(self) -> tuple[datetime, datetime, str | None]:
        now = datetime.now(UTC)
        durations = [timedelta(hours=1), timedelta(days=1), timedelta(days=7),
                     timedelta(days=30)]
        index = self.history_range.currentIndex()
        if index == 4:
            start = datetime.fromtimestamp(self.history_start.dateTime().toSecsSinceEpoch(), UTC)
            end = datetime.fromtimestamp(self.history_end.dateTime().toSecsSinceEpoch(), UTC)
        else:
            start, end = now - durations[index], now
        return start, end, self.history_destination.currentData()

    def show_history(self, series: object, incidents: list[dict]) -> None:
        self.history_chart.set_series(series)
        segments = weather_segments(series)
        observed_seconds = sum((end - start).total_seconds() for start, end, _ in segments)
        has_gaps = observed_seconds < (series.end - series.start).total_seconds() - 1
        sample_count = sum(b.sample_count for b in series.latency)
        if self.language == "en":
            status = f"{len(series.weather)} rounds · {sample_count} valid TCP samples"
        else:
            status = f"{len(series.weather)} rondas · {sample_count} muestras TCP válidas"
        status += self.t(" · gris: sin observación") if has_gaps else ""
        status += self.t(" · límite de rondas alcanzado") if series.truncated else ""
        self.history_status.setText(status)
        selected = self.history_destination.currentData()
        destinations = set(series.destinations)
        self.history_destination.blockSignals(True)
        self.history_destination.clear()
        self.history_destination.addItem(self.t("Todos los destinos"), None)
        for destination in sorted(destinations | ({selected} if selected else set())):
            self.history_destination.addItem(destination, destination)
        index = self.history_destination.findData(selected)
        self.history_destination.setCurrentIndex(max(0, index))
        self.history_destination.blockSignals(False)
        self.history_list.clear()
        for point in reversed(series.weather[-200:]):
            stamp = (point.at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                     if self.language == "en" else
                     point.at.astimezone().strftime("%d/%m %H:%M:%S"))
            self.history_list.addItem(f"{stamp} · {weather_name(point.weather, self.language)}")
        selected_id = None
        row = self.incident_list.currentRow()
        if 0 <= row < len(self._incidents):
            selected_id = self._incidents[row]["id"]
        self._incidents = incidents
        self.incident_list.clear()
        for incident in incidents:
            state = self.t("Activo") if incident["ended_at"] is None else self.t("Finalizado")
            started = datetime.fromisoformat(incident["started_at"]).astimezone()
            stamp = (started.strftime("%Y-%m-%d %H:%M") if self.language == "en"
                     else started.strftime("%d/%m/%Y %H:%M"))
            label = weather_name(Weather(incident["weather"]), self.language)
            severity = "severity" if self.language == "en" else "severidad"
            self.incident_list.addItem(
                f"{stamp} · {label} · {state} · "
                f"{severity} {incident['severity']:.0%}")
        selected_row = next((index for index, item in enumerate(incidents)
                             if item["id"] == selected_id), 0)
        if incidents:
            self.incident_list.setCurrentRow(selected_row)
        else:
            self.incident_detail.setPlainText(self.t("No hay incidentes registrados."))

    def show_overview(self, series: object, incidents: list[dict]) -> None:
        self.overview_chart.set_series(series)
        active = next((item for item in incidents if item["ended_at"] is None), None)
        if active is None:
            self.incident_summary_label.setText(self.t("Sin incidentes activos."))
            return
        phenomenon = weather_name(Weather(active["weather"]), self.language)
        severity = self.t("Severidad")
        evidence = active.get("evidence") or []
        detail = (evidence_name(evidence[-1]["code"], evidence[-1].get("detail", ""),
                                self.language) if evidence else "")
        self.incident_summary_label.setText(
            f"{phenomenon} · {severity}: {active['severity']:.0%}\n{detail}")

    def _incident_page(self) -> QWidget:
        page, layout = self._page("Incidentes")
        self._incidents: list[dict] = []
        self.incident_list = QListWidget()
        self.incident_list.currentRowChanged.connect(self._show_incident_detail)
        layout.addWidget(self.incident_list)
        self.incident_detail = QPlainTextEdit()
        self.incident_detail.setReadOnly(True)
        self.incident_detail.setMinimumHeight(210)
        self.incident_detail.setStyleSheet(
            "background:#1b2348;border:1px solid #5b598e;border-radius:10px;"
            "padding:10px;color:#f4edff"
        )
        self.incident_detail.setPlainText(
            self.t("Abre Incidentes para consultar los episodios guardados."))
        layout.addWidget(self.incident_detail)
        return page

    def _show_incident_detail(self, row: int) -> None:
        if 0 <= row < len(self._incidents):
            self.incident_detail.setPlainText(format_incident(
                self._incidents[row], language=self.language))

    def _settings_page(self) -> QWidget:
        page, layout = self._page("Configuración")
        self.weather_previews: dict[Weather, WeatherScene] = {}
        language_label = QLabel(self.t("Idioma"))
        self.language_input = QComboBox()
        self.language_input.addItem("Español", "es")
        self.language_input.addItem("English", "en")
        self.language_input.setCurrentIndex(self.language_input.findData(self.language))
        self.language_input.currentIndexChanged.connect(self._set_language)
        layout.addWidget(language_label)
        layout.addWidget(self.language_input)
        reduced = QCheckBox(self.t("Movimiento reducido"))
        reduced.setChecked(self.settings.value("reduced_motion", False, type=bool))
        reduced.toggled.connect(lambda checked: self.settings.setValue("reduced_motion", checked))
        effects = QCheckBox(self.t("Efectos meteorológicos"))
        effects.setChecked(self.settings.value("effects", True, type=bool))
        effects.toggled.connect(lambda checked: self.settings.setValue("effects", checked))
        layout.addWidget(reduced)
        layout.addWidget(effects)
        fit = QComboBox()
        fit.addItems(["cover", "contain", "center"])
        fit.setCurrentText(self.settings.value("image_fit", "cover"))
        fit.currentTextChanged.connect(lambda value: self.settings.setValue("image_fit", value))
        layout.addWidget(QLabel(self.t("Ajuste de imagen")))
        layout.addWidget(fit)
        layout.addWidget(QLabel(self.t("Mediciones · los cambios se aplican al reiniciar")))
        self.interval_input = QSpinBox()
        self.interval_input.setRange(5, 3600)
        self.interval_input.setSuffix(" s")
        self.interval_input.setValue(self.settings.value("interval", 30, type=int))
        self.retention_input = QSpinBox()
        self.retention_input.setRange(1, 3650)
        self.retention_input.setSuffix(self.t(" días"))
        self.retention_input.setValue(self.settings.value("retention_days", 30, type=int))
        self.destinations_input = QLineEdit(
            self.settings.value("destinations", "example.com, www.wikipedia.org")
        )
        self.destinations_input.setPlaceholderText("example.com, www.wikipedia.org")
        layout.addWidget(QLabel(self.t("Intervalo")))
        layout.addWidget(self.interval_input)
        layout.addWidget(QLabel(self.t("Retención del historial")))
        layout.addWidget(self.retention_input)
        layout.addWidget(QLabel(self.t("Destinos HTTPS (separados por comas)")))
        layout.addWidget(self.destinations_input)
        save_probes = QPushButton(self.t("Guardar mediciones"))
        save_probes.clicked.connect(self._save_probe_settings)
        layout.addWidget(save_probes)
        self.startup_checkbox = QCheckBox(self.t("Iniciar con Windows"))
        self.startup_status = QLabel("")
        self.startup_status.setWordWrap(True)
        self.startup_status.setStyleSheet("color:#b9c4ed;font-size:11px")
        self._refresh_startup_state()
        self.startup_checkbox.toggled.connect(self._set_startup)
        layout.addWidget(self.startup_checkbox)
        layout.addWidget(self.startup_status)
        layout.addWidget(QLabel(self.t("Apariencia → Climas")))
        grid = QGridLayout()
        for row, weather in enumerate(Weather):
            grid.addWidget(QLabel(weather_name(weather, self.language)), row, 0)
            preview = WeatherScene(self.settings)
            preview.timer.stop()
            preview.setFixedSize(72, 44)
            preview.set_weather(weather)
            self.weather_previews[weather] = preview
            grid.addWidget(preview, row, 1)
            choose = QPushButton(self.t("Seleccionar imagen…"))
            choose.clicked.connect(lambda _checked=False, state=weather: self._choose_image(state))
            reset = QPushButton(self.t("Original"))
            reset.clicked.connect(lambda _checked=False, state=weather: self._reset_image(state))
            grid.addWidget(choose, row, 2)
            grid.addWidget(reset, row, 3)
        layout.addLayout(grid)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _set_language(self, _index: int) -> None:
        chosen = self.language_input.currentData()
        if chosen == self.language:
            return
        self.settings.setValue("language", chosen)
        self.settings.sync()
        QMessageBox.information(self, "Network Weather",
                                self.t("Reinicia Network Weather para aplicar el idioma."))

    def _save_probe_settings(self) -> None:
        hosts = tuple(host.strip() for host in self.destinations_input.text().split(","))
        try:
            ProbeConfig(destinations=hosts, interval_seconds=self.interval_input.value(),
                        retention_days=self.retention_input.value())
        except ValueError as exc:
            QMessageBox.warning(self, self.t("Destinos no válidos"), str(exc))
            return
        self.settings.setValue("destinations", ", ".join(hosts))
        self.settings.setValue("interval", self.interval_input.value())
        self.settings.setValue("retention_days", self.retention_input.value())
        self.settings.sync()
        QMessageBox.information(self, self.t("Guardado"),
                                self.t("Las nuevas sondas se usarán al reiniciar Network Weather."))

    def _refresh_startup_state(self) -> None:
        if sys.platform != "win32":
            self.startup_checkbox.setEnabled(False)
            self.startup_status.setText(self.t("Esta opción requiere Windows."))
            return
        try:
            registered = read_startup_command()
        except OSError as exc:
            self.startup_checkbox.setEnabled(False)
            self.startup_status.setText(str(exc))
            return
        try:
            expected = startup_command(sys.executable, frozen=getattr(sys, "frozen", False))
        except ValueError:
            expected = None
        self.startup_checkbox.blockSignals(True)
        self.startup_checkbox.setChecked(registered is not None)
        self.startup_checkbox.blockSignals(False)
        self.startup_status.setText(
            self.t("La ruta actual es demasiado larga para el inicio de Windows.")
            if expected is None else
            self.t("La ruta registrada corresponde a otra instalación. Desactiva y activa para actualizarla.")
            if registered and registered != expected else "")

    def _set_startup(self, enabled: bool) -> None:
        try:
            command = (startup_command(sys.executable, frozen=getattr(sys, "frozen", False))
                       if enabled else None)
            set_startup_enabled(enabled, command)
            self._refresh_startup_state()
        except (OSError, ValueError) as exc:
            self._refresh_startup_state()
            QMessageBox.warning(self, self.t("No se pudo configurar"), str(exc))

    def _choose_image(self, weather: Weather) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, (f"Image for {weather_name(weather, self.language)}" if self.language == "en"
                   else f"Imagen para {weather_name(weather, self.language)}"), "",
            self.t("Imágenes (*.png *.jpg *.jpeg *.webp)")
        )
        if not file:
            return
        source = Path(file)
        reader = QImageReader(file)
        size = reader.size()
        if (source.stat().st_size > 10_000_000 or not reader.canRead() or
                size.width() < 64 or size.height() < 64 or
                size.width() > 4096 or size.height() > 4096):
            QMessageBox.warning(self, self.t("Imagen no válida"),
                                self.t("Usa PNG, JPG o WebP de 64–4096 px y hasta 10 MB."))
            return
        image = reader.read()
        if image.isNull():
            QMessageBox.warning(self, self.t("Imagen no válida"), reader.errorString())
            return
        preview = QMessageBox(self)
        title = "Preview" if self.language == "en" else "Vista previa"
        preview.setWindowTitle(f"{title} · {weather_name(weather, self.language)}")
        preview.setText(self.t("¿Aplicar esta imagen al clima seleccionado?"))
        preview.setIconPixmap(QPixmap.fromImage(image).scaled(
            300, 180, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        preview.setStandardButtons(QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel)
        if preview.exec() != QMessageBox.StandardButton.Apply:
            return
        folder = default_data_dir() / "images"
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f"{weather.value}.tmp.png"
        target = folder / f"{weather.value}.png"
        if not image.save(str(temporary), "PNG"):
            QMessageBox.warning(self, self.t("Error"),
                                self.t("No se pudo guardar la imagen importada."))
            return
        temporary.replace(target)
        self.settings.setValue(f"image/{weather.value}", str(target))
        self.widget_ref.scene.invalidate_image()
        self.weather_previews[weather].invalidate_image()

    def _reset_image(self, weather: Weather) -> None:
        self.settings.remove(f"image/{weather.value}")
        self.widget_ref.scene.invalidate_image()
        self.weather_previews[weather].invalidate_image()

    def update_measurement(self, round_: MeasurementRound, result: Classification) -> None:
        self.overview_scene.set_weather(result.weather)
        self.summary_label.setText(weather_name(result.weather, self.language))
        self.summary_description.setText(weather_description(result.weather, self.language))
        self.panel_status.setText(self.t("●  Monitoreo activo · datos reales"))
        confidence_label = "Confidence" if self.language == "en" else "Confianza"
        severity_label = "Severity" if self.language == "en" else "Severidad"
        self.confidence_label.setText(
            f"{confidence_label}: {result.confidence:.0%}   "
            f"{severity_label}: {result.severity:.0%}")
        self.evidence_label.setText("\n".join(
            evidence_name(e.code, e.detail, self.language) for e in result.evidence)
            or self.t("Sin evidencias concluyentes todavía."))
        tcp = [p for p in round_.probes if p.kind == ProbeKind.TCP]
        dns = [p for p in round_.probes if p.kind == ProbeKind.DNS]
        external = [p for p in round_.probes if p.kind in (ProbeKind.TCP, ProbeKind.HTTPS)]
        gateway = [p for p in round_.probes if p.kind == ProbeKind.ICMP]
        valid_tcp = [p.duration_ms for p in tcp if p.ok and p.duration_ms is not None]
        self.overview_cards["latency"].value.setText(
            f"{sum(valid_tcp)/len(valid_tcp):.0f} ms" if valid_tcp else "—")
        self.overview_cards["failures"].value.setText(
            f"{sum(not p.ok for p in tcp)/len(tcp):.0%}" if tcp else "—")
        self.overview_cards["dns"].value.setText(
            self.t("Correcto") if dns and all(p.ok for p in dns)
            else self.t("Con fallos") if dns else "—")
        self.overview_cards["gateway"].value.setText(
            self.t("Responde") if any(p.ok for p in gateway)
            else self.t("Sin respuesta") if gateway else "—")
        self.overview_cards["external"].value.setText(
            self.t("Confirmada") if any(p.ok for p in external)
            else self.t("Sin confirmar") if external else "—")
        adapter_label = "Route adapter" if self.language == "en" else "Adaptador de ruta"
        gateway_label = "IPv4 gateway" if self.language == "en" else "Puerta de enlace IPv4"
        lines = [
            f"{adapter_label}: {round_.route_adapter or self.t('No identificado')}",
            f"{gateway_label}: {round_.gateway_address or self.t('No identificada')}",
            "",
        ]
        for wifi in round_.wifi:
            heading = ("Connected Wi-Fi interface (route not confirmed)" if self.language == "en"
                       else "Interfaz Wi-Fi conectada (ruta no confirmada)")
            parts = [f"{heading}: {wifi.description}"]
            if wifi.signal_quality_percent is not None:
                label = "Signal quality" if self.language == "en" else "Calidad de señal"
                parts.append(f"{label}: {wifi.signal_quality_percent}%")
            if wifi.rssi_dbm is not None:
                parts.append(f"RSSI: {wifi.rssi_dbm} dBm")
            if wifi.channel is not None:
                label = "Channel" if self.language == "en" else "Canal"
                parts.append(f"{label}: {wifi.channel}")
            lines.extend(parts)
            lines.append("")
        for probe in round_.probes:
            duration = (f"{probe.duration_ms:.1f} ms" if probe.duration_ms is not None
                        else self.t("sin latencia válida"))
            status = probe_status_name(probe.status, self.language)
            lines.append(f"{probe.destination} · {probe.kind.value.upper()} · {status} · {duration}")
            if probe.detail:
                lines.append(f"  {probe.detail}")
        self.diagnostic_label.setText("\n".join(lines))

    def update_variation(self, points: tuple[CompactPoint, ...]) -> None:
        value = points[-1].variation_ms if points else None
        self.overview_cards["variation"].value.setText(
            f"{value:.0f} ms" if value is not None else "—")

    def update_diagnostics(self, summary: DiagnosticSummary) -> None:
        if self.language == "en":
            caption = f"{summary.rounds} comparable recent rounds"
        else:
            caption = f"{summary.rounds} rondas recientes comparables"
        self.diagnostic_window_label.setText(caption)
        self.diagnostic_table.setRowCount(len(summary.rows))
        for row_index, row in enumerate(summary.rows):
            def ms(value: float | None) -> str:
                return f"{value:.1f} ms" if value is not None else "—"

            values = (
                row.destination, row.kind.value.upper(), str(row.attempted),
                str(row.successful), ms(row.median_ms), ms(row.p95_ms),
                f"{ms(row.jitter_ms)} ({row.variation_pairs})",
                f"{row.failure_percent:.0f}%" if row.failure_percent is not None else "—",
            )
            for column, value in enumerate(values):
                self.diagnostic_table.setItem(row_index, column, QTableWidgetItem(value))


class DesktopController(QObject):
    def __init__(self, app: QApplication, demo: bool = False) -> None:
        super().__init__(app)
        self.app = app
        self.demo = demo
        settings_path = default_data_dir() / "settings.ini"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.language = normalize_language(self.settings.value("language", "es"))
        self.widget = WeatherWidget(self.settings)
        self.panel = ExpandedPanel(self.settings, self.widget)
        self.widget.open_panel.connect(self.show_panel)
        self.widget.hide_requested.connect(self.widget.hide)
        self.panel.history_requested.connect(self._request_history)
        self.history_worker: HistoryQueryThread | None = None
        self.history_pending = False
        self.worker: MonitorThread | None = None
        self.recent_rounds: list[MeasurementRound] = []
        self.demo_index = 0

        self.tray = QSystemTrayIcon(icon(), app)
        self.tray.setToolTip(translate("Network Weather · iniciando", self.language))
        menu = QMenu()
        menu.addAction(translate("Mostrar widget", self.language), self.show_widget)
        menu.addAction(translate("Abrir panel", self.language), self.show_panel)
        menu.addSeparator()
        menu.addAction(translate("Salir", self.language), self.exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.widget.show()
        self.widget.ensure_visible()
        if demo:
            self.widget.monitoring.setText(translate(
                "●  MODO DEMOSTRACIÓN · sin mediciones reales", self.language))
            self.demo_timer = QTimer(app)
            self.demo_timer.timeout.connect(self._demo_next)
            self._demo_next()
            self.demo_timer.start(5000)
        else:
            configured = tuple(host.strip() for host in self.settings.value(
                "destinations", "example.com, www.wikipedia.org").split(","))
            try:
                config = ProbeConfig(
                    destinations=configured,
                    interval_seconds=self.settings.value("interval", 30, type=int),
                    retention_days=self.settings.value("retention_days", 30, type=int),
                )
            except ValueError:
                config = ProbeConfig()
            self.worker = MonitorThread(config, self.language)
            self.worker.initial_history.connect(self._history_seed)
            self.worker.measured.connect(self._measured)
            self.worker.failed.connect(self._failed)
            self.worker.start()
            self._request_history()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_widget()

    def show_widget(self) -> None:
        self.widget.show()
        self.widget.ensure_visible()
        self.widget.raise_()
        self.widget.activateWindow()

    def show_panel(self) -> None:
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _measured(self, round_: MeasurementRound, result: Classification,
                  incidents: list[dict]) -> None:
        self.widget.update_measurement(round_, result)
        self.recent_rounds.append(round_)
        self.recent_rounds = self.recent_rounds[-30:]
        points = compact_points(self.recent_rounds)
        self.widget.update_history(points)
        self.panel.update_variation(points)
        interval = self.worker.config.interval_seconds if self.worker else 30
        self.panel.update_diagnostics(recent_diagnostics(self.recent_rounds, interval))
        self.panel.update_measurement(round_, result)
        self.tray.setToolTip(f"Network Weather · {weather_name(result.weather, self.language)}")
        if self.panel.nav.currentRow() in (0, 2, 3):
            self._request_history()

    def _history_seed(self, rounds: list[MeasurementRound]) -> None:
        self.recent_rounds = rounds[-30:]
        # Prior rounds belong in the chart, but compact status cards need a fresh round.
        self.widget.sparkline.set_points(compact_points(self.recent_rounds))

    def _request_history(self) -> None:
        if self.demo:
            return
        if self.history_worker is not None:
            self.history_pending = True
            return
        overview = self.panel.nav.currentRow() == 0
        if overview:
            end = datetime.now(UTC)
            start, destination = end - timedelta(hours=1), None
        else:
            start, end, destination = self.panel.selected_history_range()
        if start >= end:
            self.panel.history_status.setText(translate(
                "El inicio debe ser anterior al fin.", self.language))
            return
        self.panel.history_status.setText(translate("Consultando historial…", self.language))
        self.history_worker = HistoryQueryThread(start, end, destination)
        self.history_worker.loaded.connect(
            self.panel.show_overview if overview else self.panel.show_history)
        self.history_worker.failed.connect(self.panel.history_status.setText)
        self.history_worker.finished.connect(self._history_finished)
        self.history_worker.start()

    def _history_finished(self) -> None:
        self.history_worker = None
        if self.history_pending:
            self.history_pending = False
            self._request_history()

    def _failed(self, message: str) -> None:
        self.widget.monitoring.setText(message)
        self.tray.setToolTip(translate("Network Weather · error de medición", self.language))
        self.panel.panel_status.setText(translate(
            "Network Weather · error de medición", self.language))

    def _demo_next(self) -> None:
        weather = list(Weather)[self.demo_index % len(Weather)]
        self.demo_index += 1
        self.widget.scene.set_weather(weather)
        self.panel.overview_scene.set_weather(weather)
        self.widget.weather_label.setText(weather_name(weather, self.language))
        self.widget.description.setText(weather_description(weather, self.language))
        heading = "DEMO MODE" if self.language == "en" else "MODO DEMOSTRACIÓN"
        self.panel.summary_label.setText(
            f"{heading} · {weather_name(weather, self.language)}")
        self.panel.summary_description.setText(weather_description(weather, self.language))
        self.panel.panel_status.setText(translate(
            "●  MODO DEMOSTRACIÓN · sin mediciones reales", self.language))
        self.panel.evidence_label.setText(translate(
            "Escena visual sintética. No hay pruebas de red ni historial.", self.language))
        demo_label = "demo" if self.language == "en" else "demostración"
        self.tray.setToolTip(
            f"Network Weather · {demo_label}: {weather_name(weather, self.language)}")
        for card in self.widget.cards.values():
            card.value.setText("demo")
        for card in self.panel.overview_cards.values():
            card.value.setText("demo")

    def exit(self) -> None:
        if self.history_worker and not self.history_worker.wait(30000):
            QMessageBox.warning(self.widget, translate("Cierre pendiente", self.language),
                                translate("La consulta del historial aún no termina.", self.language))
            return
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(30000):
                QMessageBox.warning(self.widget, translate("Cierre pendiente", self.language),
                                    translate("Una prueba de red aún no termina. Intenta salir de nuevo.",
                                              self.language))
                return
        self.settings.sync()
        self.tray.hide()
        self.widget.hide()
        self.panel.close()
        self.app.quit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="network-weather-desktop")
    parser.add_argument("--demo", action="store_true", help="Visual-only demo, no network probes")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Network Weather")
    app.setQuitOnLastWindowClosed(False)
    instance = QLocalServer(app)
    server_name = "NetworkWeather.Desktop"
    if not instance.listen(server_name):
        other = QLocalSocket(app)
        other.connectToServer(server_name)
        if other.waitForConnected(500):
            other.disconnectFromServer()
            return 0
        QLocalServer.removeServer(server_name)
        if not instance.listen(server_name):
            settings_path = default_data_dir() / "settings.ini"
            language = normalize_language(QSettings(str(settings_path),
                                                    QSettings.Format.IniFormat).value("language", "es"))
            QMessageBox.critical(None, "Network Weather", translate(
                "No se pudo crear la instancia única.", language))
            return 1
    controller = DesktopController(app, demo=args.demo)
    instance.newConnection.connect(lambda: _restore_existing(instance, controller))
    # Keep the controller and its QThread alive for the duration of the event loop.
    app.controller = controller
    app.instance_server = instance
    return app.exec()


def _restore_existing(server: QLocalServer, controller: DesktopController) -> None:
    connection = server.nextPendingConnection()
    if connection:
        connection.disconnectFromServer()
        connection.deleteLater()
    controller.show_widget()


if __name__ == "__main__":
    raise SystemExit(main())
