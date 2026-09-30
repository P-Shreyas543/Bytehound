"""Single-line label that elides overflowing text instead of widening or wrapping its layout."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    """Plain-text QLabel that shows '…' when the text is wider than the label.

    Its minimum width is small, so long or changing text never forces the window wider,
    and it never wraps, so the height stays constant as the text changes. The full text is
    available as the tooltip whenever it is elided.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None, min_width: int = 40):
        super().__init__(parent)
        self._full_text = ""
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(False)
        self.setMinimumWidth(min_width)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802 (Qt naming)
        text = text or ""
        if text == self._full_text:
            return
        self._full_text = text
        self._apply_elide()

    def text(self) -> str:  # noqa: D401 - Qt naming
        return self._full_text

    def sizeHint(self):  # noqa: N802
        hint = super().sizeHint()
        hint.setWidth(self.fontMetrics().horizontalAdvance(self._full_text) + 8)
        return hint

    def minimumSizeHint(self):  # noqa: N802
        hint = super().minimumSizeHint()
        hint.setWidth(self.minimumWidth())
        return hint

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (event.Type.FontChange, event.Type.StyleChange):
            self._apply_elide()

    def _apply_elide(self) -> None:
        width = max(1, self.contentsRect().width())
        shown = self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        QLabel.setText(self, shown)
        self.setToolTip(self._full_text if shown != self._full_text else "")
