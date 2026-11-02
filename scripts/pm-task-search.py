#!/usr/bin/env python3
"""pm-task-search — recherche d'ANTÉRIORITÉ : ce sujet a-t-il déjà un ticket ? (RM3130)

À lancer **avant** de créer un ticket ou de consigner une demande. Jusqu'ici rien ne le
permettait : `pm-task-list` filtre par statut / type / priorité / tag, jamais par texte,
et le seul moyen était un `grep` jetable — que personne ne relance sur les CORPS.
Conséquence : des doublons se créent, et des demandes déjà ticketées se reconsignent.

Cherche dans le **titre**, le **corps** et les **`.think.md`** (une demande peut n'exister
que sous forme de F ou de N), tous clients/projets, **fermés inclus par défaut** : un
ticket clos est une antériorité qui compte — souvent la meilleure réponse.

**La sortie est courte, et c'est le point dur.** Cet outil est fait pour être appelé par
un agent : un `grep` brut coûte des milliers de tokens et finit contourné. Ici le script
lit, le modèle ne voit qu'un condensé — une ligne et un extrait par résultat, plafonnés.

Usage :
    pm-task-search.py <termes…> [--limit N] [--project E/P] [--type T] [--open-only]
                      [--json] [--full]

    --limit N       nombre de résultats (défaut 8 ; 0 = tout)
    --project E/P   restreint à un projet
    --type T        restreint à un type de tâche (répétable)
    --open-only     exclut les tickets fermés (par défaut ils sont INCLUS)
    --no-think      ignore les .think.md
    --full          extraits plus longs (le défaut reste court : c'est l'intérêt)
    --json          sortie machine

Classement par pertinence, jamais par date : un terme dans le TITRE pèse bien plus que
dans le corps, et un document qui porte TOUS les termes passe devant.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_think import iter_sheets, think_path

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TITLE_RE = re.compile(r"^title:\s*(.+)$", re.M)
STATUS_RE = re.compile(r"^status:\s*(\S+)", re.M)
RMID_RE = re.compile(r"^redmine_id:\s*(\d+)", re.M)
TYPE_RE = re.compile(r"^type:\s*(\S+)", re.M)

W_TITLE = 10          # un terme dans le titre vaut cinq fois le même terme dans le corps
W_BODY = 2
BODY_CAP = 3          # occurrences comptées par terme : un long document ne gagne pas en radotant
BONUS_ALL = 2.0       # tous les termes présents → le document parle bien DU sujet
BONUS_OPEN = 1.05     # à pertinence égale, un ticket vivant avant un ticket clos


def fold(s):
    """Minuscule sans accents — « déploiement » et « deploiement » doivent se trouver."""
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tokenize(query):
    """Termes signifiants d'une requête. Les mots d'un caractère et la ponctuation sautent."""
    if isinstance(query, (list, tuple)):
        query = " ".join(str(q) for q in query)
    return [t for t in re.split(r"[^\w]+", fold(query)) if len(t) > 1]


_RX_CACHE = {}


def term_rx(t):
    """Regex d'un terme, ancrée sur un DÉBUT DE MOT.

    Sans cette ancre, « rag » se trouve dans « chiff**rag**e » et « f**rag**ment » : la
    recherche d'antériorité rendait des tickets sans aucun rapport, ce qui est le plus
    sûr moyen de faire ignorer l'outil. La fin reste libre — « deploi » doit continuer de
    trouver « déploiement ».
    """
    rx = _RX_CACHE.get(t)
    if rx is None:
        rx = _RX_CACHE[t] = re.compile(r"\b" + re.escape(t))
    return rx


def count_terms(text, terms):
    """{terme: nombre d'occurrences en début de mot} dans `text` (déjà replié)."""
    return {t: len(term_rx(t).findall(text)) for t in terms}


def score(title, body, terms, closed=False):
    """Pertinence d'un document. Pure — c'est elle que les tests verrouillent.

    0 quand AUCUN terme n'apparaît : sans cela une recherche sans réponse rendrait le
    corpus entier trié au hasard, ce qui est pire que rien.
    """
    if not terms:
        return 0.0
    ft, fb = fold(title), fold(body)
    in_title = count_terms(ft, terms)
    in_body = count_terms(fb, terms)
    hits = sum(1 for t in terms if in_title[t] or in_body[t])
    if not hits:
        return 0.0
    s = sum(min(in_title[t], BODY_CAP) * W_TITLE + min(in_body[t], BODY_CAP) * W_BODY
            for t in terms)
    if hits == len(terms):
        s *= BONUS_ALL
    if not closed:
        s *= BONUS_OPEN
    return float(s)


def snippet(text, terms, width=120):
    """Extrait d'une ligne autour du premier terme trouvé. Jamais le début du document
    par défaut : ce qu'on veut lire, c'est le passage qui a déclenché le résultat."""
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if not flat:
        return ""
    low = fold(flat)
    found = [m.start() for t in terms for m in [term_rx(t).search(low)] if m]
    pos = min(found, default=-1)
    if pos < 0:
        return flat[:width] + ("…" if len(flat) > width else "")
    start = max(0, pos - width // 3)
    end = min(len(flat), start + width)
    return ("…" if start else "") + flat[start:end].strip() + ("…" if end < len(flat) else "")


def parse_task(path):
    """(rm_id, statut, type, titre, corps) d'une fiche, ou None si ce n'en est pas une."""
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = FM_RE.match(txt)
    if not m:
        return None
    fm, body = m.group(1), txt[m.end():]
    rm, title = RMID_RE.search(fm), TITLE_RE.search(fm)
    if not (rm and title):
        return None
    st = STATUS_RE.search(fm)
    ty = TYPE_RE.search(fm)
    return (int(rm.group(1)), st.group(1) if st else "?", ty.group(1) if ty else "",
            title.group(1).strip().strip("'\""), body)


def iter_tasks(cfg, project=None, with_think=True):
    """(ent, proj, path, parsed) sur les fiches — le journal est ignoré (des événements,
    pas une demande) ; la réflexion est RATTACHÉE à sa fiche, jamais comptée à part."""
    ent_f = proj_f = None
    if project:
        ent_f, _, proj_f = str(project).partition("/")
    for ent, proj, _ in cfg.iter_projects():
        if ent_f and (ent != ent_f or (proj_f and proj != proj_f)):
            continue
        d = cfg.path("tasks_dir", entity=ent, project=proj)
        if not d.is_dir():
            continue
        # `iter_sheets` est la SEULE façon d'énumérer des fiches (RM3085) : refiltrer à
        # la main ici oublierait un suffixe le jour où il s'en ajoute un — une garde de
        # `test_pm_think` interdit d'ailleurs de le refaire.
        for f in iter_sheets(d):
            parsed = parse_task(f)
            if not parsed:
                continue
            rm, st, ty, title, body = parsed
            if with_think:
                think = think_path(f)
                if think.is_file():
                    try:
                        body += "\n" + think.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        pass
            yield ent, proj, f, (rm, st, ty, title, body)


# ── RM3248 : antériorité à la CRÉATION ──────────────────────────────────────
# Le tripwire #19 demandait à l'agent de chercher avant de créer ; RM3247 a été créé sans,
# juste après une compaction. Une règle qu'il faut se rappeler d'appliquer au moment où
# l'on crée est oubliée au moment où l'on crée : `pm-task-add` appelle donc ce moteur
# lui-même. Le critère vit ICI, une fois (même logique que D023) ; pm-task-add l'importe.

#: Mots vides : deux titres partagent toujours « de », « la », « pour »… Les garder ferait
#: passer n'importe quelle paire de titres pour voisine.
STOPWORDS = frozenset("""le la les de des du un une et ou en au aux pour par sur sous dans
avec sans qui que quoi ne pas plus ce cet cette ces son sa ses leur leurs est sont etre
faire fait il elle on se si mais car donc""".split())

#: Part des termes du NOUVEAU titre retrouvés dans un titre existant, au-delà de laquelle
#: la correspondance est « forte ». Calibré sur l'arbre réel (cf. test) : assez haut pour ne
#: pas arrêter deux tickets qui partagent un sujet, assez bas pour qu'un titre reformulé
#: soit reconnu.
SEUIL_FORT = 0.8
#: En dessous, un titre est trop court pour conclure : « Bug panier » recoupe tout.
MIN_TERMES_FORT = 3


_RX_DATE = re.compile(r"\b(\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?|\d{4}-\d{2}-\d{2})\b")


def signifiants(titre):
    """Termes signifiants d'un titre, dédoublonnés, sans mots vides ni NOMBRES. Pure.

    Les nombres sautent : une date (« 02/06/2026 ») se découpe en trois « termes » que
    toutes les réunions d'un même mois partagent, et qui gonflaient le recouvrement."""
    return [t for t in dict.fromkeys(tokenize(titre)) if t not in STOPWORDS and not t.isdigit()]


def dates(titre):
    """Dates écrites dans un titre, normalisées en chaîne. Pure."""
    return {re.sub(r"[.-]", "/", d) for d in _RX_DATE.findall(str(titre or ""))}


def title_overlap(nouveau, existant):
    """Part (0..1) des termes signifiants du NOUVEAU titre présents, en début de mot, dans
    l'existant. Asymétrique à dessein : un titre court entièrement contenu dans un titre
    long est bien une antériorité ; l'inverse, rarement. Pure."""
    termes = signifiants(nouveau)
    if not termes:
        return 0.0
    fe = fold(existant)
    return sum(1 for t in termes if term_rx(t).search(fe)) / len(termes)


def prior_art(titre, tickets, project=None, seuil=SEUIL_FORT, limit=5):
    """Antériorités d'un titre qu'on s'apprête à créer. Pure.

    `tickets` : itérable de dicts {rm_id, status, title, project}.
    Rend (fortes, voisines), chacune triée par recouvrement décroissant :
      · fortes   : MÊME projet ET recouvrement ≥ seuil, sur un titre assez long pour
                   conclure — c'est ce qui justifie d'arrêter la création ;
      · voisines : tout le reste qui recoupe au moins la moitié des termes, tous projets —
                   affiché, jamais bloquant. Hors projet, un titre voisin (« mettre à jour
                   PrestaShop » chez deux clients) est rarement un doublon : bloquer
                   là-dessus ferait contourner la garde.
    """
    assez_long = len(signifiants(titre)) >= MIN_TERMES_FORT
    fortes, voisines = [], []
    d_nouveau = dates(titre)
    for t in tickets:
        r = title_overlap(titre, t.get("title") or "")
        if r <= 0:
            continue
        # Deux titres datés à des dates différentes sont deux OCCURRENCES (réunion du 2 juin,
        # réunion du 9 juin), pas un doublon. Calibration : c'était la première source de
        # faux positifs sur l'arbre réel.
        d_autre = dates(t.get("title"))
        if d_nouveau and d_autre and d_nouveau != d_autre:
            continue
        item = dict(t, overlap=round(r, 2))
        if assez_long and r >= seuil and (project is None or t.get("project") == project):
            fortes.append(item)
        elif r >= 0.5:
            voisines.append(item)
    cle = lambda x: (-x["overlap"], -int(x.get("rm_id") or 0))  # noqa: E731
    return sorted(fortes, key=cle), sorted(voisines, key=cle)[:limit]


def prior_art_cfg(cfg, titre, project=None, **kw):
    """`prior_art` sur l'arbre de tickets réel (titres seuls : c'est la création d'un
    DOUBLON qu'on arrête, pas la mention d'un sujet dans un corps)."""
    tickets = ({"rm_id": rm, "status": st, "title": title, "project": f"{ent}/{proj}"}
               for ent, proj, _p, (rm, st, _ty, title, _b) in iter_tasks(cfg, None, False))
    return prior_art(titre, tickets, project=project, **kw)


def search(cfg, query, limit=8, project=None, types=(), open_only=False,
           with_think=True, width=120):
    """Résultats classés. `limit=0` = tout."""
    terms = tokenize(query)
    out = []
    for ent, proj, path, (rm, st, ty, title, body) in iter_tasks(cfg, project, with_think):
        if open_only and st == "ferme":
            continue
        if types and ty not in types:
            continue
        sc = score(title, body, terms, closed=(st == "ferme"))
        if sc <= 0:
            continue
        where = "titre" if any(term_rx(t).search(fold(title)) for t in terms) else "corps"
        out.append({"rm_id": rm, "status": st, "type": ty, "project": f"{ent}/{proj}",
                    "title": title, "score": round(sc, 1), "match": where,
                    "snippet": snippet(body, terms, width),
                    "path": str(path)})
    out.sort(key=lambda r: (-r["score"], -r["rm_id"]))
    return out if not limit else out[:limit]


def main():
    ap = argparse.ArgumentParser(description="Recherche d'antériorité dans les tickets PM.")
    ap.add_argument("terms", nargs="+")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--project")
    ap.add_argument("--type", action="append", default=[], dest="types")
    ap.add_argument("--open-only", action="store_true")
    ap.add_argument("--no-think", action="store_true")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()
    res = search(cfg, args.terms, limit=args.limit, project=args.project,
                 types=tuple(args.types), open_only=args.open_only,
                 with_think=not args.no_think, width=240 if args.full else 120)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if not res:
        print(f"aucune antériorité pour « {' '.join(args.terms)} » — "
              f"le sujet paraît neuf (fermés inclus)")
        return
    print(f"{len(res)} antériorité(s) pour « {' '.join(args.terms)} » "
          f"— vérifier avant de créer un ticket :\n")
    for r in res:
        print(f"RM{r['rm_id']} [{r['status']}] {r['project']} — {r['title']}")
        print(f"    ({r['match']}) {r['snippet']}")


if __name__ == "__main__":
    main()
