#!/usr/bin/env python3
"""pm-check-no-client-data — aucune donnée client dans un dépôt publiable (RM3201).

Un dépôt qui porte `.client-data-guard.yml` à sa racine est publié (le dépôt de code
PM part sur un miroir GitHub public). Ce script dit s'il nomme un client ou l'une de
ses instances — slug, nom, domaine, IP, adresse, « prénom nom » d'un contact. Les
motifs sont lus dans les données privées du PM à chaque exécution, jamais écrits
dans le code (cf. `pm_client_data_guard`).

Usage :
  pm-check-no-client-data.py [--staged]      lignes AJOUTÉES dans l'index (défaut ;
                                             c'est ce que lance le hook pre-commit)
  pm-check-no-client-data.py --all           audit de tout le versionné
  pm-check-no-client-data.py --all --summary un compte par fichier, pas le détail
  pm-check-no-client-data.py --history       TOUT l'historique (chaque version de chaque
                                             fichier, supprimés compris, + messages de
                                             commit) — avant de rendre un dépôt public
  pm-check-no-client-data.py --patterns      combien de motifs, par nature (jamais
                                             les valeurs : elles sont les données)
  --repo PATH                                dépôt contrôlé (défaut : le courant)

Sortie : 0 = rien trouvé (ou dépôt non publiable : pas de `.client-data-guard.yml`),
1 = donnée client trouvée, 2 = contrôle impossible (aucune donnée privée joignable).
"""
import argparse
import collections
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_client_data_guard as G  # noqa: E402


def repo_top(path):
    r = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                       capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true", help="lignes ajoutées dans l'index (défaut)")
    mode.add_argument("--all", action="store_true", help="tout le versionné")
    mode.add_argument("--history", action="store_true", help="tout l'historique, messages compris")
    mode.add_argument("--patterns", action="store_true", help="compte des motifs, par nature")
    ap.add_argument("--summary", action="store_true", help="avec --all/--history : un compte par fichier")
    ap.add_argument("--repo", default=".", help="dépôt contrôlé")
    a = ap.parse_args(argv)

    top = repo_top(a.repo)
    if top is None:
        print("pm-check-no-client-data: pas un dépôt git", file=sys.stderr)
        return 2
    conf = G.load_guard_config(top)
    if not (top / G.GUARD_FILE).is_file() and not a.patterns:
        print(f"pm-check-no-client-data: {top} n'est pas déclaré publiable "
              f"(pas de {G.GUARD_FILE}) — rien à contrôler.")
        return 0

    from pm_paths import PMConfig
    pat = G.collect(PMConfig.load(), conf.get("common_words") or ())
    if pat.empty():
        print("pm-check-no-client-data: ⚠ AUCUN motif — les données privées du PM sont "
              "injoignables d'ici. Contrôle IMPOSSIBLE, rien n'a été vérifié.", file=sys.stderr)
        return 2
    if a.patterns:
        print(" · ".join(f"{k} {v}" for k, v in pat.counts().items()))
        return 0

    exempt = conf.get("exempt") or ()
    if a.history:
        found, where = G.check_history(top, pat, exempt), " dans tout l'historique."
    elif a.all:
        found, where = G.check_tree(top, pat, exempt), " dans le versionné."
    else:
        found, where = G.check_staged(top, pat, exempt), " dans les lignes ajoutées."
    if not found:
        print("pm-check-no-client-data: ✓ aucune donnée client" + where)
        return 0
    if (a.all or a.history) and a.summary:
        per = collections.Counter(f.path for f in found)
        for path, n in per.most_common():
            print(f"{n:6d}  {path}")
        print(f"{len(found)} occurrence(s) dans {len(per)} fichier(s).")
        return 1
    for f in found:
        print(f)
    print(f"\n{len(found)} donnée(s) client — dépôt publiable ({G.GUARD_FILE}). Remplacer par le "
          f"jeu fictif (clienta…, domaines en .example) ; la conf réelle va hors git, les "
          f"instances dans le environments.md du projet. Cf. norms/src/modules/client-data.md.",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
