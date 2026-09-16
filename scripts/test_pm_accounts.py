#!/usr/bin/env python3
"""Tests RM3208 (U1) — le registre des comptes PM, partagé par le cockpit et le CLI.

Ce qui doit tenir :
- un seul registre (`var/karl-users.json`) que le cockpit et `mmi-pm user` écrivent tous deux ;
- jamais de mot de passe en clair, fichier en 0600 ;
- les règles de l'API du cockpit (nom, réservation du superadmin, doublon, longueur) inchangées ;
- un compte peut exister SANS mot de passe (créé en CLI) : il n'ouvre alors aucune session ;
- changer le mot de passe ou désactiver révoque les appareils ;
- deux processus qui écrivent en même temps ne perdent rien (verrou fichier) ;
- une écriture faite en root rend le fichier à son propriétaire (le démon, lui, ne tourne pas en root).
"""
import json
import multiprocessing
import os
import stat
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_accounts as acc  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def raises(fn, status):
    try:
        fn()
    except acc.AccountError as e:
        return e.status == status
    return False


def _create_many(users_path, prefix, n):
    for i in range(n):
        acc.create_user(Path(users_path), f"{prefix}{i}", "motdepasse-assez-long")


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        users, devices = d / "karl-users.json", d / "karl-devices.json"

        print("résolution du dossier")
        os.environ.pop("KARL_AGENT_AUTH_DIR", None)
        check("défaut = <racine du dépôt>/var", acc.auth_dir(Path("/x/core")) == Path("/x/core/var"))
        os.environ["KARL_AGENT_AUTH_DIR"] = str(d / "ailleurs")
        check("KARL_AGENT_AUTH_DIR prime", acc.auth_dir(Path("/x/core")) == d / "ailleurs")
        os.environ.pop("KARL_AGENT_AUTH_DIR", None)

        print("création")
        r = acc.create_user(users, "Alice", "motdepasse1")
        check("nom normalisé en minuscules", r == {"user": "alice", "created": True}, r)
        raw = users.read_text(encoding="utf-8")
        check("aucun mot de passe en clair", "motdepasse1" not in raw)
        check("fichier en 0600", stat.S_IMODE(users.stat().st_mode) == 0o600, oct(users.stat().st_mode))
        check("doublon → 409", raises(lambda: acc.create_user(users, "alice", "motdepasse1"), 409))
        check("nom invalide → 400", raises(lambda: acc.create_user(users, "-x", "motdepasse1"), 400))
        check("nom trop court → 400", raises(lambda: acc.create_user(users, "a", "motdepasse1"), 400))
        check("nom du superadmin réservé → 400",
              raises(lambda: acc.create_user(users, "Admin", "motdepasse1", superadmin="admin"), 400))
        check("mot de passe < 8 → 400", raises(lambda: acc.create_user(users, "bob", "court"), 400))

        print("compte sans mot de passe (créé en CLI)")
        acc.create_user(users, "claire", None, extra={"os_role": "claire-pm"})
        rec = acc.load(users)["claire"]
        check("pas de hash", "hash" not in rec, rec)
        check("champ additionnel conservé", rec.get("os_role") == "claire-pm", rec)
        check("aucune session possible", acc.password_ok("", rec) is False and acc.password_ok("x" * 12, rec) is False)

        print("mot de passe")
        rec = acc.load(users)["alice"]
        check("bon mot de passe accepté", acc.password_ok("motdepasse1", rec))
        check("mauvais refusé", not acc.password_ok("motdepasse2", rec))

        print("appareils et révocation")
        acc.save(devices, {"d1": {"user": "alice"}, "d2": {"user": "alice"}, "d3": {"user": "claire"}})
        u = acc.update_user(users, devices, "alice", password="nouveau-mdp")
        check("changer le mot de passe révoque les appareils", u.get("devices_revoked") == 2, u)
        check("nouveau mot de passe actif", acc.password_ok("nouveau-mdp", acc.load(users)["alice"]))
        u = acc.update_user(users, devices, "claire", disabled=True)
        check("désactiver révoque", u.get("disabled") is True and u.get("devices_revoked") == 1, u)
        u = acc.update_user(users, devices, "claire", disabled=False)
        check("réactiver ne révoque rien", u.get("disabled") is False and "devices_revoked" not in u, u)
        check("rien à changer → 400", raises(lambda: acc.update_user(users, devices, "alice"), 400))
        check("compte inconnu → 404", raises(lambda: acc.update_user(users, devices, "zoe", disabled=True), 404))
        check("mot de passe court en mise à jour → 400",
              raises(lambda: acc.update_user(users, devices, "alice", password="court"), 400))

        print("liste")
        acc.save(devices, {"d9": {"user": "alice"}})
        lst = acc.list_users(users, devices, superadmin="admin")
        by = {x["user"]: x for x in lst["users"]}
        check("superadmin restitué", lst["superadmin"] == "admin")
        check("appareils comptés", by["alice"]["devices"] == 1 and by["claire"]["devices"] == 0, by)
        check("mot de passe défini signalé", by["alice"]["password_set"] and not by["claire"]["password_set"], by)
        check("rôle OS restitué", by["claire"].get("os_role") == "claire-pm", by)

        print("suppression")
        r = acc.delete_user(users, devices, "alice")
        check("supprimé + appareils révoqués", r == {"user": "alice", "deleted": True, "devices_revoked": 1}, r)
        check("inconnu → 404", raises(lambda: acc.delete_user(users, devices, "alice"), 404))

        print("concurrence inter-processus")
        ps = [multiprocessing.Process(target=_create_many, args=(str(users), p, 15)) for p in ("px", "py", "pz")]
        for p in ps:
            p.start()
        for p in ps:
            p.join()
        names = set(json.loads(users.read_text(encoding="utf-8")))
        manquants = [f"{p}{i}" for p in ("px", "py", "pz") for i in range(15) if f"{p}{i}" not in names]
        check("45 créations concurrentes, aucune perdue", not manquants, manquants[:5])

        print("propriétaire rendu après écriture root")
        check("fichier existant → son propriétaire",
              acc.target_owner(users) == (users.stat().st_uid, users.stat().st_gid))
        neuf = d / "sous" / "neuf.json"
        neuf.parent.mkdir()
        check("fichier neuf → propriétaire du dossier",
              acc.target_owner(neuf) == (neuf.parent.stat().st_uid, neuf.parent.stat().st_gid))

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
