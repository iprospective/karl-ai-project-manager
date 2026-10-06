#!/usr/bin/env python3
"""Tests RM3068 — pm-provider-secret : la valeur ne passe jamais en argument, rien ne la relit,
le reste du fichier survit, les permissions restent 0600, le journal ne garde que le fait."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ps", HERE / "pm-provider-secret.py")
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


print("[RM3068] nom de la variable")
check("axe et instance normalisés", P.nom_variable("vw-ipro", "CLIENTID", "SECRET") == "SECRET__VW_IPRO__CLIENTID")
check("point et tiret deviennent _", P.nom_variable("ollama.local-1", "API_KEY", "LLM") == "LLM__OLLAMA_LOCAL_1__API_KEY")
for mauvais in [("../x", "K", "SECRET"), ("i", "k minuscule", "SECRET"), ("i", "K", "sec ret"), ("", "K", "SECRET")]:
    try:
        P.nom_variable(*mauvais); check(f"refus {mauvais}", False)
    except ValueError:
        check(f"refus {mauvais}", True)

print("\n[RM3068] écriture : atomique, ciblée, 0600")
with tempfile.TemporaryDirectory() as tmp:
    env = pathlib.Path(tmp) / ".env"
    env.write_text("AUTRE_CLE=valeur-d-un-tiers\n# un commentaire\nREDMINE__A__API_KEY=ancienne\n")
    check("pose une clé neuve", P.ecrit(env, "SECRET__VW__CLIENTID", "v1") == "posée")
    check("remplace une clé existante", P.ecrit(env, "REDMINE__A__API_KEY", "v2") == "remplacée")
    txt = env.read_text()
    check("le reste du fichier est intact", "AUTRE_CLE=valeur-d-un-tiers" in txt and "# un commentaire" in txt)
    check("une seule ligne par variable", txt.count("REDMINE__A__API_KEY=") == 1 and "ancienne" not in txt)
    check("permissions 0600", oct(env.stat().st_mode)[-3:] == "600", oct(env.stat().st_mode))
    check("efface", P.ecrit(env, "SECRET__VW__CLIENTID", None, unset=True) == "effacée" and "SECRET__VW__CLIENTID" not in env.read_text())
    check("effacer une absente ne casse rien", P.ecrit(env, "SECRET__ZZ__X", None, unset=True) == "absente")
    check("état des clés : le fait, pas la valeur", P.etat_cles(env, "A") == [("REDMINE__A__API_KEY", True)])
    env.write_text(env.read_text() + "LLM__B__API_KEY=\n")
    check("une clé vide est signalée vide", ("LLM__B__API_KEY", False) in P.etat_cles(env))

print("\n[RM3068] la valeur ne passe QUE par l'entrée standard")
src = (HERE / "pm-provider-secret.py").read_text()
check("aucune option --value / --secret dans le CLI", "--value" not in src and '"--secret"' not in src)
with tempfile.TemporaryDirectory() as tmp:
    home = pathlib.Path(tmp); envd = home / "var" / "users" / "moi"     # RM3318 : conf dans var/, pas le home
    e = dict(os.environ, HOME=str(home), PM_USER_DIR=str(envd))
    r = subprocess.run([sys.executable, str(HERE / "pm-provider-secret.py"), "--instance", "vw", "--key", "CLIENTID",
                        "--type", "vaultwarden"], input="s3cr3t\n", capture_output=True, text=True, env=e)
    check("écrit dans le .env du dev courant", r.returncode == 0 and "s3cr3t" in (envd / ".env").read_text(), r.stdout + r.stderr)
    check("la sortie ne contient PAS la valeur", "s3cr3t" not in r.stdout and "s3cr3t" not in r.stderr, r.stdout)
    r = subprocess.run([sys.executable, str(HERE / "pm-provider-secret.py"), "--instance", "vw", "--status"],
                       capture_output=True, text=True, env=e)
    check("--status dit posée, jamais la valeur", "SECRET__VW__CLIENTID" in r.stdout and "posée" in r.stdout and "s3cr3t" not in r.stdout, r.stdout)
    r = subprocess.run([sys.executable, str(HERE / "pm-provider-secret.py"), "--instance", "vw", "--key", "CLIENTID",
                        "--type", "vaultwarden"], input="   \n", capture_output=True, text=True, env=e)
    check("valeur vide refusée (--unset pour effacer)", r.returncode != 0 and "vide" in (r.stdout + r.stderr))
    r = subprocess.run([sys.executable, str(HERE / "pm-provider-secret.py"), "--instance", "../evasion", "--key", "K",
                        "--type", "vaultwarden"], input="x\n", capture_output=True, text=True, env=e)
    check("instance qui tente une évasion de chemin refusée", r.returncode != 0)
    r = subprocess.run([sys.executable, str(HERE / "pm-provider-secret.py"), "--instance", "vw", "--key", "CLIENTID",
                        "--user", "utilisateur-qui-n-existe-pas"], input="x\n", capture_output=True, text=True, env=e)
    check("utilisateur inconnu refusé", r.returncode != 0 and "inconnu" in (r.stdout + r.stderr))

print("\n[RM3068] portées")
import getpass
_udir = os.environ.pop("PM_USER_DIR", None)          # le défaut, pas l'override du lanceur
check("scope user = le .env du dev, dans var/users/<user>/ (RM3318)",
      str(P.env_path("user")).endswith(f"/var/users/{getpass.getuser()}/.env")
      and "/.config/" not in str(P.env_path("user")), str(P.env_path("user")))
if _udir is not None:
    os.environ["PM_USER_DIR"] = _udir
os.environ["PM_CORE_DIR"] = "/tmp/faux-core"
check("scope global = le .env de l'instance", str(P.env_path("global")) == "/tmp/faux-core/.env")
del os.environ["PM_CORE_DIR"]


# ── Saisie interactive (RM3277) ─────────────────────────────────────────────
print("\nSaisie interactive")
import io
check("nom de clé demandé et normalisé", P.demander_nom_cle("NC", lambda _p: " user ") == "USER")
try:
    P.demander_nom_cle("NC", lambda _p: "clé-invalide")
    check("nom de clé invalide refusé", False)
except ValueError:
    check("nom de clé invalide refusé", True)
check("les exemples suivent le provider",
      "USER" in P.CLES_USUELLES["NC"] and "API_KEY" in P.CLES_USUELLES["REDMINE"])

saisies = iter(["s3cret", "s3cret"])
check("valeur masquée, confirmée, rendue",
      P.lire_valeur(True, lecteur_masque=lambda _p: next(saisies)) == "s3cret")
divergentes = iter(["s3cret", "s3crat"])
try:
    P.lire_valeur(True, lecteur_masque=lambda _p: next(divergentes))
    check("deux saisies différentes : refus", False)
except ValueError as e:
    check("deux saisies différentes : refus", "diffèrent" in str(e))
check("hors terminal : l'entrée standard, inchangée",
      P.lire_valeur(False, flux=io.StringIO(" valeur-pipee \n")) == "valeur-pipee")
# ── Préfixe déduit du registre (RM3263) ─────────────────────────────────────
print("\nPréfixe déduit du registre")
# registre simulé : ne dépend d'aucun type ni axe ajouté par un autre ticket
faux = {"nc-ipro": ("nextcloud", "doc"), "vault-maison": ("type-maison", "secret"),
        "mystere": ("inconnu", "inconnu")}.get
check("instance déclarée : préfixe déduit du type",
      P.deduire_prefixe(None, None, None, "nc-ipro", faux) == "NC")
check("axe en repli quand le type est inconnu",
      P.deduire_prefixe(None, None, None, "vault-maison", faux) == "SECRET")
check("--type explicite garde la priorité",
      P.deduire_prefixe(None, "vaultwarden", None, "nc-ipro", faux) == "SECRET")
check("--prefix garde la priorité",
      P.deduire_prefixe("XYZ", "nextcloud", None, "nc-ipro", faux) == "XYZ")
check("instance inconnue et aucun indice : rien à déduire",
      P.deduire_prefixe(None, None, None, "mystere", faux) is None)
check("registre injoignable : pas d'exception, juste None",
      P.deduire_prefixe(None, None, None, "x", lambda n: (_ for _ in ()).throw(RuntimeError())) is None)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — pm-provider-secret"))
sys.exit(1 if FAIL else 0)
