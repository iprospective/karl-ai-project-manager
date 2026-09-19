#!/usr/bin/env python3
"""Tests RM3206 — le contexte d'une notification (ticket, session, projet, client).

Ce que ces tests protègent :

  * **la déduplication survit à l'enrichissement.** C'est LE risque du ticket : `cle()` intègre
    `sid`, donc enrichir la clé ferait de la même alerte émise depuis deux sessions deux entrées
    distinctes — l'anti-répétition, raison d'être de cette empreinte, tomberait sans bruit ;
  * **ce que l'appelant dit explicitement gagne** sur le contexte deviné ;
  * **chaque source de contexte échoue seule.** Une notification mal située vaut mieux qu'une
    notification perdue : aucune résolution ne doit lever vers l'appelant ;
  * **le projet se lit au `meta.yml`, pas au chemin.** La première version déduisait le couple
    client/projet du chemin résolu : elle marchait pour un workspace de code (`.mmi-pm` est un
    lien) et rendait vide sur un dépôt de données (`.mmi-pm` est un vrai dossier, et son chemin
    ne contient ni « clients » ni « projects »).

Lancer : python3 scripts/test_pm_notify_contexte.py
"""
import importlib
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def fresh(tmp, **env):
    """Un module rechargé sur un fil vierge — l'état vit dans un fichier, pas en mémoire."""
    os.environ["PM_NOTIFY_DIR"] = tmp
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    import pm_notify
    return importlib.reload(pm_notify)


with tempfile.TemporaryDirectory() as tmp:
    N = fresh(tmp, CLAUDE_SESSION_ID="sess-A")

    # — le contexte est pris tout seul —
    N.add("system", "warn", "message témoin", job="j1")
    e = [x for x in N.feed() if x["msg"] == "message témoin"][0]
    check("la session est prise sans que l'appelant la passe", e.get("sid") == "sess-A")
    check("le projet est pris sans que l'appelant le passe", bool(e.get("projet")))
    check("le client est pris sans que l'appelant le passe", bool(e.get("client")))
    check("ce que l'appelant passe est conservé", e.get("job") == "j1")

    # — LE risque : la déduplication ne doit pas tomber —
    N.add("system", "warn", "répétée", job="j2")
    N.add("system", "warn", "répétée", job="j2")
    r = [x for x in N.feed() if x["msg"] == "répétée"]
    check("deux émissions identiques → UNE entrée", len(r) == 1)
    check("le compteur de répétition monte", r[0]["repeats"] == 2)

with tempfile.TemporaryDirectory() as tmp:
    N = fresh(tmp, CLAUDE_SESSION_ID="sess-A")
    N.add("system", "warn", "alerte d'instance")
    N = fresh(tmp, CLAUDE_SESSION_ID="sess-B")
    N.add("system", "warn", "alerte d'instance")
    f = [x for x in N.feed() if x["msg"] == "alerte d'instance"]
    check("DEUX SESSIONS, même alerte → une seule entrée (le sid auto n'entre pas dans la clé)",
          len(f) == 1 and f[0]["repeats"] == 2)

with tempfile.TemporaryDirectory() as tmp:
    N = fresh(tmp, CLAUDE_SESSION_ID="sess-A")
    # — l'explicite l'emporte sur le deviné —
    N.add("system", "info", "avec rm explicite", rm="9999")
    e = [x for x in N.feed() if x["msg"] == "avec rm explicite"][0]
    check("un rm passé explicitement n'est pas écrasé par le contexte", e.get("rm") == "9999")

    # — sans session déclarée, pas de champ inventé —
    N = fresh(tmp, CLAUDE_SESSION_ID=None, KARL_SESSION_ID=None)
    ctx = N.contexte_auto("/")
    check("hors de tout workspace, le contexte ne fabrique ni projet ni client",
          "projet" not in ctx and "client" not in ctx)

    # — chaque source échoue SEULE —
    check("un chemin inexistant ne lève pas", isinstance(N.contexte_auto("/nexiste/pas/du/tout"), dict))
    check("_ctx_projet sur la racine rend un dict vide", N._ctx_projet("/") == {})
    check("_ctx_ticket hors dépôt rend None", N._ctx_ticket("/") is None)

# — le projet vient du meta.yml, pas du chemin (le défaut corrigé) —
with tempfile.TemporaryDirectory() as tmp:
    faux = pathlib.Path(tmp) / "un-depot" / ".mmi-pm"
    faux.mkdir(parents=True)
    (faux / "meta.yml").write_text("schema_version: 1.7.1\nslug: mon-projet\nclient: mon-client\n",
                                   encoding="utf-8")
    N = fresh(tmp)
    got = N._ctx_projet(str(faux.parent))
    check("client et projet sont lus au meta.yml", got == {"client": "mon-client", "projet": "mon-projet"})
    check("… y compris quand le chemin ne contient ni « clients » ni « projects »",
          "clients" not in str(faux) and got.get("projet") == "mon-projet")

# — le rendu ne doit pas être le seul à savoir : la clé reste calculée sur l'explicite —
src = (HERE / "pm_notify.py").read_text(encoding="utf-8")
check("le contexte auto est appliqué par setdefault (l'explicite gagne)",
      "entree.setdefault(cl, v)" in src)
check("cle() est calculée AVANT l'enrichissement",
      src.index("k = cle(") < src.index("contexte_auto()"))

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — contexte des notifications")
sys.exit(1 if fails else 0)
