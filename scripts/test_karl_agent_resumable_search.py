#!/usr/bin/env python3
"""Tests RM2991 — chercher une session par mots-clés dans le panneau de reprise.

Ce qui est protégé ici, dans l'ordre d'importance :

  1. la recherche par DÉFAUT porte sur les métadonnées enregistrées par le PM —
     titre de session, tickets traités (numéro ET libellé), worklog (libellés,
     notes, prochaine étape, texte des demandes). C'est la demande : retrouver
     « la session où j'ai traité ça » sans balayer 400 Mo de transcripts ;
  2. `2703` et `RM2703` mordent tous les deux — les deux formes se tapent, et
     une recherche par sous-chaîne ne les relie pas d'elle-même ;
  3. le transcript n'est JAMAIS lu sans `deep=1` : c'est tout l'intérêt de
     l'opt-in, et une régression y serait invisible (mêmes résultats, en dix
     fois plus lent) — on le prouve donc par un compteur d'ouvertures ;
  4. « mots-clés » est un pluriel : tous les mots doivent être présents, sans
     être ni collés ni dans l'ordre — et le transcript COMPLÈTE les mots que les
     métadonnées n'ont pas, il ne recommence pas la recherche ;
  5. l'identifiant de session se cherche par PRÉFIXE, jamais en sous-chaîne
     libre : « 2392 » tombe au milieu de « ca239234-0fd9-… » et ramènerait une
     session au hasard ;
  6. le worklog SURVIT au transcript — la trace d'un travail dont la
     conversation a été purgée doit être nommée (sinon la recherche ment sur ce
     qui existe) mais tenue à part des reprenables (sinon le bouton ment) ;
  7. un motif à cheval sur deux blocs de lecture est trouvé quand même : la
     lecture par blocs est ce qui rend le scan tenable, le recouvrement est ce
     qui la rend correcte.

Unitaire (sans tmux, sans réseau) : stores claude / worklogs / fiches PM
fabriqués, index de sessions monkeypatchés.
Lancer : python3 scripts/test_karl_agent_resumable_search.py
"""
import importlib.util
import json
import pathlib
import re
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── Décor : quatre sessions, chacune trouvable par UNE seule voie ────────────
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm2991-"))
store = tmp / "projstore"
store.mkdir(parents=True)

S_TITLE = "aaaaaaaa-1111-2222-3333-444444444444"   # trouvable par son titre
S_TICK = "bbbbbbbb-1111-2222-3333-555555555555"    # par son ticket (n° ou sujet)
S_WLOG = "cccccccc-1111-2222-3333-666666666666"    # par son worklog
S_DEEP = "dddddddd-1111-2222-3333-777777777777"    # par son transcript SEUL

TRANSCRIPTS = {
    S_TITLE: '{"type":"custom-title","customTitle":"Refonte du cockpit"}',
    S_TICK: '{"type":"custom-title","customTitle":"Session sans indice"}',
    S_WLOG: '{"type":"custom-title","customTitle":"Autre session muette"}',
    S_DEEP: '{"type":"custom-title","customTitle":"Encore une muette"}',
}
for sid, line in TRANSCRIPTS.items():
    body = [line, '{"type":"user","cwd":"/tmp/hors-pm","message":{"content":"go"}}']
    if sid == S_DEEP:
        body.append('{"type":"user","message":{"content":"parle-moi du licorniau"}}')
    (store / f"{sid}.jsonl").write_text("\n".join(body) + "\n", encoding="utf-8")

ka.CLAUDE_STORES = [tmp]
# Stores tiers neutralisés : sans cela, les VRAIES sessions opencode / vibe de la
# machine entreraient dans le résultat et le test ne serait plus reproductible.
ka.OPENCODE_DB = tmp / "aucune-base-opencode.db"
ka.VIBE_SESSIONS = tmp / "aucun-dossier-vibe"
ka._list_sessions = lambda: []
ka._key_info = lambda rm_id: None
ka._pm_project_of_cwd = lambda cwd: (None, None)
ka._runs_by_session = lambda: {
    S_TICK: [{"rm_id": "2703", "n": 1, "client": "iprospective",
              "project": "pm-ai-agents", "session_id": S_TICK, "_file": "x"}],
}

# Fiches PM : l'index rm_id → titre, que la recherche interroge par le SUJET.
tasks = tmp / "clients" / "iprospective" / "projects" / "pm-ai-agents" / "tasks"
tasks.mkdir(parents=True)
(tasks / "RM2703_annuaire-de-contacts.md").write_text(
    "---\ntitle: 'Annuaire de contacts transverse'\nstatus: en_cours\n---\ncorps\n",
    encoding="utf-8")
ka.PROJECTS_BASE = tmp / "clients"
ka._titles_cache.update({"at": 0.0, "by_id": {}})       # cache TTL : repartir à neuf

# Worklogs PM : un seul, celui de S_WLOG.
wl = tmp / "worklogs"
wl.mkdir()
(wl / f"{S_WLOG}.json").write_text(json.dumps({
    "session_id": S_WLOG,
    "items": [{"ref": "RM1234", "label": "Migration du webmail", "project": "atombox",
               "status": "a_tester_demandeur", "note": "", "next": "attendre la MEP"}],
    "requests": [{"ts": "2026-09-05T10:00", "text": "corrige la facturation Dolibarr",
                  "status": "ticketee", "ticket": "RM1234"}],
    "notifications": [{"ts": "2026-09-05T10:05", "level": "warn",
                       "message": "quota disque presque atteint"}],
}, ensure_ascii=False), encoding="utf-8")
ka.WORKLOG_DIR = wl


def ids(**qs):
    return {e["session_id"] for e in ka.op_resumable(qs)}


def one(**qs):
    r = ka.op_resumable(qs)
    return r[0] if len(r) == 1 else None


# ── 1. le socle : les métadonnées PM, sans transcript ────────────────────────
check("sans mots-clés, les quatre sessions sont proposées", ids() == set(TRANSCRIPTS))
check("un mot du TITRE de session la trouve", ids(q="refonte") == {S_TITLE})
check("la casse est ignorée", ids(q="REFONTE") == {S_TITLE})
check("un numéro de ticket trouve sa session", ids(q="2703") == {S_TICK})
check("…sous sa forme RM<id> aussi", ids(q="RM2703") == {S_TICK})
check("le SUJET du ticket trouve sa session", ids(q="annuaire") == {S_TICK})
check("un libellé du worklog trouve sa session", ids(q="webmail") == {S_WLOG})
check("le texte d'une DEMANDE trouve sa session", ids(q="facturation dolibarr") == {S_WLOG})
check("la prochaine étape notée au worklog aussi", ids(q="attendre la mep") == {S_WLOG})
check("une notification du worklog aussi", ids(q="quota disque") == {S_WLOG})
check("un mot introuvable ne ramène rien", ids(q="licorniau") == set())

# Mots-clés au pluriel : conjonction, sans ordre imposé ni contiguïté.
check("deux mots du MÊME worklog, éloignés l'un de l'autre",
      ids(q="webmail dolibarr") == {S_WLOG})
check("…dans l'ordre inverse aussi", ids(q="dolibarr webmail") == {S_WLOG})
check("titre de session + sujet de ticket se combinent",
      ids(q="annuaire contacts") == {S_TICK})
check("un mot en trop, introuvable, vide le résultat",
      ids(q="webmail licorniau") == set())
check("les espaces multiples ne créent pas de mot vide", ids(q="  refonte   ") == {S_TITLE})

e = one(q="2703")
check("le libellé du ticket voyage avec la ligne",
      bool(e) and e["tickets"][0]["title"] == "Annuaire de contacts transverse")
check("une trouvaille par métadonnées est marquée « meta »",
      bool(e) and e.get("match") == "meta")
check("sans recherche, aucune ligne n'est marquée",
      all("match" not in x for x in ka.op_resumable({})))

# ── 2. le transcript : opt-in, et VRAIMENT pas lu autrement ──────────────────
opened = []
_vrai_open = pathlib.Path.open


def _spy_open(self, *a, **k):
    if str(self).endswith(".jsonl") and "rb" in (a[0] if a else k.get("mode", "")):
        opened.append(str(self))
    return _vrai_open(self, *a, **k)


pathlib.Path.open = _spy_open
try:
    sans = ids(q="licorniau")
    lus_sans = len(opened)
    opened.clear()
    avec = ids(q="licorniau", deep="1")
    lus_avec = len(opened)
finally:
    pathlib.Path.open = _vrai_open

check("sans deep, un mot présent SEULEMENT dans le transcript ne ramène rien",
      sans == set())
check("…et aucun transcript n'a été ouvert en lecture binaire", lus_sans == 0)
check("avec deep=1, la session est trouvée", avec == {S_DEEP})
check("…et il a bien fallu ouvrir des transcripts", lus_avec > 0)
check("une trouvaille au transcript est marquée comme telle",
      (one(q="licorniau", deep="1") or {}).get("match") == "transcript")
check("deep ne rend pas la recherche laxiste",
      ids(q="mot-qui-n-existe-nulle-part", deep="1") == set())
check("deep n'élargit pas une recherche déjà satisfaite par les métadonnées",
      ids(q="annuaire", deep="1") == {S_TICK})
# Le transcript COMPLÈTE : « encore » vient du titre, « licorniau » du transcript.
check("un mot des métadonnées + un mot du transcript se combinent",
      ids(q="encore licorniau", deep="1") == {S_DEEP})
check("…et sans deep, cette combinaison ne trouve rien",
      ids(q="encore licorniau") == set())
check("deep sans mots-clés ne filtre rien (et ne scanne rien)",
      ids(deep="1") == set(TRANSCRIPTS))

# ── 3. la recherche se combine aux filtres fermés ────────────────────────────
check("filtre projet + mots-clés : les deux s'appliquent",
      ids(q="annuaire", client="iprospective", project="pm-ai-agents") == {S_TICK})
check("un filtre projet qui ne colle pas vide le résultat",
      ids(q="annuaire", client="autre") == set())

# ── 3 bis. l'identifiant de session : par préfixe, jamais au hasard ──────────
check("un préfixe d'identifiant trouve sa session", ids(q=S_TITLE[:8]) == {S_TITLE})
check("l'identifiant entier aussi", ids(q=S_TITLE) == {S_TITLE})
check("quatre chiffres tombés au milieu d'un UUID ne ramènent rien",
      ids(q=S_TITLE[4:8]) == set())
check("sid_match : préfixe d'au moins six caractères",
      ka.sid_match("abcdefgh-1234", "abcdef") and not ka.sid_match("abcdefgh-1234", "abcde"))
check("sid_match : jamais au milieu", not ka.sid_match("abcdefgh-1234", "cdefgh"))
check("sid_match : casse ignorée", ka.sid_match("ABCDEFGH-1", "abcdef"))
check("sid_match : entrées vides tolérées",
      not ka.sid_match("", "abcdef") and not ka.sid_match("abcdefgh", ""))

# ── 3 ter. le worklog survit au transcript ───────────────────────────────────
# Une session dont le .jsonl a été purgé : plus rien à reprendre, mais la trace
# du travail existe encore. C'est la réponse à « où ai-je traité RM7777 ? ».
S_ARCH = "eeeeeeee-1111-2222-3333-888888888888"
(wl / f"{S_ARCH}.json").write_text(json.dumps({
    "session_id": S_ARCH, "updated": "2026-07-21T17:50",
    "items": [{"ref": "RM7777", "label": "Onduleur non supervisé", "project": "infra",
               "status": "en_cours"}],
}, ensure_ascii=False), encoding="utf-8")

check("la session purgée n'est PAS proposée à la reprise", ids(q="onduleur") == set())
arch = ka._archived_worklogs(["onduleur"], set())
check("…mais elle est nommée comme archive",
      len(arch) == 1 and arch[0]["session_id"] == S_ARCH)
check("l'archive porte le ticket et son sujet",
      arch and arch[0]["tickets"][0]["ref"] == "RM7777"
      and arch[0]["tickets"][0]["title"] == "Onduleur non supervisé")
check("un ticket par son numéro trouve l'archive",
      {a["session_id"] for a in ka._archived_worklogs(["rm7777"], set())} == {S_ARCH})
check("une session encore reprenable n'est jamais comptée deux fois",
      ka._archived_worklogs(["webmail"], {S_WLOG}) == [])
check("…et sans l'exclusion, elle le serait (c'est bien le rôle de `connus`)",
      {a["session_id"] for a in ka._archived_worklogs(["webmail"], set())} == {S_WLOG})
check("sans mots-clés, aucune archive n'est listée", ka._archived_worklogs([], set()) == [])

# ── 4. la matière cherchable, isolée (fonction pure) ─────────────────────────
h = ka.resumable_haystack({"title": "Titre", "cwd": "/zfs/ws", "client": "acme",
                           "project": "appli", "session_id": "abc",
                           "tickets": [{"rm_id": "42", "title": "Le Sujet"}]}, "worklog ici")
check("le haystack est en minuscules", h == h.lower())
check("il porte le couple client/projet", "acme/appli" in h)
check("il ne porte PAS l'identifiant de session (cf. sid_match)", "abc" not in h)
check("il porte le ticket sous ses deux formes", " 42 " in " " + h + " " and "rm42" in h)
check("il porte le sujet du ticket", "le sujet".lower() in h)
check("il porte le worklog passé en second argument", "worklog ici" in h)
check("une entrée vide ne casse rien", ka.resumable_haystack({}) == "")
check("des tickets absents ne cassent rien",
      "titre" in ka.resumable_haystack({"title": "Titre", "tickets": None}))

# ── 5. lecture par blocs : le motif à cheval sur deux blocs ──────────────────
gros = tmp / "gros.bin"
bloc = 1 << 20
gros.write_bytes(b"." * (bloc - 4) + b"licorniau" + b"." * 128)
pat = [re.compile(b"licorniau", re.I)]
import time as _t
check("un motif à cheval sur deux blocs de 1 Mio est trouvé",
      ka._file_contains(gros, pat, _t.monotonic() + 30))
check("un motif absent rend False",
      not ka._file_contains(gros, [re.compile(b"zzz")], _t.monotonic() + 30))
check("plusieurs motifs : tous doivent être vus",
      ka._file_contains(gros, [re.compile(b"licorniau"), re.compile(rb"\.\.\.")],
                        _t.monotonic() + 30))
check("…un seul manquant suffit à refuser",
      not ka._file_contains(gros, [re.compile(b"licorniau"), re.compile(b"zzz")],
                            _t.monotonic() + 30))
check("aucun motif ⇒ False (jamais un fourre-tout)",
      not ka._file_contains(gros, [], _t.monotonic() + 30))
check("un fichier inexistant rend False (pas d'exception)",
      not ka._file_contains(tmp / "nexiste-pas", pat, _t.monotonic() + 30))
check("budget déjà épuisé : on renonce, on ne plante pas",
      not ka._file_contains(gros, pat, _t.monotonic() - 1))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
