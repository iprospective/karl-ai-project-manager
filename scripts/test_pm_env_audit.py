#!/usr/bin/env python3
"""Tests offline de pm-env-audit (RM3163).

Lancer : python3 scripts/test_pm_env_audit.py
Couvre : détection BRANCHE (commits non intégrés par contenu, cherry-pick = intégré), gravité
d'après l'état réel de la MR (mergée → ÉLEVÉE, ouverte → info) et repli sur le ticket (fermé →
ÉLEVÉE, sans MR → moyenne), SALE avec l'âge, consignation par projet (history.md, fichier de
détail seulement si anomalie ou changement, Δ nouvelles/résolues). Aucun réseau, aucun commit.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_env_audit", str(_HERE / "pm-env-audit.py"))
ea = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ea)

from datetime import datetime  # noqa: E402


def sh(args, cwd):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


class Cfg:
    """PMConfig minimal : find_task → fiche temporaire (ou None)."""
    def __init__(self, tasks):
        self.tasks = tasks
        self.pm_dir = None

    def find_task(self, rm_id):
        return self.tasks.get(rm_id)


def make_layout(root: Path):
    """workspace RM1993 : repos/app.git (bare, origin = un autre bare) + envs/app-rm42 sur 42-foo."""
    ws = root / "client" / "proj"
    (ws / ".mmi-pm").mkdir(parents=True)
    origin = root / "origin.git"
    sh(["git", "init", "-q", "--bare", str(origin)], root)
    seed = root / "seed"
    sh(["git", "init", "-q", "-b", "master", str(seed)], root)
    (seed / "a.txt").write_text("a\n")
    sh(["git", "add", "a.txt"], seed)
    sh(["git", "commit", "-q", "-m", "init"], seed)
    sh(["git", "remote", "add", "origin", str(origin)], seed)
    sh(["git", "push", "-q", "origin", "master"], seed)
    bare = ws / "repos" / "app.git"
    sh(["git", "clone", "-q", "--bare", str(origin), str(bare)], root)
    sh(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], bare)
    wt = ws / "envs" / "app-rm42"
    sh(["git", "worktree", "add", "-q", "-b", "42-foo", str(wt), "master"], bare)
    (wt / "b.txt").write_text("b\n")
    sh(["git", "add", "b.txt"], wt)
    sh(["git", "commit", "-q", "-m", "RM42 b"], wt)
    return ws, bare, wt, origin, seed


def task_file(root: Path, rm, status, mr=None):
    p = root / f"RM{rm}_x.md"
    p.write_text("---\nredmine_id: %d\nstatus: %s\ngit:\n  mr_url: %s\n  mr_urls:\n%s---\n\nx\n" % (
        rm, status, mr or "null", f"  - {mr}\n" if mr else ""))
    return p


def test_task_info_reads_mr_urls():
    with tempfile.TemporaryDirectory() as td:
        p = task_file(Path(td), 7, "en_cours", "https://gitlab.example/g/p/-/merge_requests/12")
        ti = ea.task_info(Cfg({7: p}), 7)
        assert ti["status"] == "en_cours"
        assert ti["mr_urls"] == ["https://gitlab.example/g/p/-/merge_requests/12"], ti


def test_branche_detection_and_cherry_pick():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, bare, wt, origin, seed = make_layout(root)
        cfg = Cfg({})
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        br = [x for x in f if x["type"] == "BRANCHE"]
        assert len(br) == 1 and br[0]["commits"] == 1 and br[0]["ticket"] == 42, f
        assert br[0]["gravite"] == ea.MED, br[0]        # ticket inconnu, pas de MR → moyenne
        # le même contenu arrive sur master par cherry-pick → plus rien à signaler
        sha = sh(["git", "rev-parse", "42-foo"], bare).stdout.strip()
        sh(["git", "fetch", "-q", str(bare), "42-foo"], seed)
        sh(["git", "cherry-pick", sha], seed)
        sh(["git", "push", "-q", "origin", "master"], seed)
        sh(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], bare)
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        assert not [x for x in f if x["type"] == "BRANCHE"], f


def test_severity_from_mr_state_and_ticket(monkey=None):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        url = "https://gitlab.example/g/p/-/merge_requests/5"
        ti = {"status": "en_cours", "mr_urls": [url]}
        ea._MR_CACHE.clear()
        ea._fetch_mr_state = lambda u: {"state": "merged", "iid": 5, "source": "42-foo", "target": "master",
                                        "merged_at": "2026-08-10T10:00:00Z"}
        sev, why, mr = ea.branch_severity("42-foo", 3, 42, ti, True)
        assert sev == ea.HIGH and "mergée le 2026-08-10" in why and "3 commit(s) postérieurs" in why, (sev, why)
        assert mr["mr_state"] == "merged"
        ea._MR_CACHE.clear()
        ea._fetch_mr_state = lambda u: {"state": "opened", "iid": 5, "source": "42-foo", "target": "master"}
        sev, why, _ = ea.branch_severity("42-foo", 3, 42, ti, True)
        assert sev == ea.LOW and "ouverte" in why, (sev, why)
        ea._MR_CACHE.clear()
        ea._fetch_mr_state = lambda u: {"error": "GITLAB_WORKER_TOKEN absent"}
        sev, why, _ = ea.branch_severity("42-foo", 3, 42, ti, True)
        assert sev == ea.LOW and "non vérifié" in why, (sev, why)
        # repli ticket : fermé sans MR connue → ÉLEVÉE ; ouvert sans MR → moyenne ; --no-forge idem
        sev, why, _ = ea.branch_severity("42-foo", 1, 42, {"status": "ferme", "mr_urls": []}, True)
        assert sev == ea.HIGH, (sev, why)
        sev, why, _ = ea.branch_severity("42-foo", 1, 42, {"status": "en_cours", "mr_urls": []}, True)
        assert sev == ea.MED, (sev, why)
        ea._MR_CACHE.clear()
        ea._fetch_mr_state = lambda u: (_ for _ in ()).throw(AssertionError("forge appelée malgré --no-forge"))
        sev, why, _ = ea.branch_severity("42-foo", 1, 42, {"status": "ferme", "mr_urls": [url]}, False)
        assert sev == ea.HIGH and "ferme" in why, (sev, why)


def test_sale_age_and_consignation():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, bare, wt, origin, seed = make_layout(root)
        old = wt / "old.txt"
        old.write_text("x")
        t = time.time() - 30 * 86400
        os.utime(old, (t, t))
        cfg = Cfg({42: task_file(root, 42, "en_cours")})
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        sale = [x for x in f if x["type"] == "SALE"]
        assert len(sale) == 1 and sale[0]["gravite"] == ea.HIGH and sale[0]["age_max_j"] >= 29, sale
        # 1er audit : history + détail + last.json, sans commit
        when = datetime(2026, 9, 15, 8, 30)
        d = ea.consign_workspace(ws, f, when, fetch=False, commit=False)
        ad = ea.audit_dir(ws)
        assert (ad / "history.md").exists() and (ad / "last.json").exists()
        assert d["detail"] and d["detail"].name == "2026-09-15_0830.md", d
        txt = d["detail"].read_text()
        assert "Premier audit" in txt and "SALE" in txt and "BRANCHE" in txt, txt
        assert len(d["nouvelles"]) == 2 and not d["resolues"], d
        rows = [l for l in (ad / "history.md").read_text().splitlines() if l.startswith("| 20")]
        assert len(rows) == 1 and "| premier |" in rows[0], rows
        # 2e audit : le fichier sale a disparu → résolue ; la branche reste → détail écrit (anomalie)
        old.unlink()
        f2 = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        d2 = ea.consign_workspace(ws, f2, datetime(2026, 9, 22, 8, 30), fetch=True, commit=False)
        assert d2["resolues"] and "non commités" in d2["resolues"][0] and not d2["nouvelles"], d2
        rows = [l for l in (ad / "history.md").read_text().splitlines() if l.startswith("| 20")]
        assert len(rows) == 2 and "| oui |" in rows[1] and "+0 / −1" in rows[1], rows
        assert "résolue" in d2["detail"].read_text()
        assert ea.last_of_workspace(ws) == rows[1]
        # 3e audit : plus rien (branche mergée) → ligne d'historique, résolue, puis 4e sans changement → pas de détail
        sha = sh(["git", "rev-parse", "42-foo"], bare).stdout.strip()
        sh(["git", "fetch", "-q", str(bare), "42-foo"], seed)
        sh(["git", "merge", "-q", "--ff-only", sha], seed)
        sh(["git", "push", "-q", "origin", "master"], seed)
        sh(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], bare)
        f3 = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        assert not f3, f3
        d3 = ea.consign_workspace(ws, f3, datetime(2026, 9, 29, 8, 30), fetch=False, commit=False)
        assert d3["detail"] is not None and len(d3["resolues"]) == 1, d3
        d4 = ea.consign_workspace(ws, [], datetime(2026, 10, 6, 8, 30), fetch=False, commit=False)
        assert d4["detail"] is None and not d4["nouvelles"] and not d4["resolues"], d4
        rows = [l for l in (ad / "history.md").read_text().splitlines() if l.startswith("| 20")]
        assert len(rows) == 4 and rows[-1].endswith("| +0 / −0 | — |"), rows
        assert len(list(ad.glob("2026-*.md"))) == 3, list(ad.iterdir())
        st = json.loads((ad / "last.json").read_text())
        assert st["cles"] == [] and st["date"] == "2026-10-06 08:30"


def test_closed_ticket_worktree():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, bare, wt, origin, seed = make_layout(root)
        cfg = Cfg({42: task_file(root, 42, "ferme")})
        # fermé + commits non intégrés → FERMÉ moyenne (renvoie à BRANCHE, elle ÉLEVÉE), pas nettoyable
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        kinds = {x["type"]: x for x in f}
        assert kinds["FERMÉ"]["gravite"] == ea.MED and kinds["FERMÉ"]["nettoyable"] is False, kinds["FERMÉ"]
        assert kinds["BRANCHE"]["gravite"] == ea.HIGH, kinds["BRANCHE"]
        # fermé + modifs non commitées → ÉLEVÉE
        (wt / "wip.txt").write_text("wip")
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        kinds = {x["type"]: x for x in f}
        assert kinds["FERMÉ"]["gravite"] == ea.HIGH and "non commitée" in kinds["FERMÉ"]["quoi"], kinds["FERMÉ"]
        (wt / "wip.txt").unlink()
        # fermé, propre, intégré → env obsolète, nettoyable, commande pm-env-gc donnée
        sha = sh(["git", "rev-parse", "42-foo"], bare).stdout.strip()
        sh(["git", "fetch", "-q", str(bare), "42-foo"], seed)
        sh(["git", "merge", "-q", "--ff-only", sha], seed)
        sh(["git", "push", "-q", "origin", "master"], seed)
        sh(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], bare)
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        kinds = {x["type"]: x for x in f}
        assert list(kinds) == ["FERMÉ"], f
        assert kinds["FERMÉ"]["gravite"] == ea.LOW and kinds["FERMÉ"]["nettoyable"] is True, kinds["FERMÉ"]
        assert f"pm-env-gc --apply --workspace {ws}" in kinds["FERMÉ"]["quoi"], kinds["FERMÉ"]


def test_stash_in_bare():
    """Le stash vit dans le bare (refs/stash) : `git stash list` y est muet, le reflog non."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, bare, wt, origin, seed = make_layout(root)
        (wt / "a.txt").write_text("modif\n")
        sh(["git", "stash", "push", "-q", "-m", "essai"], wt)
        f = ea.audit_repo(Cfg({}), ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        st = [x for x in f if x["type"] == "STASH"]
        assert len(st) == 1 and st[0]["entrees"] == 1 and "essai" in st[0]["quoi"], f


def test_remote_branches_hors_convention():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws, bare, wt, origin, seed = make_layout(root)
        # une branche distante sans id de ticket, avec un commit propre à elle (pas "develop" :
        # nom réservé, désormais candidat d'intégration lui-même — cf. INTEGRATION_NAMES)
        sh(["git", "checkout", "-q", "-b", "release-9.0"], seed)
        (seed / "c.txt").write_text("c\n")
        sh(["git", "add", "c.txt"], seed)
        sh(["git", "commit", "-q", "-m", "amont"], seed)
        sh(["git", "push", "-q", "origin", "release-9.0"], seed)
        sh(["git", "fetch", "-q", "origin", "+refs/heads/*:refs/remotes/origin/*"], bare)
        cfg = Cfg({})
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False)
        br = [x for x in f if x["type"] == "BRANCHE"]
        assert any("42-foo" in x["quoi"] for x in br), br
        assert not any("release-9.0" in x["quoi"] for x in br), br        # pas parcourue par défaut
        assert any("1 branche(s) distante(s) hors convention" in x["quoi"] and x["gravite"] == ea.LOW for x in br), br
        f = ea.audit_repo(cfg, ws, bare, "app.git", fetch=False, max_age=7, use_forge=False, all_branches=True)
        br = [x for x in f if x["type"] == "BRANCHE"]
        assert any("origin/release-9.0" in x["quoi"] and "1 commit(s)" in x["quoi"] for x in br), br
        assert not any("hors convention" in x["quoi"] for x in br), br


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback
            print(f"✗ {t.__name__} : {e}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} OK")
    sys.exit(1 if failed else 0)
