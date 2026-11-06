"""GUI-Tests mit pytest-qt (offscreen, ohne Bildschirm lauffähig).

Ausführen:  python -m pytest tests/test_gui.py -v
Modale Dialoge (Dateidialog, Rückfragen, Meldungen) werden durch Aufzeichner ersetzt,
damit der gesamte Ablauf automatisch durchlaufen kann:
Dateidialog (Startordner BasePath/JJJJ/Qn, XML-Filter) -> Prüfung -> Vorschau -> Bestätigung
-> Fortschritt -> Ergebnis -> Ausgabeordner öffnen -> Protokoll.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

pytest.importorskip("pytestqt")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from sepa_splitter import gui  # noqa: E402
from sepa_splitter.config import load_config  # noqa: E402
from sepa_splitter.paths import render_name_scheme  # noqa: E402

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
TIMEOUT = 60000


class Recorder:
    def __init__(self):
        self.dialog_args = None
        self.dialog_result = ""
        self.questions = []
        self.question_answer = QMessageBox.Yes
        self.messages = []          # (art, titel, text)
        self.opened_urls = []
        self.log_texts = []


@pytest.fixture
def env(tmp_path, monkeypatch):
    rec = Recorder()
    work = tmp_path / "base" / render_name_scheme("JJJJ/Qn", date.today())
    work.mkdir(parents=True)
    for f in SAMPLES.glob("*.xml"):
        shutil.copy(f, work / f.name)
    ini = tmp_path / "SEPA-Splitter.ini"
    ini.write_text(f"[Paths]\nBasePath = {tmp_path / 'base'}\nNameScheme = JJJJ/Qn\n"
                   f"LastDirectoryOverridesBasePath = false\n", encoding="utf-8")

    def fake_open(parent, caption, directory, filters, selected="", *a, **k):
        rec.dialog_args = (caption, directory, filters, selected)
        return rec.dialog_result, selected

    def fake_question(parent, title, text, *a, **k):
        rec.questions.append((title, text))
        return rec.question_answer

    def recorder(kind):
        def f(parent, title, text, *a, **k):
            rec.messages.append((kind, title, text))
            return QMessageBox.Ok
        return f

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake_open))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(recorder(kind)))
    monkeypatch.setattr(gui.QDesktopServices, "openUrl", staticmethod(lambda url: rec.opened_urls.append(url) or True))
    monkeypatch.setattr(gui.LogDialog, "exec", lambda self: rec.log_texts.append(
        self.findChild(gui.QPlainTextEdit).toPlainText()) or 0)
    return rec, work, load_config(ini)


def make_window(qtbot, cfg):
    w = gui.MainWindow(cfg)
    qtbot.addWidget(w)
    w.show()
    return w


def wait_idle(qtbot, w):
    qtbot.waitUntil(lambda: w._thread is None, timeout=TIMEOUT)


def test_full_flow(qtbot, env):
    rec, work, cfg = env
    src = work / "beispiel_008_02_2000tx.xml"
    original = src.read_bytes()
    rec.dialog_result = str(src)
    w = make_window(qtbot, cfg)
    assert not w.btn_split.isEnabled() and not w.btn_open.isEnabled()
    assert not w.windowIcon().isNull()
    assert w.logo.pixmap() is not None and not w.logo.pixmap().isNull()   # Logo im Fenster
    # „Datei aufteilen“ sitzt unten, unterhalb von Vorschau und Fortschrittsbalken-Zeile
    split_y = w.btn_split.mapTo(w, w.btn_split.rect().topLeft()).y()
    assert split_y > w.table.mapTo(w, w.table.rect().bottomLeft()).y()
    assert split_y > w.msgs.mapTo(w, w.msgs.rect().bottomLeft()).y()

    # Dateidialog: Startordner BasePath/JJJJ/Qn, XML-Filter vorausgewählt
    qtbot.mouseClick(w.btn_choose, Qt.LeftButton)
    caption, directory, filters, selected = rec.dialog_args
    assert Path(directory) == work
    assert filters.split(";;")[0] == selected == "SEPA-XML-Dateien (*.xml *.XML *.Xml)"
    assert "Alle Dateien (*)" in filters
    assert not [m for m in rec.messages if m[1] == "Startordner"]   # kein Ersatzordner nötig

    # Prüfung läuft automatisch (CheckOnLoad) im Hintergrund-Thread; Vorschau erscheint
    wait_idle(qtbot, w)
    assert not [m for m in rec.messages if m[0] == "critical"], rec.messages
    assert w.info["version"].text() == "pain.008.001.02"
    assert w.info["tx"].text() == "2.000"
    assert w.table.rowCount() == 3
    assert [w.table.item(r, 0).text() for r in range(3)] == [
        "beispiel_008_02_2000tx_a.xml", "beispiel_008_02_2000tx_b.xml", "beispiel_008_02_2000tx_c.xml"]
    assert [w.table.item(r, 1).text() for r in range(3)] == ["667", "667", "666"]
    assert w.btn_split.isEnabled()
    assert not list(work.glob("beispiel_008_02_2000tx_?.xml"))   # Vorschau schreibt nichts
    assert w.progress.value() == 0                              # Balken läuft erst beim Aufteilen

    # Bestätigung + Fortschritt
    seen_progress = []
    w.progress.valueChanged.connect(seen_progress.append)
    qtbot.mouseClick(w.btn_split, Qt.LeftButton)
    assert rec.questions and rec.questions[0][0] == "Aufteilung bestätigen"
    assert "667 Transaktionen" in rec.questions[0][1]
    wait_idle(qtbot, w)
    assert not [m for m in rec.messages if m[0] == "critical"], rec.messages
    assert seen_progress and seen_progress[-1] == 100 and len(set(seen_progress)) > 3
    assert "erfolgreich" in w.res_struct.text() and "erfolgreich" in w.res_fid.text()
    parts = sorted(work.glob("beispiel_008_02_2000tx_?.xml"))
    assert [p.name[-5] for p in parts] == ["a", "b", "c"]
    assert src.read_bytes() == original
    assert not list(work.glob(".sepa-splitter-*"))            # keine temporären Reste
    assert not w.btn_split.isEnabled()                          # kein zweites Aufteilen ohne neue Prüfung

    # Ausgabeordner öffnen
    assert w.btn_open.isEnabled()
    qtbot.mouseClick(w.btn_open, Qt.LeftButton)
    assert Path(rec.opened_urls[-1].toLocalFile()) == work

    # Protokoll
    qtbot.mouseClick(w.btn_log, Qt.LeftButton)
    assert "Aufteilung erfolgreich: 3 Dateien" in rec.log_texts[-1]
    assert "DE" not in "".join(l for l in rec.log_texts[-1].splitlines() if "IBAN" in l)
    assert (work / cfg.log_file).is_file()


def test_confirmation_declined_writes_nothing(qtbot, env):
    rec, work, cfg = env
    rec.question_answer = QMessageBox.No
    w = make_window(qtbot, cfg)
    w.set_file(str(work / "beispiel_008_08_1000tx_crlf.xml"))
    wait_idle(qtbot, w)
    assert w.table.rowCount() == 2 and w.btn_split.isEnabled()
    assert w.progress.value() == 0
    qtbot.mouseClick(w.btn_split, Qt.LeftButton)
    wait_idle(qtbot, w)
    assert not list(work.glob("beispiel_008_08_1000tx_crlf_*.xml"))
    assert w.btn_split.isEnabled()


def test_no_split_needed(qtbot, env):
    rec, work, cfg = env
    w = make_window(qtbot, cfg)
    w.set_file(str(work / "beispiel_008_02_998tx_keine_aufteilung.xml"))
    wait_idle(qtbot, w)
    assert w.table.rowCount() == 0
    assert not w.btn_split.isEnabled()
    assert "nicht" in w.res_note.text()


def test_invalid_file_shows_error_and_stays_usable(qtbot, env):
    rec, work, cfg = env
    bad = work / "kaputt.xml"
    bad.write_text("<Document><nicht-geschlossen></Document>", encoding="utf-8")
    w = make_window(qtbot, cfg)
    w.set_file(str(bad))
    wait_idle(qtbot, w)
    assert [m for m in rec.messages if m[0] == "critical"]
    assert w.btn_check.isEnabled() and w.btn_choose.isEnabled() and not w.btn_split.isEnabled()
    # Danach ist eine weitere Prüfung möglich (Thread wurde sauber beendet)
    w.set_file(str(work / "beispiel_008_02_2000tx.xml"))
    wait_idle(qtbot, w)
    assert w.table.rowCount() == 3


def test_start_dir_fallback_message(qtbot, env, tmp_path):
    rec, work, cfg = env
    shutil.rmtree(work)
    rec.dialog_result = ""          # Dialog abgebrochen
    w = make_window(qtbot, cfg)
    qtbot.mouseClick(w.btn_choose, Qt.LeftButton)
    assert Path(rec.dialog_args[1]) == tmp_path / "base"
    assert [m for m in rec.messages if m[1] == "Startordner"]
    assert w.path_edit.text() == ""
