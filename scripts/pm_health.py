"""pm_health — santé du SYSTÈME PM : données, configuration Redmine, normes (RM3369).

Pendant de la santé du **poste** (`op_env_status` de karl-agent, RM2458/RM2722) :
même vocabulaire (familles → lignes `level`/`label`/`detail`/`fix`), même promesse
— chaque ligne en défaut porte la commande exacte qui la répare — mais l'objet
surveillé n'est plus la machine, c'est le PM lui-même.

Pourquoi ce module existe (RM3366, RM3367) : les champs personnalisés Redmine
n'étaient activés que projet par projet. L'API acceptait les écritures et les
jetait. RM3224 a porté 2 459 caractères d'étude invisibles côté Redmine pendant
des semaines, `redmine-config-check` répondant « aucun drift ». Une perte
silencieuse ne se découvre que si quelque chose la regarde tous les jours.

Ce que le module NE fait pas : il ne répare rien et n'ouvre aucun ticket. Un
invariant rouge est un état, pas une action (acté RM3177) — il se montre.

Découpage : les fonctions **pures** (agrégation, comptage, tri, péremption,
comparaison de champs) sont au-dessus, testées sans réseau ni disque par
`test_pm_health.py` ; les collecteurs d'I/O sont en dessous, chacun isolé — une
famille qui casse ne fait jamais échouer le rapport.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent

LEVELS = ("ok", "info", "warn", "error")
LEVEL_RANK = {"ok": 0, "info": 1, "warn": 2, "error": 3}

# Familles dont une anomalie doit se VOIR sans ouvrir le panneau. Le badge ne
# compte que ce qui demande un geste : un compteur qui affiche un chiffre tous
# les jours ne se regarde plus (même raison qui tient « Repos » et « PM » hors
# de `ENV_ALERT_FAMILIES` côté poste).
ALERT_FAMILIES = ("Champs Redmine", "Miroirs de champs", "Cohérence des projets", "Normes")

# Au-delà, le rapport lui-même est un souci : personne ne regarde plus.
STALE_AFTER = 6 * 3600          # warn — le rapport a vieilli
DEAD_AFTER = 24 * 3600          # error — plus personne ne le calcule


def chk(label, level, detail="", fix="", section=""):
    """Une ligne de rapport. Même forme que `_chk` de karl-agent : les deux
    rapports se lisent avec la même vue côté cockpit."""
    c = {"label": label, "level": level, "detail": detail, "fix": fix}
    if section:
        c["section"] = section
    return c


# ─────────────────────────── pur : agrégation ───────────────────────────────

def health_summary(groups):
    """Compte par niveau + niveau global (le pire), sur toutes les lignes."""
    counts = {lv: 0 for lv in LEVELS}
    worst = "ok"
    for g in groups or []:
        for c in g.get("checks", []):
            lv = c.get("level", "info")
            if lv not in counts:
                lv = "info"
            counts[lv] += 1
            if LEVEL_RANK[lv] > LEVEL_RANK[worst]:
                worst = lv
    return {"counts": counts, "worst": worst}


def health_alerts(groups, families=ALERT_FAMILIES):
    """Les lignes en défaut des familles surveillées, à plat.

    `major` ne compte que les `error` : c'est le nombre que porte le badge. Les
    `warn` voyagent avec (la page les montre) mais ne gonflent pas le compteur,
    sinon il perd son sens. Les erreurs passent devant : quand il y en a
    plusieurs, la première ligne du survol doit être la plus grave.
    """
    allowed = None if families is None else set(families)
    items = []
    for g in groups or []:
        fam = g.get("name") or ""
        if allowed is not None and fam not in allowed:
            continue
        for c in g.get("checks", []):
            if c.get("level") in ("warn", "error"):
                items.append({"family": fam, "label": c.get("label") or "",
                              "level": c.get("level"), "detail": c.get("detail") or "",
                              "fix": c.get("fix") or ""})
    items.sort(key=lambda i: (0 if i["level"] == "error" else 1, i["family"], i["label"]))
    major = sum(1 for i in items if i["level"] == "error")
    return {"items": items, "count": len(items), "major": major,
            "worst": "error" if major else ("warn" if items else "ok")}


def report_age(generated_at, now=None, stale_after=STALE_AFTER, dead_after=DEAD_AFTER):
    """La ligne qui dit si le rapport est encore digne de foi.

    Un rapport absent ou trop vieux est un souci MAJEUR : un badge à zéro parce
    que plus rien ne calcule ment plus qu'il n'informe.
    """
    now = time.time() if now is None else now
    if not generated_at:
        return chk("fraîcheur du rapport", "error", "aucun rapport de santé PM n'a été produit",
                   "mmi-pm health --refresh (ou scripts/pm-health-report.py)")
    age = max(0.0, now - float(generated_at))
    human = _human_age(age)
    if age >= dead_after:
        return chk("fraîcheur du rapport", "error", f"dernier calcul il y a {human}",
                   "mmi-pm health --refresh — puis vérifier le timer qui devait le rejouer")
    if age >= stale_after:
        return chk("fraîcheur du rapport", "warn", f"dernier calcul il y a {human}",
                   "mmi-pm health --refresh")
    return chk("fraîcheur du rapport", "ok", f"calculé il y a {human}")


def _human_age(seconds):
    s = int(max(0, seconds))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{s // 60} min"
    if s < 172800:
        return f"{s // 3600} h"
    return f"{s // 86400} j"


def marker_lines(text, mark):
    """Les lignes d'une sortie de doctor portant ce marqueur, nettoyées.

    Les deux doctors existants (`pm-doctor`, `pm-norms-doctor`) parlent en texte
    avec ✗ / ⚠ en tête de ligne ; on les consomme tels quels plutôt que de les
    réécrire — c'est leur sortie qui fait foi, pas une copie.
    """
    out = []
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith(mark):
            rest = s[len(mark):].strip()
            if rest:
                out.append(rest)
    return out


# ──────────────────── pur : champs Redmine et miroirs ───────────────────────

def missing_fields(available_ids, expected):
    """Les champs attendus qu'un projet n'a pas. `expected` : {id: nom}."""
    have = {int(i) for i in (available_ids or [])}
    return [name for cid, name in sorted(expected.items(), key=lambda kv: kv[1])
            if int(cid) not in have]


def project_cf_check(label, available_ids, expected, section=""):
    """Une ligne par projet : ce qui manque, et par quoi on le rattrape.

    Un champ manquant n'est pas cosmétique : tout ce que l'outillage y écrira
    sera accepté par l'API puis jeté. D'où le niveau `error`.
    """
    miss = missing_fields(available_ids, expected)
    if not miss:
        return chk(label, "ok", f"{len(expected)} champ(s) PM disponibles", section=section)
    shown = ", ".join(miss[:6]) + (f" … (+{len(miss) - 6})" if len(miss) > 6 else "")
    return chk(label, "error", f"{len(miss)} champ(s) non activés : {shown}",
               "Administration Redmine › Champs personnalisés › cocher le projet, "
               "ou PUT /projects/<id>.json avec issue_custom_field_ids",
               section=section)


def lost_mirror_check(entries):
    """Les contenus locaux qui ne PEUVENT pas exister côté Redmine.

    `entries` : [{task, project, field, chars}] — une entrée par miroir local non
    vide dont le champ n'est pas activé sur le projet du ticket. C'est le cas
    RM3224 exactement : du travail fait, stocké, et invisible pour quiconque ne
    lit pas le dépôt PM.
    """
    items = list(entries or [])
    if not items:
        return chk("contenus perdus", "ok", "aucun miroir local sans champ côté Redmine")
    chars = sum(int(e.get("chars") or 0) for e in items)
    tasks = sorted({str(e.get("task") or "?") for e in items})
    shown = ", ".join(tasks[:6]) + (f" … (+{len(tasks) - 6})" if len(tasks) > 6 else "")
    return chk("contenus perdus", "error",
               f"{len(items)} miroir(s) sur {len(tasks)} ticket(s) ({chars} caractères) "
               f"sans champ activé : {shown}",
               "activer les champs (famille « Champs Redmine »), puis "
               "pm-task-cf-resync.py --project <client/projet>")


def dig(data, path):
    """Valeur d'un chemin pointé dans un frontmatter (`git.branch`), ou None."""
    cur = data
    for part in (path or "").split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def mirror_is_filled(value):
    """Un miroir compte comme rempli s'il porte du contenu — pas une coquille.

    Les faux positifs coûtent la crédibilité du badge : `null`, `[]`, `""` et
    les listes de chaînes vides ne sont pas du contenu perdu.
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(mirror_is_filled(v) for v in value)
    if isinstance(value, dict):
        return any(mirror_is_filled(v) for v in value.values())
    return False


def mirror_chars(value):
    """Taille du contenu d'un miroir, en caractères — ce qu'on perdrait."""
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, (list, tuple)):
        return sum(mirror_chars(v) for v in value)
    if isinstance(value, dict):
        return sum(mirror_chars(v) for v in value.values())
    return 0


# Les miroirs dont la perte se paie cher : du contenu rédigé, pas un booléen.
# (nom du CF Redmine, chemin dans le frontmatter)
MIRROR_FIELDS = (
    ("Critères d'acceptation", "acceptance"),
    ("Actions au déploiement", "deploy_actions"),
    ("GIT Branche", "git.branch"),
    ("GIT PR", "git.mr_url"),
    ("Environnement de test", "target_env"),
    ("Réf ticket externe", "external_ref"),
)


# ────────────────────────────── I/O : familles ──────────────────────────────

def expected_issue_cfs(reference_path=None):
    """{id: nom} des champs d'ISSUE que le PM attend, d'après redmine.reference.yml.

    La référence fait foi : elle est déjà le contrat entre l'outillage et
    l'instance. Y lire évite une seconde liste qui divergerait.
    """
    import yaml
    path = Path(reference_path or (REPO_ROOT / "redmine.reference.yml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = {}
    for cid, spec in (data.get("custom_fields") or {}).items():
        if isinstance(spec, dict) and spec.get("type") == "issue" and spec.get("name"):
            out[int(cid)] = str(spec["name"])
    return out


_projects_cache = {"at": 0.0, "data": None}
_PROJECTS_TTL = 120.0


def redmine_projects_cfs(timeout=25, force=False):
    """{identifiant projet: (nom, [ids de CF d'issue activés])} pour l'instance.

    Une requête par page de 100 : `?include=issue_custom_fields` rend la liste
    déjà résolue, inutile d'interroger chaque projet.
    """
    now = time.time()
    if not force and _projects_cache["data"] is not None and now - _projects_cache["at"] < _PROJECTS_TTL:
        return _projects_cache["data"]
    sys.path.insert(0, str(SCRIPTS))
    import redmine_utils as ru
    url, key = ru.redmine_creds()
    base = url.rstrip("/")
    out, offset = {}, 0
    while True:
        st, body = ru.http_json(
            "GET", f"{base}/projects.json?include=issue_custom_fields&limit=100&offset={offset}",
            key, timeout=timeout)
        if st != 200:
            raise RuntimeError(f"API Redmine {st} sur /projects.json")
        projects = (body or {}).get("projects") or []
        for p in projects:
            ids = [c.get("id") for c in (p.get("issue_custom_fields") or []) if c.get("id")]
            out[str(p.get("identifier"))] = (str(p.get("name") or p.get("identifier")), ids)
        offset += len(projects)
        if not projects or offset >= int((body or {}).get("total_count") or 0):
            break
    _projects_cache.update({"at": now, "data": out})
    return out


def pm_projects():
    """[(entité, projet, chemin, identifiant Redmine)] des projets PM-trackés.

    Seuls ceux-là comptent : un projet Redmine sans dossier PM n'est pas un
    endroit où l'outillage écrit, et l'y signaler noierait le vrai signal.
    """
    sys.path.insert(0, str(SCRIPTS))
    from pm_paths import PMConfig
    cfg = PMConfig.load()
    out = []
    for ent, proj, path in cfg.iter_projects():
        if ent.startswith(".") or proj.startswith("."):
            continue        # entrées techniques (.mmi-pm, .mmi-pm-core) : pas des projets
        meta = cfg.project_meta(ent, proj) or {}
        rid = ((meta.get("redmine") or {}).get("project_id")) if isinstance(meta.get("redmine"), dict) else None
        out.append((ent, proj, path, str(rid) if rid else ""))
    return out


def family_redmine_cf():
    """Un champ PM non activé sur un projet PM-tracké = écritures jetées."""
    expected = expected_issue_cfs()
    by_ident = redmine_projects_cfs()
    checks = []
    unknown = []
    for ent, proj, _path, rid in sorted(pm_projects()):
        label = f"{ent}/{proj}"
        if not rid:
            unknown.append(label)
            continue
        if rid not in by_ident:
            checks.append(chk(label, "warn", f"projet Redmine « {rid} » introuvable",
                              "corriger redmine.project_id dans le meta.yml du projet"))
            continue
        name, ids = by_ident[rid]
        checks.append(project_cf_check(label, ids, expected))
    if unknown:
        checks.append(chk("projets sans identifiant Redmine", "info",
                          f"{len(unknown)} projet(s) : " + ", ".join(sorted(unknown)[:8]),
                          "renseigner redmine.project_id dans meta.yml si le projet est suivi"))
    return checks


def family_cf_mirrors():
    """Du contenu écrit localement que Redmine ne peut pas avoir reçu.

    Se calcule à partir des mêmes données que la famille précédente : aucun
    appel supplémentaire, et c'est l'incident RM3224 mot pour mot.
    """
    expected = expected_issue_cfs()
    by_name = {name: cid for cid, name in expected.items()}
    by_ident = redmine_projects_cfs()
    entries = []
    scanned = 0
    for ent, proj, path, rid in pm_projects():
        ids = set(by_ident.get(rid, ("", []))[1]) if rid else None
        if ids is None:
            continue
        tasks_dir = Path(path) / "tasks"
        if not tasks_dir.is_dir():
            continue
        for tf in sorted(tasks_dir.glob("RM*.md")):
            if tf.name.endswith((".log.md", ".think.md", ".reporting.yml")):
                continue
            fm = _read_frontmatter(tf)
            if not fm:
                continue
            scanned += 1
            for cf_name, field in MIRROR_FIELDS:
                cid = by_name.get(cf_name)
                if not cid or cid in ids:
                    continue
                value = dig(fm, field)
                if mirror_is_filled(value):
                    m = re.search(r"RM(\d+)_", tf.name)
                    entries.append({"task": "RM" + (m.group(1) if m else "?"),
                                    "project": f"{ent}/{proj}", "field": cf_name,
                                    "chars": mirror_chars(value)})
    checks = [lost_mirror_check(entries)]
    checks.append(chk("tickets examinés", "info", f"{scanned} fiche(s) de tâche lues"))
    return checks


def _read_frontmatter(path):
    """Frontmatter YAML d'une fiche, ou {} — une fiche illisible n'arrête rien."""
    import yaml
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        return yaml.safe_load(text[3:end]) or {}
    except Exception:       # noqa: BLE001 — un YAML cassé se signale ailleurs
        return {}


def _run_doctor(script, args=(), timeout=180):
    """Joue un doctor existant et rend (code, sortie standard). Sa sortie fait foi.

    STDOUT seulement : les scripts PM écrivent leurs avertissements
    d'environnement sur stderr (conf mal placée, dépendance absente), et un
    « ⚠ » qui parle du poste n'est pas un défaut de la donnée PM — le compter
    ferait clignoter le badge sur un sujet qui n'est pas le sien.
    """
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(REPO_ROOT))
    except subprocess.TimeoutExpired:
        return 1, f"  ✗ {script} : pas de réponse en {timeout} s"
    return p.returncode, (p.stdout or "")


def _doctor_family(script, label, args=()):
    rc, out = _run_doctor(script, args)
    errors = marker_lines(out, "✗")
    warns = marker_lines(out, "⚠")
    checks = []
    for level, lines in (("error", errors), ("warn", warns)):
        for line in lines:
            head, _, rest = line.partition(" : ")
            checks.append(chk(head[:90], level, rest.strip() or line,
                              f"python3 scripts/{script}"))
    if not checks:
        checks.append(chk(label, "ok" if rc == 0 else "warn",
                          "aucun défaut signalé" if rc == 0
                          else f"le contrôle sort en échec (code {rc}) sans ligne identifiable",
                          "" if rc == 0 else f"python3 scripts/{script}"))
    return checks


def family_projects():
    """Cohérence des manifestes de projets (pm-doctor)."""
    return _doctor_family("pm-doctor.py", "cohérence des projets", ("--quiet",))


def family_norms():
    """Invariants de la structure NORMS (pm-norms-doctor)."""
    return _doctor_family("pm-norms-doctor.py", "invariants NORMS")


FAMILIES = [
    ("Champs Redmine", family_redmine_cf),
    ("Miroirs de champs", family_cf_mirrors),
    ("Cohérence des projets", family_projects),
    ("Normes", family_norms),
]


def build_report(only=None):
    """Le rapport complet. Une famille qui casse devient une ligne, pas une panne."""
    groups = []
    for name, fn in FAMILIES:
        if only is not None and name not in only:
            continue
        started = time.time()
        try:
            checks = fn()
        except Exception as exc:        # noqa: BLE001 — jamais de rapport perdu
            checks = [chk(name, "warn", f"contrôle en erreur ({exc.__class__.__name__}: {exc})",
                          "relancer scripts/pm-health-report.py --verbose")]
        groups.append({"name": name, "checks": checks,
                       "duration_ms": int((time.time() - started) * 1000)})
    report = {"generated_at": time.time(),
              "generated_label": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "groups": groups, "summary": health_summary(groups)}
    report["alerts"] = health_alerts(groups)
    return report


# ───────────────────────────── I/O : le fichier ─────────────────────────────

def report_path():
    """Où vit le dernier rapport. `PM_HEALTH_REPORT` pour les tests et le cockpit."""
    env = os.environ.get("PM_HEALTH_REPORT")
    if env:
        return Path(env)
    return REPO_ROOT / "var" / "pm-health.json"


def write_report(report, path=None):
    """Écrit le rapport de façon atomique : un lecteur ne voit jamais un demi-JSON."""
    p = Path(path or report_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def read_report(path=None):
    """Le dernier rapport, ou None s'il n'y en a pas (ou qu'il est illisible)."""
    p = Path(path or report_path())
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
