#!/usr/bin/env python3
"""Tests RM3208 (A2) — installer une instance ailleurs que dans /zfs/workspaces (ex. /opt/mmi-pm/core).

Ce qui doit tenir :
- le gabarit sudoers ne fige plus aucun chemin : `<CORE_DIR>` est substitué par le chemin réel de l'instance ;
- un gabarit resté non substitué fait échouer le rendu (jamais de règle « <CORE_DIR>/bin/mmi-pm » installée) ;
- le rendu est valide pour `visudo` quand l'outil est disponible ;
- `.env.example` déclare `KARL_USER` et `KARL_SUDO_USER` (exigés par l'installeur) ; rempli, il passe
  `install-mmi-pm --dry-run` sur une instance hors /zfs/workspaces ;
- `core-lock` et `provision-core` ne visent plus /zfs/workspaces/.mmi-pm-core par défaut.
"""
import getpass
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def fake_core(base: pathlib.Path, env_text: str) -> pathlib.Path:
    core = base / "opt" / "mmi-pm" / "core"
    (core / ".git").mkdir(parents=True)
    (core / "bin").mkdir()
    (core / "bin" / "mmi-pm").write_text("#!/bin/sh\nexit 0\n")
    (core / "bin" / "mmi-pm").chmod(0o755)
    (core / "deploy").mkdir()
    shutil.copy(ROOT / "deploy" / "mmi-pm.sudoers.example", core / "deploy" / "mmi-pm.sudoers.example")
    (core / "scripts").mkdir()
    for s in ("install-mmi-pm", "provision-core", "core-lock"):
        shutil.copy(ROOT / "scripts" / s, core / "scripts" / s)
    (core / ".env").write_text(env_text)
    return core


def main():
    me = getpass.getuser()
    tpl = (ROOT / "deploy" / "mmi-pm.sudoers.example").read_text(encoding="utf-8")
    regles = [l for l in tpl.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    print("gabarit sudoers")
    check("aucun chemin d'instance figé", "/zfs/workspaces/.mmi-pm-core" not in tpl)
    check("toutes les règles passent par <CORE_DIR>", regles and all("<CORE_DIR>/" in l for l in regles), regles)

    print(".env.example")
    ex = (ROOT / ".env.example").read_text(encoding="utf-8")
    check("KARL_USER déclaré", "\nKARL_USER=" in ex)
    check("KARL_SUDO_USER déclaré", "\nKARL_SUDO_USER=" in ex)

    with tempfile.TemporaryDirectory() as d:
        base = pathlib.Path(d)
        filled = ex.replace("\nKARL_USER=\n", f"\nKARL_USER={me}\n").replace("\nKARL_SUDO_USER=\n", f"\nKARL_SUDO_USER={me}\n")
        core = fake_core(base, filled)
        inst = core / "scripts" / "install-mmi-pm"

        print("rendu des règles (--print-sudoers, sans root)")
        r = subprocess.run(["bash", str(inst), str(core), "--print-sudoers"], capture_output=True, text=True)
        out = r.stdout
        check("rendu OK", r.returncode == 0, r.stderr)
        check("chemin réel de l'instance substitué", f"{core}/bin/mmi-pm core update*" in out, out[-400:])
        check("plus aucun gabarit dans les règles",
              not any("<" in l for l in out.splitlines() if l.strip() and not l.lstrip().startswith("#")), out[-400:])
        check("comptes substitués", f"{me} ALL=(root) {core}/scripts/core-lock *" in out, out[-400:])
        visudo = shutil.which("visudo") or "/usr/sbin/visudo"
        if os.path.exists(visudo):
            f = base / "rendu.sudoers"
            f.write_text(out)
            v = subprocess.run([visudo, "-cf", str(f)], capture_output=True, text=True)
            if "permission" in (v.stderr + v.stdout).lower() and v.returncode != 0:
                print("  – visudo inaccessible sans root : vérification syntaxique sautée")
            else:
                check("syntaxe validée par visudo", v.returncode == 0, v.stdout + v.stderr)

        print("gabarit non substitué → refus")
        (core / "deploy" / "mmi-pm.sudoers.example").write_text(tpl + "\n<INCONNU> ALL=(root) /bin/true\n")
        r = subprocess.run(["bash", str(inst), str(core), "--print-sudoers"], capture_output=True, text=True)
        check("refus explicite", r.returncode != 0 and "<INCONNU>" in r.stderr, r.stdout[-200:] + r.stderr)
        shutil.copy(ROOT / "deploy" / "mmi-pm.sudoers.example", core / "deploy" / "mmi-pm.sudoers.example")

        print("installation à blanc depuis le .env.example rempli")
        r = subprocess.run(["bash", str(inst), str(core), "--dry-run"], capture_output=True, text=True)
        check("install-mmi-pm --dry-run passe", r.returncode == 0, r.stdout[-300:] + r.stderr)
        check("le rendu annoncé porte le chemin réel", f"<CORE_DIR>={core}" in r.stdout, r.stdout[-300:])

        print(".env.example non rempli → message clair")
        (core / ".env").write_text(ex)
        r = subprocess.run(["bash", str(inst), str(core), "--dry-run"], capture_output=True, text=True)
        check("refus nommant KARL_USER", r.returncode != 0 and "KARL_USER" in r.stderr, r.stderr)

        print("core-lock / provision-core auto-localisés")
        (core / ".env").write_text(filled)
        r = subprocess.run(["bash", str(core / "scripts" / "core-lock"), "lock", "--dry-run"], capture_output=True, text=True)
        check("core-lock sans chemin vise son instance", str(core) in r.stdout and "/zfs/workspaces/.mmi-pm-core" not in r.stdout,
              r.stdout[-300:] + r.stderr)
        pc = (ROOT / "scripts" / "provision-core").read_text(encoding="utf-8")
        check("provision-core : plus de défaut figé", 'CORE_DIR="${1:-/zfs/workspaces' not in pc)

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
