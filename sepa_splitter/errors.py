"""Gemeinsame Fehlerklassen (alle Meldungen sind für Anwender verständlich formuliert)."""


class SepaSplitterError(Exception):
    """Basisklasse. Die Nachricht ist direkt für die Anzeige in der Oberfläche gedacht."""


class InputError(SepaSplitterError):
    """Eingabedatei fehlt, ist nicht lesbar oder kein gültiges XML."""


class UnsupportedVersionError(SepaSplitterError):
    """Unbekannte oder (noch) nicht implementierte pain-Version."""


class ValidationError(SepaSplitterError):
    """Fachliche oder strukturelle Prüfung fehlgeschlagen."""


class FidelityError(SepaSplitterError):
    """Originaltreue kann nicht gewährleistet werden oder wurde verletzt."""


class ConfigError(SepaSplitterError):
    """Ungültige oder nicht lesbare Konfiguration."""


class OutputError(SepaSplitterError):
    """Ausgabedateien können nicht (vollständig) geschrieben werden."""
