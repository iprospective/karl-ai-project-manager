#!/usr/bin/env python3
"""pm-stores-migrate — ramène les stores de session du HOME vers le `var/` du repo PM. RM2992.

Les worklogs de session, l'état de karl-agent et les curseurs de tour vivaient dans le home de
l'utilisateur, « par défaut d'avoir choisi ». Conséquence : un agent ne voyait pas le travail d'un
autre, et le régime de partage dépendait du hasard des montages (`~/.claude` partagé hôte↔conteneur,
`~/.local/state` non — RM2391 s'est fait piéger dessus). `pm_stores` les résout désormais sous
`var/`, commun à tous les agents de la machine ; ce script y **déplace l'existant**.

Ce qu'il ne fait pas : toucher aux transcripts et à `history.jsonl`. Claude Code les écrit, nous ne
faisons que les lire — les déplacer serait les perdre.

Quatre partis pris :

  - **Il ne remplace jamais.** Un fichier déjà présent à destination est laissé tel quel et compté
    à part : c'est ce qui rend l'ordre d'exécution indifférent, y compris pendant qu'un karl-agent
    tourne encore avec l'ancien code, et qui permet de relancer sans réfléchir.
  - **Il pose un LIEN à la place de l'ancien dossier**, une fois celui-ci vidé. C'est le filet, et
    il compte autant que le déplacement : une instance non redémarrée, une session ouverte avant la
    mise à jour, un script lancé depuis un worktree sans `.env` (qui retombe sur le repli du home)
    écrivent encore à l'ancien chemin. Sans lien, leurs écritures partent dans un dossier que plus
    personne ne lit, **et rien ne le signale**. Un dossier qui contient encore quelque chose n'est
    jamais remplacé : ce qui reste n'est pas à nous.
  - **Il ne déplace que NOS fichiers.** `~/.claude/logs` est un dossier de Claude Code où nous
    déposons trois motifs (`turn-start-*`, `tick-cursor-*`, `pm-task-tick-untracked.jsonl`) : tout
    rafler emporterait ce qui ne nous appartient pas. Celui-là ne devient donc PAS un lien — il
    n'est pas à nous. Ce qu'un écrivain resté en arrière y dépose est ramassé à la migration
    suivante (`core update` la rejoue), et il ne s'agit que de curseurs de tour : les perdre fait
    recompter un tour, pas perdre une donnée.
  - **Il laisse une trace dans l'ancien dossier** (`MIGRE-VERS.txt`) quand il n'a pas pu poser de
    lien, pour l'humain qui le retrouve dans six mois et se demande pourquoi il est à moitié vide.

  pm-stores-migrate [--dry-run] [--verbose] [--no-link]
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_stores   # noqa: E402

#: Les fichiers qui sont à NOUS dans un dossier partagé avec Claude Code. None = tout le dossier.
NOTRE = {pm_stores.TURN_SUB: ("turn-start-", "tick-cursor-", "pm-task-tick-untracked.jsonl")}

#: Stores MORTS : plus personne ne les écrit ni ne les lit. Ils SUIVENT quand même — pour que
#: l'ancien dossier se vide et puisse devenir un lien —, mais on les nomme pour qu'ils se
#: suppriment un jour, plutôt que de survivre dix ans parce que personne n'ose y toucher.
MORTS = ("answers.jsonl",)      # RM3085 : plus écrit ; aucun lecteur depuis RM2302

#: Les dossiers dont NOUS sommes propriétaires, donc que l'on peut remplacer par un lien une fois
#: vidés. `~/.claude/logs` n'en est pas : il appartient à Claude Code, on n'y dépose que trois motifs.
LIENS = (pm_stores.WORKLOG_LEGACY, pm_stores.STATE_LEGACY)

TRACE = "MIGRE-VERS.txt"


#: setgid + écriture pour le groupe : c'est ce qui rend le dossier réellement PARTAGÉ (RM2438/RM2909).
#: Sans le bit setgid, un fichier déposé par un agent porte son groupe primaire et devient illisible
#: aux autres ; sans le `w` de groupe, personne d'autre que le créateur n'écrit — un « partage » qui
#: ne partage rien, et qui ne se voit qu'au premier agent qui échoue.
MODE_PARTAGE = 0o2775


def _mkdir(d: Path) -> None:
    """Crée le dossier avec le mode de partage, umask compris (mkdir seul le rabote)."""
    for parent in [*reversed(d.parents), d]:
        if not parent.exists():
            parent.mkdir()
            try:
                parent.chmod(MODE_PARTAGE)
            except OSError:
                pass


def a_nous(rel: Path, sub: str) -> bool:
    motifs = NOTRE.get(sub)
    return True if motifs is None else rel.name.startswith(motifs)


def plan(env=None) -> list:
    """[(sub, source, cible)] — les stores à déplacer, sources existantes seulement. Pure."""
    root = pm_stores.state_root(env)
    if root is None:
        return []
    out = []
    for legacy, sub in pm_stores.DEPLACABLES:
        src = Path(legacy).expanduser()
        dst = root / sub
        if src.is_dir() and src.resolve() != dst.resolve():
            out.append((sub, src, dst))
    return out


def migrer(src: Path, dst: Path, sub: str, dry=False, verbose=False) -> tuple:
    """Déplace ce qui manque à destination. Retourne (déplacés, déjà là, octets)."""
    bouges = deja = poids = 0
    morts = [p for p in src.rglob("*") if p.is_file() and p.name in MORTS]
    for f in sorted(p for p in src.rglob("*") if p.is_file()):
        rel = f.relative_to(src)
        if rel.name == TRACE or not a_nous(rel, sub):
            continue
        cible = dst / rel
        if cible.exists():
            deja += 1
            continue
        poids += f.stat().st_blocks * 512      # taille SUR DISQUE : ces journaux sont compressés (ZFS)
        bouges += 1
        if verbose:
            print(f"   {rel}")
        if not dry:
            _mkdir(cible.parent)
            shutil.move(str(f), str(cible))
    for m in morts:
        print(f"   · {m.name} déplacé, mais c'est un store MORT (RM3085) — supprimable")
    if bouges and not dry:
        try:
            (src / TRACE).write_text(
                f"Les stores de session PM ont été déplacés vers :\n  {dst}\n\n"
                "RM2992 — ils sont désormais communs à tous les agents de la machine.\n"
                "Ce dossier peut être supprimé une fois qu'on s'est assuré qu'il ne sert plus.\n",
                encoding="utf-8")
        except OSError:
            pass
    return bouges, deja, poids


def lier(src: Path, dst: Path, dry=False) -> str:
    """Remplace l'ancien dossier VIDÉ par un lien vers le nouveau. Rend un mot d'explication.

    C'est le filet, et il compte autant que le déplacement : une instance non redémarrée, un script
    lancé depuis un worktree sans `.env` (qui retombe sur le repli), une session ouverte avant la
    mise à jour — tous continuent d'écrire à l'ancien chemin. Sans lien, leurs écritures partent
    dans un dossier que plus personne ne lit, et **rien ne le signale**. Avec, elles atterrissent au
    bon endroit sans rien savoir du déplacement.

    Ne remplace JAMAIS un dossier qui contient encore quelque chose : ce qui reste n'est pas à nous
    (ou n'a pas pu être déplacé), et l'écraser serait le perdre."""
    if src.is_symlink():
        return "déjà un lien"
    # seuls les FICHIERS comptent : une arborescence de dossiers vides est un reliquat du
    # déplacement, pas un contenu — la laisser décider empêcherait tout lien (`sessions/`, `tasks/`…)
    reste = [p for p in src.rglob("*") if p.is_file() and p.name != TRACE]
    if reste:
        return f"pas de lien : {len(reste)} fichier(s) restent (ils ne sont pas à nous)"
    if dry:
        return f"lien à poser → {dst}"
    try:
        (src / TRACE).unlink(missing_ok=True)
        shutil.rmtree(src)      # sûr : on vient de vérifier qu'il ne reste PAS un seul fichier
        src.symlink_to(dst, target_is_directory=True)
        return f"ancien chemin → lien vers {dst}"
    except OSError as e:
        return f"lien IMPOSSIBLE ({e}) — les écritures restées sur l'ancien chemin seront perdues"


def humain(n: int) -> str:
    for u in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or u == "Go":
            return f"{n:.0f} {u}" if u == "o" else f"{n:.1f} {u}"
        n /= 1024.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--no-link", action="store_true",
                    help="ne pas remplacer l'ancien dossier vidé par un lien vers le nouveau")
    a = ap.parse_args()
    root = pm_stores.state_root()
    if root is None:
        sys.exit("pm-stores-migrate : racine des stores introuvable (config PM non résoluble ici) — "
                 "lancer depuis le runtime canonique, ou poser PM_STATE_DIR.")
    todo = plan()
    if not todo:
        print(f"✓ rien à migrer : les stores sont déjà sous {root}")
        return
    tot_b = tot_d = tot_p = 0
    for sub, src, dst in todo:
        bouges, deja, poids = migrer(src, dst, sub, dry=a.dry_run, verbose=a.verbose)
        tot_b += bouges; tot_d += deja; tot_p += poids
        etat = f"{bouges} déplacé(s)" + (f", {deja} déjà en place" if deja else "")
        print(f"{'(dry) ' if a.dry_run else ''}{src} → {dst} : {etat}" + (f" ({humain(poids)})" if poids else ""))
        if not a.no_link and str(src) in {str(Path(x).expanduser()) for x in LIENS}:
            print(f"   · {lier(src, dst, dry=a.dry_run)}")
    print(f"{'(dry) ' if a.dry_run else ''}total : {tot_b} fichier(s) déplacé(s)"
          + (f", {tot_d} déjà en place" if tot_d else "") + (f", {humain(tot_p)}" if tot_p else ""))


if __name__ == "__main__":
    main()
