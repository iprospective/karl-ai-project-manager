#!/usr/bin/env python3
"""Tests pm-snapshot (RM2989) — résolution de cible, choix du nœud, canal atlas, journal.

Lancer : python3 scripts/test_pm_snapshot.py
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_snapshot", HERE / "pm-snapshot.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


class Env(unittest.TestCase):
    ENVS = [{"name": "dev"}, {"name": "prod", "snapshot": {"svc": "calyclay"}}]

    def test_target_env_prioritaire(self):
        self.assertEqual(ps.pick_env(self.ENVS, "dev")["name"], "dev")

    def test_defaut_prod(self):
        self.assertEqual(ps.pick_env(self.ENVS, None)["name"], "prod")

    def test_target_env_inconnu_pas_de_repli_sur_prod(self):
        self.assertIsNone(ps.pick_env(self.ENVS, "staging"))

    def test_aucun_env(self):
        self.assertIsNone(ps.pick_env([], None))
        self.assertIsNone(ps.pick_env(None, None))


class Cible(unittest.TestCase):
    def test_env_avant_meta(self):
        t = ps.snapshot_target({"snapshot": {"svc": "a"}}, {"snapshot": {"svc": "b"}})
        self.assertEqual(t, ("a", "sync#root_hour", "environments.md"))

    def test_repli_meta(self):
        t = ps.snapshot_target({"name": "prod"}, {"snapshot": {"svc": "calyclay", "rid": "sync#root_day"}})
        self.assertEqual(t, ("calyclay", "sync#root_day", "meta.yml"))

    def test_rien_de_declare(self):
        self.assertIsNone(ps.snapshot_target({"name": "prod"}, {"slug": "infra"}))
        self.assertIsNone(ps.snapshot_target(None, None))

    def test_snapshot_sans_svc_ignore(self):
        self.assertIsNone(ps.snapshot_target({"snapshot": {"rid": "sync#root_hour"}}, {}))

    def test_validation(self):
        ps.validate("calyclay", "sync#root_hour")
        for svc, rid in (("caly clay", "sync#root_hour"), ("x;reboot", "sync#root_hour"),
                         ("calyclay", "sync#all"), ("", "sync#root_hour")):
            with self.assertRaises(ps.SnapError):
                ps.validate(svc, rid)


class Noeud(unittest.TestCase):
    def test_un_seul_up(self):
        self.assertEqual(ps.locate({"srv3": "down", "srv4": "absent", "srv5": "up"}), "srv5")

    def test_aucun_up(self):
        with self.assertRaisesRegex(ps.SnapError, "aucune instance up"):
            ps.locate({"srv3": "down", "srv5": "absent"})

    def test_tous_en_erreur_dit_que_c_est_atlas(self):
        with self.assertRaisesRegex(ps.SnapError, "aucun nœud"):
            ps.locate({"srv3": "erreur(x)", "srv5": "erreur(y)"})

    def test_plusieurs_up_ambigu(self):
        with self.assertRaisesRegex(ps.SnapError, "ambiguë"):
            ps.locate({"srv3": "up", "srv5": "up"})

    def test_noeud_en_erreur_ne_compte_pas_comme_up(self):
        self.assertEqual(ps.locate({"srv3": "erreur(timeout)", "srv5": "up"}), "srv5")


class CanalAtlas(unittest.TestCase):
    def test_parse_ok(self):
        raw = json.dumps({"ok": True, "stdout": "bruit\n" + json.dumps({"avail": "up"}) + "\n"})
        self.assertEqual(ps.parse_atlas(raw), (True, {"avail": "up"}))

    def test_parse_refus(self):
        self.assertEqual(ps.parse_atlas(json.dumps({"ok": False, "error": "op inconnue"})),
                         (False, "op inconnue"))

    def test_parse_illisible(self):
        ok, msg = ps.parse_atlas("canal atlas: op non autorisée")
        self.assertFalse(ok)
        self.assertIn("illisible", msg)

    def test_commande_ssh(self):
        vu = {}

        def runner(cmd, **kw):
            vu["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, json.dumps({"ok": True, "stdout": '{"avail":"up"}'}), "")
        a = ps.Atlas("atlas-orch@atlas", "/k", runner=runner)
        self.assertEqual(a.run("srv5", "svc-status", "calyclay"), (True, {"avail": "up"}))
        payload = vu["cmd"][-1].split()[1]
        self.assertEqual(json.loads(ps.base64.b64decode(payload)),
                         ["run", "--node", "srv5", "svc-status", "calyclay"])
        self.assertIn("BatchMode=yes", vu["cmd"])

    def test_statuses_erreur_de_canal_isolee(self):
        class A:
            def run(self, node, op, *args, **kw):
                return (True, {"avail": "up"}) if node == "srv5" else (False, "timeout")
        st = ps.statuses_of(A(), ["srv3", "srv5"], "calyclay")
        self.assertEqual(st["srv5"], "up")
        self.assertTrue(st["srv3"].startswith("erreur"))


class Journal(unittest.TestCase):
    def test_note_porte_nom_noeud_et_rollback(self):
        n = ps.journal_note("srv5", "calyclay", "sync#root_hour",
                            ["zfs/lxc/calyclay@hourly.snap.2026-09-19.10:00:00"])
        self.assertIn("srv5", n)
        self.assertIn("zfs/lxc/calyclay@hourly.snap.2026-09-19.10:00:00", n)
        self.assertIn("zfs rollback -r zfs/lxc/calyclay@hourly.snap.2026-09-19.10:00:00", n)
        self.assertIn("om calyclay sync update --rid sync#root_hour", n)
        self.assertIn("Rétention courte", n)

    def test_pas_d_avertissement_retention_hors_horaire(self):
        self.assertNotIn("Rétention courte", ps.journal_note("srv5", "c", "sync#root_week", ["d@x"]))


class Frontmatter(unittest.TestCase):
    def test_lit(self):
        self.assertEqual(ps.frontmatter("---\na: 1\n---\ncorps"), {"a": 1})

    def test_sans(self):
        self.assertEqual(ps.frontmatter("# titre"), {})


class Orchestration(unittest.TestCase):
    """main() de bout en bout, atlas simulé : jamais de svc-snapshot en dry-run ni sur refus."""

    def setUp(self):
        self.appels = []
        test = self

        class FakeAtlas:
            def __init__(self, *a, **k):
                pass

            def run(self, node, op, *args, **kw):
                test.appels.append((node, op) + args)
                if op == "svc-status":
                    return True, {"avail": test.avail.get(node, "absent")}
                return True, {"snapshots": ["zfs/lxc/calyclay@hourly.snap.X"]}
        class FakeConfig:                    # indépendant de pm.config.yml (pm-test purge l'env)
            snapshot = {}

            @classmethod
            def load(cls):
                return cls()
        self._orig = ps.Atlas, ps.PMConfig
        ps.Atlas, ps.PMConfig = FakeAtlas, FakeConfig

    def tearDown(self):
        ps.Atlas, ps.PMConfig = self._orig

    def ops(self):
        return [a[1] for a in self.appels]

    def test_dry_run_n_execute_rien(self):
        self.avail = {"srv5": "up"}
        rc = ps.main(["--svc", "calyclay", "--dry-run", "--node", "srv3", "--node", "srv5"])
        self.assertEqual(rc, 0)
        self.assertNotIn("svc-snapshot", self.ops())

    def test_ambigu_n_execute_rien(self):
        self.avail = {"srv3": "up", "srv5": "up"}
        rc = ps.main(["--svc", "calyclay", "--node", "srv3", "--node", "srv5", "--no-journal"])
        self.assertEqual(rc, 2)
        self.assertNotIn("svc-snapshot", self.ops())

    def test_execution_sur_le_seul_noeud_up(self):
        self.avail = {"srv5": "up"}
        rc = ps.main(["--svc", "calyclay", "--node", "srv3", "--node", "srv5", "--no-journal"])
        self.assertEqual(rc, 0)
        self.assertIn(("srv5", "svc-snapshot", "calyclay", "sync#root_hour"), self.appels)


if __name__ == "__main__":
    unittest.main(verbosity=1)
