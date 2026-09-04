#!/usr/bin/env python3
"""pm_output — contrat de sortie des scripts PM (RM2362, CDC RM2316 § T1).

Trois modes :

  dense (défaut)   : ≤ 1 ligne « ✓ … » par opération logique sur stdout ;
                     warnings 1 ligne « ⚠ … » ; erreurs complètes « ✗ … » sur
                     stderr (jamais tronquées : cause + remède).
  verbose          : --verbose ou PM_VERBOSE=1 — restaure le détail historique
                     (tout ce qui passe par out.info()).
  porcelain        : --porcelain — stdout est réservé aux valeurs machine
                     (out.value()) ; ✓/⚠/info partent sur stderr. Corrige la
                     pollution stdout qui cassait `ID=$(… --porcelain)`
                     (RM2307).

Usage type dans un script :

    from pm_output import out
    def main():
        ap = argparse.ArgumentParser(...)
        out.add_args(ap)                    # ajoute --verbose (et lit PM_VERBOSE)
        args = ap.parse_args()
        out.configure(args)                 # détecte aussi args.porcelain s'il existe
        ...
        out.info("détail utile en debug")   # verbose uniquement
        out.op("statut", rm=2275, extra="en_cours→a_mep assign=5", commit="316e1ca")
        out.warn("2 warnings validate → pm-doctor RM2281")
        out.value(rm_id)                    # sortie machine (mode porcelain)
        out.fail("push refusé", remede="git -C <repo> pull --rebase puis relancer")

Invariant NORMS (CDC § I1) : ce module ne supprime aucune information — le
détail masqué en mode dense est déjà porté par le .log.md, le commit ou la
note Redmine, et reste accessible via --verbose.
"""
import argparse
import os
import sys


class _HelpFullAction(argparse.Action):
    """--help-full : aide complète (docstring entière) — RM2367, CDC § S6."""

    def __init__(self, option_strings, dest, **kw):
        super().__init__(option_strings, dest, nargs=0,
                         help="Aide complète (docstring entière)")

    def __call__(self, parser, namespace, values, option_string=None):
        parser.description = getattr(parser, "_pm_full_desc", parser.description)
        parser.print_help()
        parser.exit()


class _Out:
    def __init__(self):
        self.verbose = os.environ.get("PM_VERBOSE") == "1"
        self.porcelain = False

    # ── configuration ──────────────────────────────────────────────────────
    def add_args(self, parser):
        """Ajoute --verbose et --help-full (idempotent si déjà présents), et
        raccourcit l'aide par défaut : `--help` = 1er paragraphe de la
        docstring, `--help-full` = pavé complet (RM2367, CDC § S6)."""
        try:
            parser.add_argument("--verbose", action="store_true",
                                help="Sortie détaillée historique (défaut : dense)")
            parser.add_argument("--help-full", action=_HelpFullAction, dest="help_full")
        except Exception:
            pass
        if parser.description and "\n\n" in parser.description:
            parser._pm_full_desc = parser.description
            parser.description = parser.description.split("\n\n")[0].strip()
        return parser

    def configure(self, args=None, porcelain=None, verbose=None):
        if args is not None:
            self.verbose = self.verbose or bool(getattr(args, "verbose", False))
            if porcelain is None:
                porcelain = bool(getattr(args, "porcelain", False))
        if porcelain is not None:
            self.porcelain = porcelain
        if verbose is not None:
            self.verbose = verbose

    # ── émission ───────────────────────────────────────────────────────────
    @staticmethod
    def _write(stream, text):
        """Écrit sans jamais tuer l'appelant (RM2870).

        Un `pm-task-add … --porcelain | head -1` ferme le tube dès la première
        ligne lue : l'écriture suivante lève `BrokenPipeError` et **tuait le
        script** — après le POST Redmine, donc en laissant un ticket sans fiche PM
        (incident RM2868). L'affichage n'est jamais une raison d'interrompre une
        mutation en cours : le flux mort est remplacé par `os.devnull`, le travail
        continue, et l'exception ne remonte pas.
        """
        try:
            stream.write(text)
            stream.flush()
            return
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            devnull = open(os.devnull, "w")
            if stream is sys.stdout:
                sys.stdout = devnull
            elif stream is sys.stderr:
                sys.stderr = devnull
        except OSError:
            pass

    def _emit(self, line, err=False):
        stream = sys.stderr if (err or self.porcelain) else sys.stdout
        self._write(stream, line + "\n")

    def op(self, verb, rm=None, extra="", commit=None):
        """Une opération accomplie = UNE ligne dense."""
        parts = ["✓", str(verb)]
        if rm is not None:
            parts.append("RM%s" % rm)
        if extra:
            parts.append(str(extra))
        if commit:
            parts.append("commit=%s" % str(commit)[:9])
        self._emit(" ".join(parts))

    def info(self, msg):
        """Détail : émis uniquement en mode verbose."""
        if self.verbose:
            self._emit(str(msg))

    def warn(self, msg):
        self._emit("⚠ " + str(msg))

    def fail(self, msg, remede=None, code=1):
        """Erreur complète (jamais tronquée) sur stderr, puis exit."""
        line = "✗ " + str(msg)
        if remede:
            line += "\n  → remède : " + str(remede)
        self._emit(line, err=True)
        sys.exit(code)

    def value(self, v):
        """Valeur machine : SEULE sortie stdout autorisée en mode porcelain."""
        self._write(sys.stdout, str(v) + "\n")


out = _Out()
