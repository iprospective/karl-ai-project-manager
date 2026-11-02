#!/usr/bin/env python3
"""Tests RM3229 — les notes de journée lues sur le Nextcloud.

Sans réseau : seules les fonctions PURES sont testées (nommage des fichiers, lecture
des horaires). L'accès WebDAV lui-même est une intégration tierce, vérifiée à la main.

Lancer : python3 scripts/test_pm_notes.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_notes as N  # noqa: E402

ECHECS = []


def verifie(cond, nom):
    print(("  ✓ " if cond else "  ✗ ") + nom)
    if not cond:
        ECHECS.append(nom)


# ── quel jour un fichier désigne-t-il ? ──────────────────────────────────────
verifie(N.jour_du_nom("2026-10-08.txt") == "2026-10-08", "convention courante")
verifie(N.jour_du_nom("2026-09-18.md") == "2026-09-18", "…en markdown aussi")
verifie(N.jour_du_nom("2026 08 11.txt") == "2026-08-11", "ancienne forme, à espaces")
verifie(N.jour_du_nom("2025-12-29-calicote.md") == "2025-12-29", "suffixe de client toléré")
verifie(N.jour_du_nom("2025-05-13-et-14.md") == "2025-05-13", "note à cheval : le premier jour")
verifie(N.jour_du_nom("Articles à lire.md") is None, "une note thématique n'est pas une journée")
verifie(N.jour_du_nom("2026-10-08") is None, "sans extension, on ne devine pas")
verifie(N.jour_du_nom("2026-13-45.md") is None, "une date impossible est écartée")
verifie(N.jour_du_nom("Clients") is None, "un dossier n'est pas une note")

# ── les horaires : proposés seulement quand la ligne ne dit QUE ça ───────────
verifie(N.heures_du_texte("2026-10-08\n\n9h15 - 18h15\n\nMatNat") == ("09:15", "18:15"),
        "une plage seule sur sa ligne est lue")
verifie(N.heures_du_texte("9h - 11h") == ("09:00", "11:00"), "sans minutes")
verifie(N.heures_du_texte("9:15-18:15") == ("09:15", "18:15"), "séparateur deux-points")
verifie(N.heures_du_texte("Pause 2h repas 12h30-14h30") is None,
        "la PAUSE n'est pas la journée — faux positif constaté sur la note du 02/10")
verifie(N.heures_du_texte("* lundi matin : entre 1.5 et 3h") is None,
        "une estimation de réunion non plus — faux positif du 25/09")
verifie(N.heures_du_texte("18h00 - 9h00") is None, "une plage à l'envers est refusée")
verifie(N.heures_du_texte("") is None and N.heures_du_texte(None) is None, "vide : rien")

# ── identifiants : absents ou incomplets → None, jamais d'exception ──────────
verifie(N.identifiants(None) is None, "sans chemin : None")
verifie(N.identifiants("/inexistant/.env") is None, "fichier absent : None")
import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as t:
    partiel = Path(t) / ".env"
    partiel.write_text("NEXTCLOUD_URL=https://x\nNEXTCLOUD_USER=karl\n", encoding="utf-8")
    verifie(N.identifiants(partiel) is None, "identifiants incomplets : None, pas de demi-accès")
    complet = Path(t) / "full.env"
    complet.write_text('NEXTCLOUD_URL="https://x"\nNEXTCLOUD_USER=karl\n'
                       "NEXTCLOUD_APP_PASSWORD=zzz\nAUTRE=1\n", encoding="utf-8")
    verifie(N.identifiants(complet) == ("https://x", "karl", "zzz"),
            "guillemets retirés, clés étrangères ignorées")

print("\n" + ("ÉCHECS : " + " | ".join(ECHECS) if ECHECS else "Tous les tests passent."))
sys.exit(1 if ECHECS else 0)
