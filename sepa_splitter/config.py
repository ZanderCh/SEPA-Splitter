"""Konfiguration über SEPA-Splitter.ini (liegt neben der Anwendung, nicht im Arbeitsverzeichnis)."""
from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .errors import ConfigError
from .paths import app_dir

INI_NAME = "SEPA-Splitter.ini"

DEFAULT_INI = """\
# ============================================================
# SEPA-Splitter – Konfiguration
# ============================================================
# Zeilen mit # sind Kommentare. Schlüssel sind unabhängig von Groß-/Kleinschreibung.
# Ungültige Werte werden gemeldet; es gilt dann der Standardwert.
# Fest im Programm und NICHT einstellbar (daher hier keine Einträge):
#   - Die Originaldatei wird nie verändert.
#   - Teildateien und Protokoll werden im Ordner der Originaldatei abgelegt.
#   - Prüfungen (XML, Struktur, Anzahl/Kontrollsummen) und die Originaltreue-Prüfung
#     der erzeugten Dateien laufen immer; geändert werden nur NbOfTxs, CtrlSum,
#     MsgId und PmtInfId, pain-Version und Formatierung bleiben erhalten.

# ------------------------------------------------------------
# Generelle Angaben
# ------------------------------------------------------------
[General]
# Maximale Transaktionen je Teildatei.
# Zulässig: ganze Zahl von 10 bis 99999. Sparkasse-Weboberfläche: 999.
# Beispiel: MaxTransactions = 999
# Default: 999
MaxTransactions = 999

# Datei sofort nach dem Auswählen prüfen.
# Mögliche Werte: true, false
# Default: true
CheckOnLoad = true

# Vor dem Aufteilen zusätzlich eine Sicherheitsabfrage anzeigen.
# Die Vorschau der geplanten Dateien erscheint immer; das Aufteilen startet
# nur durch ausdrücklichen Klick auf „Datei aufteilen“.
# Mögliche Werte: true, false
# Default: true
ConfirmBeforeSplit = true

# ------------------------------------------------------------
# Pfad-Festlegung
# ------------------------------------------------------------
[Paths]
# BASIS-PFAD
# Hauptordner für SEPA-Dateien. Unterhalb ergänzt das Programm
# automatisch das aktuelle Jahr und Quartal bzw. den Monat (siehe NameScheme).
# Leer = Benutzerverzeichnis. Relative Pfade gelten relativ zum Benutzerverzeichnis.
# Wirkt nur auf den Startordner des Öffnen-Dialogs, nie auf den Ausgabeort.
# Beispiele: BasePath = /home/user/Verein   |   BasePath = C:\\Verein\\Lastschriften
# Ergebnis (Quartal 3/2025): /home/user/Verein/2025/Q3
# Default: (leer)
BasePath =

# LETZTES VERZEICHNIS MERKEN
# true  = zuletzt verwendeten Ordner speichern
# false = nie speichern
# Default: true
RememberLastDirectory = true

# LETZTES VERZEICHNIS ÜBERSTEUERT BASIS-PFAD
# true  = gemerkter Ordner wird beim Start statt BasePath+NameScheme geöffnet
# false = immer BasePath + NameScheme
# Default: false
LastDirectoryOverridesBasePath = false

# NAMENSSCHEMA ZUR ERGÄNZUNG DES BASIS-PFADES
# Unterverzeichnisse unterhalb des Basis-Pfades. Trenner: unter Windows \\,
# unter Linux/macOS /. (Beides wird akzeptiert und plattformgerecht umgesetzt.)
# Platzhalter: JJJJ = Jahr vierstellig, JJ = Jahr zweistellig,
#              Qn = Quartal (Q1..Q4), Mnn = Monat (M01..M12)
# Gültige Beispiele: JJJJ/Qn, JJJJ/Mnn, JJ/Mnn, JJ/Qn, JJJJQn, JJQn, JJJJMnn
# Leer = kein Unterverzeichnis.
# Default: JJJJ/Qn
NameScheme = JJJJ/Qn

# ------------------------------------------------------------
# Ausgabedateien
# ------------------------------------------------------------
[Files]
# Trenner zwischen Dateiname und Suffix.
# Zulässig: 0 bis 3 Zeichen aus A-Z a-z 0-9 _ - .
# Beispiel: _  ->  SEPA_Lastschriften_a.xml
# Default: _
FilenameSeparator = _

# Suffix-Art. Mögliche Werte: letters (a, b, … z, aa, ab, …), numbers (01, 02, …)
# Default: letters
FilenameSuffixMode = letters

# Verhalten bei bereits vorhandenen Ausgabedateien.
# ask   = in der Oberfläche nachfragen (ohne Oberfläche: abbrechen)
# abort = abbrechen
# overwrite = vorhandene Ausgabedateien (nie das Original!) ersetzen
# Default: ask
OverwriteMode = ask

# ------------------------------------------------------------
# Oberfläche
# ------------------------------------------------------------
[GUI]
# Fenstergröße in Pixeln. Zulässig: Breite 640–4000, Höhe 480–3000.
# Default: 950 x 680
WindowWidth = 950
WindowHeight = 680

# Vorschau der geplanten Ausgabedateien anzeigen. Werte: true, false. Default: true
ShowPreview = true

# ------------------------------------------------------------
# Protokoll (wird im Ordner der bearbeiteten Datei abgelegt)
# ------------------------------------------------------------
[Logging]
# Protokoll schreiben. Werte: true, false. Default: true
Enabled = true

# Protokollstufe. Werte: DEBUG, INFO, WARNING, ERROR. Default: INFO
LogLevel = INFO

# Dateiname des Protokolls (nur Name, kein Pfad). Default: SEPA-Splitter.log
LogFile = SEPA-Splitter.log
"""

# Schlüssel älterer INI-Versionen. Die Regeln sind fest im Programm; nur ein Versuch, sie abzuschalten
# (Wert false), wird gemeldet. Neue INI-Dateien enthalten diese Schlüssel nicht mehr.
_LOCKED = ("ValidateXML", "ValidateControlSum", "UpdateMessageId", "UpdatePaymentInfoId",
           "PreservePainVersion", "PreserveOriginalFormatting", "VerifyOriginalIntegrity", "StrictMode")


@dataclass
class Config:
    max_transactions: int = 999
    check_on_load: bool = True
    confirm_before_split: bool = True
    base_path: str = ""
    remember_last_directory: bool = True
    last_directory_overrides_base_path: bool = False
    name_scheme: str = "JJJJ/Qn"
    filename_separator: str = "_"
    suffix_mode: str = "letters"
    overwrite_mode: str = "ask"
    window_width: int = 950
    window_height: int = 680
    show_preview: bool = True
    log_enabled: bool = True
    log_level: str = "INFO"
    log_file: str = "SEPA-Splitter.log"
    problems: List[str] = field(default_factory=list)   # Meldungen für den Anwender
    ini_path: Path = field(default_factory=lambda: app_dir() / INI_NAME)
    ini_created: bool = False


_SCHEME_OK = re.compile(r"^(?:JJJJ|JJ)(?:[/\\]?(?:Qn|Mnn))?$")
_SEP_OK = re.compile(r"^[A-Za-z0-9_.\-]{0,3}$")
_BOOL = {"true": True, "false": False, "1": True, "0": False, "ja": True, "nein": False, "yes": True, "no": False}


def load_config(ini_path: Path | None = None) -> Config:
    cfg = Config()
    path = Path(ini_path) if ini_path else app_dir() / INI_NAME
    cfg.ini_path = path
    if not path.exists():
        try:
            path.write_text(DEFAULT_INI, encoding="utf-8")
            cfg.ini_created = True
        except OSError as e:
            cfg.problems.append(
                f"Die Konfigurationsdatei „{path}“ fehlt und kann nicht angelegt werden ({e.strerror or e}). "
                f"Es gelten die Standardwerte.")
        return cfg
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=None, comment_prefixes=("#", ";"))
    try:
        cp.read_string(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        cfg.problems.append(f"Die Konfigurationsdatei „{path}“ ist nicht lesbar ({e}). Es gelten die Standardwerte.")
        return cfg

    def get(sec: str, key: str):
        return cp.get(sec, key).strip() if cp.has_option(sec, key) else None

    def boolean(sec: str, key: str, default: bool) -> bool:
        v = get(sec, key)
        if v is None or v == "":
            return default
        if v.lower() not in _BOOL:
            cfg.problems.append(f"[{sec}] {key}: „{v}“ ist ungültig (erlaubt: true/false). Standard: {str(default).lower()}.")
            return default
        return _BOOL[v.lower()]

    def integer(sec: str, key: str, default: int, lo: int, hi: int) -> int:
        v = get(sec, key)
        if v is None or v == "":
            return default
        if not v.isdigit() or not (lo <= int(v) <= hi):
            cfg.problems.append(f"[{sec}] {key}: „{v}“ ist ungültig (erlaubt: {lo}–{hi}). Standard: {default}.")
            return default
        return int(v)

    def choice(sec: str, key: str, default: str, allowed, upper=False) -> str:
        v = get(sec, key)
        if v is None or v == "":
            return default
        vv = v.upper() if upper else v.lower()
        if vv not in allowed:
            cfg.problems.append(f"[{sec}] {key}: „{v}“ ist ungültig (erlaubt: {', '.join(allowed)}). Standard: {default}.")
            return default
        return vv

    cfg.max_transactions = integer("General", "MaxTransactions", 999, 10, 99999)
    if cfg.max_transactions > 999:
        cfg.problems.append("[General] MaxTransactions ist größer als 999; die Sparkasse-Weboberfläche akzeptiert höchstens 999.")
    cfg.check_on_load = boolean("General", "CheckOnLoad", True)
    cfg.confirm_before_split = boolean("General", "ConfirmBeforeSplit", True)
    cfg.base_path = get("Paths", "BasePath") or ""
    cfg.remember_last_directory = boolean("Paths", "RememberLastDirectory", True)
    cfg.last_directory_overrides_base_path = boolean("Paths", "LastDirectoryOverridesBasePath", False)
    scheme = get("Paths", "NameScheme")
    if scheme is None:
        scheme = "JJJJ/Qn"
    if scheme != "" and not _SCHEME_OK.match(scheme):
        cfg.problems.append(f"[Paths] NameScheme: „{scheme}“ ist ungültig (z. B. JJJJ/Qn, JJJJ/Mnn, JJQn). Standard: JJJJ/Qn.")
        scheme = "JJJJ/Qn"
    cfg.name_scheme = scheme
    out = get("Files", "OutputDirectory")
    if out not in (None, "", "same_as_source"):
        cfg.problems.append("[Files] OutputDirectory ist nicht einstellbar und wird ignoriert: Teildateien werden immer im Ordner der Originaldatei abgelegt.")
    sep = get("Files", "FilenameSeparator")
    if sep is not None and not _SEP_OK.match(sep):
        cfg.problems.append(f"[Files] FilenameSeparator: „{sep}“ ist ungültig. Standard: _")
        sep = "_"
    cfg.filename_separator = "_" if sep is None else sep
    cfg.suffix_mode = choice("Files", "FilenameSuffixMode", "letters", ("letters", "numbers"))
    cfg.overwrite_mode = choice("Files", "OverwriteMode", "ask", ("ask", "abort", "overwrite"))
    if not boolean("Files", "PreserveOriginal", True):
        cfg.problems.append("[Files] PreserveOriginal ist nicht einstellbar und wird ignoriert: Das Original wird nie verändert.")
    for key in _LOCKED:
        if not boolean("SEPA", key, True):
            cfg.problems.append(f"[SEPA] {key} ist nicht einstellbar und wird ignoriert: Die Sicherheitsregel ist fest im Programm.")
    cfg.window_width = integer("GUI", "WindowWidth", 950, 640, 4000)
    cfg.window_height = integer("GUI", "WindowHeight", 680, 480, 3000)
    cfg.show_preview = boolean("GUI", "ShowPreview", True)
    cfg.log_enabled = boolean("Logging", "Enabled", True)
    cfg.log_level = choice("Logging", "LogLevel", "INFO", ("DEBUG", "INFO", "WARNING", "ERROR"), upper=True)
    lf = get("Logging", "LogFile") or "SEPA-Splitter.log"
    if "/" in lf or "\\" in lf or lf in (".", ".."):
        cfg.problems.append("[Logging] LogFile darf nur ein Dateiname sein. Standard: SEPA-Splitter.log")
        lf = "SEPA-Splitter.log"
    cfg.log_file = lf
    return cfg


# --------------------------------------------------------- Zuletzt verwendeter Ordner

def _state_path(cfg: Config) -> Path:
    return cfg.ini_path.with_name("SEPA-Splitter.state")


def load_last_dir(cfg: Config) -> str | None:
    try:
        t = _state_path(cfg).read_text(encoding="utf-8").strip()
        return t or None
    except OSError:
        return None


def save_last_dir(cfg: Config, directory: str) -> None:
    if not cfg.remember_last_directory:
        return
    try:
        _state_path(cfg).write_text(directory, encoding="utf-8")
    except OSError:
        pass  # nicht kritisch
