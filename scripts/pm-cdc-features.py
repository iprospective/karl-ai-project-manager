#!/usr/bin/env python3
"""pm-cdc-features — registre des fonctionnalités d'un projet, dérivé de ses tickets (RM3043).

Le CDC vivant d'un projet (modèle AtomBox) tient sa liste de fonctionnalités dans un REGISTRE
`docs/cdc/fonctionnalites.yml` (RM3015-D008 : noms génériques ; l'ancienne forme `docs/cdc-<prefix>/`
reste lue) : une entrée par ticket (identifiant F001… STABLE, jamais réattribué), avec domaine,
état et date. Le chapitre `docs/cdc-features.md` en est GÉNÉRÉ (ancienne forme :
`cdc-<prefix>-10-fonctionnalites.md`) — deux vues, une donnée. Le bloc entre marqueurs
`think-merge` (détail des fonctionnalités par ticket, `pm-think-merge`) y est conservé tel quel.

  --init --prefix <p>   crée le registre (domaines par mots-clés, à ajuster ensuite dans le yml) ; `--no-sync` le laisse vide
                        (registre CURÉ par capacité : entrées manuelles avec `tickets: [RM…]` multiples, ex. cdc-karl)
  --sync                ajoute les tickets nouveaux (tout sauf `nouveau`), met à jour état/date des
                        existants ; une entrée `manuel: true` garde son libellé et son domaine
  --build               écrit le chapitre 10 depuis le registre
  --check               registre et chapitre à jour ? (exit 1 sinon) — à brancher en garde de livraison
  --project <client>/<projet>   défaut : le projet du workspace courant (`.mmi-pm`)
  --docs-dir / --tasks-dir      surcharges (tests)

Champs optionnels par entrée : `version` (V0, V1… — RM3015-D018 : la version est une COLONNE, la roadmap un rôle par
version ; `--assign-version <V> [--etat livré]` la pose en masse sur les entrées qui n'en ont pas), `jalon` (entier, forme AtomBox),
`tickets` (liste d'ids couverts par une entrée curée — `--sync` ne les rajoute pas), `manuel: true`.

États (dérivés du statut du ticket) : livré (fermé résolu) · en cours (en_cours, tests, MEP,
a_corriger) · prévu (a_faire, étude) · en pause · écarté (fermé autre raison).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_think   # noqa: E402  RM3053
from pm_think import is_task_sheet  # RM3053 : la fiche, jamais un frère (.log.md, .think.md)
try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

DEFAULT_DOMAINES = [
    ("Cockpit & karl-agent", r"cockpit|onglet|panneau|karl-agent|ttyd|terminal|dashboard|tableau de bord|composer|vibe|mobile|android"),
    ("WORM (ORM)", r"\bworm\b"),
    ("Outillage PM (scripts, CLI, skills)", r"\bpm-|mmi-pm|\bskill|script|\bcli\b|wrapper|porcelain|cheatsheet"),
    ("Sessions & agents", r"session|transcript|orchestrat|sous-agent|worker|tmux|spawn|\bagent|claude|opencode|resume|reprise|outline"),
    ("Communication (mail, SMS, notifications)", r"\bmail|e-mail|email|telegram|\bsms\b|notif|alerte|voix|vocal|imap|dictée"),
    ("Git, forge & MEP", r"\bgit|branche|\bMR\b|merge|gitlab|gogs|github|forge|\bMEP\b|promotion|worktree|push|commit|submodule|release|licence|license"),
    ("Redmine & workflow des tickets", r"redmine|\bCF\b|statut|status|workflow|ticket|tâche|task|sous-tâche|checklist|description|done_ratio|récurr|assign|attribution|fermeture|close"),
    ("Environnements & infra", r"\benv|lxc|vhost|zfs|instance|install|provision|deploy|déploi|systemd|sudo|apache|nginx|serveur|machine|\bhost|conteneur|opensvc|zabbix|\bdns\b|backup|snapshot|infra|prestashop|runtime"),
    ("Secrets & sécurité", r"vault|secret|token|\bPAT\b|sécurité|security|droits|\bauth|permission|confinement|credential|clé|\bkey"),
    ("Métriques, ROI & coûts", r"\broi\b|temps|coût|cout|prix|pricing|\btick|timesheet|heure|usage|budget|bench|conso|métrique|metric|estim|ledger|reporting"),
    ("NORMS & méthode", r"norms|norme|kernel|\bcdc\b|méthode|tripwire|doctor|protocole|règle|governance|gouvernance|précharge|contexte|ergonomi"),
    ("Docs, wiki & knowledge", r"\bdoc|wiki|glossaire|knowledge|readme|\baide|changelog|help|dictionnaire|journal|tags?\b"),
    ("Projets, clients & modèle PM", r"projet|project|client|contact|bootstrap|aspect|overview|meta\.yml|provider|entité|workspace|\.mmi-pm|pm\.config|cascade|modèle|stack"),
    ("Tests & qualité", r"\btest|qualit|lint|\bci\b|flaky|régression"),
]
AUTRE = "Autre"
ETATS_MANUELS = ("prévu", "en cours", "en pause", "écarté", "livré")
ACTIFS = {"en_cours", "a_tester_dev", "a_tester_demandeur", "a_tester_verifier", "a_tester_preprod", "a_mep", "en_mep", "a_corriger"}
PREVUS = {"a_faire", "a_etudier_chiffrer", "etude_chiffrage_en_cours", "etude_chiffrage_a_valider"}
FM_RE = re.compile(r"\A---\n(.*?)\n---", re.S)


def etat_de(fm):
    st = fm.get("status")
    if st == "ferme":
        return "livré" if (fm.get("close_reason") in (None, "resolu")) else f"écarté ({fm.get('close_reason')})"
    if st in ACTIFS:
        return "en cours"
    if st in PREVUS:
        return "prévu"
    if st == "en_pause":
        return "en pause"
    return None   # nouveau (non trié) ou inconnu : hors registre


def date_de(fm):
    if fm.get("status") == "ferme":
        for h in reversed(fm.get("status_history") or []):
            if isinstance(h, dict) and h.get("status") == "ferme" and h.get("at"):
                return str(h["at"])[:10]
    return str(fm.get("updated") or fm.get("created") or "")[:10]


def lire_tickets(tasks_dir: Path):
    out = []
    for f in sorted(tasks_dir.glob("RM*.md")):
        if not is_task_sheet(f):
            continue
        m = FM_RE.match(f.read_text(encoding="utf-8"))
        if not m:
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not fm.get("redmine_id"):
            continue
        out.append(fm)
    out.sort(key=lambda fm: int(fm["redmine_id"]))
    return out


def domaine_de(titre, domaines):
    for d in domaines:
        if re.search(d["mots"], titre, re.I):
            return d["nom"]
    return AUTRE


def libelle_de(fm):
    return " ".join(str(fm.get("title") or "").split())


def registre_vide(prefix, projet):
    return {"prefix": prefix, "projet": projet,
            "domaines": [{"nom": n, "mots": rx} for n, rx in DEFAULT_DOMAINES],
            "jalons": [],
            "entrees": []}


def sync(reg, tickets):
    """Ajoute les tickets absents, met à jour état/date/libellé/domaine (sauf `manuel: true`). Retourne (ajoutés, modifiés)."""
    par_rm = {int(e["rm"]): e for e in reg["entrees"] if e.get("rm")}
    couverts = {int(x) for e in reg["entrees"] for x in (e.get("tickets") or [])}
    nxt = 1 + max([int(e["id"][1:]) for e in reg["entrees"]] or [0])
    ajout, modif = [], []
    for fm in tickets:
        rm = int(fm["redmine_id"]); etat = etat_de(fm)
        e = par_rm.get(rm)
        if e is None:
            if etat is None or rm in couverts:
                continue
            e = {"id": f"F{nxt:03d}", "rm": rm, "libelle": libelle_de(fm), "domaine": domaine_de(libelle_de(fm), reg["domaines"]),
                 "type": fm.get("type") or "feature", "etat": etat, "date": date_de(fm)}
            if fm.get("parent_task"):
                e["parent"] = int(fm["parent_task"])
            reg["entrees"].append(e); par_rm[rm] = e; nxt += 1; ajout.append(e)
            continue
        avant = dict(e)
        if etat is not None and not e.get("manuel"):     # RM3064 : une entrée figée garde l'état posé à la main
            e["etat"] = etat
        e["date"] = date_de(fm); e["type"] = fm.get("type") or e.get("type")
        if not e.get("manuel"):
            e["libelle"] = libelle_de(fm); e["domaine"] = domaine_de(e["libelle"], reg["domaines"])
        if e != avant:
            modif.append(e)
    return ajout, modif


def dump(reg):
    head = ("# FONCTIONNALITÉS du projet — registre GÉNÉRÉ/ENTRETENU par pm-cdc-features (RM3043).\n"
            "# Une entrée par ticket (hors `nouveau`) ; `id` F001… STABLE, jamais réattribué ; `etat` dérivé du statut du ticket\n"
            "# (livré · en cours · prévu · en pause · écarté). `domaine` posé par les mots-clés de `domaines` (premier qui matche) :\n"
            "# pour corriger à la main, éditer `libelle`/`domaine` ET poser `manuel: true`, sinon `--sync` les réécrit.\n"
            "# Le chapitre `cdc-features.md` est GÉNÉRÉ d'ici (`--build`) : ne pas l'éditer.\n")
    return head + yaml.safe_dump(reg, allow_unicode=True, sort_keys=False, width=160)


def reg_dir_name(reg):
    """`cdc` (générique, D008) ou `cdc-<prefix>` (ancienne forme)."""
    return "cdc" if reg.get("prefix") in (None, "", "cdc") else f"cdc-{reg['prefix']}"


def chapter_name(reg):
    return "cdc-features.md" if reg_dir_name(reg) == "cdc" else f"cdc-{reg['prefix']}-10-fonctionnalites.md"


def compose(reg, chap: Path) -> str:
    """Le chapitre : partie générée + bloc `think-merge` existant conservé (RM3053)."""
    block = ""
    if chap.is_file():
        old = chap.read_text(encoding="utf-8")
        if pm_think.MERGE_BEGIN in old and pm_think.MERGE_END in old:
            block = old[old.index(pm_think.MERGE_BEGIN): old.index(pm_think.MERGE_END) + len(pm_think.MERGE_END)]
    return build(reg) + ("\n## Détail par ticket (depuis les `.think.md`)\n\n" + block + "\n" if block else "")


def build(reg):
    ents = reg["entrees"]
    declares = [d["nom"] for d in reg["domaines"]]
    ordre = declares + sorted({e.get("domaine") for e in ents if e.get("domaine") and e.get("domaine") not in declares and e.get("domaine") != AUTRE}) + [AUTRE]
    par_dom = {}
    for e in ents:
        par_dom.setdefault(e.get("domaine") or AUTRE, []).append(e)
    cnt = {}
    for e in ents:
        k = "écarté" if e["etat"].startswith("écarté") else e["etat"]; cnt[k] = cnt.get(k, 0) + 1
    rd = reg_dir_name(reg)
    L = [f"# Fonctionnalités du projet `{reg['projet']}`", "",
         f"> **Généré** par `pm-cdc-features --build` depuis [`{rd}/fonctionnalites.yml`]({rd}/fonctionnalites.yml) — ne pas éditer ici.",
         "> Une ligne par ticket ; identifiant `F` stable ; l'état suit le statut du ticket. Corrections (bugfix) à part, par domaine.", "",
         "| État | Nombre |", "|---|---|"]
    for k in ("livré", "en cours", "prévu", "en pause", "écarté"):
        if k in cnt:
            L.append(f"| {k} | {cnt[k]} |")
    L.append("")
    for dom in ordre:
        rows = par_dom.get(dom)
        if not rows:
            continue
        feats = [e for e in rows if e.get("type") != "bugfix"]; bugs = [e for e in rows if e.get("type") == "bugfix"]
        ver = lambda e: str(e.get("version") or (f"V{e['jalon']}" if e.get("jalon") is not None else ""))
        jal = any(ver(e) for e in ents)
        L += [f"## {dom} ({len(rows)})", ""]
        if feats:
            L += ["| # | Fonctionnalité | Ticket(s) | Type | " + ("Version | " if jal else "") + "État | Date |", "|---|---|---|---|" + ("---|" if jal else "") + "---|---|"]
            for e in feats:
                lib = e["libelle"].replace("|", "/")
                if e.get("parent"):
                    lib += f" *(sous-tâche de RM{e['parent']})*"
                tk = ", ".join(f"RM{x}" for x in ([e["rm"]] if e.get("rm") else []) + [x for x in (e.get("tickets") or []) if x != e.get("rm")]) or "—"
                jc = (f" {ver(e)} |" if ver(e) else " — |") if jal else ""
                L.append(f"| {e['id']} | {lib} | {tk} | {e.get('type') or ''} |{jc} {e['etat']} | {e.get('date') or ''} |")
            L.append("")
        if bugs:
            L += [f"**Corrections ({len(bugs)})** :", ""]
            for e in bugs:
                L.append(f"- {e['id']} · RM{e.get('rm') or '?'} · {e['libelle'].replace('|', '/')} — {e['etat']} {e.get('date') or ''}")
            L.append("")
    return "\n".join(L).rstrip() + "\n"


def resoudre(args):
    if args.docs_dir and args.tasks_dir:
        return Path(args.docs_dir), Path(args.tasks_dir), args.project or "?"
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    ref = args.project
    if not ref:
        mm = Path.cwd() / ".mmi-pm"
        if mm.exists():
            p = mm.resolve(); ref = f"{p.parent.parent.name}/{p.name}"
    if not ref or "/" not in ref:
        sys.exit("--project <client>/<projet> requis (ou un workspace avec .mmi-pm)")
    c, p = ref.split("/", 1)
    return cfg.path("docs_dir", entity=c, project=p), cfg.path("tasks_dir", entity=c, project=p), ref


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project"); ap.add_argument("--docs-dir"); ap.add_argument("--tasks-dir")
    ap.add_argument("--init", action="store_true"); ap.add_argument("--prefix")
    ap.add_argument("--sync", action="store_true"); ap.add_argument("--build", action="store_true"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--no-sync", action="store_true", help="avec --init : registre vide (curé à la main)")
    ap.add_argument("--assign-version", metavar="V", help="pose cette version sur les entrées qui n'en ont pas (filtre --etat)")
    ap.add_argument("--set-etat", nargs=2, metavar=("ID", "ETAT"), help="pose l'état d'une entrée (prévu · en cours · en pause · écarté · livré) et la fige en manuel (RM3064)")
    ap.add_argument("--etat", help="avec --assign-version : seulement les entrées de cet état (ex. livré)")
    a = ap.parse_args()
    docs, tasks, projet = resoudre(a)
    regs = sorted(docs.glob("cdc/fonctionnalites.yml")) + sorted(docs.glob("cdc-*/fonctionnalites.yml"))
    if a.init:
        prefix = a.prefix or "cdc"
        reg_path = docs / ("cdc" if prefix == "cdc" else f"cdc-{prefix}") / "fonctionnalites.yml"
        if reg_path.exists():
            sys.exit(f"registre déjà présent : {reg_path}")
        reg = registre_vide(prefix, projet)
    elif regs:
        reg_path = regs[0]; reg = yaml.safe_load(reg_path.read_text(encoding="utf-8")) or {}
        reg.setdefault("entrees", []); reg.setdefault("domaines", [])
    else:
        sys.exit(f"aucun registre docs/cdc-*/fonctionnalites.yml sous {docs} — `--init --prefix <p>`")
    if reg_path.parent.name == "cdc":
        reg["prefix"] = "cdc"
    chap = docs / chapter_name(reg)
    if a.check:
        avant = dump(reg); sync(reg, lire_tickets(tasks)); apres = dump(reg)   # un registre curé (--no-sync) reste stable : ses tickets sont couverts
        ok_reg = avant == apres; ok_chap = chap.exists() and chap.read_text(encoding="utf-8") == compose(reg, chap)
        print(f"{'✓' if ok_reg else '✗'} registre à jour ({reg_path.name}, {len(reg['entrees'])} entrées)")
        print(f"{'✓' if ok_chap else '✗'} chapitre à jour ({chap.name})")
        if not (ok_reg and ok_chap):
            print("  → pm-cdc-features --sync --build"); sys.exit(1)
        return
    if a.set_etat:
        fid, etat = a.set_etat
        if etat not in ETATS_MANUELS:
            sys.exit(f"état inconnu « {etat} » — admis : {', '.join(ETATS_MANUELS)}")
        e = next((x for x in reg["entrees"] if x.get("id") == fid), None)
        if not e:
            sys.exit(f"entrée {fid} introuvable dans {reg_path}")
        e["etat"] = etat; e["manuel"] = True
        reg_path.write_text(dump(reg), encoding="utf-8"); print(f"✓ {fid} → {etat} (entrée figée : manuel)")
        if not a.build:
            return
    if a.assign_version:
        n = 0
        for e in reg["entrees"]:
            if not e.get("version") and e.get("jalon") is None and (not a.etat or e.get("etat") == a.etat):
                e["version"] = a.assign_version; n += 1
        reg_path.write_text(dump(reg), encoding="utf-8"); print(f"✓ version {a.assign_version} posée sur {n} entrée(s)" + (f" ({a.etat})" if a.etat else ""))
        if not a.build:
            return
    if a.init or a.sync:
        ajout, modif = ([], []) if (a.init and a.no_sync) else sync(reg, lire_tickets(tasks))
        reg_path.parent.mkdir(parents=True, exist_ok=True); reg_path.write_text(dump(reg), encoding="utf-8")
        print(f"✓ registre {reg_path.relative_to(docs)} : +{len(ajout)} ajoutée(s), {len(modif)} mise(s) à jour, {len(reg['entrees'])} au total")
    if a.build:
        chap.write_text(compose(reg, chap), encoding="utf-8")
        print(f"✓ chapitre {chap.name} régénéré ({len(reg['entrees'])} lignes)")
    if not (a.init or a.sync or a.build):
        ap.print_help()


if __name__ == "__main__":
    main()
