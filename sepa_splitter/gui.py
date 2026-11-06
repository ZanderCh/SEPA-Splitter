"""Grafische Oberfläche (PySide6, deutschsprachig)."""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
                               QHeaderView, QDialog)

from . import __version__, service
from .config import Config, load_config, load_last_dir, save_last_dir
from .errors import SepaSplitterError
from .paths import dialog_filters, resolve_start_dir
from .protocol import Protocol


def fmt_money(v: Decimal, ccy: str = "EUR") -> str:
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {ccy}"


def fmt_size(n: int) -> str:
    return f"{n:,} Bytes".replace(",", ".") if n < 1024 else f"{n / 1024:,.1f} KB ({n:,} Bytes)".replace(",", "X").replace(".", ",").replace("X", ".")


class Worker(QObject):
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn(lambda p, t: self.progress.emit(p, t)))
        except SepaSplitterError as e:
            self.failed.emit(str(e))
        except Exception as e:  # unerwartet – nie still schlucken
            self.failed.emit(f"Unerwarteter Fehler: {type(e).__name__}: {e}")


class LogDialog(QDialog):
    def __init__(self, parent, text: str, path: Optional[Path]):
        super().__init__(parent)
        self.setWindowTitle("Protokoll")
        self.resize(760, 460)
        lay = QVBoxLayout(self)
        if path:
            lay.addWidget(QLabel(f"Protokolldatei: {path}"))
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        lay.addWidget(box)
        b = QPushButton("Schließen")
        b.clicked.connect(self.accept)
        lay.addWidget(b)


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.proto = Protocol(cfg.log_enabled, cfg.log_level, cfg.log_file)
        self.chk: Optional[service.CheckResult] = None
        self.outdir: Optional[Path] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[Worker] = None
        self.setWindowTitle(f"SEPA-Splitter {__version__}")
        self.resize(cfg.window_width, cfg.window_height)
        self.setAcceptDrops(True)
        self._build()
        for p in cfg.problems:
            self.proto.log("WARNING", p)
        if cfg.problems:
            QMessageBox.warning(self, "Hinweis zur Konfiguration", "\n\n".join(cfg.problems))
        if cfg.ini_created:
            self.status("Standard-Konfiguration angelegt: " + str(cfg.ini_path))

    # ------------------------------------------------------------ Aufbau
    def _build(self):
        w = QWidget()
        self.setCentralWidget(w)
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Vollständiger Pfad der SEPA-XML-Datei – oder Datei hierher ziehen")
        self.path_edit.returnPressed.connect(self.on_check)
        self.btn_choose = QPushButton("Datei auswählen")
        self.btn_choose.clicked.connect(self.on_choose)
        row.addWidget(self.path_edit, 1)
        row.addWidget(self.btn_choose)
        v.addLayout(row)

        row = QHBoxLayout()
        self.btn_check = QPushButton("Datei prüfen")
        self.btn_split = QPushButton("Datei aufteilen")
        self.btn_open = QPushButton("Ausgabeordner öffnen")
        self.btn_log = QPushButton("Protokoll anzeigen")
        self.btn_quit = QPushButton("Beenden")
        self.btn_check.clicked.connect(self.on_check)
        self.btn_split.clicked.connect(self.on_split)
        self.btn_open.clicked.connect(self.on_open_dir)
        self.btn_log.clicked.connect(self.on_log)
        self.btn_quit.clicked.connect(self.close)
        for b in (self.btn_check, self.btn_split, self.btn_open, self.btn_log):
            row.addWidget(b)
        row.addStretch(1)
        row.addWidget(self.btn_quit)
        v.addLayout(row)

        box = QGroupBox("Dateiinformationen")
        form = QFormLayout(box)
        self.info = {}
        for key, label in (("name", "Dateiname"), ("dir", "Dateipfad"), ("size", "Dateigröße"),
                           ("version", "Erkannte pain-Version"), ("tx", "Transaktionen gesamt"),
                           ("pmt", "Anzahl PmtInf-Blöcke"), ("sum", "Ursprüngliche Kontrollsumme"),
                           ("max", "Maximal zulässige Transaktionen je Datei"),
                           ("struct", "Strukturprüfung"), ("sums", "Summenprüfung")):
            lab = QLabel("–")
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lab.setWordWrap(True)
            self.info[key] = lab
            form.addRow(label + ":", lab)
        v.addWidget(box)

        self.preview_box = QGroupBox("Geplante Ausgabedateien (Vorschau)")
        pl = QVBoxLayout(self.preview_box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Datei", "Transaktionen", "Kontrollsumme"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        pl.addWidget(self.table)
        v.addWidget(self.preview_box, 1)
        self.preview_box.setVisible(self.cfg.show_preview)

        self.msgs = QPlainTextEdit()
        self.msgs.setReadOnly(True)
        self.msgs.setMaximumHeight(110)
        v.addWidget(self.msgs)
        self.res_struct = QLabel("")
        self.res_fid = QLabel("")
        self.res_note = QLabel("")
        self.res_note.setWordWrap(True)
        for l in (self.res_struct, self.res_fid, self.res_note):
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(l)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        v.addWidget(self.progress)
        self.statusBar().showMessage("Bereit.")
        self._update_buttons()

    def status(self, t: str):
        self.statusBar().showMessage(t)

    def _update_buttons(self):
        busy = self._thread is not None
        self.btn_check.setEnabled(not busy)
        self.btn_choose.setEnabled(not busy)
        self.btn_split.setEnabled(not busy and bool(self.chk and self.chk.doc.ok and self.chk.split_needed))
        self.btn_open.setEnabled(self.outdir is not None)

    # ------------------------------------------------------------ Drag & Drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not urls:
            return
        if not urls[0].lower().endswith(".xml"):
            QMessageBox.warning(self, "Falsche Dateiart", "Bitte eine SEPA-XML-Datei (*.xml) ablegen.")
            return
        self.set_file(urls[0])

    # ------------------------------------------------------------ Aktionen
    def on_choose(self):
        last = load_last_dir(self.cfg)
        r = resolve_start_dir(self.cfg.base_path, self.cfg.name_scheme, date.today(), last,
                              self.cfg.remember_last_directory, self.cfg.last_directory_overrides_base_path)
        if r.message:
            QMessageBox.information(self, "Startordner", r.message)
            self.proto.log("WARNING", r.message)
        filters, selected = dialog_filters()
        fn, _ = QFileDialog.getOpenFileName(self, "SEPA-Lastschriftdatei auswählen", str(r.path), filters, selected)
        if fn:
            save_last_dir(self.cfg, str(Path(fn).parent))
            self.set_file(fn)

    def set_file(self, fn: str):
        self.path_edit.setText(fn)
        self._reset_results()
        if self.cfg.check_on_load:
            self.on_check()

    def _reset_results(self):
        self.chk = None
        self.outdir = None
        self.table.setRowCount(0)
        self.msgs.clear()
        for l in self.info.values():
            l.setText("–")
        self.res_struct.setText("")
        self.res_fid.setText("")
        self.res_note.setText("")
        self.progress.setValue(0)
        self._update_buttons()

    def _run(self, fn, on_done):
        if self._thread:
            return
        self._thread = QThread(self)
        self._worker = Worker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda p, t: (self.progress.setValue(p), self.status(t)))
        self._worker.done.connect(lambda r: self._finish(on_done, r))
        self._worker.failed.connect(self._fail)
        self._thread.start()
        self._update_buttons()

    def _stop_thread(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None

    def _finish(self, on_done, result):
        self._stop_thread()
        on_done(result)
        self._update_buttons()

    def _fail(self, msg: str):
        self._stop_thread()
        self.progress.setValue(0)
        self.status("Fehler.")
        self.res_struct.setText("")
        self.res_fid.setText("")
        self.msgs.setPlainText(msg)
        QMessageBox.critical(self, "Fehler", msg)
        self._update_buttons()

    def on_check(self):
        text = self.path_edit.text().strip().strip('"')
        if not text:
            QMessageBox.information(self, "Keine Datei", "Bitte zuerst eine Datei auswählen.")
            return
        self.chk = None
        self.table.setRowCount(0)
        self.res_struct.setText("")
        self.res_fid.setText("")
        self.res_note.setText("")
        path = Path(text)
        self._run(lambda prog: service.check_file(path, self.cfg, self.proto, prog), self._show_check)

    def _show_check(self, chk: service.CheckResult):
        self.chk = chk
        d = chk.doc
        self.outdir = d.path.resolve().parent
        self.info["name"].setText(d.path.name)
        self.info["dir"].setText(str(self.outdir))
        self.info["size"].setText(fmt_size(len(d.data)))
        self.info["version"].setText(d.version)
        self.info["tx"].setText(f"{d.total_tx:,}".replace(",", "."))
        self.info["pmt"].setText(str(len(d.pmtinfs)))
        self.info["sum"].setText(fmt_money(d.declared_sum, d.currency) if d.declared_sum is not None else "nicht angegeben")
        self.info["max"].setText(str(self.cfg.max_transactions))
        self.info["struct"].setText(("in Ordnung" if d.structure_ok else "FEHLER") + f" – Schema: {d.schema_status}")
        self.info["sums"].setText("in Ordnung (Anzahl und Kontrollsummen stimmen)" if d.sums_ok else "FEHLER – siehe Meldungen")
        self.msgs.setPlainText("\n".join(f"[{'Fehler' if i.level == 'error' else 'Hinweis'}] {i.text}" for i in d.issues))
        if not d.ok:
            self.status("Die Datei hat Prüffehler und kann nicht aufgeteilt werden.")
        elif not chk.split_needed:
            self.status(f"Keine Aufteilung nötig: {d.total_tx} ≤ {self.cfg.max_transactions}. Es wird nichts erzeugt.")
            self.res_note.setText("Die Datei überschreitet den Grenzwert nicht. Das Original bleibt unverändert, es wird keine Ausgabedatei erzeugt.")
        else:
            for n, p in zip(chk.names, chk.plans):
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(n.name))
                for c, txt in ((1, str(p.count)), (2, fmt_money(p.total, d.currency))):
                    it = QTableWidgetItem(txt)
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.table.setItem(r, c, it)
            self.status(f"Aufteilung in {len(chk.plans)} Dateien geplant. Mit „Datei aufteilen“ bestätigen.")

    def on_split(self):
        if not (self.chk and self.chk.doc.ok and self.chk.split_needed):
            return
        chk = self.chk
        if self.cfg.confirm_before_split:
            files = "\n".join(f"  {n.name} – {p.count} Transaktionen" for n, p in zip(chk.names, chk.plans))
            if QMessageBox.question(self, "Aufteilung bestätigen",
                                    f"Die Datei „{chk.doc.path.name}“ wird in {len(chk.plans)} Dateien aufgeteilt:\n\n{files}\n\n"
                                    f"Das Original bleibt unverändert. Fortfahren?") != QMessageBox.Yes:
                return
        allow = False
        existing = [p for p in chk.names if p.exists()]
        if existing and self.cfg.overwrite_mode == "ask":
            names = "\n".join("  " + p.name for p in existing[:10])
            allow = QMessageBox.question(self, "Dateien existieren bereits",
                                         f"Folgende Ausgabedateien existieren bereits:\n\n{names}\n\nÜberschreiben?") == QMessageBox.Yes
            if not allow:
                self.status("Abgebrochen – es wurde nichts geschrieben.")
                return
        self.res_struct.setText("")
        self.res_fid.setText("")
        self._run(lambda prog: service.split_file(chk, self.cfg, self.proto, lambda _: allow, prog), self._show_split)

    def _show_split(self, res: service.SplitResult):
        self.res_struct.setText("✔ SEPA-Strukturprüfung erfolgreich\nDie erzeugten Dateien erfüllen die implementierten XML-, Schema- und fachlichen Prüfregeln.")
        self.res_fid.setText("✔ Originaltreue erfolgreich geprüft\nAlle übernommenen Transaktionsblöcke sind unverändert. Sämtliche übrigen Unterschiede sind dokumentiert und zulässig.")
        self.res_note.setText("Hinweis: Daraus lässt sich nicht automatisch ableiten, dass die Sparkasse die Dateien annimmt."
                              + ("\nSchema-Hinweis: " + self.chk.doc.schema_status if self.chk and "fehlt" in self.chk.doc.schema_status else ""))
        self.msgs.setPlainText("Erzeugt:\n" + "\n".join(str(f) for f in res.files) + "\n\n" + "\n".join(res.changes))
        self.status(f"Fertig: {len(res.files)} Dateien erzeugt.")
        self.btn_split.setEnabled(False)

    def on_open_dir(self):
        if self.outdir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.outdir)))   # Finder / Explorer / Dateimanager

    def on_log(self):
        LogDialog(self, self.proto.text(), self.proto.path).exec()

    def closeEvent(self, e):
        if self._thread:
            QMessageBox.information(self, "Verarbeitung läuft", "Bitte warten, bis die Verarbeitung abgeschlossen ist.")
            e.ignore()
        else:
            e.accept()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("SEPA-Splitter")
    cfg = load_config()
    win = MainWindow(cfg)
    win.show()
    return app.exec()
