#!/usr/bin/env python3
"""pm-wiki-sync — Synchronise les docs de design d'un projet PM vers son Wiki Redmine.

Spec : clients/iprospective/projects/pm-ai-agents/project/wiki-sync.md (RM1821).

**Phase P1 (RM1841) — push mono-directionnel** : ce module ne fait QUE le sens
git → wiki. Chaque aspect `project/*.md` (hors `overview.md`) devient une page
wiki ; une page index liste les aspects. Le fold-back wiki → git (merge 3-way,
conflits `.wikiconflict`) est la phase P2 (RM1842) ; overview → description projet
est P3 (RM1843) ; le câblage git (`pm-sync-push` + cron) est P4 (RM1844).

Conséquence P1 : le wiki est **dérivé** du git. Une retouche manuelle d'une page
sera **écrasée** au prochain sync. Le bandeau le signale. (P2 lèvera cette limite.)

Frontière inviolable (spec §2) : le **frontmatter n'est JAMAIS** poussé. Seul le
corps part au wiki. Garde anti-secret avant tout push (spec §5).

État local : `clients/<e>/projects/<p>/.wiki-sync/` (sibling de `project/`, hors
dossier synchronisé) — `state.json` + `<aspect>.base` (corps canonique du dernier
sync, futur ancêtre du merge 3-way en P2).

Usage :
    pm-wiki-sync.py <projet>                 # push tous les aspects + index
    pm-wiki-sync.py <projet> --aspect <slug> # un seul aspect
    pm-wiki-sync.py <projet> --dry-run       # n'écrit rien (ni wiki ni état local)
    pm-wiki-sync.py <projet> --force         # repousse même si corps inchangé
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import redmine_utils as rm  # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


# ── Frontmatter / corps ──────────────────────────────────────────────────
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def split_frontmatter(text):
    """Sépare (frontmatter_dict, corps). Sans frontmatter → ({}, texte entier)."""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    body = text[m.end():]
    return fm, body


def canonicalize(body):
    """Corps canonique : CRLF→LF, strip des lignes vides terminales (spec §5).

    Minimal — on ne réécrit pas le contenu. C'est ce corps (sans wrappers gérés)
    qui est hashé et stocké en `.base`.
    """
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    return body.rstrip("\n") + "\n"


def body_hash(body):
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── Dérivation des titres de page wiki ───────────────────────────────────
def wiki_title_for_slug(slug):
    """Identifiant de page wiki dérivé du slug d'aspect (URL propre, stable).

    Raffinement spec §3 : on dérive du slug (pas du `title:` frontmatter, qui
    ferait un identifiant d'URL illisible). Le `title:` humain devient le H1 du
    corps (cf. build_page_body). Restreint à [A-Za-z0-9_-], 1ʳᵉ lettre capitalisée.
    """
    clean = re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-")
    clean = re.sub(r"-{2,}", "-", clean)
    return clean[:1].upper() + clean[1:] if clean else "Page"


# ── Réécriture des liens (sens push : .md → [[wiki]]) ─────────────────────
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def rewrite_links_push(body, basename_to_title):
    """Réécrit `[txt](aspect.md[#ancre])` → `[[WikiTitle[#ancre]|txt]]` (spec §5).

    `basename_to_title` : {nom_fichier.md → wiki_title} des aspects synchronisés.
    Liens externes / vers fichiers non synchronisés (overview.md, tasks, http…) :
    laissés tels quels (texte inerte dans le wiki) — limitation V1 assumée.
    """
    def repl(m):
        txt, target = m.group(1), m.group(2)
        anchor = ""
        path = target
        if "#" in target:
            path, anchor = target.split("#", 1)
            anchor = "#" + anchor
        base = path.rsplit("/", 1)[-1]
        title = basename_to_title.get(base)
        if title is None:
            return m.group(0)  # non synchronisé → inchangé
        return f"[[{title}{anchor}|{txt}]]"

    return _MD_LINK_RE.sub(repl, body)


# ── Garde anti-secret (spec §5) ──────────────────────────────────────────
_SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clé privée PEM"),
    (re.compile(r"(?i)\bpassword\s*[:=]\s*\S+"), "password: <valeur>"),
    (re.compile(r"(?i)\bpasswd\s*[:=]\s*\S+"), "passwd: <valeur>"),
    (re.compile(r"(?i)\bsecret\s*[:=]\s*\S+"), "secret: <valeur>"),
    (re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*\S+"), "api_key: <valeur>"),
    (re.compile(r"\b[A-Za-z0-9+/]{32,}={0,2}\b"), "jeton haute entropie (≥32c base64)"),
]
_ALLOW_MARK = "<!-- wiki-sync: allow -->"


def scan_secrets(body):
    """Retourne la liste des libellés de motifs secrets détectés (vide si OK).

    Échappatoire : présence de `<!-- wiki-sync: allow -->` dans le corps → on
    n'inspecte pas (le rédacteur atteste qu'il n'y a pas de secret littéral).
    """
    if _ALLOW_MARK in body:
        return []
    hits = []
    for rx, label in _SECRET_PATTERNS:
        if rx.search(body):
            hits.append(label)
    return hits


# ── Bandeau géré (ajouté au push, retiré à la canonicalisation en P2) ─────
_BANNER_PREFIX = "> 🤖 **Page générée**"


def banner(rel_source, sha):
    """Bandeau d'en-tête P1 : page dérivée du git, lecture seule côté wiki."""
    return (f"{_BANNER_PREFIX} depuis `{rel_source}` (git @ {sha}). "
            f"Ne pas éditer ici : modifications écrasées au prochain sync "
            f"(fold-back wiki→git = P2/RM1842).\n\n")


def build_page_body(rel_source, sha, human_title, canon_body):
    """Corps complet poussé au wiki = bandeau + H1 titre humain + corps canonique."""
    head = banner(rel_source, sha)
    if human_title:
        head += f"# {human_title}\n\n"
    return head + canon_body


# ── Accès Wiki Redmine ───────────────────────────────────────────────────
def wiki_get(url, key, proj, title):
    """GET d'une page wiki. Retourne (exists, text, version)."""
    code, body = rm.http_json("GET", f"{url}/projects/{proj}/wiki/{title}.json", key)
    if code == 200:
        wp = body.get("wiki_page", {})
        return True, wp.get("text", ""), wp.get("version")
    if code == 404:
        return False, "", None
    sys.exit(f"ERREUR Redmine HTTP {code} sur GET wiki/{title} : {body.get('_error', '')}")


def wiki_put(url, key, proj, title, text):
    """PUT (create/update) d'une page wiki. Retourne le code HTTP (201/204)."""
    payload = {"wiki_page": {"text": text}}
    code, body = rm.http_json("PUT", f"{url}/projects/{proj}/wiki/{title}.json", key, payload)
    if code not in (200, 201, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} sur PUT wiki/{title} : {body.get('_error', '')}")
    return code


# ── Helpers projet / git ─────────────────────────────────────────────────
def resolve_project(cfg, slug):
    """Trouve (entity, project, project_root, project_dir) pour un slug de projet."""
    for ent, proj, proj_path in cfg.iter_projects():
        if proj == slug:
            return ent, proj, proj_path, cfg.path("project_dir", entity=ent, project=proj)
    sys.exit(f"ERREUR : projet '{slug}' introuvable dans l'arbo PM")


def read_overview_meta(project_dir):
    """Lit overview.md → (redmine_project_id, project_name). Sys.exit si absent."""
    ov = project_dir / "overview.md"
    if not ov.is_file():
        sys.exit(f"ERREUR : {ov} introuvable")
    fm, _ = split_frontmatter(ov.read_text(encoding="utf-8"))
    rid = (fm.get("redmine") or {}).get("project_id")
    if not rid:
        sys.exit(f"ERREUR : redmine.project_id absent du frontmatter de {ov}")
    return rid, fm.get("name") or str(rid)


def git_short_sha(repo, relpath):
    """SHA court du dernier commit touchant `relpath` (fallback HEAD, puis '?')."""
    for args in (["log", "-1", "--format=%h", "--", relpath], ["rev-parse", "--short", "HEAD"]):
        try:
            out = subprocess.run(["git", "-C", str(repo)] + args,
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return "?"


# ── État local (.wiki-sync/) ─────────────────────────────────────────────
def load_state(state_dir):
    f = state_dir / "state.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema": 1, "targets": {}}


def save_state(state_dir, state):
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps(state, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8")


# ── Pipeline principal P1 ────────────────────────────────────────────────
def collect_aspects(project_dir, only_aspect=None):
    """Énumère project/*.md (non récursif) hors overview.md et hors wiki_sync:false.

    Retourne une liste de dicts {slug, path, title, body_canon, wiki_title}.
    """
    aspects = []
    for f in sorted(project_dir.glob("*.md")):
        slug = f.stem
        if slug == "overview":
            continue
        if only_aspect and slug != only_aspect:
            continue
        fm, body = split_frontmatter(f.read_text(encoding="utf-8"))
        if fm.get("wiki_sync") is False:
            print(f"  ⏭  {slug} : wiki_sync=false → skip")
            continue
        aspects.append({
            "slug": slug,
            "path": f,
            "title": fm.get("title") or "",
            "body_canon": canonicalize(body),
            "wiki_title": wiki_title_for_slug(slug),
        })
    return aspects


def build_index_body(project_name, aspects, sha):
    """Corps de la page index (spec §8) : bandeau + liste des aspects synchronisés."""
    lines = [f"{_BANNER_PREFIX} (index) depuis git @ {sha}. Liste des documents de "
             f"design synchronisés.\n", f"# {project_name}\n", "## Documents synchronisés\n"]
    for a in aspects:
        label = a["title"] or a["slug"]
        lines.append(f"- [[{a['wiki_title']}|{label}]]")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="Sync docs PM → Wiki Redmine (P1 push mono-dir)")
    ap.add_argument("project", help="slug du projet PM (ex: pm-ai-agents)")
    ap.add_argument("--aspect", help="ne synchroniser qu'un aspect (par slug)")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien (wiki ni état local)")
    ap.add_argument("--force", action="store_true", help="repousse même si corps inchangé")
    ap.add_argument("--index-title", default="Wiki",
                    help="titre de la page index wiki (défaut: Wiki = start page Redmine)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    url, key = rm.redmine_creds()
    ent, proj, project_root, project_dir = resolve_project(cfg, args.project)
    rproj, project_name = read_overview_meta(project_dir)
    state_dir = project_root / ".wiki-sync"
    repo = cfg.projects_root

    aspects = collect_aspects(project_dir, args.aspect)
    if not aspects:
        sys.exit("Aucun aspect à synchroniser.")

    basename_to_title = {a["path"].name: a["wiki_title"] for a in aspects}
    # Map complète (tous les aspects du projet, même hors --aspect) pour que la
    # réécriture des liens reste correcte quand on sync un seul aspect.
    for f in project_dir.glob("*.md"):
        if f.stem not in ("overview",) and f.name not in basename_to_title:
            basename_to_title[f.name] = wiki_title_for_slug(f.stem)

    state = load_state(state_dir)
    state.setdefault("targets", {})
    pushed, skipped, blocked = [], [], []

    print(f"▶ {proj} (Redmine={rproj}) — {len(aspects)} aspect(s)"
          + (" [dry-run]" if args.dry_run else ""))

    for a in aspects:
        slug, wtitle = a["slug"], a["wiki_title"]
        rel_source = str(a["path"].relative_to(repo))
        sha = git_short_sha(repo, rel_source)

        # 1. Garde anti-secret sur le corps canonique (avant toute transformation).
        hits = scan_secrets(a["body_canon"])
        if hits:
            print(f"  🚫 {slug} : secret(s) détecté(s) [{', '.join(hits)}] → push bloqué")
            blocked.append(slug)
            continue

        # 2. Réécriture des liens (push) sur le corps canonique.
        transformed = rewrite_links_push(a["body_canon"], basename_to_title)
        new_hash = body_hash(transformed)

        # 3. Skip si inchangé depuis le dernier sync (sauf --force). Le hash porte
        #    sur le corps transformé SANS bandeau → un simple changement de SHA git
        #    ne force pas un re-push inutile.
        tgt = state["targets"].get(slug, {})
        exists, _, version = wiki_get(url, key, rproj, wtitle)
        if exists and not args.force and tgt.get("last_body_hash") == new_hash:
            print(f"  ⏭  {slug} → [[{wtitle}]] inchangé (v{version})")
            skipped.append(slug)
            continue

        # 4. Construire la page (bandeau + H1 + corps) et pousser.
        page = build_page_body(rel_source, sha, a["title"], transformed)
        if args.dry_run:
            print(f"  ✎ {slug} → [[{wtitle}]] (push simulé, {len(page)} c)")
        else:
            code = wiki_put(url, key, rproj, wtitle, page)
            _, _, version = wiki_get(url, key, rproj, wtitle)
            print(f"  ✓ {slug} → [[{wtitle}]] {'créée' if code == 201 else 'maj'} (v{version})")
            # 5. Mettre à jour base + state.
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / f"{slug}.base").write_text(transformed, encoding="utf-8")
            state["targets"][slug] = {
                "kind": "wiki",
                "source_file": rel_source,
                "wiki_title": wtitle,
                "last_wiki_version": version,
                "last_body_hash": new_hash,
            }
        pushed.append(slug)
        print(f"     → {url}/projects/{rproj}/wiki/{wtitle}")

    # 6. Page index (régénérée à chaque run).
    if not args.aspect:  # un sync ciblé ne touche pas l'index
        idx_body = build_index_body(project_name, aspects, git_short_sha(repo, "."))
        if args.dry_run:
            print(f"  ✎ index → [[{args.index_title}]] (push simulé)")
        else:
            wiki_put(url, key, rproj, args.index_title, idx_body)
            print(f"  ✓ index → [[{args.index_title}]]")

    if not args.dry_run:
        save_state(state_dir, state)

    print(f"\n— pushed={len(pushed)} skipped={len(skipped)} blocked={len(blocked)}")
    if blocked:
        sys.exit(2)  # au moins un secret a bloqué un push


if __name__ == "__main__":
    main()
