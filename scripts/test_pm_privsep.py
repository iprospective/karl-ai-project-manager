#!/usr/bin/env python3
"""Tests RM3379 (A1) — la propriété des fichiers de l'instance : une seule source, configurable.

Ce qui doit tenir :
- le modèle se lit dans la CONFIGURATION de l'instance (une instance cliente ne se règle pas comme celle
  d'iProspective) ; `pm.config.local.yml` prime ;
- **les secrets de service ne sont pas lisibles par les devs** : `.env` en `root:<groupe d'admin>` 640 ;
- les DÉRIVÉS de `.env` (sauvegardes) entrent dans le modèle — c'est par là qu'une copie s'est retrouvée
  lisible par tous (RM3378) — et `.env.example`, qui n'est pas un secret, n'y entre pas ;
- `pm.env` (non secret) en `root:<groupe>` 640, plus 644 ;
- `var/` au service PM, groupe partagé, setgid ; `projects/` de même ;
- un groupe absent ne fait JAMAIS échouer : repli DIT (un `core update` ne doit pas tomber parce qu'un
  groupe n'a pas encore été créé) ;
- le shell (`core-lock`) consomme le MÊME modèle, sans le redéclarer, et l'export résiste à `eval`
  (les messages portent des apostrophes).
"""
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_privsep as P  # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


ENV = {"KARL_USER": "agent", "KARL_SUDO_USER": "agent-pm"}
TOUS = lambda n: True           # tous les groupes existent
AUCUN = lambda n: False         # aucun groupe n'existe


def main():
    with tempfile.TemporaryDirectory() as d:
        core = Path(d) / "core"
        (core / "var").mkdir(parents=True)
        (core / "projects").mkdir()

        print("configuration de l'instance")
        m = P.load(core, environ=ENV, group_exists=TOUS)
        check("défauts : pm et pm-admin", (m.group, m.admin_group) == ("pm", "pm-admin"), m)
        check("comptes lus dans l'environnement du .env", (m.service_user, m.runtime_user) == ("agent-pm", "agent"), m)
        (core / "pm.config.yml").write_text("privsep:\n  group: equipe\n  admin_group: equipe-admin\n")
        m = P.load(core, environ=ENV, group_exists=TOUS)
        check("pm.config.yml fait foi", (m.group, m.admin_group) == ("equipe", "equipe-admin"), m)
        (core / "pm.config.local.yml").write_text("privsep:\n  admin_group: patrons\n")
        m = P.load(core, environ=ENV, group_exists=TOUS)
        check("pm.config.local.yml prime", (m.group, m.admin_group) == ("equipe", "patrons"), m)
        (core / "pm.config.local.yml").unlink()
        (core / "pm.config.yml").write_text("privsep: [pas, un, dict]\n")
        check("section mal formée → défauts, pas d'exception", P.load(core, environ=ENV, group_exists=TOUS).group == "pm")
        (core / "pm.config.yml").write_text("privsep:\n  group: pm\n  admin_group: pm-admin\n")

        print("replis dits, jamais d'échec")
        m = P.load(core, environ=ENV, group_exists=AUCUN)
        check("groupe partagé absent → repli sur le compte runtime", m.group == "agent", m)
        check("groupe d'admin absent → repli sur le groupe partagé", m.admin_group == "agent", m)
        check("les deux replis sont DITS", len(m.fallbacks) == 2 and all("groupadd" in w for w in m.fallbacks), m.fallbacks)
        seulement_pm = lambda n: n == "pm"
        m = P.load(core, environ=ENV, group_exists=seulement_pm)
        check("admin absent seul → secrets au groupe partagé, et c'est dit",
              (m.group, m.admin_group) == ("pm", "pm") and len(m.fallbacks) == 1, m)

        print("secrets et dérivés")
        (core / ".env").write_text("X=1\n")
        (core / ".env.bak-20260818").write_text("X=1\n")
        (core / ".env.example").write_text("X=\n")
        (core / "pm.env").write_text("Y=2\n")
        noms = [p.name for p in P.secret_files(core)]
        check("le .env et sa sauvegarde sont des secrets", noms == [".env", ".env.bak-20260818"], noms)
        check(".env.example n'est pas un secret", ".env.example" not in noms)
        m = P.load(core, environ=ENV, group_exists=TOUS)
        cibles = {t.path.name: t for t in P.core_targets(core, core / "var", m)}
        check("secrets : root:<admin> 640",
              all((cibles[n].owner, cibles[n].group, cibles[n].mode) == ("root", "pm-admin", 0o640)
                  for n in (".env", ".env.bak-20260818")), [(n, cibles[n]) for n in cibles])
        check("pm.env : root:<groupe partagé> 640",
              (cibles["pm.env"].owner, cibles["pm.env"].group, cibles["pm.env"].mode) == ("root", "pm", 0o640),
              cibles["pm.env"])
        check("var/ : service PM, groupe partagé, setgid, récursif",
              (cibles["var"].owner, cibles["var"].group, cibles["var"].mode, cibles["var"].recurse)
              == ("agent-pm", "pm", 0o2775, True), cibles["var"])
        check("projects/ : idem (écrit sans privilège par les devs)",
              (cibles["projects"].owner, cibles["projects"].group, cibles["projects"].recurse)
              == ("agent-pm", "pm", True), cibles["projects"])
        check("un dev ne lit pas les secrets : groupe des secrets ≠ groupe partagé",
              cibles[".env"].group != cibles["var"].group)

        print("consommation par le shell")
        sh = P.sh_exports(core, core / "var", m)
        for clef in ("PRIVSEP_GROUP=pm", "PRIVSEP_ADMIN_GROUP=pm-admin", "PRIVSEP_SERVICE_USER=agent-pm",
                     "PRIVSEP_SECRET_MODE=0640", "PRIVSEP_CONF_MODE=0640"):
            check(f"export {clef.split('=')[0]}", clef in sh, sh)
        check("les deux secrets sont listés pour le shell",
              ".env " in sh.split("PRIVSEP_SECRET_FILES='")[1] and ".env.bak-20260818'" in sh, sh)
        check("les replis voyagent aussi", "PRIVSEP_WARN" not in sh)
        mf = P.load(core, environ=ENV, group_exists=AUCUN)
        shf = P.sh_exports(core, core / "var", mf)
        check("un repli est exporté pour que le shell le dise", "PRIVSEP_WARN_1=" in shf)
        import subprocess
        r = subprocess.run(["bash", "-c", f"eval \"$(cat)\"; printf '%s|%s' \"$PRIVSEP_GROUP\" \"$PRIVSEP_WARN_1\""],
                           input=shf, capture_output=True, text=True)
        check("l'export survit à eval malgré les apostrophes des messages",
              r.returncode == 0 and r.stdout.startswith("agent|groupe"), r.stdout + r.stderr)
        check("résumé lisible d'une ligne", "code=root" in m.describe() and "var/=" in m.describe(), m.describe())

    print("\n" + ("VERT" if not FAIL else f"ROUGE — {len(FAIL)} échec(s)"))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
