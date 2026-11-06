"""Analyse und Prüfung einer SEPA-Lastschriftdatei (pain.008.001.xx).

Ablauf: Rohbytes lesen -> Sicherheitsvorprüfung (kein DOCTYPE) -> lxml-Wohlgeformtheit ->
Version über Namespace -> Strukturprüfung (eingebaut + optional XSD) ->
positionsgenauer Elementbaum (xmlscan) -> Zählung/Summenprüfung.
"""
from __future__ import annotations

import codecs
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lxml import etree

from . import xmlscan
from .errors import InputError, UnsupportedVersionError, ValidationError, FidelityError
from .paths import schema_dir

SUPPORTED_VERSIONS = ("pain.008.001.02", "pain.008.001.08")
_NS_RE = re.compile(r"^urn:iso:std:iso:20022:tech:xsd:(pain\.\d{3}\.\d{3}\.\d{2})$")
_AMOUNT_RE = re.compile(r"^\d{1,18}(\.\d{1,5})?$")
_ENC_RE = re.compile(rb"^\s*<\?xml[^>]*?encoding\s*=\s*[\"']([A-Za-z0-9._\-]+)[\"']")
_ASCII_COMPATIBLE = {
    "utf-8": "utf-8", "utf8": "utf-8", "us-ascii": "ascii", "ascii": "ascii",
    "iso-8859-1": "iso-8859-1", "latin-1": "iso-8859-1", "latin1": "iso-8859-1",
    "iso-8859-15": "iso-8859-15", "windows-1252": "cp1252", "cp1252": "cp1252",
}


@dataclass
class Issue:
    level: str      # "error" | "warning" | "info"
    text: str


@dataclass
class Tx:
    node: xmlscan.Node
    amount: Decimal
    ccy: str


@dataclass
class PmtInf:
    node: xmlscan.Node
    id_node: xmlscan.Node
    id_text: str
    nb_node: Optional[xmlscan.Node]
    ctrl_node: Optional[xmlscan.Node]
    txs: List[Tx]
    due_date: str = ""
    seq_type: str = ""
    first_tx_index: int = 0       # globaler Index der ersten Transaktion


@dataclass
class SepaDocument:
    path: Path
    data: bytes
    encoding: str
    newline: str
    version: str
    ns: str
    root: xmlscan.Node
    grphdr: xmlscan.Node
    msgid_node: xmlscan.Node
    msgid: str
    nb_node: xmlscan.Node
    ctrl_node: Optional[xmlscan.Node]
    pmtinfs: List[PmtInf]
    currency: str
    total_tx: int
    total_sum: Decimal
    declared_nb: int
    declared_sum: Optional[Decimal]
    issues: List[Issue] = field(default_factory=list)
    schema_status: str = "nicht geprüft"
    structure_ok: bool = False
    sums_ok: bool = False

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors


def secure_parser() -> etree.XMLParser:
    return etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                           dtd_validation=False, huge_tree=True, remove_blank_text=False,
                           remove_comments=False, remove_pis=False)


def detect_encoding(data: bytes) -> str:
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE, codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise InputError("Die Datei ist UTF-16/UTF-32-kodiert. Unterstützt werden nur "
                         "ASCII-kompatible Kodierungen (SEPA verlangt UTF-8).")
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8"
    m = _ENC_RE.match(data[:512])
    if not m:
        return "utf-8"
    name = m.group(1).decode("ascii").lower()
    if name not in _ASCII_COMPATIBLE:
        raise InputError(f"Die Zeichenkodierung „{name}“ wird nicht unterstützt "
                         f"(unterstützt: UTF-8, ISO-8859-1/-15, Windows-1252, ASCII).")
    return _ASCII_COMPATIBLE[name]


def newline_style(data: bytes) -> str:
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    cr = data.count(b"\r") - crlf
    if crlf and not lf and not cr:
        return "CRLF"
    if lf and not crlf and not cr:
        return "LF"
    if not (crlf or lf or cr):
        return "keine"
    return "gemischt"


def read_file(path: Path) -> bytes:
    path = Path(path)
    if not path.exists():
        raise InputError(f"Die Datei „{path}“ existiert nicht.")
    if not path.is_file():
        raise InputError(f"„{path}“ ist keine Datei.")
    try:
        return path.read_bytes()
    except OSError as e:
        raise InputError(f"Die Datei „{path}“ kann nicht gelesen werden: {e.strerror or e}") from e


def _text(el) -> str:
    return (el.text or "").strip() if el is not None else ""


def _builtin_structure_check(tree, ns: str, version: str, issues: List[Issue]) -> None:
    """Eingebaute Strukturprüfung der für den Splitter relevanten Pflichtelemente."""
    X = lambda el, p: el.xpath(p, namespaces={"p": ns})  # noqa: E731
    root = tree.getroot()
    if etree.QName(root).localname != "Document":
        issues.append(Issue("error", "Wurzelelement ist nicht „Document“."))
        return
    init = X(root, "p:CstmrDrctDbtInitn")
    if len(init) != 1 or len([c for c in root if isinstance(c.tag, str)]) != 1:
        issues.append(Issue("error", "Es muss genau ein Element „CstmrDrctDbtInitn“ unterhalb von „Document“ stehen."))
        return
    init = init[0]
    hdrs = X(init, "p:GrpHdr")
    if len(hdrs) != 1:
        issues.append(Issue("error", "Es muss genau ein „GrpHdr“ vorhanden sein."))
        return
    hdr = hdrs[0]
    for req in ("MsgId", "CreDtTm", "NbOfTxs", "InitgPty"):
        if len(X(hdr, f"p:{req}")) != 1:
            issues.append(Issue("error", f"GrpHdr/{req} fehlt oder ist mehrfach vorhanden."))
    pmts = X(init, "p:PmtInf")
    if not pmts:
        issues.append(Issue("error", "Es ist kein „PmtInf“-Block vorhanden."))
    allowed_fin = {
        "pain.008.001.02": {"BIC", "ClrSysMmbId", "Nm", "PstlAdr", "Othr"},
        "pain.008.001.08": {"BICFI", "ClrSysMmbId", "LEI", "Nm", "PstlAdr", "Othr"},
    }[version]
    for n, p in enumerate(pmts, 1):
        for req in ("PmtInfId", "PmtMtd", "PmtTpInf", "ReqdColltnDt", "Cdtr", "CdtrAcct", "CdtrAgt"):
            if len(X(p, f"p:{req}")) != 1:
                issues.append(Issue("error", f"PmtInf Nr. {n}: Element „{req}“ fehlt oder ist mehrfach vorhanden."))
        if _text((X(p, "p:PmtMtd") or [None])[0]) != "DD":
            issues.append(Issue("error", f"PmtInf Nr. {n}: PmtMtd muss „DD“ sein."))
        txs = X(p, "p:DrctDbtTxInf")
        if not txs:
            issues.append(Issue("error", f"PmtInf Nr. {n}: enthält keine Transaktion."))
        for fin in X(p, ".//p:FinInstnId"):
            for ch in fin:
                if not isinstance(ch.tag, str):
                    continue
                if etree.QName(ch).localname not in allowed_fin:
                    issues.append(Issue("error",
                        f"PmtInf Nr. {n}: Element „{etree.QName(ch).localname}“ in FinInstnId ist in {version} nicht zulässig "
                        f"(Hinweis: BIC heißt in .08 „BICFI“)."))
        for t, tx in enumerate(txs, 1):
            for req, path in (("PmtId/EndToEndId", "p:PmtId/p:EndToEndId"), ("InstdAmt", "p:InstdAmt"),
                              ("DrctDbtTx", "p:DrctDbtTx"), ("Dbtr", "p:Dbtr"), ("DbtrAcct", "p:DbtrAcct")):
                if len(X(tx, path)) != 1:
                    issues.append(Issue("error", f"PmtInf Nr. {n}, Transaktion {t}: „{req}“ fehlt oder ist mehrfach vorhanden."))
            if len(issues) > 200:
                issues.append(Issue("error", "Zu viele Strukturfehler – weitere Meldungen unterdrückt."))
                return


def _xsd_check(tree, version: str, issues: List[Issue]) -> str:
    xsd = schema_dir() / f"{version}.xsd"
    if not xsd.is_file():
        return "XSD-Datei fehlt – nur eingebaute Strukturprüfung"
    try:
        schema = etree.XMLSchema(etree.parse(str(xsd), parser=secure_parser()))
    except (etree.XMLSchemaParseError, OSError, etree.XMLSyntaxError) as e:
        issues.append(Issue("error", f"Die Schemadatei {xsd.name} ist nicht lesbar: {e}"))
        return "Schemadatei defekt"
    if schema.validate(tree):
        return f"gültig gegen {version}.xsd"
    for err in list(schema.error_log)[:20]:
        issues.append(Issue("error", f"Schemafehler Zeile {err.line}: {err.message}"))
    return f"UNGÜLTIG gegen {version}.xsd"


def analyze(path: Path, validate_schema: bool = True, validate_control_sum: bool = True) -> SepaDocument:
    """Liest und prüft eine Datei. Wirft bei nicht verarbeitbaren Dateien eine Fehlerklasse,
    liefert sonst ein SepaDocument; fachliche Befunde stehen in ``doc.issues``."""
    path = Path(path)
    data = read_file(path)
    if not data.strip():
        raise InputError("Die Datei ist leer.")
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise InputError("Die Datei enthält eine DOCTYPE-/ENTITY-Deklaration und wird aus "
                         "Sicherheitsgründen (XXE-Schutz) nicht verarbeitet.")
    encoding = detect_encoding(data)
    try:
        tree = etree.fromstring(data, parser=secure_parser()).getroottree()
    except etree.XMLSyntaxError as e:
        raise InputError(f"Die Datei ist kein wohlgeformtes XML: {e}") from e
    root_el = tree.getroot()
    m = _NS_RE.match(etree.QName(root_el).namespace or "")
    if not m:
        raise UnsupportedVersionError(
            "Der XML-Namespace entspricht keiner ISO-20022-Nachricht (urn:iso:std:iso:20022:tech:xsd:pain…). "
            "Die Datei wird nicht verarbeitet.")
    version = m.group(1)
    ns = etree.QName(root_el).namespace
    if version not in SUPPORTED_VERSIONS:
        raise UnsupportedVersionError(
            f"Die Nachrichtenversion „{version}“ wird nicht unterstützt (unterstützt: "
            f"{', '.join(SUPPORTED_VERSIONS)}). Es erfolgt keine spekulative Verarbeitung.")

    issues: List[Issue] = []
    _builtin_structure_check(tree, ns, version, issues)
    structure_errors_before_xsd = len([i for i in issues if i.level == "error"])
    schema_status = "nicht geprüft (ValidateSchema=false)"
    if validate_schema:
        schema_status = _xsd_check(tree, version, issues)
    if structure_errors_before_xsd:
        # Ohne gültige Grundstruktur ist keine Positionsanalyse sinnvoll.
        raise ValidationError("Die Struktur der Datei ist ungültig:\n" + "\n".join(
            f"• {i.text}" for i in issues if i.level == "error")[:3000])

    try:
        scan_root = xmlscan.scan(data)
    except FidelityError:
        raise
    init = scan_root.first(ns, "CstmrDrctDbtInitn")
    grphdr = init.first(ns, "GrpHdr")
    tx_lxml = tree.getroot().xpath("//p:DrctDbtTxInf", namespaces={"p": ns})
    tx_lxml_iter = iter(tx_lxml)

    def leaf(node: xmlscan.Node, name: str, required: bool = True) -> Optional[xmlscan.Node]:
        n = node.first(ns, name)
        if n is None and required:
            raise ValidationError(f"Element „{name}“ fehlt.")
        if n is not None and not n.has_only_text():
            raise FidelityError(f"Element „{name}“ hat keinen reinen Textinhalt; Änderung wäre nicht originalgetreu möglich.")
        return n

    msgid_node = leaf(grphdr, "MsgId")
    nb_node = leaf(grphdr, "NbOfTxs")
    ctrl_node = leaf(grphdr, "CtrlSum", required=False)

    pmtinfs: List[PmtInf] = []
    idx = 0
    currencies = set()
    total = Decimal(0)
    for pn in init.find(ns, "PmtInf"):
        id_node = leaf(pn, "PmtInfId")
        nbn = leaf(pn, "NbOfTxs", required=False)
        csn = leaf(pn, "CtrlSum", required=False)
        txs: List[Tx] = []
        for tn in pn.find(ns, "DrctDbtTxInf"):
            el = next(tx_lxml_iter)
            amt_el = el.find(f"{{{ns}}}InstdAmt")
            amt_txt = _text(amt_el)
            if not _AMOUNT_RE.match(amt_txt):
                issues.append(Issue("error", f"Ungültiger Betrag „{amt_txt}“ in Transaktion {idx + len(txs) + 1}."))
                amount = Decimal(0)
            else:
                amount = Decimal(amt_txt)
                if amount <= 0:
                    issues.append(Issue("error", f"Betrag ≤ 0 in Transaktion {idx + len(txs) + 1}."))
            ccy = amt_el.get("Ccy", "") if amt_el is not None else ""
            currencies.add(ccy)
            txs.append(Tx(tn, amount, ccy))
        due = _text(pn_el_first(tree, ns, len(pmtinfs), "ReqdColltnDt"))
        seq = _text(pn_el_first(tree, ns, len(pmtinfs), "PmtTpInf/p:SeqTp", raw=True))
        pmtinfs.append(PmtInf(pn, id_node, xmlscan.text_of(data, id_node, encoding), nbn, csn, txs,
                              due_date=due, seq_type=seq, first_tx_index=idx))
        idx += len(txs)
        total += sum((t.amount for t in txs), Decimal(0))
    if len(currencies) > 1:
        issues.append(Issue("error", "Die Datei enthält mehrere Währungen; eine Kontrollsumme ist nicht eindeutig."))
    currency = next(iter(currencies)) if currencies else ""

    # Plausibilität von Anzahl- und Summenfeldern (Originalwerte, keine stillschweigende Korrektur)
    sums_ok = True
    def parse_int(node: xmlscan.Node, label: str) -> int:
        t = xmlscan.text_of(data, node, encoding)
        if not t.isdigit():
            raise ValidationError(f"{label} enthält keine gültige Zahl („{t}“).")
        return int(t)
    def parse_dec(node: xmlscan.Node, label: str) -> Decimal:
        t = xmlscan.text_of(data, node, encoding)
        try:
            return Decimal(t)
        except InvalidOperation:
            raise ValidationError(f"{label} enthält keinen gültigen Betrag („{t}“).")

    declared_nb = parse_int(nb_node, "GrpHdr/NbOfTxs")
    if declared_nb != idx:
        sums_ok = False
        issues.append(Issue("error", f"GrpHdr/NbOfTxs ({declared_nb}) stimmt nicht mit der tatsächlichen Anzahl ({idx}) überein."))
    declared_sum = None
    if ctrl_node is not None:
        declared_sum = parse_dec(ctrl_node, "GrpHdr/CtrlSum")
        if validate_control_sum and declared_sum != total:
            sums_ok = False
            issues.append(Issue("error", f"GrpHdr/CtrlSum ({declared_sum}) weicht von der berechneten Summe ({total}) ab."))
    seen_ids = set()
    for n, p in enumerate(pmtinfs, 1):
        if p.id_text in seen_ids:
            issues.append(Issue("error", f"PmtInfId „{p.id_text}“ kommt mehrfach in der Originaldatei vor."))
        seen_ids.add(p.id_text)
        if len(p.id_text) > 35:
            issues.append(Issue("error", f"PmtInfId von PmtInf Nr. {n} ist länger als 35 Zeichen."))
        if p.nb_node is not None and parse_int(p.nb_node, f"PmtInf Nr. {n}/NbOfTxs") != len(p.txs):
            sums_ok = False
            issues.append(Issue("error", f"PmtInf Nr. {n}: NbOfTxs stimmt nicht mit der Anzahl der Transaktionen überein."))
        if p.ctrl_node is not None and validate_control_sum:
            s = sum((t.amount for t in p.txs), Decimal(0))
            if parse_dec(p.ctrl_node, f"PmtInf Nr. {n}/CtrlSum") != s:
                sums_ok = False
                issues.append(Issue("error", f"PmtInf Nr. {n}: CtrlSum weicht von der berechneten Summe ({s}) ab."))
    msgid = xmlscan.text_of(data, msgid_node, encoding)
    if len(msgid) > 35:
        issues.append(Issue("error", "GrpHdr/MsgId ist länger als 35 Zeichen."))
    if next(tx_lxml_iter, None) is not None:
        raise FidelityError("Abweichende Transaktionszählung zwischen XML-Parser und Positionsanalyse.")

    doc = SepaDocument(
        path=path, data=data, encoding=encoding, newline=newline_style(data), version=version, ns=ns,
        root=scan_root, grphdr=grphdr, msgid_node=msgid_node, msgid=msgid, nb_node=nb_node,
        ctrl_node=ctrl_node, pmtinfs=pmtinfs, currency=currency, total_tx=idx, total_sum=total,
        declared_nb=declared_nb, declared_sum=declared_sum, issues=issues, schema_status=schema_status,
        sums_ok=sums_ok)
    doc.structure_ok = not any(i.level == "error" and not i.text.startswith(("GrpHdr/NbOfTxs", "GrpHdr/CtrlSum", "PmtInf Nr."))
                               for i in issues) and "UNGÜLTIG" not in schema_status
    return doc


def pn_el_first(tree, ns: str, index: int, relpath: str, raw: bool = False):
    """Hilfsfunktion: erstes Element ``relpath`` im index-ten PmtInf (per lxml)."""
    pm = tree.getroot().xpath("p:CstmrDrctDbtInitn/p:PmtInf", namespaces={"p": ns})[index]
    path = relpath if raw else "p:" + relpath
    if not raw and "/" in relpath:
        path = "/".join("p:" + s for s in relpath.split("/"))
    found = pm.xpath(path if path.startswith("p:") else "p:" + path, namespaces={"p": ns})
    return found[0] if found else None
