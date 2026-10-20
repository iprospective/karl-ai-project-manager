#!/usr/bin/env python3
"""Tests RM3274 (lot 1) + RM3465 (faux positifs) — pm_secret_scan : reconnaître un secret sans jamais le recopier.

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

print("\n[RM3465] ce qui n'en a que l'air ne déclenche plus")
SHA = "33184ae3feeeded031da64a7e9870f78cf7d9173"
MD5 = "5cc77527d35007e28ddf04f30600c011"
for nom, texte in (
    ("hash git (submodule status)", f" {SHA} modules/mmi_x (heads/main)"),
    ("hash git (ls-remote)", f"{SHA}\trefs/heads/main"),
    ("hash git seul, sous un Merge", f"2da64c78c Merge branch 'dev' into 'master'\n{SHA}"),
    ("hash dans une variable *_SHA", f"EXPECTED_SHA={SHA}"),
    ("nom de classe PHP sans chiffre", "class MmiCombinationAttributePlannerTransformsRepository"),
    ("chemin aux segments longs", "modules/x/controllers/admin/AdminMmiCombinationAttributesController.php:74"),
    ("fichier de cache md5", f"?? adminpisc/yaml/{MD5}.php"),
    ("jeton d'URL du BO PrestaShop", f"index.php?controller=AdminProducts&token={MD5}"),
    ("jeton Symfony _token=", "employees/new?_token=h89A209mp09uWCtLZ6RfO4BCCKBu2aBtq0bE"),
    ("clé publique d'un DSN Sentry", f"$sentryDsn = 'https://{MD5}@o298402.ingest.sentry.io/6066714'"),
    ("classe générée dans une pile d'appels", "9. ComposerAutoloaderInit5f3e2a1b9c8d7e6f5a4b3c2d1e0f9a8b::getLoader()"),
    ("blob base64 (capture d'écran)", "iVBORw0KGgo" + "A1b2C3d4" * 80),
    ("URI de coffre secret:<chemin>", "resolve-secret.sh secret:karl@pisceen-presta.test.iprospective.fr password"),
    ("URI de coffre secret://", "secret://<instance>/<chemin…>[#champ]"),
    ("instance de coffre en config", "providers:\n  defaults:\n    secret: vaultwarden"),
    ("gabarit <valeur>", "Sécurité : régénérer (password: <valeur>, secret: <valeur>)"),
    ("prose française", "**le texte montre** un secret : préfixes connus"),
):
    check(f"{nom} : pas de détection", S.scan(texte) == [], str(S.scan(texte)))

print("\n[RM3465] les vrais secrets restent vus")
REDMINE = "7d1f" + "0a9be2c4d6f8" * 3
for nom, texte in (
    ("clé Redmine (40 hexa) en en-tête", f"X-Redmine-API-Key: {REDMINE}"),
    ("clé Redmine (40 hexa) en .env", f"REDMINE_API_KEY={REDMINE}"),
    ("blob base64 mixte de 40c", "token: Zm9vYmFyYmF6cXV4MTIzNDU2Nzg5MGFiY2RlZmdo"),
    ("mot de passe en YAML", "password: S3cr3t-Pa55word"),
    ("secret en YAML", "secret: s3cr3t9value"),
    ("glpat- dans une ligne git", f"git push https://oauth2:{GLPAT}@gitlab.example/x.git"),
):
    check(f"{nom} : détecté", S.scan(texte) != [], str(S.scan(texte)))

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
