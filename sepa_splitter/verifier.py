"""Unabhängige Originaltreue-Prüfung.

Diese Prüfung benutzt NICHT den Scanner und NICHT die Planung aus splitter.py.
Sie vergleicht Original und Ausgabedateien auf zwei unabhängigen Wegen:

A) Semantisch (lxml): kanonisierte Transaktionen, Zahlungsgruppen-Metadaten,
   Kopfdaten, Anzahl- und Summenfelder, Kennungen.
B) Byte-/Zeilenebene: Transaktionsblöcke werden per eigenem Muster aus den Rohbytes
   geschnitten und bytegenau verglichen; der Rest (Residuum) darf sich nur durch das
   Entfernen ganzer Zeilen und die erlaubten Feldersetzungen unterscheiden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Sequence

from lxml import etree

from .analyzer import secure_parser, newline_style, detect_encoding, _NS_RE

ALLOWED_FIELDS = ("NbOfTxs", "CtrlSum", "MsgId", "PmtInfId")
_ID_RE = re.compile(r"^[A-Za-z0-9/\-?:().,'+ ]{1,35}$|^.{1,35}$", re.S)


@dataclass
class VerifyResult:
    structure_ok: bool = True
    fidelity_ok: bool = True
    messages: List[str] = field(default_factory=list)
    changes: List[str] = field(default_factory=list)   # dokumentierte zulässige Unterschiede

    def fail(self, text: str, structure: bool = False) -> None:
        self.messages.append(text)
        self.fidelity_ok = False
        if structure:
            self.structure_ok = False

    @property
    def ok(self) -> bool:
        return self.structure_ok and self.fidelity_ok


def _blocks(data: bytes, local: str) -> List[bytes]:
    pat = re.compile(rb"<(?:[A-Za-z_][\w.\-]*:)?" + local.encode() + rb"[\s>/].*?</(?:[A-Za-z_][\w.\-]*:)?" +
                     local.encode() + rb"\s*>", re.S)
    return [m.group(0) for m in pat.finditer(data)]


def _strip_blocks(data: bytes, local: str) -> bytes:
    pat = re.compile(rb"<(?:[A-Za-z_][\w.\-]*:)?" + local.encode() + rb"[\s>/].*?</(?:[A-Za-z_][\w.\-]*:)?" +
                     local.encode() + rb"\s*>", re.S)
    return pat.sub(b"", data)


def _c14n(el) -> bytes:
    return etree.tostring(el, method="c14n")


def _blank_fields(el, ns: str) -> bytes:
    """Kanonische Form mit geleerten Feldern, die ändern dürfen; Transaktionen entfernt."""
    import copy
    c = copy.deepcopy(el)
    for tx in c.xpath(".//p:DrctDbtTxInf", namespaces={"p": ns}):
        tx.getparent().remove(tx)
    for name in ALLOWED_FIELDS:
        for f in c.xpath(f".//p:{name}", namespaces={"p": ns}):
            f.text = ""
    # Reiner Whitespace ist hier ausgenommen (beim Entfernen von Elementen entfällt ihr Zwischenraum);
    # die Whitespace-Treue wird separat auf Byte-/Zeilenebene geprüft (B).
    for e in c.iter():
        if e.text is not None and not e.text.strip():
            e.text = None
        if e.tail is not None and not e.tail.strip():
            e.tail = None
    return etree.tostring(c, method="c14n", with_comments=False)


def verify(original: bytes, outputs: Sequence[bytes], max_tx: int) -> VerifyResult:
    r = VerifyResult()
    try:
        otree = etree.fromstring(original, parser=secure_parser()).getroottree()
    except etree.XMLSyntaxError as e:
        r.fail(f"Original nicht lesbar: {e}", True)
        return r
    ns = etree.QName(otree.getroot()).namespace
    version = _NS_RE.match(ns).group(1)
    P = {"p": ns}
    o_tx = otree.getroot().xpath("//p:DrctDbtTxInf", namespaces=P)
    o_tx_c14n = [_c14n(t) for t in o_tx]
    o_pmt = otree.getroot().xpath("//p:PmtInf", namespaces=P)
    o_hdr = otree.getroot().xpath("//p:GrpHdr", namespaces=P)[0]
    o_hdr_blank = _blank_fields(o_hdr, ns)
    o_pmt_blank = [_blank_fields(p, ns) for p in o_pmt]

    seen_c14n: List[bytes] = []
    seen_raw: List[bytes] = []
    all_msgids, all_files_count = set(), 0
    orig_raw_tx = _blocks(original, "DrctDbtTxInf")
    if len(orig_raw_tx) != len(o_tx):
        r.fail("Prüfroutine: Zählung der Rohblöcke im Original stimmt nicht mit dem XML-Parser überein.")
        return r
    o_decl = original[:original.find(b"?>") + 2] if original.lstrip().startswith(b"<?xml") else b""
    o_nl = newline_style(original)
    o_resid = _strip_blocks(original, "DrctDbtTxInf")

    for fi, out in enumerate(outputs, 1):
        tag = f"Datei {fi}"
        try:
            t = etree.fromstring(out, parser=secure_parser()).getroottree()
        except etree.XMLSyntaxError as e:
            r.fail(f"{tag}: kein wohlgeformtes XML ({e})", True)
            continue
        root = t.getroot()
        if etree.QName(root).namespace != ns:
            r.fail(f"{tag}: pain-Version/Namespace verändert.", True)
            continue
        if root.nsmap != otree.getroot().nsmap or root.prefix != otree.getroot().prefix:
            r.fail(f"{tag}: Namespace-Deklarationen verändert.")
        if out.startswith(b"\xef\xbb\xbf") != original.startswith(b"\xef\xbb\xbf"):
            r.fail(f"{tag}: Byte-Order-Mark verändert.")
        decl = out[:out.find(b"?>") + 2] if out.lstrip().startswith(b"<?xml") else b""
        if decl != o_decl:
            r.fail(f"{tag}: XML-Deklaration verändert.")
        if newline_style(out) != o_nl:
            r.fail(f"{tag}: Zeilenumbruch-Stil verändert.")
        if detect_encoding(out) != detect_encoding(original):
            r.fail(f"{tag}: Zeichenkodierung verändert.")
        if out.endswith((b"\n", b"\r")) != original.endswith((b"\n", b"\r")):
            r.fail(f"{tag}: Abschluss der Datei (Zeilenende) verändert.")

        # --- A) semantisch
        txs = root.xpath("//p:DrctDbtTxInf", namespaces=P)
        if len(txs) > max_tx:
            r.fail(f"{tag}: enthält {len(txs)} Transaktionen (Maximum {max_tx}).")
        seen_c14n += [_c14n(x) for x in txs]
        hdr = root.xpath("//p:GrpHdr", namespaces=P)
        if len(hdr) != 1 or _blank_fields(hdr[0], ns) != o_hdr_blank:
            r.fail(f"{tag}: GrpHdr unterscheidet sich in unzulässigen Teilen.")
            continue
        hdr = hdr[0]
        nb = hdr.find(f"{{{ns}}}NbOfTxs")
        if nb is None or (nb.text or "").strip() != str(len(txs)):
            r.fail(f"{tag}: GrpHdr/NbOfTxs ist nicht korrekt.", True)
        total = Decimal(0)
        for x in txs:
            total += Decimal((x.find(f"{{{ns}}}InstdAmt").text or "0").strip())
        cs = hdr.find(f"{{{ns}}}CtrlSum")
        o_cs = o_hdr.find(f"{{{ns}}}CtrlSum")
        if (cs is None) != (o_cs is None):
            r.fail(f"{tag}: Vorhandensein von GrpHdr/CtrlSum verändert.")
        elif cs is not None and Decimal((cs.text or "").strip()) != total:
            r.fail(f"{tag}: GrpHdr/CtrlSum ist nicht korrekt.", True)
        elif cs is not None and len((cs.text or "").strip().partition(".")[2]) < len((o_cs.text or "").strip().partition(".")[2]):
            r.fail(f"{tag}: Nachkommastellen von GrpHdr/CtrlSum weichen vom Original ab.")
        mid = (hdr.find(f"{{{ns}}}MsgId").text or "").strip()
        if mid in all_msgids or not (1 <= len(mid) <= 35):
            r.fail(f"{tag}: MsgId „{mid}“ nicht eindeutig oder zu lang.", True)
        all_msgids.add(mid)
        pmts = root.xpath("//p:PmtInf", namespaces=P)
        ids = set()
        pos_in_orig = -1
        for p in pmts:
            blank = _blank_fields(p, ns)
            nxt = None
            for k in range(pos_in_orig + 1, len(o_pmt_blank)):
                if o_pmt_blank[k] == blank:
                    nxt = k
                    break
            if nxt is None:
                r.fail(f"{tag}: PmtInf-Metadaten unterscheiden sich vom Original oder Reihenfolge verändert.")
                continue
            pos_in_orig = nxt
            ptx = p.xpath("p:DrctDbtTxInf", namespaces=P)
            if not ptx:
                r.fail(f"{tag}: leerer PmtInf-Block vorhanden.")
            pid = (p.find(f"{{{ns}}}PmtInfId").text or "").strip()
            if pid in ids or not (1 <= len(pid) <= 35):
                r.fail(f"{tag}: PmtInfId „{pid}“ nicht eindeutig oder ungültige Länge.", True)
            ids.add(pid)
            pnb = p.find(f"{{{ns}}}NbOfTxs")
            if pnb is not None and (pnb.text or "").strip() != str(len(ptx)):
                r.fail(f"{tag}: PmtInf/NbOfTxs nicht korrekt.", True)
            pcs = p.find(f"{{{ns}}}CtrlSum")
            if pcs is not None:
                s = sum((Decimal((x.find(f"{{{ns}}}InstdAmt").text or "0").strip()) for x in ptx), Decimal(0))
                if Decimal((pcs.text or "").strip()) != s:
                    r.fail(f"{tag}: PmtInf/CtrlSum nicht korrekt.", True)

        # --- B) Byte-/Zeilenebene
        raw = _blocks(out, "DrctDbtTxInf")
        if len(raw) != len(txs):
            r.fail(f"{tag}: Prüfroutine: Zählung der Rohblöcke weicht ab.")
        seen_raw += raw
        resid = _strip_blocks(out, "DrctDbtTxInf")
        _check_residual(o_resid, resid, tag, r)
        r.changes.append(f"{tag}: {len(txs)} Transaktionen, MsgId „{mid}“, PmtInfId {sorted(ids)}")

    if seen_c14n != o_tx_c14n:
        r.fail("Die Transaktionen aller Ausgabedateien ergeben nicht exakt die Originaltransaktionen "
               "(fehlend, doppelt, verändert oder andere Reihenfolge).", True)
    if seen_raw != orig_raw_tx:
        r.fail("Die Transaktionsblöcke sind auf Byte-Ebene nicht identisch zum Original.")
    if len(outputs) < 2:
        r.fail("Es wurden weniger als zwei Ausgabedateien geprüft.")
    return r


_FIELD_LINE = re.compile(rb"<(?:[\w.\-]+:)?(NbOfTxs|CtrlSum|MsgId|PmtInfId)\b")


def _lines(b: bytes) -> List[bytes]:
    return [l for l in b.splitlines(keepends=True) if l.strip()]


def _norm(line: bytes) -> bytes:
    """Feldzeilen der erlaubten Felder: Inhalt neutralisieren, Rest (Tags, Einrückung, Zeilenende) bleibt."""
    if _FIELD_LINE.search(line):
        return re.sub(rb">[^<]*<", b"><", line, count=1)
    return line


def _check_residual(orig: bytes, out: bytes, tag: str, r: VerifyResult) -> None:
    """Residuum (ohne Transaktionen): Die Zeilen der Ausgabe müssen – bis auf den Inhalt der
    erlaubten Felder – eine geordnete Teilfolge der Originalzeilen sein (nur Löschungen,
    keine Einfügungen, keine sonstigen Änderungen). Leere Zeilen bleiben unberücksichtigt."""
    a = [_norm(l) for l in _lines(orig)]
    b = [_norm(l) for l in _lines(out)]
    i = 0
    for k, line in enumerate(b):
        while i < len(a) and a[i] != line:
            i += 1
        if i == len(a):
            r.fail(f"{tag}: Unzulässige Änderung oder Einfügung bei Zeile {k + 1} des Residuums: {line.strip()[:70]!r}")
            return
        i += 1
