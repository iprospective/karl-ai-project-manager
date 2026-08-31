#!/usr/bin/env python3
"""Tests RM2809 — pm-promote trace la promotion sur les tickets du lot.

Un ticket promu restait, dans son suivi, arrêté à `dev` : l'information n'était
pas perdue, elle n'était jamais produite.

Sans réseau : dépôt git local jetable, forge remplacée par un double, et les
appels aux scripts PM (`pm-task-comment`, `pm-task-status-update`) interceptés.

Lancer : python3 scripts/test_pm_promote_tickets.py
"""
import contextlib
import importlib.util
import io
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_forge
import pm_paths

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=str(cwd), check=True,
                          capture_output=True, text=True).stdout.strip()


def load_promote():
    spec = importlib.util.spec_from_file_location("pm_promote", HERE / "pm-promote.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Caps:
    pull_request_api = True


class _Project:
    path = "test/repo"
    id = 1


class _Forge:
    capabilities = _Caps()

    def token(self, _role):
        return "fake-token"

    def resolve_project(self, _token):
        return _Project()


def seed(tmp):
    """main aligné, puis sur dev : un commit de ticket direct + un commit de merge."""
    bare = tmp / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    work = tmp / "work"
    subprocess.run(["git", "clone", "-q", str(bare), str(work)], check=True)
    git("config", "user.email", "t@t", cwd=work)
    git("config", "user.name", "t", cwd=work)
    (work / "a.txt").write_text("1\n")
    git("add", "a.txt", cwd=work)
    git("commit", "-qm", "init", cwd=work)
    git("push", "-q", "origin", "main:main", cwd=work)
    git("checkout", "-q", "-b", "dev", cwd=work)

    # 1) commit direct portant le RM<id> dans son sujet
    (work / "b.txt").write_text("2\n")
    git("add", "b.txt", cwd=work)
    git("commit", "-qm", "RM2857 : porter le timeout de 1 h à 4 h", cwd=work)

    # 2) branche de ticket mergée — le sujet du merge ne porte PAS le RM<id>,
    #    seulement le nom de branche. C'est le cas nominal d'un lot passé par MR.
    git("checkout", "-q", "-b", "2777-barre-progression-panier", cwd=work)
    (work / "c.txt").write_text("3\n")
    git("add", "c.txt", cwd=work)
    git("commit", "-qm", "barre de progression", cwd=work)
    git("checkout", "-q", "dev", cwd=work)
    git("merge", "-q", "--no-ff", "-m",
        "Merge branch '2777-barre-progression-panier' into 'dev'",
        "2777-barre-progression-panier", cwd=work)

    # 3) auto-commit sans ticket : ne doit rien casser
    (work / "d.txt").write_text("4\n")
    git("add", "d.txt", cwd=work)
    git("commit", "-qm", "pm(tick): métriques", cwd=work)

    git("push", "-q", "origin", "dev:dev", cwd=work)
    git("fetch", "-q", "origin", cwd=work)
    return work


def run_promote(work, *argv):
    mod = load_promote()
    real = pm_forge.get_forge
    pm_forge.get_forge = lambda _repo: _Forge()
    old_argv = sys.argv
    sys.argv = ["pm-promote.py", "--repo", str(work), *argv]
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                mod.main()
            except SystemExit:
                pass
    finally:
        sys.argv = old_argv
        pm_forge.get_forge = real
    return buf.getvalue()


class _FakeSubprocess:
    """Intercepte les appels aux scripts PM et note ce qui a été demandé."""

    def __init__(self):
        self.calls = []

    def run(self, argv, **kw):
        self.calls.append([str(a) for a in argv])

        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        work = seed(tmp)
        mod = load_promote()

        # ---- énumération du lot -------------------------------------------
        ids = mod.batch_ticket_ids(work, "main", "origin/dev")
        check("le commit direct RM<id> est reconnu", 2857 in ids, str(ids))
        check("le commit de MERGE est reconnu par son nom de branche",
              2777 in ids, str(ids))
        check("aucun id parasite", sorted(ids) == [2777, 2857], str(ids))

        # ---- le lot est annoncé, y compris en dry-run ----------------------
        out = run_promote(work, "--source", "dev", "--target", "main",
                          "--no-flush", "--dry-run")
        check("--dry-run annonce les tickets du lot",
              "RM2857" in out and "RM2777" in out, out.strip())
        check("--dry-run ne pose aucune note",
              "ni note sur les tickets" in out, out.strip())

        # ---- un id sans ticket n'interrompt rien ---------------------------
        class _EmptyCfg:
            def find_task(self, _rm_id):
                return None

        real_load = pm_paths.PMConfig.load
        pm_paths.PMConfig.load = staticmethod(lambda *a, **k: _EmptyCfg())
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                mod.annotate_tickets([2857, 2777], work, "main", "deadbeefcafe")
        except Exception as e:                                   # noqa: BLE001
            check("un id sans ticket n'interrompt pas la promotion", False, repr(e))
        else:
            check("un id sans ticket n'interrompt pas la promotion", True)
            check("les ids sans ticket sont annoncés",
                  "sans ticket" in buf.getvalue(), buf.getvalue().strip())
        finally:
            pm_paths.PMConfig.load = real_load

        # ---- ticket réel : note posée, transition proposée puis appliquée ---
        tf = tmp / "RM2857_x.md"
        tf.write_text("---\nredmine_id: 2857\nstatus: a_mep\n---\n\ncorps\n", encoding="utf-8")

        class _OneCfg:
            def find_task(self, rm_id):
                return tf if rm_id == 2857 else None

        pm_paths.PMConfig.load = staticmethod(lambda *a, **k: _OneCfg())
        fake = _FakeSubprocess()
        real_sp = mod.subprocess
        mod.subprocess = fake
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                mod.annotate_tickets([2857], work, "main", "deadbeefcafe")
            noted = [c for c in fake.calls if any("pm-task-comment.py" in a for a in c)]
            check("une note est posée sur le ticket", len(noted) == 1, str(fake.calls))
            check("la note porte le commit de promotion et la cible",
                  any("deadbeefcafe"[:12] in a for a in noted[0])
                  and any("`main`" in a for a in noted[0]), str(noted))
            check("sans --advance, la transition est seulement proposée",
                  "--advance" in buf.getvalue()
                  and not any("pm-task-status-update.py" in a for c in fake.calls for a in c),
                  buf.getvalue().strip())

            fake.calls.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                mod.annotate_tickets([2857], work, "main", "deadbeefcafe", advance=True)
            adv = [c for c in fake.calls if any("pm-task-status-update.py" in a for a in c)]
            check("avec --advance, a_mep → en_mep est appliqué",
                  len(adv) == 1 and "en_mep" in adv[0], str(fake.calls))

            # un ticket qui n'est pas en a_mep ne doit pas être poussé plus loin
            tf.write_text("---\nredmine_id: 2857\nstatus: en_cours\n---\n", encoding="utf-8")
            fake.calls.clear()
            with contextlib.redirect_stdout(io.StringIO()):
                mod.annotate_tickets([2857], work, "main", "deadbeefcafe", advance=True)
            check("un ticket hors a_mep n'est pas transitionné",
                  not any("pm-task-status-update.py" in a for c in fake.calls for a in c),
                  str(fake.calls))
        finally:
            mod.subprocess = real_sp
            pm_paths.PMConfig.load = real_load

    print()
    if fails:
        print(f"{len(fails)} test(s) en échec : {', '.join(fails)}")
        return 1
    print("tous les tests passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
