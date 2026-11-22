from PySide6.QtCore import QPoint, QRect, QSize

from network_weather.window_placement import visible_position


def test_position_stays_on_second_display_when_connected():
    primary = QRect(0, 0, 1920, 1080)
    secondary = QRect(1920, 0, 1600, 900)
    assert visible_position(QPoint(2500, 100), QSize(440, 500),
                            [primary, secondary], primary) == QPoint(2500, 100)


def test_disconnected_display_falls_back_and_clamps_inside_primary():
    primary = QRect(0, 0, 1920, 1080)
    assert visible_position(QPoint(2500, 100), QSize(440, 500),
                            [primary], primary) == QPoint(1480, 100)


def test_partly_offscreen_window_is_fully_recovered():
    primary = QRect(0, 0, 1920, 1080)
    assert visible_position(QPoint(1810, 1000), QSize(440, 500),
                            [primary], primary) == QPoint(1480, 580)


def test_negative_coordinates_and_small_displays():
    primary = QRect(0, 0, 800, 400)
    left = QRect(-1024, 0, 1024, 768)
    assert visible_position(QPoint(-1100, -20), QSize(440, 500),
                            [primary, left], primary) == QPoint(-1024, 0)
    assert visible_position(QPoint(600, 200), QSize(900, 500),
                            [primary], primary) == QPoint(0, 0)
