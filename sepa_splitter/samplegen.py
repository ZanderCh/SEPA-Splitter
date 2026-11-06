"""Erzeugt synthetische SEPA-Testdateien (keine echten Personen-/Kontodaten)."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Sequence


def _iban(n: int) -> str:
    # Syntaktisch plausible, frei erfundene IBAN-Form (Prüfziffern nicht gültig – nur Testdaten)
    return f"DE00123456780000{n:06d}"[:22]


def generate(version: str = "pain.008.001.02", counts: Sequence[int] = (10,), nl: str = "\n",
             indent: str = "  ", comments: bool = True, pmt_sums: bool = True, pmt_nb: bool = True,
             prefix: str = "ns", long_ids: bool = False, ctrl_decimals: int = 2,
             seq_types: Sequence[str] = ("RCUR", "FRST", "OOFF", "FNAL")) -> bytes:
    ns = f"urn:iso:std:iso:20022:tech:xsd:{version}"
    bic = "BICFI" if version.endswith(".08") else "BIC"
    p = (prefix + ":") if prefix else ""
    xmlns = f'xmlns:{prefix}="{ns}"' if prefix else f'xmlns="{ns}"'
    total_n = sum(counts)
    amounts: List[Decimal] = []
    g = 0
    lines: List[str] = []
    I = indent

    def add(level: int, s: str) -> None:
        lines.append(I * level + s)

    pm_blocks: List[List[str]] = []
    for pi, c in enumerate(counts):
        blk: List[str] = []
        sub = Decimal(0)
        txs: List[str] = []
        for t in range(c):
            g += 1
            amt = Decimal(g % 97 + 1) + Decimal(g % 100) / 100
            sub += amt
            amounts.append(amt)
            txs += [
                f"{I*3}<{p}DrctDbtTxInf>",
                f"{I*4}<{p}PmtId>",
                f"{I*5}<{p}EndToEndId>E2E-{g:07d}</{p}EndToEndId>",
                f"{I*4}</{p}PmtId>",
                f'{I*4}<{p}InstdAmt Ccy="EUR">{amt:.2f}</{p}InstdAmt>',
                f"{I*4}<{p}DrctDbtTx>",
                f"{I*5}<{p}MndtRltdInf>",
                f"{I*6}<{p}MndtId>MANDAT-{g:06d}</{p}MndtId>",
                f"{I*6}<{p}DtOfSgntr>2020-01-{g % 28 + 1:02d}</{p}DtOfSgntr>",
                f"{I*5}</{p}MndtRltdInf>",
                f"{I*4}</{p}DrctDbtTx>",
                f"{I*4}<{p}DbtrAgt>",
                f"{I*5}<{p}FinInstnId>",
                f"{I*6}<{p}Othr><{p}Id>NOTPROVIDED</{p}Id></{p}Othr>" if g % 2 else f"{I*6}<{p}{bic}>TESTDEFFXXX</{p}{bic}>",
                f"{I*5}</{p}FinInstnId>",
                f"{I*4}</{p}DbtrAgt>",
                f"{I*4}<{p}Dbtr><{p}Nm>Testperson {g} &amp; Co</{p}Nm></{p}Dbtr>",
                f"{I*4}<{p}DbtrAcct><{p}Id><{p}IBAN>{_iban(g)}</{p}IBAN></{p}Id></{p}DbtrAcct>",
                f"{I*4}<{p}RmtInf><{p}Ustrd>Beitrag {g}</{p}Ustrd></{p}RmtInf>",
                f"{I*3}</{p}DrctDbtTxInf>",
            ]
            if comments and g % 250 == 0:
                txs.append(f"{I*3}<!-- Kommentar nach Transaktion {g} -->")
        pid = ("LASTSCHRIFT-LANGER-NAME-20261106-A" if long_ids else "SAMMELLASTSCHRIFT20261106-") + f"{pi + 1}"
        blk += [f"{I}<{p}PmtInf>", f"{I*2}<{p}PmtInfId>{pid}</{p}PmtInfId>", f"{I*2}<{p}PmtMtd>DD</{p}PmtMtd>"]
        if pmt_nb:
            blk.append(f"{I*2}<{p}NbOfTxs>{c}</{p}NbOfTxs>")
        if pmt_sums:
            blk.append(f"{I*2}<{p}CtrlSum>{sub:.{ctrl_decimals}f}</{p}CtrlSum>")
        blk += [
            f"{I*2}<{p}PmtTpInf>",
            f"{I*3}<{p}SvcLvl><{p}Cd>SEPA</{p}Cd></{p}SvcLvl>",
            f"{I*3}<{p}LclInstrm><{p}Cd>CORE</{p}Cd></{p}LclInstrm>",
            f"{I*3}<{p}SeqTp>{seq_types[pi % len(seq_types)]}</{p}SeqTp>",
            f"{I*2}</{p}PmtTpInf>",
            f"{I*2}<{p}ReqdColltnDt>2026-12-{pi % 20 + 1:02d}</{p}ReqdColltnDt>",
            f"{I*2}<{p}Cdtr><{p}Nm>Testverein e.V.</{p}Nm></{p}Cdtr>",
            f"{I*2}<{p}CdtrAcct><{p}Id><{p}IBAN>DE00123456780000999999</{p}IBAN></{p}Id></{p}CdtrAcct>",
            f"{I*2}<{p}CdtrAgt><{p}FinInstnId><{p}{bic}>TESTDEFFXXX</{p}{bic}></{p}FinInstnId></{p}CdtrAgt>",
            f"{I*2}<{p}ChrgBr>SLEV</{p}ChrgBr>",
        ]
        blk += txs
        blk.append(f"{I}</{p}PmtInf>")
        pm_blocks.append(blk)
    total = sum(amounts, Decimal(0))
    head = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f"<{p}Document {xmlns}>",
    ]
    if comments:
        head.append(f"{I}<!-- Synthetische Testdatei -->")
    head += [
        f"{I}<{p}CstmrDrctDbtInitn>",
        f"{I*2}<{p}GrpHdr>",
        f"{I*3}<{p}MsgId>MSG20261106001</{p}MsgId>",
        f"{I*3}<{p}CreDtTm>2026-11-06T10:00:00</{p}CreDtTm>",
        f"{I*3}<{p}NbOfTxs>{total_n}</{p}NbOfTxs>",
        f"{I*3}<{p}CtrlSum>{total:.{ctrl_decimals}f}</{p}CtrlSum>",
        f"{I*3}<{p}InitgPty><{p}Nm>Testverein e.V.</{p}Nm></{p}InitgPty>",
        f"{I*2}</{p}GrpHdr>",
    ]
    body: List[str] = []
    for blk in pm_blocks:
        body += [I + l for l in blk]
    tail = [f"{I}</{p}CstmrDrctDbtInitn>", f"</{p}Document>"]
    return (nl.join(head + body + tail) + nl).encode("utf-8")
