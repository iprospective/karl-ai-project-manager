#!/usr/bin/env python3
"""Tests du garde anti-secret de pm-wiki-sync (RM2826).

Lancer : python3 scripts/test_pm_wiki_sync_secrets.py

Couvre les deux faces du garde :

- les CHEMINS de fichiers ne doivent plus être pris pour des jetons base64. C'est le
  défaut qui a rendu le CDC transport de pisceen/presta impubliable pendant un mois : le
  motif `\\b[A-Za-z0-9+/]{32,}={0,2}\\b` accepte le `/`, donc tout chemin un peu long
  devenait un « jeton haute entropie » ;
- les vrais secrets restent détectés, y compris les jetons de forge que l'ancien motif
  laissait passer (le `_` de `ghp_` et le `-` de `glpat-` empêchaient de trouver 32
  caractères contigus dans la classe).
"""
import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

# (texte, doit_être_signalé, intitulé)
CAS = [
    # --- des chemins, pas des secrets : aucun ne doit bloquer une publication
    ("/zfs/workspaces/prestashop/modules/customshippingrate", False, "chemin absolu long"),
    ("modules/thecheckout/controllers/front/front", False, "chemin relatif long"),
    ("override/classes/checkout/DeliveryOptionsFinder.php", False, "chemin avec majuscules"),
    ("modules/cins_newproductfields/upgrade/upgrade-1.0.5.php", False, "chemin avec chiffres et points"),
    ("var/rm2649-flag-feature-20261006-120524.json", False, "chemin avec horodatage"),
    ("https://gitlab.iprospective.fr/sfy/pisceen-dercya/pisceen-prestashop.git", False, "URL de dépôt"),
    ("Voir modules/cins_newproductfields/classes/CinsCartColis.php et override/classes/Cart.php",
     False, "prose citant deux chemins"),
    ("un texte normal sans rien de particulier dedans", False, "prose"),

    # --- de vrais secrets : tous doivent être signalés
    ("aGVsbG8gd29ybGQgdGhpcyBpcyBhIHNlY3JldCB0b2tlbiBoZXJlCg==", True, "jeton base64"),
    ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0", True, "JWT"),
    ("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8", True, "jeton GitHub"),
    ("glpat-A1b2C3d4E5f6G7h8I9j0", True, "jeton GitLab"),
    ("github_pat_11ABCDEFG0abcdefghij_KLMNOPQRSTUVWXYZ0123456789", True, "jeton GitHub à portée fine"),
    ("xoxb-123456789012-ABCDEFGHIJKLMNOP", True, "jeton Slack"),
    ("password: hunter2", True, "mot de passe"),
    ("api_key = 1234", True, "clé d'API"),
    ("-----BEGIN RSA PRIVATE KEY-----", True, "clé privée PEM"),
]


def _load():
    spec = importlib.util.spec_from_file_location("pm_wiki_sync", SCRIPTS / "pm-wiki-sync.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = _load()
    echecs = []

    for texte, attendu, intitule in CAS:
        obtenu = bool(m.scan_secrets(texte))
        if obtenu != attendu:
            echecs.append("%s : attendu %s, obtenu %s (%r)" % (intitule, attendu, obtenu, texte[:60]))

    # La marque allow désarme tout, volontairement — c'est documenté comme tel.
    assert m.scan_secrets("password: hunter2\n" + m._ALLOW_MARK) == [], "la marque allow doit désarmer le garde"

    # Le départage chemin / jeton, directement.
    assert m._ressemble_a_un_chemin("a/b/c/d") is True
    assert m._ressemble_a_un_chemin("modules/thecheckout/controllers/front/front") is True
    assert m._ressemble_a_un_chemin("aGVsbG8gd29ybGQgdGhpcyBpcyBhIHNlY3JldA==") is False
    # un jeton contigu de 32+ caractères reste un jeton, même avec un / en bordure
    assert m._ressemble_a_un_chemin("aGVsbG8gd29ybGQgdGhpcyBpcyBhIHNlY3JldA==/x") is False

    # LIMITE CONNUE ET ASSUMÉE (RM2826)
    # Un jeton base64 dont un `/` tombe de façon à produire DEUX morceaux de moins de 32
    # caractères passe pour un chemin, et échappe donc à ce motif :
    assert m._ressemble_a_un_chemin("aGVsbG8gd29ybGQgdGhpcyBpcyBh/c2VjcmV0IHRva2VuIGhlcmU") is True
    #
    # Pourquoi on l'accepte plutôt que de baisser le seuil de 32 : de vrais segments de
    # chemin dépassent cette longueur — « transport-couverture-apres-nettoyage » en fait 36,
    # et c'est un nom d'aspect bien réel. Descendre le seuil rendrait impubliables les
    # documents qu'on cherche précisément à débloquer, pour fermer un cas de bord étroit.
    #
    # Ce qui couvre le risque résiduel : les jetons réellement émis par les forges sont
    # captés par des motifs ancrés sur leur préfixe (glpat-, ghp_, github_pat_, xox…-), et
    # le garde reste un filet de sécurité, pas une preuve d'absence de secret.

    if echecs:
        print("ÉCHEC — %d cas en défaut :" % len(echecs))
        for e in echecs:
            print("  · " + e)
        return 1

    print("OK — %d cas de détection + le départage chemin/jeton" % len(CAS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
