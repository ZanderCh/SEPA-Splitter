"""Aufteilungsplanung und bytebewahrende Erzeugung der Teildateien.

Prinzip: Jede Ausgabedatei entsteht aus den Originalbytes durch eine Liste von
Kantenänderungen (Entfernen von Bytebereichen, Ersetzen von Feldinhalten). Alles andere
wird unverändert kopiert. Es gibt kein Neu-Serialisieren und kein Pretty-Printing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from . import xmlscan
from .analyzer import SepaDocument
from .errors import FidelityError, ValidationError

MAX_ID_LEN = 35


# ------------------------------------------------------------------ Planung

def split_counts(total: int, max_tx: int) -> List[int]:
    """Gleichmäßige Verteilung; die ersten ``rest`` Dateien erhalten je eine Transaktion mehr."""
    if max_tx < 1:
        raise ValueError("max_tx muss ≥ 1 sein")
    if total <= max_tx:
        return [total]
    n_files = math.ceil(total / max_tx)
    base, rest = divmod(total, n_files)
    return [base + 1 if i < rest else base for i in range(n_files)]


def letter_suffix(index: int) -> str:
    """0 -> a, 25 -> z, 26 -> aa, 27 -> ab, ... (bijektiv, wie Tabellenspalten)."""
    s = ""
    n = index + 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(ord("a") + r) + s
    return s


def number_suffix(index: int, total: int) -> str:
    return str(index + 1).zfill(max(2, len(str(total))))


@dataclass
class PartPlan:
    index: int
    suffix: str
    lo: int                      # erster globaler Transaktionsindex (inkl.)
    hi: int                      # letzter + 1
    total: Decimal
    msgid: str = ""
    pmtinf_ids: Dict[int, str] = field(default_factory=dict)   # PmtInf-Index -> neue ID
    pmtinf_counts: Dict[int, int] = field(default_factory=dict)
    pmtinf_sums: Dict[int, Decimal] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return self.hi - self.lo


def fit_id(base: str, suffix: str, used: Set[str], salt: int = 0) -> str:
    """Hängt ``suffix`` an ``base`` an, ohne 35 Zeichen zu überschreiten und ohne Kollision.

    Zu lange Kennungen werden am Ende gekürzt (deterministisch). Bei Kollision wird eine
    zweistellige laufende Nummer vor dem Suffix eingefügt (z. B. ``…01a``)."""
    cand = (base[:MAX_ID_LEN - len(suffix)] + suffix) if len(base) + len(suffix) > MAX_ID_LEN else base + suffix
    n = 0
    while cand in used:
        n += 1
        tag = f"{n:02d}"
        cand = base[:MAX_ID_LEN - len(suffix) - len(tag)] + tag + suffix
        if n > 99:
            raise ValidationError("Es kann keine eindeutige Kennung gebildet werden.")
    return cand


def make_plan(doc: SepaDocument, max_tx: int, suffix_mode: str = "letters") -> List[PartPlan]:
    counts = split_counts(doc.total_tx, max_tx)
    if len(counts) == 1:
        return []
    amounts = [t.amount for p in doc.pmtinfs for t in p.txs]
    plans: List[PartPlan] = []
    lo = 0
    used_msg: Set[str] = {doc.msgid}
    for i, c in enumerate(counts):
        suffix = letter_suffix(i) if suffix_mode == "letters" else number_suffix(i, len(counts))
        plan = PartPlan(i, suffix, lo, lo + c, sum(amounts[lo:lo + c], Decimal(0)))
        plan.msgid = fit_id(doc.msgid, suffix, used_msg)
        used_msg.add(plan.msgid)
        used_pmt: Set[str] = set()
        for pi, p in enumerate(doc.pmtinfs):
            a, b = max(lo, p.first_tx_index), min(lo + c, p.first_tx_index + len(p.txs))
            if a >= b:
                continue
            plan.pmtinf_counts[pi] = b - a
            plan.pmtinf_sums[pi] = sum(amounts[a:b], Decimal(0))
            new_id = fit_id(p.id_text, suffix, used_pmt)
            used_pmt.add(new_id)
            plan.pmtinf_ids[pi] = new_id
        plans.append(plan)
        lo += c
    return plans


# ------------------------------------------------------------------ Formatierung

def _places(txt: str) -> int:
    return len(txt.split(".")[1]) if "." in txt else 0


def format_like(original_text: str, value: Decimal, min_places: int) -> str:
    """Formatiert ``value`` mit der Nachkommastellenzahl des Originalfeldes (mind. ``min_places``)."""
    places = max(_places(original_text.strip()), min_places)
    return f"{value.quantize(Decimal(1).scaleb(-places)):f}"


# ------------------------------------------------------------------ Erzeugung

def _replace_leaf(edits: list, data: bytes, node: xmlscan.Node, new_text: str, encoding: str) -> None:
    if not node.has_only_text():
        raise FidelityError("Feld hat keinen reinen Textinhalt – Ersetzung nicht originalgetreu möglich.")
    edits.append((node.open_end, node.close_start, xmlscan.escape_xml(new_text).encode(encoding)))


def build_part(doc: SepaDocument, plan: PartPlan) -> bytes:
    data = doc.data
    enc = doc.encoding
    edits: List[Tuple[int, int, bytes]] = []
    amounts_places = max((_places(str(t.amount)) for p in doc.pmtinfs for t in p.txs), default=0)

    def remove(node: xmlscan.Node) -> None:
        edits.append((xmlscan.leading_ws_start(data, node.start), node.end, b""))

    for pi, p in enumerate(doc.pmtinfs):
        if pi not in plan.pmtinf_ids:
            remove(p.node)
            continue
        for ti, t in enumerate(p.txs):
            g = p.first_tx_index + ti
            if not (plan.lo <= g < plan.hi):
                remove(t.node)
        _replace_leaf(edits, data, p.id_node, plan.pmtinf_ids[pi], enc)
        if p.nb_node is not None:
            _replace_leaf(edits, data, p.nb_node, str(plan.pmtinf_counts[pi]), enc)
        if p.ctrl_node is not None:
            old = xmlscan.text_of(data, p.ctrl_node, enc)
            _replace_leaf(edits, data, p.ctrl_node, format_like(old, plan.pmtinf_sums[pi], amounts_places), enc)

    _replace_leaf(edits, data, doc.msgid_node, plan.msgid, enc)
    _replace_leaf(edits, data, doc.nb_node, str(plan.count), enc)
    if doc.ctrl_node is not None:
        old = xmlscan.text_of(data, doc.ctrl_node, enc)
        _replace_leaf(edits, data, doc.ctrl_node, format_like(old, plan.total, amounts_places), enc)

    edits.sort(key=lambda e: (e[0], e[1]))
    out = bytearray()
    pos = 0
    for s, e, rep in edits:
        if s < pos:
            raise FidelityError("Interner Fehler: überlappende Änderungen.")
        out += data[pos:s]
        out += rep
        pos = e
    out += data[pos:]
    return bytes(out)
