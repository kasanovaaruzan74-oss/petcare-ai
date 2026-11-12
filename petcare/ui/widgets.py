from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

ASSETS = Path(__file__).parent
TASK_TYPES = {"feeding": "Тамақтандыру", "walk": "Серуен", "play": "Ойын",
              "vaccination": "Вакцинация", "care": "Басқа күтім"}
ICONS = {
    "home": "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    "pets": "M4 11l-1-7 6 3q3-1 6 0l6-3-1 8q2 8-8 9Q2 20 4 11Z",
    "add": "M12 4v16M4 12h16",
    "ai": "M12 2q1 8 10 10-8 1-10 10-2-9-10-10Q10 10 12 2Z",
    "calendar": "M3 5h18v16H3zM7 3v5m10-5v5M3 11h18",
    "check": "M20 11a8 8 0 1 1-4-6M8 11l4 4 9-10",
}


def icon(name, color):
    path = ICONS[name]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{path}" stroke="{color}" fill="none" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round"/></svg>'
    pix = QPixmap(24, 24)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    return QIcon(pix)


def label(value, role="", wrap=False):
    item = QLabel(str(value))
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(wrap)
    if role:
        item.setProperty("role", role)
    return item


def button(title, callback=None, role=""):
    b = QPushButton(title)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(40)
    if role:
        b.setProperty("role", role)
    if callback:
        b.clicked.connect(lambda checked=False: callback())
    return b


def field(value="", placeholder="", secret=False):
    item = QLineEdit()
    item.setText(value)
    item.setPlaceholderText(placeholder)
    if secret:
        item.setEchoMode(QLineEdit.EchoMode.Password)
    return item


def combo(choices):
    item = QComboBox()
    for key, title in choices:
        item.addItem(title, key)
    return item


def panel(name="panel"):
    box = QFrame()
    box.setObjectName(name)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    return box, lay


def rule():
    item = QFrame()
    item.setObjectName("rule")
    item.setFixedHeight(1)
    return item


def formatted_day(value):
    return date.fromisoformat(str(value)[:10]).strftime("%d.%m.%Y")


def formatted_time(value):
    return datetime.fromisoformat(value).strftime("%H:%M")


def table(headers, widths=None):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(43)
    widget.setShowGrid(False)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    header = widget.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    for index, width in (widths or {}).items():
        header.setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
        widget.setColumnWidth(index, width)
    return widget


def table_row(widget, values):
    row = widget.rowCount()
    widget.insertRow(row)
    for col, value in enumerate(values):
        widget.setItem(row, col, QTableWidgetItem(str(value)))
    return row


class Form(QDialog):
    """Modal editor that keeps the entered values when validation fails."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(24, 24, 24, 24)
        self.layout_.setSpacing(16)
        self.layout_.addWidget(label(title, "heading"))
        self.fields = QFormLayout()
        self.fields.setSpacing(12)
        self.layout_.addLayout(self.fields)
        self.error = label("", "error", True)
        self.layout_.addWidget(self.error)

    def submit(self, title, callback):
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(button("Бас тарту", self.reject))
        ok = button(title, lambda: self.apply(callback), "primary")
        ok.setDefault(True)
        buttons.addWidget(ok)
        self.layout_.addLayout(buttons)

    def apply(self, callback):
        from sqlite3 import Error as DatabaseError

        try:
            callback()
        except (ValueError, PermissionError, RuntimeError, OSError) as exc:
            self.error.setText(str(exc))
        except DatabaseError:
            self.error.setText("Деректер базасымен байланысу мүмкін болмады.")
        else:
            self.accept()

