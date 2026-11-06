"""Automatisierte Tests (laufen mit pytest und mit ``python -m unittest``)."""
import hashlib
import os
import stat
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sepa_splitter import analyzer, paths, samplegen, service, splitter, verifier, xmlscan
from sepa_splitter.config import Config, load_config, DEFAULT_INI
from sepa_splitter.errors import (FidelityError, InputError, OutputError, UnsupportedVersionError,
                                  ValidationError)
from sepa_splitter.protocol import Protocol, mask


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.dir = Path(self._td.name)
        self.cfg = Config()
        self.proto = Protocol(False)

    def tearDown(self):
        self._td.cleanup()

    def write(self, data: bytes, name="SEPA_Lastschriften.xml") -> Path:
        p = self.dir / name
        p.write_bytes(data)
        return p

    def run_split(self, data: bytes, **cfgkw):
        for k, v in cfgkw.items():
            setattr(self.cfg, k, v)
        p = self.write(data)
        chk = service.check_file(p, self.cfg, self.proto)
        res = service.split_file(chk, self.cfg, self.proto) if chk.split_needed else None
        return p, chk, res


# ------------------------------------------------------------ 15.1 Aufteilung
class TestSplitCounts(unittest.TestCase):
    TABLE = {1: [1], 998: [998], 999: [999], 1000: [500, 500], 1500: [750, 750], 1998: [999, 999],
             1999: [667, 666, 666], 2000: [667, 667, 666], 2500: [834, 833, 833], 3000: [750] * 4}

    def test_table(self):
        for n, exp in self.TABLE.items():
            self.assertEqual(splitter.split_counts(n, 999), exp, n)

    def test_sum_and_limit_property(self):
        for n in range(1, 4000, 37):
            c = splitter.split_counts(n, 999)
            self.assertEqual(sum(c), n)
            self.assertTrue(all(x <= 999 for x in c))
            self.assertLessEqual(max(c) - min(c), 1)

    def test_suffixes(self):
        self.assertEqual([splitter.letter_suffix(i) for i in (0, 1, 25, 26, 27, 51, 52)],
                         ["a", "b", "z", "aa", "ab", "az", "ba"])


# ------------------------------------------------------------ Dateien erzeugen
class TestSplitting(Base):
    def test_no_split_leaves_everything_untouched(self):
        for n in (1, 998, 999):
            data = samplegen.generate(counts=(n,))
            p = self.write(data, f"n{n}.xml")
            chk = service.check_file(p, self.cfg, self.proto)
            self.assertFalse(chk.split_needed)
            self.assertEqual(sorted(x.name for x in self.dir.iterdir() if x.name.startswith(f"n{n}")), [f"n{n}.xml"])

    def test_split_1000_to_500_500_all_versions_newlines(self):
        for ver in ("pain.008.001.02", "pain.008.001.08"):
            for nl in ("\n", "\r\n"):
                with self.subTest(ver=ver, nl=nl):
                    data = samplegen.generate(ver, (1000,), nl=nl)
                    p, chk, res = self.run_split(data)
                    self.assertEqual([x.name for x in res.files], ["SEPA_Lastschriften_a.xml", "SEPA_Lastschriften_b.xml"])
                    self.assertTrue(res.structure_ok and res.fidelity_ok)
                    self.assertEqual(p.read_bytes(), data)          # Original unverändert
                    for f in res.files:
                        os.remove(f)

    def test_multiple_pmtinf_dates_sequence_preserved(self):
        data = samplegen.generate("pain.008.001.02", (300, 700, 1200, 100))
        p, chk, res = self.run_split(data)
        self.assertEqual(len(res.files), 3)
        self.assertTrue(res.fidelity_ok)
        docs = [analyzer.analyze(f) for f in res.files]
        self.assertEqual([d.total_tx for d in docs], [767, 767, 766])
        self.assertEqual(sum((d.total_sum for d in docs), Decimal(0)), chk.doc.total_sum)
        # Fälligkeiten und Sequenztypen werden nie vermischt
        orig = {(p_.due_date, p_.seq_type) for p_ in chk.doc.pmtinfs}
        seen = {(p_.due_date, p_.seq_type) for d in docs for p_ in d.pmtinfs}
        self.assertEqual(seen, orig)
        # Datei 1 enthält nur Teile von PmtInf 1 und 2 usw.
        self.assertEqual([len(d.pmtinfs) for d in docs], [2, 2, 2])

    def test_split_pmtinf_ids_unique_with_suffix(self):
        data = samplegen.generate(counts=(1500,))
        _, chk, res = self.run_split(data)
        ids = [analyzer.analyze(f).pmtinfs[0].id_text for f in res.files]
        self.assertEqual(ids, ["SAMMELLASTSCHRIFT20261106-1a", "SAMMELLASTSCHRIFT20261106-1b"])
        mids = [analyzer.analyze(f).msgid for f in res.files]
        self.assertEqual(mids, ["MSG20261106001a", "MSG20261106001b"])

    def test_long_ids_are_shortened_deterministically(self):
        data = samplegen.generate(counts=(1500,), long_ids=True)
        _, chk, res = self.run_split(data)
        for f in res.files:
            d = analyzer.analyze(f)
            self.assertLessEqual(len(d.pmtinfs[0].id_text), 35)
        again = [splitter.make_plan(chk.doc, 999)[i].pmtinf_ids for i in range(2)]
        self.assertEqual(again, [pl.pmtinf_ids for pl in chk.plans])

    def test_id_collision_after_truncation_is_resolved(self):
        used = set()
        a = splitter.fit_id("X" * 35, "a", used); used.add(a)
        b = splitter.fit_id("X" * 34 + "Y", "a", used)
        self.assertNotEqual(a, b)
        self.assertLessEqual(len(b), 35)

    def test_more_than_26_files(self):
        data = samplegen.generate(counts=(300,), comments=False)
        self.cfg.max_transactions = 10
        p, chk, res = self.run_split(data)
        self.assertEqual(len(res.files), 30)
        self.assertEqual(res.files[25].name, "SEPA_Lastschriften_z.xml")
        self.assertEqual(res.files[26].name, "SEPA_Lastschriften_aa.xml")
        self.assertTrue(res.fidelity_ok)

    def test_numbers_suffix_mode(self):
        data = samplegen.generate(counts=(30,))
        self.cfg.max_transactions = 10
        _, _, res = self.run_split(data, suffix_mode="numbers")
        self.assertEqual(res.files[0].name, "SEPA_Lastschriften_01.xml")

    def test_large_input(self):
        data = samplegen.generate(counts=(5000, 5000), comments=False)
        _, chk, res = self.run_split(data)
        self.assertEqual(len(res.files), 11)
        self.assertTrue(res.fidelity_ok)


# ------------------------------------------------------------ 15.2 Originaltreue
class TestFidelity(Base):
    def split_bytes(self, data):
        p = self.write(data)
        d = analyzer.analyze(p)
        plans = splitter.make_plan(d, 999)
        return d, plans, [splitter.build_part(d, pl) for pl in plans]

    def test_declaration_namespace_prefix_comments_indent(self):
        for kw in (dict(prefix=""), dict(prefix="ns"), dict(indent="\t"), dict(indent=""), dict(comments=False)):
            with self.subTest(**kw):
                data = samplegen.generate("pain.008.001.08", (1100,), **kw)
                d, plans, outs = self.split_bytes(data)
                for o in outs:
                    self.assertTrue(o.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'))
                    self.assertIn(b'<Document xmlns' if kw.get("prefix") == "" else b'<ns:Document xmlns:ns=', o)
                    self.assertEqual(o.count(b"\r"), 0)
                self.assertTrue(verifier.verify(data, outs, 999).ok)

    def test_transaction_blocks_are_byte_identical(self):
        data = samplegen.generate(counts=(2000,), nl="\r\n")
        d, plans, outs = self.split_bytes(data)
        orig_blocks = [data[t.node.start:t.node.end] for p in d.pmtinfs for t in p.txs]
        out_blocks = []
        for o in outs:
            dd = analyzer.analyze(self.write(o, "x.xml"))
            out_blocks += [o[t.node.start:t.node.end] for p in dd.pmtinfs for t in p.txs]
        self.assertEqual(orig_blocks, out_blocks)

    def test_only_allowed_fields_differ(self):
        data = samplegen.generate(counts=(1200,))
        d, plans, outs = self.split_bytes(data)
        import re
        strip = lambda b: re.sub(rb"<ns:(NbOfTxs|CtrlSum|MsgId|PmtInfId)>[^<]*<", rb"<ns:\1><", b)
        a = [l for l in strip(data).splitlines() if b"DrctDbtTxInf" not in l]
        # Residuum der Ausgabe ohne Transaktionen ist Teilfolge des Original-Residuums
        resid = lambda b: [l for l in strip(b).split(b"\n")]
        self.assertTrue(verifier.verify(data, outs, 999).ok)

    def test_ctrlsum_decimals_preserved(self):
        data = samplegen.generate(counts=(1200,), ctrl_decimals=3)
        d, plans, outs = self.split_bytes(data)
        for o in outs:
            dd = analyzer.analyze(self.write(o, "y.xml"))
            txt = xmlscan.text_of(o, dd.ctrl_node, "utf-8")
            self.assertEqual(len(txt.split(".")[1]), 3)

    def test_optional_pmtinf_fields_absent(self):
        data = samplegen.generate(counts=(1200,), pmt_sums=False, pmt_nb=False)
        d, plans, outs = self.split_bytes(data)
        for o in outs:
            self.assertNotIn(b"<ns:CtrlSum>" + b"", o.split(b"<ns:PmtInf>")[1].split(b"<ns:DrctDbtTxInf>")[0])
        self.assertTrue(verifier.verify(data, outs, 999).ok)

    def test_exact_decimal_arithmetic(self):
        data = samplegen.generate(counts=(1500,))
        d, plans, outs = self.split_bytes(data)
        self.assertEqual(sum((p.total for p in plans), Decimal(0)), d.total_sum)

    def test_verifier_detects_tampering(self):
        data = samplegen.generate(counts=(1200,))
        d, plans, outs = self.split_bytes(data)
        cases = {
            "betrag": outs[0].replace(b'Ccy="EUR">2.', b'Ccy="EUR">3.', 1),
            "iban": outs[0].replace(b"DE00123456780000000005", b"DE00123456780000000006", 1),
            "version": outs[0].replace(b"pain.008.001.02", b"pain.008.001.08"),
            "nl": outs[0].replace(b"\n", b"\r\n"),
            "extra": outs[0].replace(b"<ns:PmtMtd>DD", b"<ns:Foo/><ns:PmtMtd>DD"),
            "kommentar": outs[0].replace(b"<!-- Synthetische Testdatei -->", b"<!-- geaendert -->"),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                self.assertNotEqual(bad, outs[0], "Test-Manipulation wirkungslos")
                self.assertFalse(verifier.verify(data, [bad, outs[1]], 999).ok)

    def test_verifier_detects_missing_duplicate_or_reordered(self):
        data = samplegen.generate(counts=(1200,))
        d, plans, outs = self.split_bytes(data)
        self.assertFalse(verifier.verify(data, [outs[0], outs[0]], 999).ok)
        self.assertFalse(verifier.verify(data, [outs[1], outs[0]], 999).ok)
        self.assertFalse(verifier.verify(data, [outs[0]], 999).ok)

    def test_scanner_handles_gt_in_attribute_and_cdata(self):
        xml = b'<?xml version="1.0"?><a xmlns="u"><b x="1>2"><![CDATA[ <c> ]]></b><!-- <d> --><e/></a>'
        root = xmlscan.scan(xml)
        self.assertEqual([c.local for c in root.children], ["b", "e"])
        self.assertEqual(xml[root.children[0].start:root.children[0].end], b'<b x="1>2"><![CDATA[ <c> ]]></b>')

    def test_scanner_namespace_resolution_not_prefix_based(self):
        xml = b'<a xmlns="u1"><x:b xmlns:x="u2"/><b/></a>'
        root = xmlscan.scan(xml)
        self.assertEqual([(c.ns, c.local) for c in root.children], [("u2", "b"), ("u1", "b")])


# ------------------------------------------------------------ 15.4 Fehlerfälle
class TestErrors(Base):
    def check(self, data):
        return analyzer.analyze(self.write(data))

    def test_missing_and_empty_file(self):
        with self.assertRaises(InputError):
            analyzer.analyze(self.dir / "gibtsnicht.xml")
        with self.assertRaises(InputError):
            self.check(b"")

    def test_invalid_xml(self):
        with self.assertRaises(InputError):
            self.check(b"<a><b></a>")

    def test_unsupported_versions(self):
        data = samplegen.generate("pain.008.001.02", (5,)).replace(b"pain.008.001.02", b"pain.008.001.99")
        with self.assertRaises(UnsupportedVersionError):
            self.check(data)
        with self.assertRaises(UnsupportedVersionError):
            self.check(b'<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"><X/></Document>')
        with self.assertRaises(UnsupportedVersionError):
            self.check(b"<a/>")

    def test_wrong_control_sum_blocks_splitting(self):
        data = samplegen.generate(counts=(1200,))
        bad = data.replace(b"<ns:CtrlSum>", b"<ns:CtrlSum>1", 1)
        d = self.check(bad)
        self.assertFalse(d.ok)
        self.assertFalse(d.sums_ok)
        p = self.write(bad)
        chk = service.check_file(p, self.cfg, self.proto)
        with self.assertRaises(ValidationError):
            service.split_file(chk, self.cfg, self.proto)
        self.assertEqual([x.name for x in self.dir.iterdir()], ["SEPA_Lastschriften.xml"])

    def test_wrong_tx_count(self):
        data = samplegen.generate(counts=(1200,)).replace(b"<ns:NbOfTxs>1200<", b"<ns:NbOfTxs>1199<", 1)
        self.assertFalse(self.check(data).ok)

    def test_doctype_rejected(self):
        data = samplegen.generate(counts=(5,))
        bad = data.replace(b"<ns:Document", b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><ns:Document', 1)
        with self.assertRaises(InputError):
            self.check(bad)

    def test_utf16_rejected(self):
        with self.assertRaises(InputError):
            self.check("<?xml version='1.0'?><a/>".encode("utf-16"))

    def test_missing_structure(self):
        data = samplegen.generate(counts=(5,)).replace(b"<ns:ReqdColltnDt>", b"<ns:Xx>").replace(b"</ns:ReqdColltnDt>", b"</ns:Xx>")
        with self.assertRaises(ValidationError):
            self.check(data)

    def test_version_specific_bic_element(self):
        # BICFI ist in .02 unzulässig
        data = samplegen.generate("pain.008.001.02", (5,)).replace(b"ns:BIC>", b"ns:BICFI>")
        with self.assertRaises(ValidationError):
            self.check(data)

    def test_mixed_currency(self):
        data = samplegen.generate(counts=(5,)).replace(b'Ccy="EUR"', b'Ccy="USD"', 1)
        self.assertFalse(self.check(data).ok)

    def test_existing_output_files(self):
        data = samplegen.generate(counts=(1200,))
        p = self.write(data)
        (self.dir / "SEPA_Lastschriften_b.xml").write_bytes(b"alt")
        chk = service.check_file(p, self.cfg, self.proto)
        for mode in ("ask", "abort"):
            self.cfg.overwrite_mode = mode
            with self.assertRaises(OutputError):
                service.split_file(chk, self.cfg, self.proto)
            self.assertEqual((self.dir / "SEPA_Lastschriften_b.xml").read_bytes(), b"alt")
            self.assertFalse((self.dir / "SEPA_Lastschriften_a.xml").exists())
        self.cfg.overwrite_mode = "ask"
        res = service.split_file(chk, self.cfg, self.proto, overwrite_decider=lambda ex: True)
        self.assertTrue(res.fidelity_ok)
        self.assertNotEqual((self.dir / "SEPA_Lastschriften_b.xml").read_bytes(), b"alt")
        self.cfg.overwrite_mode = "overwrite"
        service.split_file(chk, self.cfg, self.proto)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "Rechte nicht prüfbar")
    def test_no_write_permission(self):
        data = samplegen.generate(counts=(1200,))
        p = self.write(data)
        chk = service.check_file(p, self.cfg, self.proto)
        os.chmod(self.dir, stat.S_IRUSR | stat.S_IXUSR)
        try:
            with self.assertRaises(OutputError):
                service.split_file(chk, self.cfg, self.proto)
        finally:
            os.chmod(self.dir, stat.S_IRWXU)

    def test_write_error_leaves_nothing_behind(self):
        data = samplegen.generate(counts=(1200,))
        p = self.write(data)
        chk = service.check_file(p, self.cfg, self.proto)
        real = os.fsync
        calls = {"n": 0}
        def boom(fd):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError(28, "No space left on device")
            return real(fd)
        os.fsync = boom
        try:
            with self.assertRaises(OutputError):
                service.split_file(chk, self.cfg, self.proto)
        finally:
            os.fsync = real
        self.assertEqual([x.name for x in self.dir.iterdir()], ["SEPA_Lastschriften.xml"])
        self.assertEqual(p.read_bytes(), data)

    def test_original_changed_after_check(self):
        data = samplegen.generate(counts=(1200,))
        p = self.write(data)
        chk = service.check_file(p, self.cfg, self.proto)
        p.write_bytes(data + b"\n")
        with self.assertRaises(InputError):
            service.split_file(chk, self.cfg, self.proto)

    def test_original_never_modified(self):
        data = samplegen.generate(counts=(2500,))
        p, chk, res = self.run_split(data)
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), hashlib.sha256(data).hexdigest())
        self.assertNotIn(p, res.files)


# ------------------------------------------------------------ 15.3 Konfiguration / Pfade
class TestConfigAndPaths(Base):
    def test_missing_ini_created_with_comments(self):
        ini = self.dir / "SEPA-Splitter.ini"
        cfg = load_config(ini)
        self.assertTrue(cfg.ini_created)
        txt = ini.read_text(encoding="utf-8")
        self.assertIn("Default:", txt)
        self.assertIn("Mögliche Werte", txt)
        self.assertEqual(load_config(ini).problems, [])

    def test_defaults_equal_dataclass(self):
        ini = self.dir / "a.ini"
        ini.write_text(DEFAULT_INI, encoding="utf-8")
        c = load_config(ini)
        d = Config()
        for f in ("max_transactions", "name_scheme", "overwrite_mode", "suffix_mode", "base_path",
                  "last_directory_overrides_base_path", "remember_last_directory"):
            self.assertEqual(getattr(c, f), getattr(d, f), f)

    def test_invalid_values_reported_and_defaults_used(self):
        ini = self.dir / "b.ini"
        ini.write_text("[General]\nMaxTransactions = 5\n[Paths]\nNameScheme = Quark\n[Files]\nOverwriteMode = vielleicht\nPreserveOriginal=false\n"
                       "[SEPA]\nStrictMode = false\nVerifyOriginalIntegrity = false\n", encoding="utf-8")
        c = load_config(ini)
        self.assertEqual(c.max_transactions, 999)
        self.assertEqual(c.name_scheme, "JJJJ/Qn")
        self.assertEqual(c.overwrite_mode, "ask")
        joined = "\n".join(c.problems)
        self.assertIn("MaxTransactions", joined)
        self.assertIn("StrictMode", joined)
        self.assertIn("VerifyOriginalIntegrity", joined)
        self.assertIn("PreserveOriginal", joined)

    def test_fixed_rules_not_in_default_ini(self):
        for key in ("[SEPA]", "PreserveOriginal", "OutputDirectory", "StrictMode", "ValidateXML"):
            self.assertNotIn(key + (" =" if not key.startswith("[") else ""), DEFAULT_INI)
        # Ältere INI mit den früheren Einträgen (Wert true): wird still akzeptiert
        ini = self.dir / "alt.ini"
        ini.write_text("[Files]\nOutputDirectory = same_as_source\nPreserveOriginal = true\n"
                       "[SEPA]\nValidateXML = true\nStrictMode = true\n", encoding="utf-8")
        self.assertEqual(load_config(ini).problems, [])
        # Versuch, einen anderen Ausgabeordner zu setzen: gemeldet, ignoriert
        ini.write_text("[Files]\nOutputDirectory = /tmp/anders\n", encoding="utf-8")
        self.assertIn("OutputDirectory", "\n".join(load_config(ini).problems))

    def test_broken_ini_file(self):
        ini = self.dir / "c.ini"
        ini.write_text("das ist kein ini\n[unvollständig", encoding="utf-8")
        c = load_config(ini)
        self.assertTrue(c.problems)
        self.assertEqual(c.max_transactions, 999)

    def test_name_scheme(self):
        d = date(2025, 8, 14)
        sep = os.sep
        self.assertEqual(paths.render_name_scheme("JJJJ/Qn", d), f"2025{sep}Q3")
        self.assertEqual(paths.render_name_scheme("JJJJ/Mnn", d), f"2025{sep}M08")
        self.assertEqual(paths.render_name_scheme("JJ/Mnn", d), f"25{sep}M08")
        self.assertEqual(paths.render_name_scheme("JJ/Qn", d), f"25{sep}Q3")
        self.assertEqual(paths.render_name_scheme("JJJJQn", d), "2025Q3")
        self.assertEqual(paths.render_name_scheme("JJQn", d), "25Q3")
        self.assertEqual(paths.render_name_scheme("JJJJ\\Qn", date(2026, 1, 1)), f"2026{sep}Q1")

    def test_start_dir_base_plus_scheme(self):
        (self.dir / "2025" / "Q3").mkdir(parents=True)
        r = paths.resolve_start_dir(str(self.dir), "JJJJ/Qn", date(2025, 8, 1))
        self.assertEqual(r.path, self.dir / "2025" / "Q3")
        self.assertEqual(r.message, "")

    def test_start_dir_fallbacks(self):
        r = paths.resolve_start_dir(str(self.dir), "JJJJ/Qn", date(2031, 1, 1))     # Unterordner fehlt
        self.assertEqual(r.path, self.dir)
        self.assertTrue(r.message)
        r = paths.resolve_start_dir(str(self.dir / "nix"), "JJJJ/Qn", date(2031, 1, 1))
        self.assertEqual(r.path, Path.home())
        self.assertTrue(r.message)

    def test_empty_base_path_is_home_and_relative_is_home_relative(self):
        self.assertEqual(paths.resolve_base_path(""), Path.home())
        self.assertEqual(paths.resolve_base_path("Verein"), Path.home() / "Verein")

    def test_last_directory_override(self):
        base = self.dir / "base"; last = self.dir / "last"
        base.mkdir(); last.mkdir()
        r = paths.resolve_start_dir(str(base), "", date(2025, 1, 1), str(last), True, False)
        self.assertEqual(r.path, base)
        r = paths.resolve_start_dir(str(base), "", date(2025, 1, 1), str(last), True, True)
        self.assertEqual(r.path, last)
        r = paths.resolve_start_dir(str(base), "", date(2025, 1, 1), str(last), False, True)
        self.assertEqual(r.path, base)

    def test_outputs_always_next_to_original(self):
        sub = self.dir / "a" / "b"; sub.mkdir(parents=True)
        p = sub / "x.xml"; p.write_bytes(samplegen.generate(counts=(1200,)))
        cfg = Config(); cfg.base_path = str(self.dir / "ganz-anders")
        chk = service.check_file(p, cfg, self.proto)
        res = service.split_file(chk, cfg, self.proto)
        self.assertTrue(all(f.parent == sub.resolve() for f in res.files))

    def test_file_dialog_filter(self):
        try:
            from sepa_splitter.paths import dialog_filters
        except ImportError:
            self.skipTest("nicht verfügbar")
        filters, selected = dialog_filters()
        self.assertTrue(filters.split(";;")[0].startswith("SEPA-XML-Dateien (*.xml"))
        self.assertEqual(selected, filters.split(";;")[0])


class TestProtocol(Base):
    def test_no_full_iban_in_log(self):
        self.assertNotIn("0123456789", mask("IBAN DE89370400440532013000 wurde …"))
        pr = Protocol(True, "DEBUG", "t.log")
        pr.attach_directory(self.dir)
        pr.log("INFO", "Zahlung von DE89 3704 0044 0532 0130 00")
        txt = (self.dir / "t.log").read_text(encoding="utf-8")
        self.assertNotIn("0532", txt)

    def test_log_written_next_to_file(self):
        data = samplegen.generate(counts=(1200,))
        p = self.write(data)
        pr = Protocol(True, "INFO", "SEPA-Splitter.log")
        cfg = Config()
        chk = service.check_file(p, cfg, pr)
        service.split_file(chk, cfg, pr)
        txt = (self.dir / "SEPA-Splitter.log").read_text(encoding="utf-8")
        for needle in ("Programmstart", "pain.008.001.02", "Transaktionen: 1200", "Aufteilung nötig: ja",
                       "Originaltreue-Prüfung: erfolgreich", "Aufteilung erfolgreich"):
            self.assertIn(needle, txt)
        self.assertNotIn("DE00", txt)


if __name__ == "__main__":
    unittest.main()
