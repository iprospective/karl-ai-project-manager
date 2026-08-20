#!/usr/bin/env python3
"""Tests RM2713 (L3d) — backend fichier chiffré `age`.

Deux niveaux :
  1. avec un FAUX `age` (script qui décode du base64) — toujours joué, donc le
     comportement est vérifié même sur un poste où `age` n'est pas installé ;
  2. avec le VRAI `age` s'il est présent — aller-retour complet
     (`age-keygen` → chiffrement → résolution), sinon annoncé comme non joué.

L'invariant central est testé pour de vrai : le clair déchiffré ne touche JAMAIS
le disque. Le fichier posé est illisible en l'état, et on relit l'arborescence
après résolution pour s'assurer qu'aucun octet du secret n'y est apparu.

Lancer : python3 scripts/test_pm_secrets_age.py
"""
import base64
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_secrets", HERE / "pm_secrets.py")
ps = importlib.util.module_from_spec(spec)
sys.modules["pm_secrets"] = ps
spec.loader.exec_module(ps)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def erreur(fn, *a, **kw):
    """Code d'erreur levé par un appel, ou None s'il passe."""
    try:
        fn(*a, **kw)
        return None
    except ps.SecretError as e:
        return e.code


SECRET = "s3cr3t-de-test-tr3s-reconnaissable"
DOC = f"""
acme:
  db:
    username: acme_app
    password: {SECRET}
    host: db.acme.local
  api:
    token: tok-42
racine_simple: valeur-a-plat
"""

# ── faux `age` : le fichier « chiffré » est du base64, le binaire le décode ───
tmp = tempfile.mkdtemp(prefix="rm2713-")
bindir = pathlib.Path(tmp) / "bin"
bindir.mkdir()
(bindir / "age").write_text(
    '#!/bin/sh\n'
    '# faux age : `age --decrypt -i <cle> <fichier>` → clair sur stdout\n'
    '[ "$1" = "--decrypt" ] || { echo "usage" >&2; exit 2; }\n'
    'base64 -d "$4"\n')
(bindir / "age").chmod(0o755)

vault = pathlib.Path(tmp) / "acme.yml.age"
vault.write_bytes(base64.b64encode(DOC.encode()))
cle = pathlib.Path(tmp) / "id.age"
cle.write_text("AGE-SECRET-KEY-FACTICE\n")
cle.chmod(0o600)

PATH_ORIG = os.environ["PATH"]
os.environ["PATH"] = f"{bindir}:{PATH_ORIG}"

b = ps.get_backend("age", name="age-acme", file=str(vault), identity=str(cle))

# — registre et capacités —
check("type `age` enregistré dans BACKENDS", ps.BACKENDS.get("age") is ps.AgeBackend)
check("get_backend rend un AgeBackend", isinstance(b, ps.AgeBackend))
check("caps : pas de déverrouillage, listable, hiérarchique",
      b.caps.needs_unlock is False and b.caps.listable and b.caps.hierarchical)
check("caps : jamais en écriture", b.caps.writable is False)
check("`sops` n'est pas un type connu (décision RM2713)",
      erreur(ps.get_backend, "sops", name="x") == "unsupported")
try:
    ps.get_backend("sops", name="x")
except ps.SecretError as e:
    check("… en citant `age` dans les types connus", "age" in str(e))

# — résolution —
check("chemin imbriqué + champ", b.resolve(["acme", "db"], "username") == "acme_app")
check("sans champ → `password` par convention",
      b.resolve(["acme", "db"], None) == SECRET)
check("chemin jusqu'au scalaire", b.resolve(["acme", "db", "password"]) == SECRET)
check("scalaire à la racine", b.resolve(["racine_simple"]) == "valeur-a-plat")
check("statut : utilisable sans session", b.status() == "unlocked")

# — refus explicites plutôt que valeur vide —
check("clé absente → not_found", erreur(b.resolve, ["acme", "absent"]) == "not_found")
check("champ absent → not_found (jamais \"\")",
      erreur(b.resolve, ["acme", "db"], "zzz") == "not_found")
check("groupe sans password → not_found", erreur(b.resolve, ["acme", "api"]) == "not_found")
check("champ demandé sur un scalaire → not_found",
      erreur(b.resolve, ["racine_simple"], "password") == "not_found")
check("chemin vide → bad_uri", erreur(b.resolve, []) == "bad_uri")
try:
    b.resolve(["acme", "db"], "zzz")
except ps.SecretError as e:
    check("l'erreur liste les champs disponibles (des NOMS)",
          "username" in str(e) and "password" in str(e))
    check("… sans jamais citer une valeur", SECRET not in str(e))

# — listing : des chemins, pas des valeurs —
items = b.list()
ids = [i["id"] for i in items]
check("list() rend un enregistrement par item",
      "acme/db" in ids and "acme/api" in ids and "racine_simple" in ids)
check("list() range l'item sous son groupe",
      next(i for i in items if i["id"] == "acme/db")["collections"] == ["acme"])
check("list() ne rend aucune valeur", SECRET not in repr(items))
check("list(filtre) filtre sur le nom", [i["id"] for i in b.list("db")] == ["acme/db"])

# — déverrouillage : il n'y en a pas —
check("unlock() → unsupported, avec le nom de la variable de clé",
      erreur(b.unlock) == "unsupported")

# — INVARIANT : le clair ne touche jamais le disque —
b.resolve(["acme", "db"], "password")
sur_disque = []
for p in pathlib.Path(tmp).rglob("*"):
    if p.is_file():
        try:
            if SECRET in p.read_text(errors="ignore"):
                sur_disque.append(str(p))
        except OSError:
            pass
check(f"aucun fichier ne contient le clair après résolution ({sur_disque})",
      not sur_disque)

# — diagnostics : configuration d'abord, dépendance ensuite —
check("aucun fichier déclaré → unreachable",
      erreur(ps.get_backend("age", name="x", identity=str(cle)).resolve, ["a"]) == "unreachable")
try:
    ps.get_backend("age", name="x", identity=str(cle)).resolve(["a"])
except ps.SecretError as e:
    check("… en nommant SECRET__X__FILE", "SECRET__X__FILE" in str(e))
check("fichier déclaré mais absent → unreachable",
      erreur(ps.get_backend("age", name="x", file=tmp + "/nope.age",
                            identity=str(cle)).resolve, ["a"]) == "unreachable")
sans_cle = ps.get_backend("age", name="x", file=str(vault))
check("aucune clé → unreachable (pas `locked` : c'est de la config)",
      erreur(sans_cle.resolve, ["a"]) == "unreachable")
try:
    sans_cle.resolve(["a"])
except ps.SecretError as e:
    check("… en nommant SECRET__X__AGE_KEY_FILE", "SECRET__X__AGE_KEY_FILE" in str(e))
check("statut d'une instance sans clé → unreachable", sans_cle.status() == "unreachable")

# — identifiants par variables d'environnement —
os.environ["SECRET__AGE_ENV__FILE"] = str(vault)
os.environ["SECRET__AGE_ENV__AGE_KEY_FILE"] = str(cle)
benv = ps.get_backend("age", name="age-env")
check("chemins lus depuis SECRET__<SLUG>__FILE / __AGE_KEY_FILE",
      benv.resolve(["acme", "db"], "username") == "acme_app")
check("creds_keys ne rend que des noms",
      ps.creds_keys("age-env", legacy=False) == ["AGE_KEY_FILE", "FILE"])

# — binaire absent : les autres vaults doivent continuer de marcher —
os.environ["PATH"] = "/nonexistent"
check("`age` absent → unreachable", erreur(b.resolve, ["acme", "db"]) == "unreachable")
try:
    b.resolve(["acme", "db"])
except ps.SecretError as e:
    check("… avec la commande d'installation", "apt install age" in str(e))
check("statut sans binaire → unreachable", b.status() == "unreachable")
os.environ["PATH"] = f"{bindir}:{PATH_ORIG}"

# — échec de déchiffrement : mauvaise identité —
# Le VRAI `age` fait suivre son diagnostic d'une ligne d'invitation à signaler le
# bug : sans elle, ce faux passait alors que le vrai échouait (constaté à
# l'installation d'`age`). Le faux doit donc imiter la sortie réelle.
(bindir / "age").write_text(
    '#!/bin/sh\n'
    'echo "age: error: no identity matched any of the recipients" >&2\n'
    'echo "age: report unexpected or unhelpful errors at https://filippo.io/age/report" >&2\n'
    'exit 1\n')
(bindir / "age").chmod(0o755)
check("identité qui ne déchiffre pas → denied", erreur(b.resolve, ["acme", "db"]) == "denied")
try:
    b.resolve(["acme", "db"])
except ps.SecretError as e:
    check("… le message montre le diagnostic, pas l'invitation à signaler le bug",
          "no identity matched" in str(e) and "filippo.io" not in str(e))
(bindir / "age").write_text('#!/bin/sh\necho "age: failed to read header" >&2\nexit 1\n')
(bindir / "age").chmod(0o755)
check("fichier corrompu → unreachable", erreur(b.resolve, ["acme", "db"]) == "unreachable")

# — contenu déchiffré illisible : le message ne doit PAS citer le clair —
(bindir / "age").write_text(
    f'#!/bin/sh\nprintf \'%s\\n\' "clef: [non, ferme, pas: {SECRET}" \n')
(bindir / "age").chmod(0o755)
code = erreur(b.resolve, ["acme"])
check("YAML invalide → unreachable", code == "unreachable")
try:
    b.resolve(["acme"])
except ps.SecretError as e:
    check("… sans recopier le contenu déchiffré dans l'erreur", SECRET not in str(e))
(bindir / "age").write_text('#!/bin/sh\nprintf \'une liste:\\n- a\\n- b\\n\' | sed "s/^une liste://" \n')
(bindir / "age").chmod(0o755)
check("document qui n'est pas un mapping → unreachable",
      erreur(b.resolve, ["a"]) == "unreachable")

# ── niveau 2 : vrai `age`, si le poste l'a ───────────────────────────────────
os.environ["PATH"] = PATH_ORIG
vrai_age = shutil.which("age") and shutil.which("age-keygen")
if vrai_age:
    kdir = pathlib.Path(tempfile.mkdtemp(prefix="rm2713-reel-"))
    k = kdir / "id.age"
    subprocess.run(["age-keygen", "-o", str(k)], capture_output=True, check=True)
    k.chmod(0o600)
    pub = subprocess.run(["age-keygen", "-y", str(k)], capture_output=True,
                         text=True, check=True).stdout.strip()
    chiffre = kdir / "reel.yml.age"
    subprocess.run(["age", "--encrypt", "-r", pub, "-o", str(chiffre)],
                   input=DOC.encode(), capture_output=True, check=True)
    check("aller-retour réel : le fichier posé est bien chiffré",
          SECRET not in chiffre.read_bytes().decode(errors="ignore"))
    r = ps.get_backend("age", name="age-reel", file=str(chiffre), identity=str(k))
    check("aller-retour réel : résolution du mot de passe",
          r.resolve(["acme", "db"], "password") == SECRET)
    check("aller-retour réel : listing", "acme/api" in [i["id"] for i in r.list()])
    check("aller-retour réel : statut unlocked", r.status() == "unlocked")
    autre = kdir / "autre.age"
    subprocess.run(["age-keygen", "-o", str(autre)], capture_output=True, check=True)
    check("aller-retour réel : mauvaise clé → denied",
          erreur(ps.get_backend("age", name="x", file=str(chiffre),
                                identity=str(autre)).resolve, ["acme", "db"]) == "denied")
    shutil.rmtree(kdir, ignore_errors=True)
else:
    print("⊘ `age` non installé : aller-retour réel non joué "
          "(`sudo apt install age`) — le niveau 1 couvre le comportement")

# ── unlock-vault.sh : le diagnostic d'une instance `age` ─────────────────────
# Rien à déverrouiller, mais le script doit rester utile : dire si l'instance est
# réellement utilisable, et alerter quand la clé privée est trop ouverte.
core = pathlib.Path(tempfile.mkdtemp(prefix="rm2713-core-"))
conf = (HERE.parent / "pm.config.yml").read_text(encoding="utf-8")
ancre = "    vw-ipro:"
i = conf.index(ancre)
fin = conf.index("\n", i) + 1
conf = (conf[:fin] + f'    age-test: {{ axis: secret, type: age, '
                     f'file: "{vault}" }}\n' + conf[fin:])
(core / "pm.config.yml").write_text(conf, encoding="utf-8")
(core / ".env").write_text(f"PROJECTS_PATH={core}/projects\n", encoding="utf-8")
(core / "projects").mkdir()


def unlock(*args, **surcharges):
    env = dict(os.environ, PM_CORE_DIR=str(core), PATH=f"{bindir}:{PATH_ORIG}")
    env.update(surcharges)
    return subprocess.run([str(HERE / "unlock-vault.sh"), "-i", "age-test", *args],
                          capture_output=True, text=True, env=env, timeout=60)

# Le faux `age` a été abîmé par les tests d'erreur : on le remet en état.
(bindir / "age").write_text('#!/bin/sh\nbase64 -d "$4"\n')
(bindir / "age").chmod(0o755)

p = unlock("--print-instance", **{"SECRET__AGE_TEST__AGE_KEY_FILE": str(cle)})
check("unlock-vault.sh --print-instance : type age",
      "type=age" in p.stdout and f"file={vault}" in p.stdout)
check("… liste les clés attendues pour age (des NOMS)",
      "FILE" in p.stdout and "AGE_KEY_FILE" in p.stdout)
check("… et jamais les identifiants Vaultwarden d'une autre instance",
      "CLIENTID" not in p.stdout and "CLIENTSECRET" not in p.stdout)

p = unlock(**{"SECRET__AGE_TEST__AGE_KEY_FILE": str(cle)})
check("unlock-vault.sh : instance age utilisable → exit 0", p.returncode == 0)
check("… en disant qu'il n'y a rien à déverrouiller",
      "aucun déverrouillage" in p.stdout)
p = unlock()
check("unlock-vault.sh sans clé → exit 1", p.returncode == 1)
check("… en nommant la variable à renseigner", "AGE_KEY_FILE" in p.stderr)
cle.chmod(0o644)
p = unlock(**{"SECRET__AGE_TEST__AGE_KEY_FILE": str(cle)})
check("clé lisible par d'autres → avertissement chmod",
      "chmod 600" in p.stderr and p.returncode == 0)
cle.chmod(0o600)

shutil.rmtree(core, ignore_errors=True)
shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests du backend age passent")
