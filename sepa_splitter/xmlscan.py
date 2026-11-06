"""Positionsgenauer XML-Scanner.

Der Scanner arbeitet auf den *Rohbytes* der Datei und liefert für jedes Element die
exakten Byte-Positionen (Start-Tag, Ende des Start-Tags, Beginn des End-Tags, Ende).
Er ersetzt NICHT die Wohlgeformtheitsprüfung: Diese erfolgt vorab mit lxml
(siehe analyzer.py). Der Scanner dient ausschließlich dazu, die von lxml bestätigte
Struktur auf Bytebereiche abzubilden, damit unveränderte Bereiche bytegenau
übernommen werden können.

Namespaces werden über die xmlns-Deklarationen korrekt aufgelöst; Elemente werden
nie über Textsuche, sondern über (Namespace, lokaler Name) im Elementbaum gefunden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .errors import FidelityError

# Tokenarten: Kommentar, CDATA, Verarbeitungsanweisung, DOCTYPE/ENTITY (werden abgelehnt),
# End-Tag, Start-Tag (mit Attributen in Anführungszeichen, '>' in Attributwerten erlaubt).
_TOKEN = re.compile(
    rb"<!--.*?-->"
    rb"|<!\[CDATA\[.*?\]\]>"
    rb"|<\?.*?\?>"
    rb"|<!DOCTYPE|<!ENTITY"
    rb"|</(?P<end>[^\s>]+)\s*>"
    rb"|<(?P<start>[^\s/>!?]+)(?P<attrs>(?:\s+[^\s=/>]+\s*=\s*(?:\"[^\"]*\"|'[^']*'))*)\s*(?P<empty>/?)>",
    re.S,
)
_ATTR = re.compile(rb"\s+([^\s=/>]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


@dataclass(eq=False)
class Node:
    qname: str
    prefix: str
    local: str
    ns: Optional[str]
    start: int            # Position von '<' des Start-Tags
    open_end: int         # Position direkt hinter '>' des Start-Tags
    close_start: Optional[int] = None  # Position von '<' des End-Tags (None bei <x/>)
    end: int = 0          # Position direkt hinter dem letzten '>' des Elements
    parent: Optional["Node"] = None
    children: List["Node"] = field(default_factory=list)

    def find(self, ns: str, local: str) -> List["Node"]:
        return [c for c in self.children if c.local == local and c.ns == ns]

    def first(self, ns: str, local: str) -> Optional["Node"]:
        for c in self.children:
            if c.local == local and c.ns == ns:
                return c
        return None

    def has_only_text(self) -> bool:
        return not self.children and self.close_start is not None


def scan(data: bytes) -> Node:
    """Liefert das Wurzelelement samt Positionen. Wirft FidelityError bei Unstimmigkeiten."""
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise FidelityError(
            "Die Datei enthält eine DOCTYPE-/ENTITY-Deklaration. Aus Sicherheitsgründen "
            "(XXE-Schutz) werden solche Dateien nicht verarbeitet."
        )
    stack: List[Node] = []
    nsstack: List[Dict[str, str]] = [{"xml": "http://www.w3.org/XML/1998/namespace"}]
    root: Optional[Node] = None
    pos = 0
    for m in _TOKEN.finditer(data):
        gap_end = m.start()
        if data.find(b"<", pos, gap_end) != -1:
            raise FidelityError("Interner Scanner-Fehler: unerwartetes '<' im Textbereich.")
        pos = m.end()
        end_name = m.group("end")
        start_name = m.group("start")
        if start_name is not None:
            qname = start_name.decode("ascii", "replace")
            nsmap = dict(nsstack[-1])
            for am in _ATTR.finditer(m.group("attrs")):
                an = am.group(1).decode("ascii", "replace")
                val = (am.group(2) if am.group(2) is not None else am.group(3)).decode("utf-8", "replace")
                if an == "xmlns":
                    nsmap[""] = val
                elif an.startswith("xmlns:"):
                    nsmap[an[6:]] = val
            if ":" in qname:
                prefix, local = qname.split(":", 1)
            else:
                prefix, local = "", qname
            ns = nsmap.get(prefix)
            node = Node(qname, prefix, local, ns, m.start(), m.end())
            if stack:
                node.parent = stack[-1]
                stack[-1].children.append(node)
            elif root is None:
                root = node
            else:
                raise FidelityError("Mehrere Wurzelelemente gefunden.")
            if m.group("empty"):
                node.end = m.end()
            else:
                stack.append(node)
                nsstack.append(nsmap)
        elif end_name is not None:
            if not stack or stack[-1].qname != end_name.decode("ascii", "replace"):
                raise FidelityError("Interner Scanner-Fehler: End-Tag passt nicht zum Start-Tag.")
            node = stack.pop()
            nsstack.pop()
            node.close_start = m.start()
            node.end = m.end()
    if stack or root is None:
        raise FidelityError("Interner Scanner-Fehler: Elementbaum unvollständig.")
    if data.find(b"<", pos) != -1:
        raise FidelityError("Interner Scanner-Fehler: Inhalt hinter dem Wurzelelement.")
    return root


def text_of(data: bytes, node: Node, encoding: str) -> str:
    """Textinhalt eines Blattelements (Entities aufgelöst, Rand-Whitespace entfernt)."""
    if node.close_start is None:
        return ""
    raw = data[node.open_end:node.close_start].decode(encoding)
    return unescape_xml(raw).strip()


_ENT = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}
_ENT_RE = re.compile(r"&(?:amp|lt|gt|quot|apos|#\d+|#x[0-9A-Fa-f]+);")


def unescape_xml(s: str) -> str:
    def rep(m: "re.Match[str]") -> str:
        t = m.group(0)
        if t in _ENT:
            return _ENT[t]
        return chr(int(t[3:-1], 16)) if t.startswith("&#x") else chr(int(t[2:-1]))
    return _ENT_RE.sub(rep, s)


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_WS = b" \t\r\n"


def leading_ws_start(data: bytes, pos: int) -> int:
    """Beginn des Whitespace-Laufs unmittelbar vor ``pos``."""
    while pos > 0 and data[pos - 1] in _WS:
        pos -= 1
    return pos
