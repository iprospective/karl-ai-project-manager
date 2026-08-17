#!/usr/bin/env python3
"""RM2679 — le teardown ne doit pas se bloquer sur les artefacts qu'il a lui-même posés.

Défaut d'origine : l'exemption comparait des chaînes concaténées, donc avec
`docroot: "."` elle produisait `./pm-env.txt` là où git écrit `pm-env.txt`.
"""
import importlib.util
import pathlib
import sys
import unittest

SPEC = importlib.util.spec_from_file_location(
    "pm_env_session", pathlib.Path(__file__).with_name("pm-env-session.py"))
M = importlib.util.module_from_spec(SPEC)
sys.modules["pm_env_session"] = M
SPEC.loader.exec_module(M)


class OwnArtifacts(unittest.TestCase):
    def test_docroot_point_normalise(self):
        """Le cas qui cassait : docroot '.' ne doit PAS produire './pm-env.txt'."""
        own = M.own_artifacts(".")
        self.assertIn("pm-env.txt", own)
        self.assertIn(".user.ini", own)
        self.assertNotIn("./pm-env.txt", own)

    def test_docroot_sous_dossier(self):
        own = M.own_artifacts("public")
        self.assertEqual(own, {"public/pm-env.txt", "public/.user.ini"})

    def test_docroot_absent(self):
        self.assertEqual(M.own_artifacts(None), set())

    def test_docroot_avec_slash_final(self):
        self.assertIn("public/pm-env.txt", M.own_artifacts("public/"))


class StatusPath(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(M.status_path("?? pm-env.txt"), "pm-env.txt")

    def test_modifie(self):
        self.assertEqual(M.status_path(" M modules/x/y.php"), "modules/x/y.php")

    def test_chemin_quote_avec_espaces(self):
        self.assertEqual(M.status_path('?? "views/img/a b.png"'), "views/img/a b.png")

    def test_renommage_garde_la_destination(self):
        self.assertEqual(M.status_path("R  vieux.txt -> neuf.txt"), "neuf.txt")

    def test_normalise_le_point(self):
        self.assertEqual(M.status_path("?? ./pm-env.txt"), "pm-env.txt")


class Disposable(unittest.TestCase):
    def setUp(self):
        self.own = M.own_artifacts(".")

    def test_canari_est_jetable(self):
        self.assertTrue(M.is_disposable("?? pm-env.txt", self.own, []))

    def test_user_ini_est_jetable(self):
        self.assertTrue(M.is_disposable("?? .user.ini", self.own, []))

    def test_fichier_neuf_inconnu_bloque(self):
        """Un fichier non suivi qu'on a oublié d'ajouter DOIT bloquer le teardown."""
        self.assertFalse(M.is_disposable("?? correctif-oublie.php", self.own, []))

    def test_fichier_suivi_modifie_bloque_toujours(self):
        self.assertFalse(M.is_disposable(" M modules/mmi_sync/mmi_sync.php", self.own, []))

    def test_fichier_suivi_modifie_bloque_meme_si_motif_correspond(self):
        """Le motif ne doit jamais rendre jetable un fichier SUIVI et modifié."""
        self.assertFalse(M.is_disposable(" M yaml/abc.php", self.own, ["yaml/*.php"]))

    def test_motif_projet(self):
        self.assertTrue(M.is_disposable("?? yaml/abc123.php", self.own, ["yaml/*.php"]))

    def test_motif_projet_non_correspondant(self):
        self.assertFalse(M.is_disposable("?? app/Truc.php", self.own, ["yaml/*.php"]))

    def test_ligne_vide(self):
        self.assertTrue(M.is_disposable("", self.own, []))


class GardeComplete(unittest.TestCase):
    """Le scénario réel de pisceen/presta, docroot '.'."""

    def test_cas_pisceen(self):
        st = ["?? pm-env.txt",
              "?? yaml/f6aec2be.php",
              "?? yaml/f6aec2be.php.meta"]
        own = M.own_artifacts(".")
        pats = ["yaml/*.php", "yaml/*.php.meta"]
        dirt = [l for l in st if not M.is_disposable(l, own, pats)]
        self.assertEqual(dirt, [], "le teardown ne doit plus rien trouver de sale")

    def test_cas_pisceen_sans_motifs_projet(self):
        """Sans teardown_ignore, le canari passe mais le cache de l'appli bloque encore."""
        st = ["?? pm-env.txt", "?? yaml/f6aec2be.php"]
        dirt = [l for l in st if not M.is_disposable(l, M.own_artifacts("."), [])]
        self.assertEqual(dirt, ["?? yaml/f6aec2be.php"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
