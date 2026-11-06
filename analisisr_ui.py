"""Widgets y procesos de AnalisisR: estilo propio, procesos cancelables y Markdown."""
from __future__ import annotations

import codecs
from pathlib import Path
import re

import analisisr_core as engine
from PySide6.QtCore import (
    QObject, QProcess, QProcessEnvironment, Qt, QTimer, QUrl, Signal
)
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QIcon, QKeySequence, QShortcut, QTextCharFormat, QTextCursor, QTextDocument, QTextDocumentFragment, QTextFrameFormat, QTextTable
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QVBoxLayout, QWidget
)

QSS = """
* { font-size: 13px; }
QMainWindow, QDialog { background: #f1f5f9; }
QWidget#central { background: #f1f5f9; }

QTabWidget::pane {
    border: 1px solid #e2e8f0; border-radius: 8px; background: #ffffff; top: -1px;
}
QTabBar::tab {
    background: #e2e8f0; color: #334155; padding: 7px 14px; margin-right: 2px;
    border-top-left-radius: 7px; border-top-right-radius: 7px; font-weight: 600;
}
QTabBar::tab:selected { background: #ffffff; color: #1e3a8a; }
QTabBar::tab:hover:!selected { background: #cbd5e1; }

QGroupBox {
    border: 1px solid #e2e8f0; border-radius: 8px; margin-top: 14px;
    padding: 12px 12px 10px 12px; background: #ffffff; font-weight: 700;
    color: #1e3a8a;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }

QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
    padding: 5px 8px; selection-background-color: #bfdbfe; color: #0f172a;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #1d4ed8; }
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QCheckBox:disabled { color: #94a3b8; }
QPlainTextEdit {
    font-family: "Cascadia Mono", "Consolas", "Courier New", monospace;
}
QPlainTextEdit#ai_prompt { background-color: rgba(34, 197, 94, 18); }
QTextBrowser#ai_response {
    background-color: rgba(59, 130, 246, 18);
    border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px;
}

QPushButton {
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 6px;
    padding: 3px 10px; font-weight: 600; color: #1e3a8a;
}
QPushButton:hover { background: #eff6ff; border-color: #93c5fd; }
QPushButton:pressed { background: #dbeafe; }
QPushButton:disabled { color: #94a3b8; background: #f8fafc; border-color: #e2e8f0; }
QPushButton#primary {
    background: #1e3a8a; color: #ffffff; border: 1px solid #1e3a8a; padding: 8px 20px;
}
QPushButton#primary:hover { background: #1d4ed8; border-color: #1d4ed8; }
QPushButton#primary:disabled { background: #94a3b8; border-color: #94a3b8; }
QPushButton#danger { color: #991b1b; border-color: #fca5a5; }
QPushButton#danger:hover { background: #fef2f2; }

QTableWidget {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px;
    gridline-color: #eef2f7; selection-background-color: #dbeafe;
    selection-color: #0f172a;
}
QHeaderView::section {
    background: #f1f5f9; color: #0f172a; font-weight: 700;
    border: none; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0;
    padding: 6px 8px;
}
QTableCornerButton::section { background: #f1f5f9; border: none; }

QProgressBar {
    border: 1px solid #e2e8f0; border-radius: 6px; background: #f8fafc;
    height: 8px; text-align: center; color: #1e3a8a; font-size: 11px;
}
QProgressBar::chunk { background: #1d4ed8; border-radius: 5px; }

QStatusBar { background: #e2e8f0; color: #334155; }
QStatusBar QLabel { color: #334155; padding: 0 6px; }

QSplitter::handle { background: #e2e8f0; }
QSplitter::handle:horizontal { width: 3px; }
QScrollArea { border: none; background: transparent; }

QToolBar { background: #ffffff; border-bottom: 1px solid #e2e8f0; spacing: 6px; padding: 4px; }
QToolBar QToolButton {
    padding: 6px 12px; border-radius: 6px; font-weight: 600; color: #1e3a8a;
}
QToolBar QToolButton:hover { background: #eff6ff; }
QToolBar QToolButton:disabled { color: #94a3b8; }

QLabel#hint { color: #4b5768; font-size: 12px; }
QLabel#verdict { font-size: 20px; font-weight: 800; padding: 10px 14px; border-radius: 8px; }
QLabel#badge {
    background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;
    border-radius: 11px; padding: 3px 10px; font-size: 11px; font-weight: 700;
}
QCheckBox { spacing: 7px; }
"""

class Proc(QObject):
    """Lanza un comando y transmite su salida línea a línea."""

    line = Signal(str)
    done = Signal(int)          # código de salida
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.p = QProcess(self)
        self.p.setProcessChannelMode(QProcess.MergedChannels)
        self.p.readyReadStandardOutput.connect(self._read)
        self.p.finished.connect(self._finished)
        self.p.errorOccurred.connect(self._error)
        self._buf = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._pendiente: list[str] = []

    def start(self, program: str, args: list[str], cwd: Path,
              env_extra: dict | None = None) -> None:
        self._buf = ""
        self._decoder.reset()
        self.p.setWorkingDirectory(str(cwd))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        for k, v in (env_extra or {}).items():
            env.insert(k, v)
        self.p.setProcessEnvironment(env)
        self.p.start(program, args)

    def kill(self) -> None:
        """Mata el proceso y su descendencia (Rscript incluido).

        `QProcess.kill()` sólo alcanza al hijo directo: R seguiría consumiendo CPU y VRAM.
        """
        if self.p.state() == QProcess.NotRunning:
            return
        pid = int(self.p.processId())
        if pid and engine.kill_tree(pid):
            self.line.emit(f"(árbol de procesos {pid} terminado: hijo y descendientes)")
            QTimer.singleShot(400, self.p.kill)
            return
        self.p.kill()

    @property
    def running(self) -> bool:
        return self.p.state() != QProcess.NotRunning

    def _read(self) -> None:
        chunk = self._decoder.decode(bytes(self.p.readAllStandardOutput()))
        self._buf += chunk
        while "\n" in self._buf:
            ln, self._buf = self._buf.split("\n", 1)
            self.line.emit(ln.rstrip("\r"))

    def _finished(self, code: int, _status) -> None:
        self._read()
        self._buf += self._decoder.decode(b"", final=True)
        if self._buf.strip():
            self.line.emit(self._buf.rstrip("\r"))
            self._buf = ""
        self.done.emit(code)

    def _error(self, err) -> None:
        if err == QProcess.FailedToStart:
            self.failed.emit("no se pudo iniciar el proceso (¿ruta de Python correcta?)")

class PromptEdit(QPlainTextEdit):
    variables_requested = Signal()

    def keyPressEvent(self, event):
        if event.text() == "@":
            self.variables_requested.emit()
        else:
            super().keyPressEvent(event)


class FactorBuilder(QWidget):
    """Define variables latentes con sus indicadores para un modelo de medida.

    Cada indicador pertenece a una sola latente: las cargas cruzadas exigen
    justificacion y no se especifican desde este formulario.
    """

    NOMBRE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$")

    def __init__(self, columns: list[str], parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.factors: list[tuple[str, list[str]]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Nombre de la variable latente, por ejemplo Satisfaccion")
        layout.addWidget(self.name)
        self.items = QListWidget()
        self.items.addItems(self.columns)
        self.items.setSelectionMode(QAbstractItemView.MultiSelection)
        self.items.setMaximumHeight(120)
        layout.addWidget(self.items)
        row = QHBoxLayout()
        self.add = QPushButton("Añadir variable latente")
        self.add.clicked.connect(self.add_factor)
        self.drop = QPushButton("Quitar la seleccionada")
        self.drop.clicked.connect(self.remove_factor)
        row.addWidget(self.add)
        row.addWidget(self.drop)
        layout.addLayout(row)
        self.summary = QListWidget()
        self.summary.setMaximumHeight(90)
        layout.addWidget(self.summary)

        def aviso(texto: str) -> None:
            QMessageBox.information(self, "Modelo de medida", texto)

        self.aviso = aviso

    def add_factor(self) -> bool:
        nombre = self.name.text().strip()
        elegidos = [item.text() for item in self.items.selectedItems()]
        usados = {item for _, items in self.factors for item in items}
        if not self.NOMBRE.match(nombre):
            self.aviso("El nombre de la variable latente debe empezar por una letra y contener "
                       "solo letras, dígitos, punto o guion bajo.")
            return False
        if nombre in [n for n, _ in self.factors]:
            self.aviso("Ya existe una variable latente con ese nombre.")
            return False
        if nombre in self.columns:
            self.aviso("El nombre de la variable latente no puede coincidir con una columna de los datos.")
            return False
        if len(elegidos) < 2:
            self.aviso("Selecciona al menos dos indicadores para esa variable latente.")
            return False
        repetidos = [item for item in elegidos if item in usados]
        if repetidos:
            self.aviso("Estos indicadores ya pertenecen a otra variable latente: " + ", ".join(repetidos))
            return False
        self.factors.append((nombre, elegidos))
        self.summary.addItem(nombre + ": " + ", ".join(elegidos))
        self.name.clear()
        self.items.clearSelection()
        return True

    def remove_factor(self) -> None:
        fila = self.summary.currentRow()
        if fila < 0:
            return
        self.summary.takeItem(fila)
        del self.factors[fila]

    def text(self) -> str:
        """Descripcion del modelo para insertar en la consulta."""
        partes = []
        for nombre, items in self.factors:
            indicadores = ", ".join(items[:-1]) + " y " + items[-1] if len(items) > 1 else items[0]
            partes.append(f"{nombre} medida por {indicadores}")
        return "; ".join(partes)

def _table(cols: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.horizontalHeader().setStretchLastSection(True)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return t

def render_chat(browser: QTextBrowser, quien: str, texto: str) -> None:
    import html as _html
    mio = quien == "Tú"
    color = "#1d4ed8" if mio else "#166534"
    # La pregunta va en azul y negrita; la respuesta, en texto normal, para que una
    # conversacion larga se lea de un vistazo.
    if mio:
        cuerpo = _html.escape(texto).replace("\n", "<br>")
        browser.append(
            f"<p><b style='color:{color}'>{quien}:</b><br>"
            f"<b style='color:{color}'>{cuerpo}</b></p>")
    else:
        from analisisr_docx import readable_math

        doc = QTextDocument()
        doc.setMarkdown(readable_math(texto), QTextDocument.MarkdownDialectGitHub |
                        QTextDocument.MarkdownNoHTML)
        # El chat sólo necesita texto y tablas, sin cargar imágenes locales o remotas.
        imagen = doc.find("\ufffc")
        while not imagen.isNull():
            if imagen.charFormat().isImageFormat():
                imagen.insertText("[imagen omitida]", QTextCharFormat())
            imagen = doc.find("\ufffc", imagen)
        for frame in doc.rootFrame().childFrames():
            if isinstance(frame, QTextTable):
                fmt = frame.format()
                fmt.setBorder(1)
                fmt.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
                fmt.setBorderBrush(QColor("#94a3b8"))
                fmt.setBorderCollapse(True)
                fmt.setCellPadding(5)
                fmt.setCellSpacing(0)
                frame.setFormat(fmt)
        browser.append(f"<p><b style='color:{color}'>{quien}:</b><br></p>")
        cursor = browser.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertFragment(QTextDocumentFragment(doc))
        browser.setTextCursor(cursor)
    browser.verticalScrollBar().setValue(
        browser.verticalScrollBar().maximum())
