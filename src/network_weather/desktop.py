"""Windows desktop widget and expanded view. All network work runs in MonitorThread."""

from __future__ import annotations

import argparse
import math
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, QSettings, QSize, Qt, QThread, QTimer, Signal
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
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from network_weather.config import ProbeConfig, default_data_dir
from network_weather.history import HistoryStore
from network_weather.metrics import summarize
from network_weather.models import MeasurementRound, ProbeKind
from network_weather.monitor import Monitor
from network_weather.weather import Classification, Weather

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
NAMES = {
    Weather.SUNNY: "Soleado", Weather.CLOUDY: "Nublado",
    Weather.WINDY: "Ventoso", Weather.RAINY: "Lluvioso",
    Weather.FOGGY: "Neblina", Weather.STORMY: "Tormenta",
    Weather.OFFLINE: "Sin conexión", Weather.UNKNOWN: "Desconocido",
}
DESCRIPTIONS = {
    Weather.SUNNY: "Conexión estable observada",
    Weather.CLOUDY: "Latencia elevada sostenida",
    Weather.WINDY: "Variación de latencia elevada",
    Weather.RAINY: "Fallos de respuesta intermitentes",
    Weather.FOGGY: "Problemas de resolución DNS",
    Weather.STORMY: "Degradación combinada",
    Weather.OFFLINE: "Sin respuesta de varios destinos",
    Weather.UNKNOWN: "Esperando evidencia suficiente",
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
QFrame#shell { background: #1b1b3b; border: 1px solid #7665bf; border-radius: 22px; }
QFrame#card { background: #292849; border: 1px solid #554e82; border-radius: 13px; }
QPushButton { background: #35345e; border: 1px solid #665aa0; border-radius: 9px; padding: 6px 9px; }
QPushButton:hover { background: #514483; }
QListWidget { background: #1d2147; border: 1px solid #5b5792; border-radius: 12px; padding: 8px; }
QListWidget::item { padding: 10px; border-radius: 8px; }
QListWidget::item:selected { background: #6c47a6; }
QComboBox { background: #33335f; border: 1px solid #665aa0; padding: 5px; }
QScrollArea { background: transparent; border: none; }
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
    def __init__(self) -> None:
        super().__init__()
        self.samples: list[float | None] = []
        self.setMinimumHeight(60)

    def paintEvent(self, _event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor("#27264c"))
        points = [(i, value) for i, value in enumerate(self.samples) if value is not None]
        if len(points) >= 2:
            values = [value for _, value in points]
            low, high = min(values), max(values)
            scale = max(10, high - low)
            p.setPen(QPen(QColor("#ee79d1"), 2))
            previous = None
            for index, value in points:
                x = 8 + index * (self.width()-16) / max(1, len(self.samples)-1)
                y = self.height()-8 - (value-low) / scale * (self.height()-20)
                point = QPoint(int(x), int(y))
                if previous and index == previous[0] + 1:
                    p.drawLine(previous[1], point)
                previous = (index, point)
        p.end()


class MonitorThread(QThread):
    measured = Signal(object, object)
    failed = Signal(str)

    def __init__(self, config: ProbeConfig) -> None:
        super().__init__()
        self.config = config
        self.stop_event = threading.Event()

    def run(self) -> None:
        try:
            with Monitor(self.config) as monitor:
                while not self.stop_event.is_set():
                    try:
                        round_, result = monitor.measure()
                        self.measured.emit(round_, result)
                    except Exception as exc:  # noqa: BLE001 - report probe failures without killing UI
                        self.failed.emit(f"No se pudo medir: {exc}")
                    self.stop_event.wait(self.config.interval_seconds)
        except Exception as exc:  # noqa: BLE001 - show startup failures in the widget
            self.failed.emit(f"No se pudo iniciar el monitor: {exc}")

    def stop(self) -> None:
        self.stop_event.set()


class WeatherWidget(QWidget):
    open_panel = Signal()
    hide_requested = Signal()

    def __init__(self, settings: QSettings) -> None:
        super().__init__()
        self.settings = settings
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
        self.pin_button.setToolTip("Fijar encima de otras ventanas")
        self.pin_button.setFixedWidth(38)
        self.pin_button.clicked.connect(self.toggle_pin)
        panel_button = QPushButton("▣")
        panel_button.setToolTip("Abrir panel")
        panel_button.setFixedWidth(38)
        panel_button.clicked.connect(self.open_panel.emit)
        hide_button = QPushButton("−")
        hide_button.setToolTip("Ocultar en la bandeja")
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
        self.weather_label = QLabel("Desconocido")
        self.weather_label.setStyleSheet("font-size:27px;font-weight:700;color:#f5e9ff")
        self.description = QLabel("Esperando evidencia suficiente")
        self.description.setStyleSheet("color:#c7bfe1")
        self.monitoring = QLabel("●  Monitoreo activo")
        self.monitoring.setStyleSheet("color:#6cf2bd;font-size:11px")
        layout.addWidget(self.weather_label)
        layout.addWidget(self.description)
        layout.addWidget(self.monitoring)
        metrics = QHBoxLayout()
        self.cards = {
            "latency": MetricCard("Latencia"),
            "jitter": MetricCard("Variación"),
            "loss": MetricCard("Fallos TCP"),
            "dns": MetricCard("DNS"),
        }
        for card in self.cards.values():
            metrics.addWidget(card)
        layout.addLayout(metrics)
        self.sparkline = Sparkline()
        history_caption = QLabel("Historial TCP · una muestra por ronda")
        history_caption.setStyleSheet("color:#b9b0dc;font-size:10px")
        layout.addWidget(history_caption)
        layout.addWidget(self.sparkline)
        self._apply_pin()
        saved = settings.value("widget_position")
        if isinstance(saved, QPoint):
            self.move(saved)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.right()-self.width()-25, screen.top()+25)

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

    def update_measurement(self, round_: MeasurementRound, result: Classification) -> None:
        self.scene.set_weather(result.weather)
        self.weather_label.setText(NAMES[result.weather])
        self.description.setText(DESCRIPTIONS[result.weather])
        self.monitoring.setText("●  Monitoreo activo · datos reales")
        tcp = [p for p in round_.probes if p.kind == ProbeKind.TCP]
        dns = [p for p in round_.probes if p.kind == ProbeKind.DNS]
        times = [p.duration_ms for p in tcp if p.ok and p.duration_ms is not None]
        self.cards["latency"].value.setText(f"{sum(times)/len(times):.0f} ms" if times else "—")
        self.cards["loss"].value.setText(
            f"{100 * sum(not p.ok for p in tcp)/len(tcp):.0f}%" if tcp else "—"
        )
        self.cards["dns"].value.setText("OK" if dns and all(p.ok for p in dns) else "Error")
        # The graph receives one observed TCP value per round. No interpolated points.
        self.sparkline.samples.append(sum(times)/len(times) if times else None)
        self.sparkline.samples = self.sparkline.samples[-30:]
        self.sparkline.update()
        self.cards["jitter"].value.setText("—")

    def set_jitter(self, value: float | None) -> None:
        self.cards["jitter"].value.setText(f"{value:.0f} ms" if value is not None else "—")

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
    def __init__(self, settings: QSettings, widget: WeatherWidget) -> None:
        super().__init__()
        self.settings = settings
        self.widget_ref = widget
        self.setWindowTitle("Network Weather · Panel")
        self.setWindowIcon(icon())
        self.resize(1020, 650)
        root = QWidget()
        root.setStyleSheet(STYLE)
        self.setCentralWidget(root)
        horizontal = QHBoxLayout(root)
        horizontal.setContentsMargins(15, 15, 15, 15)
        self.nav = QListWidget()
        self.nav.addItems(["Resumen", "Diagnóstico", "Historial", "Incidentes", "Configuración"])
        self.nav.setFixedWidth(160)
        horizontal.addWidget(self.nav)
        self.stack = QStackedWidget()
        horizontal.addWidget(self.stack)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        for page in (self._summary_page(), self._diagnostic_page(), self._history_page(),
                     self._incident_page(), self._settings_page()):
            self.stack.addWidget(page)
        self.nav.setCurrentRow(0)

    def _page(self, heading: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel(heading)
        title.setStyleSheet("font-size:24px;font-weight:700;color:#f5ddff")
        layout.addWidget(title)
        return page, layout

    def _summary_page(self) -> QWidget:
        page, layout = self._page("Resumen de la conexión")
        self.summary_label = QLabel("Esperando las primeras mediciones…")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size:19px")
        layout.addWidget(self.summary_label)
        self.confidence_label = QLabel("Confianza: —   Severidad: —")
        layout.addWidget(self.confidence_label)
        self.evidence_label = QLabel("Las evidencias aparecerán tras tres rondas.")
        self.evidence_label.setWordWrap(True)
        layout.addWidget(self.evidence_label)
        layout.addStretch()
        return page

    def _diagnostic_page(self) -> QWidget:
        page, layout = self._page("Diagnóstico técnico")
        self.diagnostic_label = QLabel("Esperando pruebas DNS, TCP y HTTPS…")
        self.diagnostic_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.diagnostic_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.diagnostic_label.setWordWrap(True)
        layout.addWidget(self.diagnostic_label)
        layout.addStretch()
        return page

    def _history_page(self) -> QWidget:
        page, layout = self._page("Historial observado")
        self.history_list = QListWidget()
        layout.addWidget(self.history_list)
        return page

    def _incident_page(self) -> QWidget:
        page, layout = self._page("Incidentes")
        self.incident_list = QListWidget()
        layout.addWidget(self.incident_list)
        return page

    def _settings_page(self) -> QWidget:
        page, layout = self._page("Configuración")
        self.weather_previews: dict[Weather, WeatherScene] = {}
        reduced = QCheckBox("Movimiento reducido")
        reduced.setChecked(self.settings.value("reduced_motion", False, type=bool))
        reduced.toggled.connect(lambda checked: self.settings.setValue("reduced_motion", checked))
        effects = QCheckBox("Efectos meteorológicos")
        effects.setChecked(self.settings.value("effects", True, type=bool))
        effects.toggled.connect(lambda checked: self.settings.setValue("effects", checked))
        layout.addWidget(reduced)
        layout.addWidget(effects)
        fit = QComboBox()
        fit.addItems(["cover", "contain", "center"])
        fit.setCurrentText(self.settings.value("image_fit", "cover"))
        fit.currentTextChanged.connect(lambda value: self.settings.setValue("image_fit", value))
        layout.addWidget(QLabel("Ajuste de imagen"))
        layout.addWidget(fit)
        layout.addWidget(QLabel("Mediciones · los cambios se aplican al reiniciar"))
        self.interval_input = QSpinBox()
        self.interval_input.setRange(5, 3600)
        self.interval_input.setSuffix(" s")
        self.interval_input.setValue(self.settings.value("interval", 30, type=int))
        self.retention_input = QSpinBox()
        self.retention_input.setRange(1, 3650)
        self.retention_input.setSuffix(" días")
        self.retention_input.setValue(self.settings.value("retention_days", 30, type=int))
        self.destinations_input = QLineEdit(
            self.settings.value("destinations", "example.com, www.wikipedia.org")
        )
        self.destinations_input.setPlaceholderText("example.com, www.wikipedia.org")
        layout.addWidget(QLabel("Intervalo"))
        layout.addWidget(self.interval_input)
        layout.addWidget(QLabel("Retención del historial"))
        layout.addWidget(self.retention_input)
        layout.addWidget(QLabel("Destinos HTTPS (separados por comas)"))
        layout.addWidget(self.destinations_input)
        save_probes = QPushButton("Guardar mediciones")
        save_probes.clicked.connect(self._save_probe_settings)
        layout.addWidget(save_probes)
        startup = QCheckBox("Iniciar con Windows")
        startup.setChecked(self.settings.value("startup", False, type=bool))
        startup.toggled.connect(self._set_startup)
        layout.addWidget(startup)
        layout.addWidget(QLabel("Apariencia → Climas"))
        grid = QGridLayout()
        for row, weather in enumerate(Weather):
            grid.addWidget(QLabel(NAMES[weather]), row, 0)
            preview = WeatherScene(self.settings)
            preview.timer.stop()
            preview.setFixedSize(72, 44)
            preview.set_weather(weather)
            self.weather_previews[weather] = preview
            grid.addWidget(preview, row, 1)
            choose = QPushButton("Seleccionar imagen…")
            choose.clicked.connect(lambda _checked=False, state=weather: self._choose_image(state))
            reset = QPushButton("Original")
            reset.clicked.connect(lambda _checked=False, state=weather: self._reset_image(state))
            grid.addWidget(choose, row, 2)
            grid.addWidget(reset, row, 3)
        layout.addLayout(grid)
        layout.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _save_probe_settings(self) -> None:
        hosts = tuple(host.strip() for host in self.destinations_input.text().split(","))
        try:
            ProbeConfig(destinations=hosts, interval_seconds=self.interval_input.value(),
                        retention_days=self.retention_input.value())
        except ValueError as exc:
            QMessageBox.warning(self, "Destinos no válidos", str(exc))
            return
        self.settings.setValue("destinations", ", ".join(hosts))
        self.settings.setValue("interval", self.interval_input.value())
        self.settings.setValue("retention_days", self.retention_input.value())
        self.settings.sync()
        QMessageBox.information(self, "Guardado", "Las nuevas sondas se usarán al reiniciar Network Weather.")

    def _set_startup(self, enabled: bool) -> None:
        if sys.platform != "win32":
            QMessageBox.warning(self, "No disponible", "Esta opción requiere Windows.")
            return
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
                if enabled:
                    command = f'"{sys.executable}"'
                    if not getattr(sys, "frozen", False):
                        command += " -m network_weather.desktop"
                    winreg.SetValueEx(key, "NetworkWeather", 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, "NetworkWeather")
                    except FileNotFoundError:
                        pass
            self.settings.setValue("startup", enabled)
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo configurar", str(exc))

    def _choose_image(self, weather: Weather) -> None:
        file, _ = QFileDialog.getOpenFileName(
            self, f"Imagen para {NAMES[weather]}", "", "Imágenes (*.png *.jpg *.jpeg *.webp)"
        )
        if not file:
            return
        source = Path(file)
        reader = QImageReader(file)
        size = reader.size()
        if (source.stat().st_size > 10_000_000 or not reader.canRead() or
                size.width() < 64 or size.height() < 64 or
                size.width() > 4096 or size.height() > 4096):
            QMessageBox.warning(self, "Imagen no válida", "Usa PNG, JPG o WebP de 64–4096 px y hasta 10 MB.")
            return
        image = reader.read()
        if image.isNull():
            QMessageBox.warning(self, "Imagen no válida", reader.errorString())
            return
        preview = QMessageBox(self)
        preview.setWindowTitle(f"Vista previa · {NAMES[weather]}")
        preview.setText("¿Aplicar esta imagen al clima seleccionado?")
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
            QMessageBox.warning(self, "Error", "No se pudo guardar la imagen importada.")
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
        self.summary_label.setText(f"{NAMES[result.weather]} · {DESCRIPTIONS[result.weather]}")
        self.confidence_label.setText(
            f"Confianza: {result.confidence:.0%}   Severidad: {result.severity:.0%}"
        )
        self.evidence_label.setText("\n".join(e.detail for e in result.evidence))
        lines = [f"Adaptador de ruta: {round_.route_adapter or 'No identificado'}", ""]
        for probe in round_.probes:
            duration = f"{probe.duration_ms:.1f} ms" if probe.duration_ms is not None else "sin latencia válida"
            lines.append(f"{probe.destination} · {probe.kind.value.upper()} · {probe.status.value} · {duration}")
            if probe.detail:
                lines.append(f"  {probe.detail}")
        self.diagnostic_label.setText("\n".join(lines))
        self.history_list.insertItem(0, f"{round_.started_at.astimezone():%d/%m %H:%M:%S}  ·  {NAMES[result.weather]}")
        while self.history_list.count() > 200:
            self.history_list.takeItem(self.history_list.count()-1)


class DesktopController:
    def __init__(self, app: QApplication, demo: bool = False) -> None:
        self.app = app
        self.demo = demo
        settings_path = default_data_dir() / "settings.ini"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
        self.widget = WeatherWidget(self.settings)
        self.panel = ExpandedPanel(self.settings, self.widget)
        self.widget.open_panel.connect(self.show_panel)
        self.widget.hide_requested.connect(self.widget.hide)
        if not demo:
            try:
                with HistoryStore(default_data_dir() / "history.db") as history:
                    for at, weather in history.recent_weather(200):
                        self.panel.history_list.addItem(f"{at} · {NAMES[weather]}")
                    for incident in history.incidents(100):
                        state = "Activo" if incident["ended_at"] is None else "Finalizado"
                        self.panel.incident_list.addItem(
                            f"{incident['started_at']} · {NAMES[Weather(incident['weather'])]} · {state}"
                        )
            except (OSError, ValueError):
                pass
        self.worker: MonitorThread | None = None
        self.recent_tcp = []
        self.demo_index = 0

        self.tray = QSystemTrayIcon(icon(), app)
        self.tray.setToolTip("Network Weather · iniciando")
        menu = QMenu()
        menu.addAction("Mostrar widget", self.show_widget)
        menu.addAction("Abrir panel", self.show_panel)
        menu.addSeparator()
        menu.addAction("Salir", self.exit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self.widget.show()
        if demo:
            self.widget.monitoring.setText("●  MODO DEMOSTRACIÓN · sin mediciones reales")
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
            self.worker = MonitorThread(config)
            self.worker.measured.connect(self._measured)
            self.worker.failed.connect(self._failed)
            self.worker.start()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_widget()

    def show_widget(self) -> None:
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def show_panel(self) -> None:
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    def _measured(self, round_: MeasurementRound, result: Classification) -> None:
        self.widget.update_measurement(round_, result)
        self.panel.update_measurement(round_, result)
        self.tray.setToolTip(f"Network Weather · {NAMES[result.weather]}")
        self.recent_tcp.extend(p for p in round_.probes if p.kind == ProbeKind.TCP)
        self.recent_tcp = self.recent_tcp[-60:]
        if self.recent_tcp:
            destination = self.recent_tcp[-1].destination
            summary = summarize(self.recent_tcp, destination, ProbeKind.TCP)
            self.widget.set_jitter(summary.jitter_ms)
        try:
            with HistoryStore(default_data_dir() / "history.db") as store:
                self.panel.incident_list.clear()
                for incident in store.incidents(100):
                    state = "Activo" if incident["ended_at"] is None else "Finalizado"
                    self.panel.incident_list.addItem(
                        f"{incident['started_at']} · {NAMES[Weather(incident['weather'])]} · "
                        f"{state} · severidad {incident['severity']:.0%}"
                    )
        except (OSError, ValueError):
            pass

    def _failed(self, message: str) -> None:
        self.widget.monitoring.setText(message)
        self.tray.setToolTip("Network Weather · error de medición")

    def _demo_next(self) -> None:
        weather = list(Weather)[self.demo_index % len(Weather)]
        self.demo_index += 1
        self.widget.scene.set_weather(weather)
        self.widget.weather_label.setText(NAMES[weather])
        self.widget.description.setText(DESCRIPTIONS[weather])
        self.panel.summary_label.setText(f"MODO DEMOSTRACIÓN · {NAMES[weather]}")
        self.panel.evidence_label.setText("Escena visual sintética. No hay pruebas de red ni historial.")
        self.tray.setToolTip(f"Network Weather · demostración: {NAMES[weather]}")
        for card in self.widget.cards.values():
            card.value.setText("demo")

    def exit(self) -> None:
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(30000):
                QMessageBox.warning(self.widget, "Cierre pendiente", "Una prueba de red aún no termina. Intenta salir de nuevo.")
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
            QMessageBox.critical(None, "Network Weather", "No se pudo crear la instancia única.")
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
