from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QRect, QPoint, QEasingCurve
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QWidget, QVBoxLayout, QGraphicsOpacityEffect

class Toast(QWidget):
    """
    A non-blocking floating toast notification widget for PySide6.
    """
    def __init__(self, parent: QWidget, message: str, duration_ms: int = 3000, level: str = "info"):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self._label = QLabel(message, self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        
        # Determine colors based on level (hardcoded for toast context is fine, but better to use palette if possible. We use neutral colors that work on both for now)
        bg_color = "#333333"
        text_color = "#ffffff"
        border_color = "#555555"
        
        if level == "warning":
            bg_color = "#f59e0b"
            text_color = "#000000"
            border_color = "#d97706"
        elif level == "error":
            bg_color = "#ef4444"
            text_color = "#ffffff"
            border_color = "#dc2626"
        elif level == "success":
            bg_color = "#10b981"
            text_color = "#ffffff"
            border_color = "#059669"
            
        self._label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 10px 16px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 13px;
                font-weight: 500;
            }}
        """)
        
        layout.addWidget(self._label)
        
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(0.0)
        
        self.adjustSize()
        
        # Position at the bottom-center of the parent
        if parent:
            parent_rect = parent.rect()
            parent_pos = parent.mapToGlobal(QPoint(0, 0))
            x = parent_pos.x() + (parent_rect.width() - self.width()) // 2
            y = parent_pos.y() + parent_rect.height() - self.height() - 60
            self.move(x, y)
            
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(duration_ms)
        self._timer.timeout.connect(self._fade_out)
        
        self._fade_in()
        
    def _fade_in(self):
        self.show()
        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_in.setDuration(250)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim_in.finished.connect(self._timer.start)
        self._anim_in.start()
        
    def _fade_out(self):
        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_out.setDuration(350)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.Type.InQuad)
        self._anim_out.finished.connect(self.close)
        self._anim_out.start()

    @staticmethod
    def show_toast(parent: QWidget, message: str, duration_ms: int = 3000, level: str = "info"):
        if not parent:
            return None
        toast = Toast(parent, message, duration_ms, level)
        if not hasattr(parent, "_active_toasts"):
            parent._active_toasts = []
        parent._active_toasts.append(toast)
        
        def cleanup():
            if toast in parent._active_toasts:
                parent._active_toasts.remove(toast)
                
        toast._timer.timeout.connect(cleanup)
        return toast
