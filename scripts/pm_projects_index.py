"""pm_projects_index — l'INDEX des projets PM : les symlinks `projects/clients/<c>/projects/<p>` → `<workspace>/.mmi-pm` (RM3033, porté de bin/mmi-pm).

L'index est karl-writable, régénérable et gitignored : il pointe vers les données co-localisées dans les workspaces (modèle RM1942/1949).
Aucun privilège : `add`/`remove` posent ou retirent un lien, `rebuild` redécouvre les manifestes (`meta.yml`, RM1994) sous la racine
des workspaces, `list` lit. Fonctions pures + I/O minimales, testables sur une arborescence temporaire.

**RM3142 — pourquoi ce nom.** Ce module s'appelait `pm_index`. RM3128 a créé un autre index (celui de
REQUÊTAGE, une projection SQLite du Markdown) et lui a donné le même nom de fichier : celui-ci a été
écrasé, et les quatre commandes qui s'en servaient (`index add|list|remove|rebuild`) appelaient depuis
des fonctions qui n'existaient plus. Elles étaient mortes sans que rien ne le dise — on ne pouvait
plus reconstruire les liens de co-localisation, c'est-à-dire l'outil de RÉPARATION de ce qui permet
au PM de trouver ses fiches. Deux index, deux noms : `pm_index` requête, `pm_projects_index` relie.
"""
import os
from pathlib import Path

WORKSPACES_ROOT = Path(os.environ.get("WORKSPACES_ROOT", "/zfs/workspaces"))


def split_spec(spec: str) -> tuple[str, str]:
    """`<client>/<projet>` → (client, projet) ; lève ValueError sinon."""
    s = str(spec or "")
    if "/" not in s:
        raise ValueError(f"format attendu : <client>/<projet> (reçu : {s!r})")
    client, project = s.split("/", 1)
    if not client or not project or "/" in project:
        raise ValueError(f"format attendu : <client>/<projet> (reçu : {s!r})")
    return client, project


def link_path(projects_root, client: str, project: str) -> Path:
    return Path(projects_root) / "clients" / client / "projects" / project


def link_project(projects_root, client: str, project: str, loc, dry: bool = False) -> Path:
    """Pose (ou remplace) le lien d'index d'un projet vers `<loc>/.mmi-pm`."""
    link = link_path(projects_root, client, project)
    target = Path(loc) / ".mmi-pm"
    if dry:
        return link
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            raise FileExistsError(f"{link} est un vrai dossier, pas un lien d'index — refus d'écraser")
        link.unlink()
    link.symlink_to(target)
    return link


def add(projects_root, spec: str, loc=None, dry: bool = False, workspaces_root=None) -> dict:
    client, project = split_spec(spec)
    loc = Path(loc) if loc else Path(workspaces_root or WORKSPACES_ROOT) / client / project
    if not (loc / ".mmi-pm").is_dir():
        raise FileNotFoundError(f"pas de .mmi-pm dans {loc}")
    link = link_project(projects_root, client, project, loc, dry)
    return {"client": client, "project": project, "link": str(link), "target": str(loc / ".mmi-pm"), "dry": dry}


def remove(projects_root, spec: str, dry: bool = False) -> dict:
    client, project = split_spec(spec)
    link = link_path(projects_root, client, project)
    if not link.is_symlink():
        raise FileNotFoundError(f"pas de lien d'index pour {client}/{project}")
    if not dry:
        link.unlink()
    return {"client": client, "project": project, "link": str(link), "dry": dry}


def _meta_field(path: Path, key: str) -> str:
    """Valeur d'une clé de premier niveau d'un meta.yml (lecture sans yaml, comme le faisait awk)."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key + ":"):
                return line[len(key) + 1:].split("#", 1)[0].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def discover(workspaces_root, maxdepth: int = 6):
    """Manifestes clients (`.mmi-pm-client/meta.yml`) et projets (`.mmi-pm/meta.yml`) sous la racine, `.git` élagué,
    un `.mmi-pm` SYMLINK (ancienne instance) n'est pas traversé. Rend (clients, projects) = listes de (loc, meta_path)."""
    root = Path(workspaces_root)
    clients, projects = [], []
    if not root.is_dir():
        return clients, projects
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        if len(d.parts) - base_depth >= maxdepth:
            dirnames[:] = []
        dirnames[:] = [x for x in dirnames if x != ".git" and not (d / x).is_symlink()]
        if d.name == ".mmi-pm-client" and "meta.yml" in filenames:
            clients.append((d.parent, d / "meta.yml"))
        if d.name == ".mmi-pm" and "meta.yml" in filenames:
            projects.append((d.parent, d / "meta.yml"))
    return clients, projects


def rebuild(projects_root, workspaces_root=None, dry: bool = False, say=print) -> dict:
    """Reconstruit l'index depuis les emplacements canoniques. Rend les compteurs."""
    wroot = Path(workspaces_root or WORKSPACES_ROOT)
    clients, projects = discover(wroot)
    nc = np = 0
    for loc, mf in clients:
        slug = _meta_field(mf, "slug") or loc.name
        for sub in ("client", "memory", "projects_used"):
            src = loc / ".mmi-pm-client" / sub
            if not src.is_dir():
                continue
            clink = Path(projects_root) / "clients" / slug / sub
            if dry:
                say(f"  [dry] client {slug}/{sub} -> {src}")
            else:
                clink.parent.mkdir(parents=True, exist_ok=True)
                if clink.is_symlink() or clink.exists():
                    if clink.is_dir() and not clink.is_symlink():
                        say(f"  ⚠ {clink} est un vrai dossier — laissé tel quel"); continue
                    clink.unlink()
                clink.symlink_to(src)
        nc += 1
    for loc, mf in projects:
        slug = _meta_field(mf, "slug") or loc.name
        client = _meta_field(mf, "client") or loc.parent.name
        if dry:
            say(f"  [dry] {client}/{slug} -> {loc}/.mmi-pm")
        else:
            try:
                link_project(projects_root, client, slug, loc)
            except FileExistsError as e:
                say(f"  ⚠ {e}"); continue
        np += 1
    return {"clients": nc, "projects": np, "dry": dry}


def listing(projects_root) -> list:
    """[(client, [(projet, cible|None)])] — l'inventaire de l'index."""
    root = Path(projects_root) / "clients"
    if not root.is_dir():
        raise FileNotFoundError(f"index absent : {root}")
    out = []
    for cdir in sorted(p for p in root.iterdir() if p.is_dir()):
        rows = []
        pdir = cdir / "projects"
        if pdir.is_dir():
            for p in sorted(pdir.iterdir()):
                rows.append((p.name, os.readlink(p) if p.is_symlink() else None))
        out.append((cdir.name, rows))
    return out


def format_listing(rows: list) -> str:
    lines = []
    for client, projects in rows:
        lines.append(client)
        for name, target in projects:
            lines.append(f"  └ {name}" + (f" -> {target}" if target else ""))
    return "\n".join(lines)
