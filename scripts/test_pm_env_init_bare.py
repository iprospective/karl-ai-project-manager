#!/usr/bin/env python3
"""Tests RM3587 — pm-env-init crée un bare sous une racine 2750 via le helper.

Sans privilège : un faux helper reproduit le seul effet utile (`git init --bare
--shared=group`), et `repos/` est rendu non inscriptible pour forcer le chemin
privilégié. Le chemin direct reste couvert sur un `repos/` inscriptible.
"""
import importlib.util
import os
import pathlib
import shutil
import stat
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def load():
    spec = importlib.util.spec_from_file_location("pm_env_init", HERE / "pm-env-init.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_ws(root):
    ws = root / "client" / "proj"
    (ws / "repos").mkdir(parents=True)
    return ws


def run_case(use_helper, root, mod):
    ws = make_ws(root)
    repos = ws / "repos"
    if use_helper:
        repos.chmod(0o555)
        helper = root / "fake-helper"
        helper.write_text(
            "#!/bin/sh\n"
            "set -e\n"
            "ws=\"$2\"; name=\"$3\"\n"
            "chmod u+w \"$ws/repos\"\n"
            "git init --bare -q --shared=group \"$ws/repos/$name.git\"\n"
            "chmod 2770 \"$ws/repos/$name.git\"\n"
            "chmod u-w \"$ws/repos\"\n"
        )
        helper.chmod(0o755)
        os.environ["PM_ENV_HELPER"] = str(helper)
        os.environ["PM_ENV_HELPER_NO_SUDO"] = "1"
    else:
        repos.chmod(0o770)
        os.environ.pop("PM_ENV_HELPER", None)
        os.environ.pop("PM_ENV_HELPER_NO_SUDO", None)

    repo = {"name": "demo", "remotes": {"origin": f"file://{root}/absent.git"}}
    bare = mod.ensure_bare(mod.Ctx(dry=False, verbose=False), ws, repo)
    return bare


def main():
    mod = load()
    fails = []

    def check(label, cond):
        print(f"  {'✓' if cond else '✗'} {label}")
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for use_helper in (False, True):
            label = "helper (repos 0555)" if use_helper else "direct (repos inscriptible)"
            print(f"1) {label}")
            case = root / ("helper" if use_helper else "direct")
            case.mkdir()
            bare = run_case(use_helper, case, mod)
            check("bare créé", bare.is_dir())
            check("bare valide", os.popen(f"git -C {bare} rev-parse --is-bare-repository").read().strip() == "true")
            check("core.sharedRepository=group",
                  os.popen(f"git -C {bare} config core.sharedRepository").read().strip() == "group")
            check("gc.auto=0", os.popen(f"git -C {bare} config gc.auto").read().strip() == "0")
            if use_helper:
                check("repos/ toujours verrouillé", stat.S_IMODE((case / "client" / "proj" / "repos").stat().st_mode) == 0o555)

    print()
    if fails:
        print(f"ÉCHEC : {len(fails)} assertion(s) — {fails}")
        return 1
    print("OK — bare direct et via helper")
    return 0


if __name__ == "__main__":
    sys.exit(main())
