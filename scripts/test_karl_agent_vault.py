#!/usr/bin/env python3
"""Tests RM2748 — déverrouillage du vault et chargement de clé SSH par le cockpit.

Ce qui compte ici n'est pas « ça marche » mais « le secret ne fuit nulle part » :
on lance un VRAI ssh-agent jetable et un FAUX unlock-vault.sh qui enregistre tout
ce qu'il voit (argv, environnement, entrée standard), puis on vérifie que le mot
de passe n'apparaît que là où il doit — l'entrée standard — et nulle part ailleurs :
ni ligne de commande, ni environnement, ni fichier, ni réponse HTTP.

Lancer : python3 scripts/test_karl_agent_vault.py
"""
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2748-"))
os.environ["KARL_AGENT_STATE_DIR"] = str(tmp / "state")

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def refuses(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return False
    except ka.ApiError:
        return True
    except Exception:            # noqa: BLE001 — un autre échec n'est pas un refus
        return False


# ── lecture de l'état : rien que du public ───────────────────────────────────
inst = ka.vault_dashboard(
    "vw-ipro\tunlocked since=2026-08-20T10:00:00 last_access=2026-08-20T10:05:00\n"
    "kp-client\tlocked\n"
    "ligne sans tabulation")
check("tableau de bord : une entrée par instance", [i["slug"] for i in inst] == ["vw-ipro", "kp-client"])
check("tableau de bord : état déverrouillé lu", inst[0]["unlocked"] and not inst[1]["unlocked"])
check("tableau de bord : date de déverrouillage lue", inst[0]["since"] == "2026-08-20T10:00:00")
check("tableau de bord : vide si daemon muet", ka.vault_dashboard(None) == [])

keys = ka.ssh_keys_parse(
    "4096 SHA256:abc root@web-12.iprospective.fr (RSA)\n"
    "256 SHA256:def clef de test (ED25519)\n"
    "The agent has no identities.\n")
check("clés : une entrée par clé chargée", len(keys) == 2)
check("clés : commentaire multi-mots conservé", keys[1]["comment"] == "clef de test")
check("clés : type isolé", keys[0]["type"] == "RSA")

st = ka.op_vault_status()
check("statut : forme complète", set(st) >= {"daemon", "instances", "locked", "ssh", "needs_action"})
check("statut : aucune session/jeton rendu",
      "session" not in json.dumps(st).lower())

# ── garde des routes sensibles ───────────────────────────────────────────────
ka._guard_secret_route({"mode": "device", "user": "mathieu"})    # ne lève pas
check("garde : session authentifiée acceptée", True)
check("garde : sans mode → refus", refuses(ka._guard_secret_route, {}))
host = ka.HOST
try:
    ka.HOST = "127.0.0.1"
    ka._guard_secret_route({"mode": "open"})
    open_local = True
except ka.ApiError:
    open_local = False
finally:
    ka.HOST = host
check("garde : mode ouvert toléré sur écoute locale", open_local)
try:
    ka.HOST = "0.0.0.0"
    check("garde : mode ouvert REFUSÉ si l'écoute n'est pas locale",
          refuses(ka._guard_secret_route, {"mode": "open"}))
finally:
    ka.HOST = host

CTX = {"mode": "device", "user": "mathieu", "admin": True}
check("unlock : instance invalide refusée",
      refuses(ka.op_vault_unlock, {"instance": "../../etc", "password": "x"}, CTX))
check("unlock : mot de passe manquant refusé",
      refuses(ka.op_vault_unlock, {"instance": "vw-ipro"}, CTX))
check("unlock : mot de passe démesuré refusé",
      refuses(ka.op_vault_unlock, {"instance": "vw-ipro", "password": "x" * 5000}, CTX))
for bad in ("../id_rsa", "id_rsa.pub", "", "clé/../../x", "a" * 100):
    check(f"ssh-add : nom de clé refusé ({bad[:14] or '(vide)'})",
          refuses(ka.op_vault_ssh_add, {"key": bad, "passphrase": "x"}, CTX))

# ── déverrouillage : par où passe le mot de passe ────────────────────────────
SECRET = "mot-de-passe-maitre-JETABLE-42"
fake_root = tmp / "repo"
(fake_root / "scripts").mkdir(parents=True)
trace = tmp / "trace.json"
(fake_root / "scripts" / "unlock-vault.sh").write_text(
    "#!/usr/bin/env python3\n"
    "import json, os, sys\n"
    "json.dump({'argv': sys.argv, 'env': dict(os.environ), 'stdin': sys.stdin.read()},\n"
    f"          open({str(trace)!r}, 'w'))\n"
    "print('✓ Vault « vw-ipro » unlocked. unlocked since=…')\n",
    encoding="utf-8")
(fake_root / "scripts" / "unlock-vault.sh").chmod(0o755)

real_root = ka.REPO_ROOT
try:
    ka.REPO_ROOT = fake_root
    res = ka.op_vault_unlock({"instance": "vw-ipro", "password": SECRET}, CTX)
finally:
    ka.REPO_ROOT = real_root

seen = json.loads(trace.read_text(encoding="utf-8"))
check("unlock : script appelé avec --stdin", "--stdin" in seen["argv"])
check("unlock : instance transmise", "vw-ipro" in seen["argv"])
check("unlock : mot de passe ABSENT de la ligne de commande",
      not any(SECRET in a for a in seen["argv"]))
check("unlock : mot de passe ABSENT de l'environnement",
      not any(SECRET in v for v in seen["env"].values()))
check("unlock : mot de passe transmis par l'entrée standard",
      seen["stdin"].strip() == SECRET)
check("unlock : mot de passe ABSENT de la réponse", SECRET not in json.dumps(res))
check("unlock : verdict rendu", res["ok"] is True and res["instance"] == "vw-ipro")
check("unlock : aucun fichier temporaire laissé avec le secret",
      not any(SECRET in p.read_text(encoding="utf-8", errors="ignore")
              for p in tmp.glob("*.tmp")))

# ── RM2822 : le programme d'assistance lui-même ──────────────────────────────
# Contrat : il lit le descripteur que $KARL_ASKPASS_FD désigne, et garde le 3 en
# repli pour un appelant qui ne dit rien (le montage d'avant RM2822).
_ASKPASS = HERE.parent / "deploy" / "karl-agent" / "karl-askpass.sh"
_SANS_VAR = (
    "import os, subprocess, sys\n"
    "r, w = os.pipe()\n"
    "os.write(w, b'secret-fd3\\n'); os.close(w)\n"
    "p = subprocess.run([sys.argv[1], 'invite'], pass_fds=(r,), stdin=subprocess.DEVNULL,\n"
    "                   capture_output=True, text=True)\n"
    "print(r, p.returncode, p.stdout.strip(), p.stderr.strip())\n"
)
# processus neuf : os.pipe() y rend 3, c'est-à-dire le cas de l'appelant historique
_env_sans = {k: v for k, v in os.environ.items() if k != "KARL_ASKPASS_FD"}
_out = subprocess.run([sys.executable, "-c", _SANS_VAR, str(_ASKPASS)],
                      capture_output=True, text=True, env=_env_sans).stdout.split()
check("askpass : sans KARL_ASKPASS_FD, le descripteur 3 reste lu (repli)",
      _out[:3] == ["3", "0", "secret-fd3"])

_bad = subprocess.run([str(_ASKPASS), "invite"], capture_output=True, text=True,
                      stdin=subprocess.DEVNULL,
                      env={**os.environ, "KARL_ASKPASS_FD": "3; rm -rf /"})
check("askpass : un KARL_ASKPASS_FD non numérique est refusé (pas d'eval sauvage)",
      _bad.returncode == 2 and "invalide" in _bad.stderr)

# ── ssh-add : agent jetable, clé jetable, passphrase par descripteur ─────────
if not shutil.which("ssh-agent") or not shutil.which("ssh-keygen"):
    print("… ssh-agent/ssh-keygen absents : partie SSH non jouée")
else:
    home = tmp / "home"
    (home / ".ssh").mkdir(parents=True)
    PASS = "passphrase-JETABLE-77"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-f", str(home / ".ssh" / "tkey"),
                    "-N", PASS, "-C", "rm2748-test"], check=True)
    agent = subprocess.run(["ssh-agent", "-a", str(tmp / "agent.sock")],
                           capture_output=True, text=True)
    agent_pid = ""
    for line in agent.stdout.splitlines():
        if line.startswith("SSH_AGENT_PID="):
            agent_pid = line.split("=", 1)[1].split(";", 1)[0]
    old_home, old_sock = os.environ.get("HOME"), os.environ.get("SSH_AUTH_SOCK")
    try:
        os.environ["HOME"] = str(home)
        os.environ["SSH_AUTH_SOCK"] = str(tmp / "agent.sock")

        check("ssh-add : clés candidates listées par leur nom",
              ka._ssh_candidates() == ["tkey"])

        bad = ka.op_vault_ssh_add({"key": "tkey", "passphrase": "mauvaise"}, CTX)
        check("ssh-add : mauvaise passphrase → échec net (pas de blocage)", bad["ok"] is False)
        check("ssh-add : la passphrase n'est pas renvoyée", "mauvaise" not in json.dumps(bad))

        res = ka.op_vault_ssh_add({"key": "tkey", "passphrase": PASS}, CTX)
        check("ssh-add : clé chargée avec la bonne passphrase", res["ok"] is True)
        listed = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True,
                                env=dict(os.environ)).stdout
        check("ssh-add : la clé est bien dans l'agent", "rm2748-test" in listed)
        check("ssh-add : passphrase ABSENTE de la réponse", PASS not in json.dumps(res))

        st = ka.op_vault_status()
        check("statut : la clé chargée apparaît",
              any(k["comment"] == "rm2748-test" for k in st["ssh"]["keys"]))

        # RM2822 — le cas RÉEL : karl-agent est un serveur, ses sockets occupent
        # déjà les descripteurs bas, et le tube de la passphrase n'atterrit donc
        # JAMAIS sur 3. Un test lancé dans un processus nu, lui, obtient 3 par
        # hasard et ne voit rien. On occupe les descripteurs bas pour reproduire
        # le serveur : sans le correctif, l'askpass lit un fd inexistant et
        # ssh-add échoue en « Bad file descriptor ».
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-f", str(home / ".ssh" / "tkey2"),
                        "-N", PASS, "-C", "rm2822-test"], check=True)
        garde = [os.open(os.devnull, os.O_RDONLY) for _ in range(8)]
        try:
            res2 = ka.op_vault_ssh_add({"key": "tkey2", "passphrase": PASS}, CTX)
        finally:
            for fd in garde:
                os.close(fd)
        check("ssh-add : clé chargée alors que les descripteurs bas sont pris (RM2822)",
              res2["ok"] is True)
        check("ssh-add : aucun « bad file descriptor » (RM2822)",
              "file descriptor" not in (res2.get("detail") or "").lower())
        listed2 = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True,
                                 env=dict(os.environ)).stdout
        check("ssh-add : la 2e clé est bien dans l'agent (RM2822)", "rm2822-test" in listed2)
        check("ssh-add : passphrase ABSENTE de la réponse (RM2822)", PASS not in json.dumps(res2))
    finally:
        if old_home is not None:
            os.environ["HOME"] = old_home
        if old_sock is not None:
            os.environ["SSH_AUTH_SOCK"] = old_sock
        else:
            os.environ.pop("SSH_AUTH_SOCK", None)
        if agent_pid.isdigit():
            os.kill(int(agent_pid), 15)

shutil.rmtree(tmp, ignore_errors=True)
print()
if fails:
    print(f"✗ {len(fails)} test(s) en échec : {', '.join(fails)}")
    sys.exit(1)
print("✓ tous les tests passent")
