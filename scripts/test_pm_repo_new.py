#!/usr/bin/env python3
"""RM2640 — pm-repo-new : résolution de chemin, refus, et garde anti-basename.

Aucun appel réseau : la forge est simulée. Ce qui est éprouvé ici, ce sont les gardes
qui ont coûté des incidents — tripwire #14 (résolution par chemin EXACT, jamais par
basename : RM2219/RM2410) et le refus d'écraser un dépôt existant.
"""
import importlib.util
import pathlib
import sys
import unittest

SPEC = importlib.util.spec_from_file_location(
    "pm_repo_new", pathlib.Path(__file__).with_name("pm-repo-new.py"))
M = importlib.util.module_from_spec(SPEC)
sys.modules["pm_repo_new"] = M
SPEC.loader.exec_module(M)


class FakeForge:
    """Forge simulée : `api()` répond depuis des listes fournies au constructeur."""

    def __init__(self, groups=(), projects=()):
        self.groups, self.projects = list(groups), list(projects)
        self.calls = []

    def api(self, method, path, token, fields=None):
        self.calls.append((method, path, fields))
        if path.startswith("/groups?"):
            return 200, self.groups, ""
        if path.startswith("/projects?"):
            return 200, self.projects, ""
        if method == "POST" and path == "/projects":
            return 201, {"id": 999, "path_with_namespace":
                         f"grp/{fields['name']}"}, ""
        return 404, None, "not found"


class SplitPath(unittest.TestCase):
    def test_groupe_et_nom(self):
        self.assertEqual(M.split_path("prestashop/mod-x"), ("prestashop", "mod-x"))

    def test_sous_groupe(self):
        self.assertEqual(M.split_path("a/b/c/nom"), ("a/b/c", "nom"))

    def test_slashs_superflus(self):
        self.assertEqual(M.split_path("/grp/nom/"), ("grp", "nom"))

    def test_refus_sans_groupe(self):
        with self.assertRaises(SystemExit):
            M.split_path("toutseul")

    def test_refus_segment_invalide(self):
        with self.assertRaises(SystemExit):
            M.split_path("grp/nom avec espace")


class ResolveGroup(unittest.TestCase):
    def test_match_exact(self):
        f = FakeForge(groups=[{"id": 7, "full_path": "prestashop"}])
        self.assertEqual(M.resolve_group(f, "t", "prestashop"), 7)

    def test_refuse_le_basename_homonyme(self):
        """Le cœur du tripwire #14 : deux groupes, même basename, chemins différents.

        `?search=modules` renvoie les deux ; seul le chemin EXACT doit être retenu.
        Un match par basename choisirait le mauvais groupe — l'incident RM2219.
        """
        f = FakeForge(groups=[{"id": 1, "full_path": "clientA/modules"},
                              {"id": 2, "full_path": "clientB/modules"}])
        self.assertEqual(M.resolve_group(f, "t", "clientB/modules"), 2)

    def test_aucun_match_exact_refuse(self):
        f = FakeForge(groups=[{"id": 1, "full_path": "clientA/modules"}])
        with self.assertRaises(SystemExit):
            M.resolve_group(f, "t", "clientB/modules")

    def test_groupe_absent_refuse(self):
        with self.assertRaises(SystemExit):
            M.resolve_group(FakeForge(), "t", "inexistant")


class ProjectExists(unittest.TestCase):
    def test_detecte_par_chemin_exact(self):
        f = FakeForge(projects=[{"id": 5, "path_with_namespace": "grp/nom"}])
        self.assertEqual(M.project_exists(f, "t", "grp/nom")["id"], 5)

    def test_homonyme_dans_un_autre_groupe_nest_pas_un_conflit(self):
        """Même nom, autre groupe : ce n'est PAS le même projet, la création doit passer."""
        f = FakeForge(projects=[{"id": 5, "path_with_namespace": "autre/nom"}])
        self.assertIsNone(M.project_exists(f, "t", "grp/nom"))

    def test_absent(self):
        self.assertIsNone(M.project_exists(FakeForge(), "t", "grp/nom"))


class CreateProject(unittest.TestCase):
    class Args:
        visibility, default_branch, description = "private", "main", "desc"

    def test_champs_envoyes(self):
        f = FakeForge()
        M.create_project(f, "t", "mod-x", 42, self.Args())
        method, path, fields = f.calls[-1]
        self.assertEqual((method, path), ("POST", "/projects"))
        self.assertEqual(fields["namespace_id"], 42)
        self.assertEqual(fields["visibility"], "private")
        self.assertEqual(fields["default_branch"], "main")
        self.assertEqual(fields["initialize_with_readme"], "false")

    def test_prive_par_defaut_dans_le_parseur(self):
        """La valeur par défaut de --visibility doit rester `private`."""
        import subprocess
        h = subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name(
            "pm-repo-new.py")), "--help"], capture_output=True, text=True).stdout
        self.assertIn("--visibility", h)
        self.assertIn("private", h)


class PushFrom(unittest.TestCase):
    def test_refuse_un_chemin_qui_nest_pas_un_depot(self):
        with self.assertRaises(SystemExit):
            M.push_from("/tmp", "grp/nom", "main", True)

    def test_url_en_alias_ssh_canonique(self):
        """RM2328 : jamais d'HTTPS dans le remote posé."""
        src = pathlib.Path(__file__).resolve().parents[1]
        out_lines = []
        M.say = lambda m: out_lines.append(str(m))
        M.push_from(src, "grp/nom", "main", True)
        joined = "\n".join(out_lines)
        self.assertIn("gitlab:grp/nom.git", joined)
        self.assertNotIn("https://", joined)


class ValidationEnAmont(unittest.TestCase):
    """RM2640 — `--push-from` doit être validé AVANT le POST /projects.

    Sinon un chemin erroné laisse un projet vide derrière lui sur la forge.
    """

    def test_source_invalide_refusee(self):
        with self.assertRaises(SystemExit):
            M.check_push_source("/tmp")

    def test_bare_accepte(self):
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "--bare", "-q", d], check=True)
            self.assertEqual(M.check_push_source(d), pathlib.Path(d).resolve())

    def test_appelee_avant_la_creation(self):
        """Garde de source : la validation précède `project_exists` dans main()."""
        src = pathlib.Path(__file__).with_name("pm-repo-new.py").read_text()
        self.assertLess(src.index("check_push_source(args.push_from)"),
                        src.index("existing = project_exists"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
