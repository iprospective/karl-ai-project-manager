#!/usr/bin/env python3
"""Tests RM3274 (lot 1) — pm_secret_scan : reconnaître un secret sans jamais le recopier.

Ce qui doit tenir : les motifs de forge et de fournisseurs sont vus ; les faux
positifs de RM2826 (chemins de fichiers) restent écartés ; l'agent qui signale
lui-même l'incident est un signal à part entière ; et surtout **aucune sortie du
module ne contient la valeur détectée** — c'est la propriété qui empêche le garde
de propager ce qu'il dénonce.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


import pm_secret_scan as S  # noqa: E402

GLPAT = "glpat-" + "a1b2c3d4e5f6g7h8i9j0"
META = "EAA" + "WMKexnIMYBO4a5ZB6YdVqgqiOccMJFZAOf14aSDeTcT26gF4JhcYGNQiwZAbUiU6p10"
AWS = "AKIA" + "IOSFODNN7EXAMPLE"
SK = "sk-ant-" + "abcdefghijklmnopqrstuvwxyz0123"

print("[RM3274] les préfixes connus sont vus")
for nom, val, attendu in (("GitLab", GLPAT, "jeton GitLab (glpat-)"),
                          ("Meta", META, "jeton Meta/Facebook (EAA…)"),
                          ("AWS", AWS, "clé d'accès AWS (AKIA…)"),
                          ("clé de modèle", SK, "clé d'API modèle (sk-…)")):
    labels = [h["label"] for h in S.scan(f"la valeur est {val} voilà")]
    check(f"{nom} détecté", attendu in labels, str(labels))
check("clé privée PEM détectée",
      "clé privée PEM" in [h["label"] for h in S.scan("-----BEGIN RSA PRIVATE KEY-----\nabc")])
check("mot-clé porteur détecté",
      "password: <valeur>" in [h["label"] for h in S.scan("password: hunter2")])
check("en-tête Bearer détecté",
      "en-tête Authorization: Bearer" in [h["label"] for h in S.scan(
          "Authorization: Bearer abcdefghijklmnopqrstuvwx")])

print("\n[RM3274] AUCUNE sortie ne contient la valeur — la propriété centrale")
for val in (GLPAT, META, AWS, SK, "hunter2"):
    texte = f"secret={val}"
    rendu = repr(S.scan(texte)) + repr(S.scan_secrets(texte)) + repr(S.incident(texte))
    # On cherche la valeur entière ET sa seconde moitié : un module qui tronquerait
    # au lieu de hacher laisserait fuir la queue, qui suffit souvent à retrouver le reste.
    moitie = val[len(val) // 2:]
    check(f"la valeur n'est nulle part dans ce que rend le module ({val[:8]}…)",
          val not in rendu and moitie not in rendu)
check("l'empreinte est courte et stable", S.fingerprint(GLPAT) == S.fingerprint(GLPAT)
      and len(S.fingerprint(GLPAT)) == 12)
check("deux secrets différents ont deux empreintes", S.fingerprint(GLPAT) != S.fingerprint(META))

print("\n[RM3274] les faux positifs de RM2826 restent écartés")
for chemin in ("/zfs/workspaces/prestashop/modules/customshippingrate",
               "modules/thecheckout/controllers/front/front",
               "scripts/pm-task-status-update.py"):
    check(f"« {chemin[:42]} » n'est pas un secret", S.scan(chemin) == [], str(S.scan(chemin)))
check("mais un vrai blob base64 l'est toujours",
      S.scan("dGhpcy1pcy1hLXZlcnktbG9uZy1iYXNlNjQtc3RyaW5nLXZhbHVl") != [])

print("\n[RM3274] un même secret répété ne compte qu'une fois")
hits = S.scan(f"{GLPAT} puis encore {GLPAT} et toujours {GLPAT}")
check("trois occurrences, une détection", len(hits) == 1, str(len(hits)))

print("\n[RM3274] l'aveu de l'agent est un signal à part entière")
for phrase in ("le token API Meta a été affiché en clair",
               "⚠ Un point de sécurité : le jeton est exposé",
               "je te conseille de régénérer le token côté Meta",
               "la clé a été divulguée dans le transcript"):
    check(f"« {phrase[:44]}… » est un aveu", S.avowal(phrase) != [], str(S.avowal(phrase)))
check("une phrase anodine n'est pas un aveu",
      S.avowal("j'ai lu la configuration du module et tout va bien") == [])
check("parler de sécurité en général ne suffit pas",
      S.avowal("le module gère les droits d'accès des utilisateurs") == [])

print("\n[RM3274] l'incident : ce que le texte montre + ce que l'agent dit")
check("rien de suspect → pas d'incident", S.incident("tout va bien, j'ai lu trois fichiers") is None)
inc = S.incident(f"sortie SQL : {GLPAT}", "voilà le résultat")
check("un secret vu, sans aveu → incident", inc and inc["labels"] and not inc["avowal"])
inc2 = S.incident("rien de visible ici", "le token a été affiché en clair plus haut")
check("un aveu, sans valeur visible → incident quand même",
      inc2 and inc2["avowal"] and not inc2["labels"])
check("…et il a quand même une clé d'incident", inc2 and inc2["key"])

print("\n[RM3274] la clé d'incident regroupe les occurrences d'un même secret")
a = S.incident(f"vu ici : {GLPAT}", "")
b = S.incident(f"et revu là, autrement formulé : {GLPAT}", "je le signale")
check("deux tours, même secret → même clé", a["key"] == b["key"], f"{a['key']} vs {b['key']}")
c = S.incident(f"un autre : {META}", "")
check("un secret différent → clé différente", a["key"] != c["key"])

print("\n[RM3274] la marque allow ne désarme que si on la demande")
check("sans marque demandée, la détection tient",
      S.scan_secrets(f"{GLPAT} <!-- wiki-sync: allow -->") != [])
check("avec la marque demandée, le garde se tait",
      S.scan_secrets(f"{GLPAT} <!-- wiki-sync: allow -->",
                     allow_mark="<!-- wiki-sync: allow -->") == [])

print("\n[RM3274] entrées dégénérées")
for val in (None, "", 12345):
    check(f"{val!r} ne fait pas tomber le scan", S.scan(val if isinstance(val, str) else "") == [])
check("incident(None) ne lève pas", S.incident(None) is None)

print()
if FAIL:
    print(f"✗ {len(FAIL)} test(s) en échec :")
    for f in FAIL:
        print(f"   · {f}")
    sys.exit(1)
print("✓ tous les tests passent")
