#!/usr/bin/env python3
"""Tests RM3023 — sauvegarde ZFS de la machine.

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **la purge ne mord que sur NOS snapshots.** Un snapshot posé à la main
     (pré-MEP, migration de workspace) n'est pas un déchet à ramasser ; le
     détruire ferait perdre un point de restauration délibéré ;
  2. **un seau retiré de la politique ne déclenche pas une destruction.** Sinon
     éditer une ligne de config effacerait, au tick suivant et en silence, tout
     l'historique correspondant ;
  3. **un seau jamais pris est toujours dû** — sur une machine qui démarre, la
     première sauvegarde ne doit pas attendre un tour de cadran. C'est ce qui
     remplace un timer sur un portable souvent éteint ;
  4. le contrôle distingue *jamais tourné*, *a décroché* et *tourne mais
     échoue* : trois situations qui n'appellent pas la même réaction.

Lancer : python3 scripts/test_pm_zfs_backup.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pzb", HERE / "pm-zfs-backup.py")
z = importlib.util.module_from_spec(spec)
sys.modules["pzb"] = z
spec.loader.exec_module(z)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


BUCKETS = {"hourly": {"every_minutes": 60, "keep": 3},
           "daily": {"every_minutes": 1440, "keep": 2}}
NOW = 1_000_000

# ── 1. ce qui est dû ─────────────────────────────────────────────────────────
check("un seau jamais pris est dû", "hourly" in z.due_buckets({}, BUCKETS, NOW))
check("…tous, au premier démarrage",
      sorted(z.due_buckets({}, BUCKETS, NOW)) == ["daily", "hourly"])
check("un seau pris à l'instant n'est pas dû",
      "hourly" not in z.due_buckets({"hourly": NOW}, BUCKETS, NOW))
check("…et le devient passé sa période",
      "hourly" in z.due_buckets({"hourly": NOW - 3601}, BUCKETS, NOW))
check("pile à la période, c'est dû (pas de dérive lente)",
      "hourly" in z.due_buckets({"hourly": NOW - 3600}, BUCKETS, NOW))
check("le quotidien reste en attente quand l'horaire vient de passer",
      z.due_buckets({"hourly": NOW - 3601, "daily": NOW - 60}, BUCKETS, NOW) == ["hourly"])
check("aucune politique ⇒ rien de dû", z.due_buckets({}, {}, NOW) == [])

# ── 2. la purge ──────────────────────────────────────────────────────────────
noms = [f"pm-auto-hourly-2026091{i}T0300" for i in range(1, 6)]     # 5 pour keep=3
purge = z.to_prune(noms, BUCKETS)
check("au-delà du quota, les plus ANCIENS partent",
      purge == ["pm-auto-hourly-20260911T0300", "pm-auto-hourly-20260912T0300"])
check("…et les plus récents restent", len(noms) - len(purge) == 3)
check("sous le quota, rien n'est purgé", z.to_prune(noms[:2], BUCKETS) == [])

# LE test qui compte : un snapshot posé à la main n'est jamais ramassé.
a_la_main = ["rm2460_pre_mep", "migration-20260601", "pre-mep-2026",
             "pm-auto-hourly-20260901T0300"]
check("un snapshot posé à la main est épargné",
      z.to_prune(a_la_main + noms, BUCKETS) ==
      z.to_prune(noms + ["pm-auto-hourly-20260901T0300"], BUCKETS))
check("…et aucun nom hors préfixe ne sort jamais de la purge",
      all(n.startswith("pm-auto-") for n in z.to_prune(a_la_main + noms, BUCKETS)))

# Retirer un seau de la config ne doit pas effacer son historique.
check("un seau inconnu de la politique n'est pas purgé",
      z.to_prune([f"pm-auto-weekly-2026090{i}T0300" for i in range(1, 9)], BUCKETS) == [])
check("keep=0 n'est pas lu comme « tout détruire »",
      z.to_prune(noms, {"hourly": {"every_minutes": 60, "keep": 0}}) == [])
check("liste vide tolérée", z.to_prune([], BUCKETS) == [])
check("un nom presque conforme ne passe pas",
      z.to_prune(["pm-auto-hourly-2026"], BUCKETS) == [])

# ── 3. le contrôle : trois situations distinctes ─────────────────────────────
retard, msg = z.stale(None, NOW, 26)
check("jamais tourné ⇒ rouge, et le dit", retard and "jamais" in msg)
retard, msg = z.stale({"at": NOW - 3600, "datasets": {"zfs/root": {"hourly": {"n": 3}}}}, NOW, 26)
check("passé il y a 1 h ⇒ vert", not retard and "sauvegardé" in msg)
retard, msg = z.stale({"at": NOW - 40 * 3600, "datasets": {}}, NOW, 26)
check("passé il y a 40 h ⇒ rouge (a décroché)", retard and "décroch" not in msg and "seuil" in msg)
retard, msg = z.stale({"at": NOW - 600, "datasets": {}, "errors": ["zfs/root : refusé"]}, NOW, 26)
check("récent MAIS en erreur ⇒ rouge (tourne et échoue)", retard and "erreur" in msg)
check("le seuil est paramétrable", not z.stale({"at": NOW - 40 * 3600}, NOW, 48)[0])

# ── 4. le nom de snapshot ────────────────────────────────────────────────────
m = z.SNAP_RE.match("pm-auto-hourly-20260912T0311")
check("le nom porte son seau et son horodatage",
      m and m.group("bucket") == "hourly" and m.group("stamp") == "20260912T0311")
check("un nom d'humain n'est pas reconnu comme nôtre",
      z.SNAP_RE.match("rm2460_pre_mep") is None)
check("le tri chronologique est le tri alphabétique (horodatage ISO compact)",
      sorted(["pm-auto-hourly-20260912T0100", "pm-auto-hourly-20260911T2300"])[0]
      == "pm-auto-hourly-20260911T2300")

# ── 5. le guichet visé est celui du runtime, pas le voisin de branche ────────
check("le guichet sudo est visé par son chemin de runtime",
      str(z.WRAPPER) == "/zfs/workspaces/.mmi-pm-core/scripts/pm-zfs-snap.sh"
      or "PM_ZFS_SNAP" in str(z.WRAPPER))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
