#!/usr/bin/env python3
"""pm-wiki-sync — Synchronise les docs de design d'un projet PM ⇄ son Wiki Redmine.

Spec : clients/iprospective/projects/pm-ai-agents/project/wiki-sync.md (RM1821).

**Bidirectionnel** (défaut) — un seul passage gère les deux sens par cible
(« pull-then-push »), via un **merge 3-way** sur les corps canoniques :

    base    = .wiki-sync/<aspect>.base   (corps au dernier sync = ancêtre commun)
    local   = corps git courant (frontmatter strippé, liens réécrits .md→[[wiki]])
    distant = page wiki courante (bandeau + H1 + {{fnlist}} retirés)

Table de décision (spec §6) :
    base=local=distant            → rien
    local≠base, distant=base      → PUSH    git→wiki
    local=base, distant≠base      → FOLD-BACK wiki→git (réécrit le corps local)
    local≠base, distant≠base, OK  → AUTO-MERGE (git merge-file) → écrit les 2 sens
    local≠base, distant≠base, ✗   → CONFLIT → <fichier>.md.wikiconflict + notif, skip

Phases : P1 (RM1841) = push mono-dir ✅. P2 (RM1842) = fold-back + merge 3-way +
conflits + réécriture liens inverse ✅. P3 (RM1843) = overview→description projet ✅.
**P4 (RM1844, ici)** = câblage git : lock-file anti-concurrence, `--all` (cron
fallback), **auto-commit** des fold-back par défaut, `--push` (`pm-sync-push`).

Frontière inviolable (spec §2) : le **frontmatter n'est JAMAIS** poussé ni écrasé.
Au fold-back, on **relit le fichier local à chaud** et on ne remplace QUE le corps
(discipline optimistic-lock NORMS — leçon TOCTOU RM1834).

Anti-boucle (spec §9) : aucun hook git ne déclenche le sync — il n'est lancé que
manuellement ou par cron. Un commit `[wiki-sync]` ne re-déclenche donc rien (et de
toute façon, après fold-back base=local=distant → le passage suivant est noop).

Usage :
    pm-wiki-sync.py <projet>                 # sync bidirectionnel (défaut), auto-commit des fold-back
    pm-wiki-sync.py --all                     # tous les projets wiki-sync-enabled (cron fallback)
    pm-wiki-sync.py <projet> --push           # sync puis `git push` du repo projects (= pm-sync-push)
    pm-wiki-sync.py <projet> --push-only      # git→wiki seul (écrase le wiki, = P1)
    pm-wiki-sync.py <projet> --pull-only      # wiki→git seul (jamais de push)
    pm-wiki-sync.py <projet> --aspect <slug>  # une seule cible
    pm-wiki-sync.py <projet> --dry-run        # n'écrit rien (wiki, git, état)
    pm-wiki-sync.py <projet> --force          # repousse local→wiki même si inchangé
    pm-wiki-sync.py <projet> --no-commit      # n'auto-commite pas les fold-back (les signale)
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402
import redmine_utils as rm  # noqa: E402
from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)  # noqa: E402
from pm_doc import get_doc_provider, DocProviderError  # seam DocProvider (P3/RM2545)  # noqa: E402

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
    return fm, text[m.end():]


def split_raw(text):
    """Sépare (header_brut, corps) en préservant le bloc frontmatter à l'octet près.

    `header_brut` inclut les deux `---` et tout ce qu'il y a entre eux (jamais
    re-sérialisé). Utilisé au fold-back pour réécrire le corps SANS toucher au
    frontmatter. Sans frontmatter → ("", texte entier).
    """
    m = _FM_RE.match(text)
    if not m:
        return "", text
    return text[:m.end()], text[m.end():]


def canonicalize(body):
    """Corps canonique : CRLF→LF, strip des lignes vides terminales (spec §5)."""
    return body.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n") + "\n"


def body_hash(body):
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


# ── Dérivation des titres de page wiki ───────────────────────────────────
def wiki_title_for_slug(slug):
    """Identifiant de page wiki dérivé du slug (URL propre, [[lien]] stable).

    Décision spec §3 : du slug, pas du `title:` frontmatter (qui devient le H1).
    Restreint à [A-Za-z0-9_-], 1ʳᵉ lettre capitalisée.
    """
    clean = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9_-]", "-", slug).strip("-"))
    return clean[:1].upper() + clean[1:] if clean else "Page"


# ── Réécriture des liens (bidirectionnelle) ──────────────────────────────
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def rewrite_links_push(body, basename_to_title):
    """`[txt](aspect.md[#ancre])` → `[[WikiTitle[#ancre]|txt]]` (spec §5).

    Liens externes / vers fichiers non synchronisés : inchangés (limitation V1).
    """
    def repl(m):
        txt, target = m.group(1), m.group(2)
        path, _, anchor = target.partition("#")
        anchor = "#" + anchor if anchor else ""
        title = basename_to_title.get(path.rsplit("/", 1)[-1])
        return f"[[{title}{anchor}|{txt}]]" if title else m.group(0)

    return _MD_LINK_RE.sub(repl, body)


def rewrite_links_foldback(body, title_to_basename):
    """`[[WikiTitle[#ancre]|txt]]` → `[txt](basename[#ancre])` (réécriture inverse).

    `[[WikiTitle]]` sans texte → `[WikiTitle](basename)`. Lien wiki vers une page
    non gérée (titre absent de la table) : laissé tel quel (inerte côté git).
    """
    def repl(m):
        target, txt = m.group(1), m.group(2)
        title, _, anchor = target.partition("#")
        anchor = "#" + anchor if anchor else ""
        base = title_to_basename.get(title)
        if base is None:
            return m.group(0)
        return f"[{txt or title}]({base}{anchor})"

    return _WIKI_LINK_RE.sub(repl, body)


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
    """Libellés des motifs secrets détectés (vide si OK ou si marque allow présente)."""
    if _ALLOW_MARK in body:
        return []
    return [label for rx, label in _SECRET_PATTERNS if rx.search(body)]


# ── Wrappers gérés (ajoutés au push, retirés à la canonicalisation) ──────
_BANNER_PREFIX = "> 🤖 **Page générée**"
_BANNER_RE = re.compile(r"^> 🤖 \*\*Page générée\*\*.*?\n\n", re.DOTALL)
_FNLIST_RE = re.compile(r"(?:\s*\{\{fnlist\}\})+\s*$")  # Redmine ré-ajoute {{fnlist}} à chaque PUT → strip TOUS les terminaux


def banner(rel_source, sha):
    """Bandeau d'en-tête : page synchronisée bidirectionnellement depuis git."""
    return (f"{_BANNER_PREFIX} depuis `{rel_source}` (git @ {sha}). "
            f"Tes modifs ici sont **rapatriées** au prochain sync (fold-back) ; "
            f"conflit → fichier `.wikiconflict` côté git.\n\n")


def build_page_body(rel_source, sha, human_title, canon_body):
    """Corps complet poussé = bandeau + H1 (title humain) + corps canonique."""
    head = banner(rel_source, sha)
    if human_title:
        head += f"# {human_title}\n\n"
    return head + canon_body


def canonicalize_remote(text, human_title):
    """Retire les wrappers gérés d'une page wiki → corps canonique comparable à `.base`.

    Strip (dans l'ordre) : CRLF→LF, suffixe `{{fnlist}}` (ajouté par Redmine),
    bandeau (`> 🤖 …\\n\\n`), H1 généré (`# <title>\\n\\n`) — **exactement** les
    préfixes ajoutés par build_page_body (pas de strip glouton qui mangerait une
    ligne vide légitime du corps). Trailing normalisé comme canonicalize().
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _FNLIST_RE.sub("", text)
    text = _BANNER_RE.sub("", text, count=1)
    if human_title:
        h1 = re.compile(r"^# " + re.escape(human_title) + r"\n\n")
        text = h1.sub("", text, count=1)
    return text.rstrip("\n") + "\n"


# ── Accès Wiki Redmine ───────────────────────────────────────────────────
# Les 4 primitives d'I/O documentaire délèguent au seam DocProvider (P3/RM2545,
# backend wiki Redmine) tout en gardant leur contrat historique (mêmes retours,
# sys.exit sur erreur). `url`/`key` restent dans la signature des appelants mais
# le provider résout les creds lui-même (globaux — iso ; par instance = P4).
def wiki_get(url, key, proj, title):
    """GET d'une page wiki. Retourne (exists, text, version)."""
    try:
        return get_doc_provider().get_doc(proj, title)
    except DocProviderError as e:
        sys.exit(f"ERREUR Redmine {e}")


def wiki_put(url, key, proj, title, text):
    """PUT (create/update) d'une page wiki. Retourne le code HTTP (200/201/204)."""
    try:
        return get_doc_provider().put_doc(proj, title, text)
    except DocProviderError as e:
        sys.exit(f"ERREUR Redmine {e}")


# ── Description native du projet (cible P3) ──────────────────────────────
def proj_desc_get(url, key, proj):
    """Description native du projet Redmine (str, '' si vide). Sys.exit si HTTP≠200."""
    try:
        return get_doc_provider().get_project_description(proj)
    except DocProviderError as e:
        sys.exit(f"ERREUR Redmine {e}")


def proj_desc_put(url, key, proj, text):
    """PUT partiel de la description du projet. Sys.exit si échec."""
    try:
        return get_doc_provider().put_project_description(proj, text)
    except DocProviderError as e:
        sys.exit(f"ERREUR Redmine {e}")


def canonicalize_desc(text):
    """Description distante → forme canonique comparable (CRLF→LF, strip fnlist + blancs).

    Pas de bandeau/H1 sur la description projet (c'est le champ réel du projet),
    juste une normalisation. '' si vide.
    """
    text = _FNLIST_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    stripped = text.strip("\n")
    return stripped + "\n" if stripped else ""


# ── Parsing de sections H2 (pour overview → description, section-level) ───
_H2_LINE_RE = re.compile(r"^## (.+?)\s*$")


def parse_sections(body):
    """Découpe un corps markdown en blocs H2. Retourne [{heading, title, body}].

    Le 1ᵉʳ bloc (préambule avant tout `## `) a heading/title None. Round-trip
    exact via reassemble_sections().
    """
    parts, heading, title, buf = [], None, None, []
    for ln in body.split("\n"):
        m = _H2_LINE_RE.match(ln)
        if m:
            parts.append({"heading": heading, "title": title, "body": "\n".join(buf)})
            heading, title, buf = ln, m.group(1).strip(), []
        else:
            buf.append(ln)
    parts.append({"heading": heading, "title": title, "body": "\n".join(buf)})
    return parts


def reassemble_sections(parts):
    out = []
    for p in parts:
        if p["heading"] is not None:
            out.append(p["heading"])
        out.append(p["body"])
    return "\n".join(out)


def section_content(parts, title):
    """Contenu (sans blancs d'encadrement) de la section H2 `title`, ou None."""
    for p in parts:
        if p["title"] == title:
            return p["body"].strip("\n")
    return None


# ── Merge 3-way ──────────────────────────────────────────────────────────
def git_merge3(local, base, remote, labels=("local (git)", "base (dernier sync)", "wiki (Redmine)")):
    """Merge 3-way via `git merge-file -p`. Retourne (texte_mergé, conflit: bool).

    En conflit, `texte_mergé` contient les marqueurs `<<<<<<< / ======= / >>>>>>>`.
    """
    tmp = []
    try:
        for content in (local, base, remote):
            f = tempfile.NamedTemporaryFile("w", suffix=".m", delete=False, encoding="utf-8")
            f.write(content)
            f.close()
            tmp.append(f.name)
        proc = subprocess.run(
            ["git", "merge-file", "-p",
             "-L", labels[0], "-L", labels[1], "-L", labels[2],
             tmp[0], tmp[1], tmp[2]],
            capture_output=True, text=True)
        # returncode : 0 = propre, >0 = nb de conflits, <0 = erreur git
        if proc.returncode < 0:
            sys.exit(f"ERREUR git merge-file : {proc.stderr.strip()}")
        return proc.stdout, proc.returncode > 0
    finally:
        for p in tmp:
            try:
                os.unlink(p)
            except OSError:
                pass


# ── Helpers projet / git ─────────────────────────────────────────────────
def resolve_project(cfg, ref):
    # RM2430 : résolution PRÉCISE (client/slug ou redmine.project_id), jamais par
    # match de slug silencieux. require_redmine=True → refuse un projet sans
    # redmine.project_id en conf (« pas de projet Redmine précis → on n'avance pas »).
    try:
        ent, proj, proj_path = cfg.resolve_project_ref(ref, require_redmine=True)
    except ValueError as e:
        sys.exit(f"ERREUR : {e}")
    return (ent, proj, proj_path,
            cfg.path("project_dir", entity=ent, project=proj),
            cfg.path("docs_dir", entity=ent, project=proj))


def read_overview_meta(project_dir):
    # RM1994 : manifeste = meta.yml (sinon fallback frontmatter overview)
    meta = project_dir.parent / "meta.yml"
    if meta.is_file():
        fm = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
    else:
        ov = project_dir / "overview.md"
        if not ov.is_file():
            sys.exit(f"ERREUR : ni {meta} ni {ov} trouvés")
        fm, _ = split_frontmatter(ov.read_text(encoding="utf-8"))
    rid = (fm.get("redmine") or {}).get("project_id")
    if not rid:
        sys.exit(f"ERREUR : redmine.project_id absent du manifeste de {project_dir}")
    return rid, fm.get("name") or str(rid)


def git_short_sha(repo, relpath):
    for args in (["log", "-1", "--format=%h", "--", relpath], ["rev-parse", "--short", "HEAD"]):
        try:
            out = subprocess.run(["git", "-C", str(repo)] + args,
                                 capture_output=True, text=True, timeout=10)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return "?"


def git_commit_paths(repo, paths, message):
    """Commit ciblé de `paths` (relatifs au repo) avec `message`. Retourne ok: bool."""
    try:
        add = subprocess.run(["git", "-C", str(repo), "add", "--"] + paths,
                             capture_output=True, text=True)
        if add.returncode != 0:
            print(f"  ⚠ git add échoué : {add.stderr.strip()}", file=sys.stderr)
            return False
        com = subprocess.run(["git", "-C", str(repo), "commit", "-m", message, "--"] + paths,
                            capture_output=True, text=True)
        if com.returncode != 0:
            print(f"  ⚠ git commit échoué : {com.stderr.strip()}", file=sys.stderr)
            return False
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  ⚠ git : {e}", file=sys.stderr)
        return False


def git_push(repo):
    """`git push` du repo (branche courante). Retourne ok: bool. Non fatal si échec."""
    try:
        out = subprocess.run(["git", "-C", str(repo), "push"],
                             capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            print(f"  ⚠ git push échoué : {out.stderr.strip()}", file=sys.stderr)
            return False
        msg = (out.stderr or out.stdout).strip().splitlines()
        print(f"  ✓ git push : {msg[-1] if msg else 'OK'}")
        return True
    except (OSError, subprocess.SubprocessError) as e:
        print(f"  ⚠ git push : {e}", file=sys.stderr)
        return False


# ── Lock anti-concurrence (.wiki-sync/.lock) ─────────────────────────────
class LockBusy(Exception):
    """Levée quand un autre sync détient déjà le lock du projet (process vivant)."""


class ProjectLock:
    """Sérialise deux syncs concurrents d'un même projet (spec §9).

    Lock-file `.wiki-sync/.lock` (gitignore'd) créé en O_EXCL. Un lock détenu par
    un PID mort est volé (récupération après crash). Un lock vivant → LockBusy.
    """

    def __init__(self, state_dir):
        self.path = state_dir / ".lock"
        self.state_dir = state_dir
        self.acquired = False

    def __enter__(self):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            if not self._stale():
                raise LockBusy(str(self.path))
            try:
                os.unlink(self.path)
            except OSError:
                pass
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.write(fd, f"{os.getpid()}\n".encode())
        os.close(fd)
        self.acquired = True
        return self

    def _stale(self):
        """True si le lock pointe un PID absent/illisible (donc volable)."""
        try:
            pid = int(self.path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            return True
        if pid <= 0:
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False  # process vivant (autre utilisateur) → pas volable
        return False

    def __exit__(self, *exc):
        if self.acquired:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        return False


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


# ── Collecte des aspects ─────────────────────────────────────────────────
def collect_aspects(docs_dir, only_aspect=None):
    """Énumère docs/*.md (non récursif) hors overview.md et hors wiki_sync:false.

    Depuis RM2043 (privsep) les aspects-docs LIBRES vivent dans `.mmi-pm/docs/`
    (group-writable mathieu, wiki-syncés) ; `project/` ne garde que les canoniques
    (overview.md, environments.md), gérés par mathieu-pm et HORS wiki-sync. Cette
    fonction ne scrute donc QUE `docs/`. Un projet sans docs/ (aucun aspect libre)
    → liste vide.

    Retourne [{slug, path, title, rm_ticket, body_canon, wiki_title}].
    """
    aspects = []
    if not docs_dir.is_dir():
        return aspects
    for f in sorted(docs_dir.glob("*.md")):
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
            "slug": slug, "path": f,
            "title": fm.get("title") or "",
            "rm_ticket": fm.get("rm_ticket"),
            "body_canon": canonicalize(body),
            "wiki_title": wiki_title_for_slug(slug),
        })
    return aspects


def build_index_body(project_name, aspects, sha):
    lines = [f"{_BANNER_PREFIX} (index) depuis git @ {sha}. Liste des documents de "
             f"design synchronisés.\n", f"# {project_name}\n", "## Documents synchronisés\n"]
    for a in aspects:
        lines.append(f"- [[{a['wiki_title']}|{a['title'] or a['slug']}]]")
    return "\n".join(lines) + "\n"


# ── Traitement d'une cible ───────────────────────────────────────────────
def sync_aspect(a, *, url, key, rproj, repo, state, state_dir, maps, args):
    """Synchronise un aspect (merge 3-way). Retourne un libellé d'action."""
    slug, wtitle, title = a["slug"], a["wiki_title"], a["title"]
    rel_source = str(a["path"].relative_to(repo))
    basename_to_title, title_to_basename = maps

    # Garde anti-secret sur le corps local (bloque tout push de cette cible).
    secret_hits = scan_secrets(a["body_canon"])

    local = canonicalize(rewrite_links_push(a["body_canon"], basename_to_title))
    exists, wiki_text, version = wiki_get(url, key, rproj, wtitle)
    remote = canonicalize_remote(wiki_text, title) if exists else None
    tgt = state["targets"].get(slug)
    base = None
    if tgt and (state_dir / f"{slug}.base").is_file():
        base = canonicalize((state_dir / f"{slug}.base").read_text(encoding="utf-8"))

    def do_push(content, why):
        if secret_hits:
            print(f"  🚫 {slug} : secret(s) [{', '.join(secret_hits)}] → push bloqué")
            return "blocked"
        sha = git_short_sha(repo, rel_source)
        page = build_page_body(rel_source, sha, title, content)
        if args.dry_run:
            print(f"  ✎ {slug} → [[{wtitle}]] {why} (push simulé)")
        else:
            wiki_put(url, key, rproj, wtitle, page)
            _, _, v = wiki_get(url, key, rproj, wtitle)
            write_base_state(content, v)
            print(f"  ✓ {slug} → [[{wtitle}]] {why} (push, v{v})")
        return "pushed"

    def do_foldback(content, v, why):
        """Réécrit le corps local depuis `content` (canonique, repr. wiki-link)."""
        new_body = rewrite_links_foldback(content, title_to_basename)
        if args.dry_run:
            print(f"  ✎ {slug} ← [[{wtitle}]] {why} (fold-back simulé)")
            return "folded"
        raw = a["path"].read_text(encoding="utf-8")  # relecture À CHAUD (anti-TOCTOU)
        header, _ = split_raw(raw)
        a["path"].write_text(header + new_body, encoding="utf-8")
        write_base_state(content, v)
        print(f"  ✓ {slug} ← [[{wtitle}]] {why} (fold-back → {rel_source})")
        return "folded"

    def write_base_state(content, v):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / f"{slug}.base").write_text(content, encoding="utf-8")
        state["targets"][slug] = {
            "kind": "wiki", "source_file": rel_source, "wiki_title": wtitle,
            "last_wiki_version": v, "last_body_hash": body_hash(content),
        }

    # ── Cas particuliers d'amorçage ──────────────────────────────────────
    if not exists:
        return do_push(local, "création")              # page absente → init (P1)
    if args.push_only:
        return do_push(local, "push-only")             # écrase le wiki (= P1)
    if base is None:
        # Pas d'ancêtre (état perdu / page créée hors sync) : on ne peut pas
        # merger. Local fait foi (sauf --pull-only). Évite d'écraser silencieusement.
        if args.pull_only:
            return do_foldback(remote, version, "adopt-wiki (pas de base)")
        return do_push(local, "réamorçage base")

    local_changed = local != base
    remote_changed = remote != base

    if not local_changed and not remote_changed:
        print(f"  =  {slug} ↔ [[{wtitle}]] inchangé (v{version})")
        return "noop"
    if args.pull_only:
        return do_foldback(remote, version, "pull-only") if remote_changed \
            else (print(f"  =  {slug} (pull-only, distant inchangé)") or "noop")
    if local_changed and not remote_changed:
        return do_push(local, "local modifié")
    if remote_changed and not local_changed:
        return do_foldback(remote, version, "wiki modifié")

    # Les deux ont changé → merge 3-way.
    merged, conflict = git_merge3(local, base, remote)
    if conflict:
        cf = a["path"].with_suffix(a["path"].suffix + ".wikiconflict")
        if not args.dry_run:
            cf.write_text(merged, encoding="utf-8")
        notify_conflict(a, cf, rproj, url, key, dry=args.dry_run)
        print(f"  ⚠ {slug} ✗ CONFLIT → {cf.name} (push/fold-back skippés, base intacte)")
        return "conflict"
    # Auto-merge propre : écrire les deux sens.
    if secret_hits:
        print(f"  🚫 {slug} : merge OK mais secret côté local → push bloqué, fold-back seul")
        return do_foldback(merged, version, "auto-merge (push bloqué)")
    merged = canonicalize(merged)
    do_push(merged, "auto-merge")
    if not args.dry_run:
        new_body = rewrite_links_foldback(merged, title_to_basename)
        raw = a["path"].read_text(encoding="utf-8")
        header, _ = split_raw(raw)
        a["path"].write_text(header + new_body, encoding="utf-8")
    print(f"  ✓ {slug} ⇄ [[{wtitle}]] auto-merge (3-way, écrit des deux côtés)")
    return "merged"


def sync_description(overview_path, *, url, key, rproj, repo, state, state_dir, maps, args):
    """Synchronise overview ## Description ⇄ description native du projet (spec §7).

    Section-level : seule la section `## Description` est synchronisée ; le reste de
    overview.md (Workspace, Équipe, Notes, Aspects documentés) n'est pas touché.
    Détection distant = comparaison directe (le champ description n'a pas de
    compteur de version). Fold-back = remplace UNIQUEMENT la section Description.
    """
    basename_to_title, title_to_basename = maps
    rel = str(overview_path.relative_to(repo))
    raw = overview_path.read_text(encoding="utf-8")
    _, body = split_frontmatter(raw)
    content = section_content(parse_sections(body), "Description")
    if content is None:
        print("  ⏭  overview : pas de section ## Description → skip")
        return "noop"

    secret_hits = scan_secrets(content)
    local = canonicalize(rewrite_links_push(canonicalize(content), basename_to_title))
    remote = canonicalize_desc(proj_desc_get(url, key, rproj))
    tgt = state["targets"].get("overview")
    base = None
    if tgt and (state_dir / "overview.base").is_file():
        base = canonicalize((state_dir / "overview.base").read_text(encoding="utf-8"))

    def write_base_state(merged):
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "overview.base").write_text(merged, encoding="utf-8")
        state["targets"]["overview"] = {
            "kind": "project_description", "source_file": rel,
            "last_desc_hash": body_hash(merged),
        }

    def do_push(content_canon, why):
        if secret_hits:
            print(f"  🚫 overview (desc) : secret(s) [{', '.join(secret_hits)}] → push bloqué")
            return "blocked"
        if args.dry_run:
            print(f"  ✎ overview → description projet {why} (push simulé)")
        else:
            proj_desc_put(url, key, rproj, content_canon)
            write_base_state(content_canon)
            print(f"  ✓ overview → description projet {why} (push)")
        return "pushed"

    def do_foldback(merged, why):
        new_content = rewrite_links_foldback(merged, title_to_basename).strip("\n")
        if args.dry_run:
            print(f"  ✎ overview ← description projet {why} (fold-back simulé)")
            return "folded"
        hot = overview_path.read_text(encoding="utf-8")     # relecture À CHAUD
        header, hbody = split_raw(hot)
        parts = parse_sections(hbody)
        for p in parts:
            if p["title"] == "Description":
                p["body"] = "\n" + new_content + "\n"
                break
        overview_path.write_text(header + reassemble_sections(parts), encoding="utf-8")
        write_base_state(merged)
        print(f"  ✓ overview ← description projet {why} (fold-back → {rel}, section Description)")
        return "folded"

    if args.push_only:
        return do_push(local, "push-only")
    if base is None:
        if args.pull_only and remote:
            return do_foldback(remote, "adopt-desc (pas de base)")
        return do_push(local, "réamorçage base")

    local_changed, remote_changed = local != base, remote != base
    if not local_changed and not remote_changed:
        print("  =  overview ↔ description projet inchangé")
        return "noop"
    if args.pull_only:
        return do_foldback(remote, "pull-only") if remote_changed \
            else (print("  =  overview (pull-only, distant inchangé)") or "noop")
    if local_changed and not remote_changed:
        return do_push(local, "local modifié")
    if remote_changed and not local_changed:
        return do_foldback(remote, "description projet modifiée")

    merged, conflict = git_merge3(local, base, remote)
    if conflict:
        cf = overview_path.with_suffix(overview_path.suffix + ".wikiconflict")
        if not args.dry_run:
            cf.write_text(merged, encoding="utf-8")
        print(f"  ⚠ overview ✗ CONFLIT description → {cf.name} (push/fold-back skippés)")
        return "conflict"
    if secret_hits:
        print("  🚫 overview : merge OK mais secret local → push bloqué, fold-back seul")
        return do_foldback(merged, "auto-merge (push bloqué)")
    merged = canonicalize(merged)
    if not args.dry_run:
        proj_desc_put(url, key, rproj, merged)
        do_foldback(merged, "auto-merge")  # écrit aussi la section locale + base
    print("  ✓ overview ⇄ description projet auto-merge (3-way, écrit des deux côtés)")
    return "merged"


def notify_conflict(a, conflict_path, rproj, url, key, dry=False):
    """Notifie un conflit de sync : note Redmine sur le ticket de l'aspect (si connu)."""
    rm_ticket = a.get("rm_ticket")
    msg = (f"⚠ **Conflit wiki-sync** sur l'aspect `{a['slug']}` "
           f"(page [[{a['wiki_title']}]]).\n\n"
           f"Le wiki ET le fichier git ont divergé sur des lignes qui se chevauchent. "
           f"Le fichier canonique n'a **pas** été modifié ; les marqueurs de conflit "
           f"sont dans `{conflict_path.name}`. Résous puis relance `pm-wiki-sync`.")
    if dry:
        print(f"     (notif simulée → RM{rm_ticket})")
        return
    if rm_ticket:
        try:
            get_task_provider().add_note(int(rm_ticket), msg)
            print(f"     → notif postée sur RM{rm_ticket}")
        except SystemExit:
            print(f"     ⚠ notif RM{rm_ticket} échouée (note non postée)", file=sys.stderr)
    # TODO P4 : notif Telegram (RM1774) en plus de la note Redmine.


def discover_wiki_projects(cfg):
    """Projets wiki-sync-enabled = ceux ayant un `.wiki-sync/state.json` (initialisés).

    L'opt-in est implicite : un premier `pm-wiki-sync.py <projet>` crée l'état, après
    quoi le cron `--all` prend le projet en charge. Retourne une liste de slugs triés.
    """
    out = []
    for ent, proj, proj_path in cfg.iter_projects():
        if (Path(proj_path) / ".wiki-sync" / "state.json").is_file():
            out.append(f"{ent}/{proj}")   # RM2430 : réf non ambiguë (client/slug)
    return sorted(out)


def sync_one_project(cfg, url, key, slug, args):
    """Synchronise un projet (sous lock). Retourne le dict de comptes d'actions.

    Lève LockBusy si un autre sync du même projet est déjà en cours.
    """
    ent, proj, project_root, project_dir, docs_dir = resolve_project(cfg, slug)
    rproj, project_name = read_overview_meta(project_dir)
    state_dir = project_root / ".wiki-sync"
    repo = cfg.projects_root

    # Périmètre : aspects (pages wiki) et/ou overview→description projet.
    if args.project_desc_only:
        do_aspects, do_desc = False, True
    elif args.aspect:
        do_aspects, do_desc = True, False   # un aspect ciblé ne touche pas la description
    else:
        do_aspects, do_desc = True, True

    aspects = collect_aspects(docs_dir, args.aspect) if do_aspects else []
    if do_aspects and not aspects:
        print(f"▶ {proj} : aucun aspect à synchroniser — skip")
        return {}

    # Tables de réécriture des liens (sur TOUS les aspects du projet, pas juste
    # ceux de ce run — pour que les liens restent corrects en --aspect ciblé).
    basename_to_title, title_to_basename = {}, {}
    for f in (docs_dir.glob("*.md") if docs_dir.is_dir() else []):
        if f.stem == "overview":
            continue
        wt = wiki_title_for_slug(f.stem)
        basename_to_title[f.name] = wt
        title_to_basename[wt] = f.name
    maps = (basename_to_title, title_to_basename)

    mode = "push-only" if args.push_only else ("pull-only" if args.pull_only else "bidir")

    with ProjectLock(state_dir):  # sérialise deux syncs concurrents du même projet
        state = load_state(state_dir)
        state.setdefault("targets", {})

        print(f"▶ {proj} (Redmine={rproj}) — {len(aspects)} aspect(s) [{mode}"
              + (", dry-run" if args.dry_run else "") + "]")

        counts = {}
        for a in aspects:
            r = sync_aspect(a, url=url, key=key, rproj=rproj, repo=repo, state=state,
                            state_dir=state_dir, maps=maps, args=args)
            counts[r] = counts.get(r, 0) + 1

        if do_desc:
            r = sync_description(project_dir / "overview.md", url=url, key=key, rproj=rproj,
                                 repo=repo, state=state, state_dir=state_dir, maps=maps, args=args)
            counts[r] = counts.get(r, 0) + 1

        # Page index (régénérée — pas de fold-back, dérivée) sauf en sync ciblé / pull-only.
        if do_aspects and not args.aspect and not args.pull_only:
            idx = build_index_body(project_name, aspects, git_short_sha(repo, "."))
            if args.dry_run:
                print(f"  ✎ index → [[{args.index_title}]] (simulé)")
            else:
                wiki_put(url, key, rproj, args.index_title, idx)
                print(f"  ✓ index → [[{args.index_title}]]")

        if not args.dry_run:
            save_state(state_dir, state)

        # Auto-commit des fold-back (défaut P4) — commit ciblé par chemin (jamais
        # `git add -A` : le repo projects est partagé/dirty). `--no-commit` les signale.
        folded = counts.get("folded", 0) + counts.get("merged", 0)
        if folded and not args.dry_run:
            if args.no_commit:
                print(f"  ℹ {folded} fichier(s) modifié(s) par fold-back — non commité(s) "
                      f"(--no-commit)")
            else:
                paths = [str(a["path"].relative_to(repo)) for a in aspects]
                paths += [str((state_dir / "state.json").relative_to(repo))]
                paths += [str(p.relative_to(repo)) for p in state_dir.glob("*.base")]
                if do_desc:
                    paths.append(str((project_dir / "overview.md").relative_to(repo)))
                if git_commit_paths(repo, paths, f"chore(wiki): fold-back {proj} [wiki-sync]"):
                    print(f"  ✓ {folded} fold-back commité(s) [wiki-sync]")

    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "rien"
    print(f"— {proj}: {summary}")
    return counts


def main():
    ap = argparse.ArgumentParser(description="Sync docs PM ⇄ Wiki Redmine (RM1821, P1→P4)")
    ap.add_argument("project", nargs="?",
                    help="réf projet PRÉCISE : client/slug (ex. matnat/infra) ou "
                         "redmine.project_id (ex. matnat-infra) — RM2430, plus de slug ambigu")
    ap.add_argument("--all", action="store_true",
                    help="tous les projets wiki-sync-enabled (.wiki-sync/state.json présent)")
    ap.add_argument("--push", action="store_true",
                    help="après le sync, `git push` du repo projects (= pm-sync-push)")
    ap.add_argument("--aspect", help="ne synchroniser qu'un aspect (par slug)")
    ap.add_argument("--dry-run", action="store_true", help="n'écrit rien (wiki, git, état)")
    ap.add_argument("--force", action="store_true", help="repousse local→wiki même si inchangé")
    ap.add_argument("--push-only", action="store_true", help="git→wiki seul (écrase le wiki)")
    ap.add_argument("--pull-only", action="store_true", help="wiki→git seul (jamais de push)")
    ap.add_argument("--project-desc-only", action="store_true",
                    help="ne synchroniser que overview ## Description ⇄ description projet")
    ap.add_argument("--no-commit", action="store_true",
                    help="ne pas auto-committer les fold-back (juste les signaler)")
    ap.add_argument("--commit", action="store_true",
                    help="(déprécié — l'auto-commit est désormais le défaut ; sans effet)")
    ap.add_argument("--index-title", default="Wiki", help="titre de la page index wiki")
    args = ap.parse_args()
    if args.push_only and args.pull_only:
        sys.exit("ERREUR : --push-only et --pull-only sont exclusifs")
    if args.all and args.project:
        sys.exit("ERREUR : --all et un projet nommé sont exclusifs")
    if args.all and args.aspect:
        sys.exit("ERREUR : --aspect n'a pas de sens avec --all")
    if not args.all and not args.project:
        sys.exit("ERREUR : préciser un projet, ou --all")
    if args.force:
        args.push_only = True  # --force ⇒ push inconditionnel (override base)

    cfg = PMConfig.load()
    url, key = rm.redmine_creds()
    repo = cfg.projects_root

    if args.all:
        slugs = discover_wiki_projects(cfg)
        if not slugs:
            print("Aucun projet wiki-sync-enabled (.wiki-sync/state.json) trouvé.")
            return
        print(f"▶▶ --all : {len(slugs)} projet(s) wiki-sync-enabled : {', '.join(slugs)}")
    else:
        slugs = [args.project]

    total = {}
    for slug in slugs:
        try:
            counts = sync_one_project(cfg, url, key, slug, args)
        except LockBusy as e:
            print(f"  ⏭  {slug} : sync déjà en cours (lock {e}) → skip")
            total["busy"] = total.get("busy", 0) + 1
            continue
        for k, v in counts.items():
            total[k] = total.get(k, 0) + v

    # `git push` après tous les projets (repo projects partagé → un seul push suffit).
    if args.push and not args.dry_run:
        git_push(repo)

    if args.all or len(slugs) > 1:
        summary = " ".join(f"{k}={v}" for k, v in sorted(total.items())) or "rien"
        print(f"\n══ total : {summary}")

    if total.get("conflict"):
        sys.exit(3)
    if total.get("blocked"):
        sys.exit(2)


if __name__ == "__main__":
    main()
