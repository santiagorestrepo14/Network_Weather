"""Keep remembered floating-window positions inside a current display."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize


def visible_position(
    requested: QPoint, size: QSize, displays: list[QRect], fallback: QRect,
) -> QPoint:
    """Preserve a valid position; clamp displaced windows to one available screen."""
    window = QRect(requested, size)
    candidates = displays or [fallback]
    overlaps = [window.intersected(display).width() *
                window.intersected(display).height() for display in candidates]
    largest = max(overlaps)
    display = candidates[overlaps.index(largest)] if largest > 0 else fallback
    max_x = max(display.left(), display.right() - size.width() + 1)
    max_y = max(display.top(), display.bottom() - size.height() + 1)
    return QPoint(
        min(max(requested.x(), display.left()), max_x),
        min(max(requested.y(), display.top()), max_y),
    )
