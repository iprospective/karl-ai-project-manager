#!/usr/bin/env python3
"""pm-think-harvest — moisson automatique du transcript vers le `.think.md` du ticket courant. RM3015 D005, RM3053.

« Scripts et automatisations au maximum » : ce hook (Claude Code `Stop` / `SessionEnd`) relit le
transcript de la session et consigne, sans geste de l'agent :
  - les QUESTIONS posées à l'utilisateur (AskUserQuestion / ExitPlanMode, typage RM2549) :
      répondues  → une décision D « question → réponse » (✅, auteur M) ; la Q ouverte homonyme passe ✅ ;
      sans réponse → une question Q (🕐) ;
  - les PROPOSITIONS et réflexions pertinentes de l'IA (non posées en question outillée) → notes N signées du modèle ;
  - les QUESTIONS DU DEMANDEUR (RM3090) → questions Q signées de lui : une question ouverte est tout
    ce qui n'est pas tranché, **quel qu'en soit l'auteur** (RM3015-D011). Elles ne passent PAS par le
    critère de la note — une question n'a pas à porter une dette pour mériter d'être consignée, c'est
    justement ce qui n'est pas encore tranché. Critère partagé avec `pm-think-classify` (RM3067, D023) ;
  - les REMARQUES de l'utilisateur qui passent le critère de la note (RM3062 : réflexion, constat, idée —
    jamais une demande immédiate, un accord, un accusé ; `pm_think.note_pertinente`) → notes N verbatim.
Dédoublonné sur le texte : rejouer la moisson n'écrit rien de plus.

**Chaque TOUR va au ticket qu'il a touché** (RM3100), résolu comme pour le tick de conso
(`pm-task-tick` : mutation PM > fiche éditée > mention ; un tour sans signal continue le précédent).
Attribuer toute une passe au ticket courant au moment où elle tourne est juste sur une session
mono-ticket et faux sur une séance longue — et la garde de clôture refuse alors de fermer un ticket
sur des questions qui ne sont pas les siennes. `--no-split` rend l'ancien comportement.
Sans ticket résolu du tout : rien, silencieusement (RM2440).

  hook   : payload JSON sur stdin ({session_id, transcript_path, cwd}) — jamais d'échec bloquant.
           `--full` (RM3098, câblé sur `PreCompact`) relit TOUT le transcript au lieu de reprendre au
           curseur : c'est le dernier passage avant que la conversation ne devienne un résumé, et le
           curseur n'a pas à décider ce qu'on relit à ce moment-là
  CLI    : pm-think-harvest --rm <id> [--session <sid>] [--transcript <jsonl>] [--dry-run]
  élagage: pm-think-harvest --prune (--rm <id> | --all) [--dry-run] — les notes en attente qui ne passent pas le
           critère passent ❌ « élaguée (RM3062) », jamais supprimées ; à rejouer après une évolution du critère.
"""
import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git                                   # noqa: E402
import pm_think                                 # noqa: E402
from pm_paths import PMConfig                   # noqa: E402
from pm_transcript import transcript_outline    # noqa: E402


def _type_heuristique(role, texte):
    """RM3090 : LE critère vit dans `pm-think-classify` (RM3067, D023) — importé, jamais recopié.
    Un hook de fin de tour doit rendre la main tout de suite : c'est la version SANS modèle ; la
    passe LLM (`pm-think-classify --all`) reste le filet qui complète et corrige.
    Indisponible : tout retombe en note, comme avant."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "pm_think_classify", Path(__file__).resolve().parent / "pm-think-classify.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod.type_heuristique(role, texte)
    except Exception:      # noqa: BLE001 — la moisson ne casse jamais un tour
        return "dette"

MIN_NOTE = 20
MAX_NOTE = 400
#: en mode hook, on ne relit que la fin du transcript (depuis le dernier tour moissonné, avec
#: un recul pour retrouver la question d'un tour précédent à laquelle ce tour répond)
LOOKBACK = 80
CLAUDE_STORES = [Path(p).expanduser() for p in
                 os.environ.get("PM_CLAUDE_STORES", str(Path.home() / ".claude" / "projects")).split(":") if p.strip()]


def _tick_module():
    spec = importlib.util.spec_from_file_location("pm_task_tick", Path(__file__).resolve().parent / "pm-task-tick.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def transcript_of(sid):
    return next((p for root in CLAUDE_STORES for p in root.glob(f"*/{sid}.jsonl")), None) if sid else None


def harvest_items(lines) -> list:
    """[(kind, text, extra)] à consigner, dans l'ordre du fil, sans doublon. Pure — c'est elle qui est testée."""
    out, seen = [], set()
    for it in transcript_outline(lines, max_items=1000000):
        k = it.get("kind")
        if k == "question":
            q = " / ".join(l.strip() for l in str(it.get("full") or "").splitlines()
                           if l.strip() and not l.startswith("  - ")) or it.get("text", "")
            item = ("decision", f"{q} → {it['answer']}", {"question": q}) if it.get("answer") else ("question", q, {})
        elif k == "assistant":
            # RM3062 lot 3 : les propositions / réflexions pertinentes de l'IA, non posées en question outillée → note signée du modèle
            ok, extrait = pm_think.proposition_pertinente(it.get("full") or it.get("text") or "")
            if not ok or not pm_think.note_pertinente(extrait)[0]:   # RM3066 : même critère pour l'IA — une proposition sans reste à faire n'est pas une note
                continue
            item = ("note", extrait, {"by": "A"})
        elif k == "user":
            t = " ".join(str(it.get("full") or it.get("text") or "").split())
            # ni commandes, ni enveloppes techniques, ni marqueurs d'interruption
            if len(t) < MIN_NOTE or t.startswith(("/", "<", "[")):
                continue
            texte = t[:MAX_NOTE] + ("…" if len(t) > MAX_NOTE else "")
            if _type_heuristique("M", t) == "question":
                # RM3090 : ce que le demandeur DEMANDE est une note, ce qu'il se DEMANDE est une
                # question. Le critère de la note (dette à faire) l'aurait écartée : une question
                # ne porte pas de dette, elle porte un arbitrage en attente.
                item = ("question", texte, {"by": "M"})
            else:
                ok, _motif = pm_think.note_pertinente(t)      # RM3062 : le critère de la note
                if not ok:
                    continue
                item = ("note", texte, {})
        else:
            continue
        key = (item[0], pm_think._norm(item[1]))
        if key in seen:
            continue
        seen.add(key); out.append(item)
    return out


def _cursor_path(cfg, sid):
    return Path(cfg.state_dir) / "think-harvest" / f"{sid}.json"


def _window(cfg, sid, lines: list) -> list:
    """En mode hook : les lignes depuis le dernier tour moissonné (moins LOOKBACK), et le curseur avance."""
    cp = _cursor_path(cfg, sid) if sid else None
    start = 0
    if cp and cp.is_file():
        try:
            start = max(0, int(json.loads(cp.read_text()).get("line", 0)) - LOOKBACK)
        except (ValueError, OSError):
            start = 0
    if cp:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps({"line": len(lines)}))
        except OSError:
            pass
    return lines[start:]


def apply(think: Path, rm_id: int, items: list, *, sid=None, title="", dry=False) -> list:
    """Écrit ce qui manque ; retourne les ids ajoutés."""
    added = []
    parsed = pm_think.load(think)
    for kind, text, extra in items:
        # RM3090 : déjà consigné, sous CETTE rubrique ou une autre — une remarque relue plus tard
        # comme une question ne doit pas apparaître deux fois. Reclasser reste un geste explicite.
        if pm_think.has_text_anywhere(parsed, text):
            continue
        if dry:
            added.append(f"{kind}:{text[:60]}"); continue
        if kind == "decision":
            rid = pm_think.append(think, "decision", text, rm_id=rm_id, title=title, by="M", state="valide", sid=sid)
            # la question homonyme laissée ouverte par une moisson précédente est tranchée
            for r in parsed.get("question", {}).get("rows", []):
                if not r["closed"] and r["state"] not in ("valide", "invalide") and len(r["cells"]) > 1 \
                        and pm_think._norm(r["cells"][1]) == pm_think._norm(extra.get("question")):
                    pm_think.set_state(think, r["id"], "valide", dest=rid)
        elif kind == "question":
            # RM3090 : l'auteur suit la provenance — une question posée PAR l'agent (AskUserQuestion)
            # reste « A » ; une question que le demandeur se pose est de lui.
            rid = pm_think.append(think, "question", text, rm_id=rm_id, title=title,
                                  by=extra.get("by", "A"), state="attente", sid=sid, urgence="moyenne")
        else:
            rid = pm_think.append(think, "note", text, rm_id=rm_id, title=title, by=extra.get("by", "M"), state="attente", sid=sid)
        added.append(rid)
        parsed = pm_think.load(think)
    return added


#: statuts où le travail du ticket est FAIT : une note laissée « à trier » n'a plus d'objet (RM3066)
LIVRES = ("a_tester_dev", "a_tester_demandeur", "a_tester_preprod", "a_mep", "en_mep", "ferme")


def ticket_livre(sheet: Path) -> bool:
    """Le ticket est-il livré ou fermé ? Ses notes en attente sont alors mortes : ce qui devait
    en sortir est soit fait, soit devenu une question ou une fonctionnalité avant la livraison."""
    try:
        m = re.search(r"^status:\s*(\S+)", sheet.read_text(encoding="utf-8"), re.M)
    except OSError:
        return False
    return bool(m) and m.group(1).strip().strip("'\"") in LIVRES


def prune(think: Path, dry=False, delete=False) -> list:
    """Élague les notes en attente qui ne passent pas le critère : ❌ « élaguée (RM3062) : <motif> », ou SUPPRIMÉES
    (`delete`, décision Mathieu 2026-09-09 : « les notes pourries, tu peux les supprimer vraiment ») — les lignes déjà
    marquées élaguées partent aussi. Retourne les ids."""
    parsed = pm_think.load(think)
    livre = ticket_livre(pm_think.sheet_of(think))
    out = []
    for r in parsed.get("note", {}).get("rows", []):
        if len(r["cells"]) < 3:
            continue
        if livre and not (r["closed"] or r["state"] in ("valide", "invalide")):
            out.append(r["id"]); continue      # ticket livré : la note n'a plus d'objet
        deja = "élaguée (RM3062)" in (r["cells"][4] if len(r["cells"]) > 4 else "")
        if deja and delete:
            out.append(r["id"]); continue
        if r["closed"] or r["state"] in ("valide", "invalide"):
            continue
        ok, motif = pm_think.note_pertinente(r["cells"][2])
        if ok:
            continue
        out.append(r["id"])
        if not dry and not delete:
            pm_think.set_state(think, r["id"], "invalide", dest=f"élaguée (RM3062) : {motif}")
    if delete and not dry and out:
        pm_think.remove_rows(think, out)
    return out


def meme_projet(sheet: Path, cwd) -> bool:
    """RM3066 : la fiche du ticket courant et le cwd de la session désignent-ils le MÊME projet ?

    Sans cette garde, une session qui travaille sur un projet (AtomBox) mais dont le « ticket courant »
    résolu appartient à un autre (le PM) déverse toute sa conception dans le mauvais think : 36 des 51
    notes de RM2967 parlaient d'AtomBox. Un doute (cwd hors projet PM-tracké) laisse passer."""
    try:
        mm = Path(cwd or "").resolve()
    except (OSError, ValueError):
        return True
    for d in [mm, *mm.parents]:
        link = d / ".mmi-pm"
        if link.exists():
            try:
                return link.resolve() in sheet.resolve().parents
            except OSError:
                return True
    return True


def par_ticket(lines, defaut=None, tick=None, connu=None) -> list:
    """[(rm_id, lignes)] — le transcript découpé par TOUR, chaque tour attribué au ticket qu'il a
    RÉELLEMENT touché (RM3100). Pure (hors lecture des fiches par `_pick_from_events`).

    La moisson attribuait TOUT au ticket courant au moment où elle tournait. C'est juste sur une
    session mono-ticket, faux sur une séance longue : une passe lancée sous RM3099 a versé dans son
    carnet cinq questions qui appartenaient à RM3015, RM3074 et RM3090, traités plus tôt dans le même
    fil. Ce n'est pas cosmétique — la garde de clôture refuse de fermer un ticket sur des questions
    ouvertes qui ne sont pas les siennes.

    La résolution par tour est celle du tick de conso (`pm-task-tick`, mutation PM > édition de fiche
    > mention) : une seule définition de « le ticket de ce tour », partagée. Un tour sans aucun signal
    hérite du tour précédent — c'est la continuation d'un travail, pas un changement de sujet ; au
    tout début du fil, il retombe sur `defaut`. Les tours consécutifs d'un même ticket sont regroupés
    pour que `harvest_items` voie une question et sa réponse ensemble."""
    tick = tick or _tick_module()
    segs, cur_l, cur_e = [], [], []
    for ln in lines:
        try:
            evt = json.loads(ln)
        except ValueError:
            evt = None
        try:
            frontiere = evt is not None and tick._is_human_prompt(evt)
        except Exception:      # noqa: BLE001 — un event exotique ne coupe pas le fil
            frontiere = False
        if frontiere and cur_l:
            segs.append((cur_e, cur_l)); cur_l, cur_e = [], []
        cur_l.append(ln)
        if evt is not None:
            cur_e.append(evt)
    if cur_l:
        segs.append((cur_e, cur_l))
    # un en-tête de fichier sans aucun message (résumé de compaction, lignes illisibles) n'est pas
    # un tour : il rejoint le premier vrai, sinon il s'attribuerait tout seul au défaut
    if len(segs) > 1 and not segs[0][0]:
        segs[1][1][:0] = segs[0][1]; segs.pop(0)
    out, dernier = [], None
    for evts, lns in segs:
        try:
            pick = tick._pick_from_events(evts)
        except Exception:      # noqa: BLE001
            pick = None
        rid = pick[0] if pick else None
        if rid is not None and connu is not None and not connu(rid):
            rid = None      # un id capté au passage (chemin, URL) qui n'est aucun ticket d'ici
        if rid is not None and pick[1] < 2 and dernier is not None and rid != dernier:
            # signal FAIBLE : le ticket n'est que cité. Une citation ne change pas de sujet — sinon
            # un tour qui raconte « comme dans RM2792 » emporterait toute sa moisson chez RM2792.
            # Sauf si c'est le DEMANDEUR qui la fait dans son prompt : « et RM3082 ? » est une consigne.
            prompt = evts[0] if evts else None
            try:
                voulu = bool(prompt) and tick._is_human_prompt(prompt) \
                    and any(r == rid for r, _f in tick._evidence_from_event(prompt))
            except Exception:      # noqa: BLE001
                voulu = False
            if not voulu:
                rid = dernier
        if rid is None:
            rid = dernier if dernier is not None else defaut
        if rid is None:
            continue
        dernier = rid
        if out and out[-1][0] == rid:
            out[-1][1].extend(lns)
        else:
            out.append((rid, list(lns)))
    return out


def _verse(cfg, rm_id, lines, sid, dry, commit, cwd) -> list:
    """Moissonne CES lignes vers le think de CE ticket. Retourne les ids ajoutés."""
    sheet = cfg.find_task(int(rm_id))
    if not sheet:
        return []
    if cwd and not meme_projet(sheet, cwd):
        return []
    items = harvest_items(lines)
    if not items:
        return []
    think = pm_think.think_path(sheet)
    added = apply(think, int(rm_id), items, sid=sid, dry=dry)
    if added and not dry:
        pm_think.set_counters(sheet, pm_think.counters(pm_think.load(think)))
        if commit:
            pm_git.autocommit([think, sheet], f"pm(think): RM{rm_id} moisson {len(added)} entrée(s)")
    return added


def run(rm_id, sid, transcript, dry=False, commit=True, incremental=False, cwd=None, split=True) -> list:
    """RM3100 : chaque tour va au ticket qu'il a touché ; `rm_id` n'est plus que le défaut des tours
    sans signal. `split=False` rend l'ancien comportement (tout au ticket donné) — utile pour
    rattraper à la main une moisson mal répartie."""
    cfg = PMConfig.load()
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    if incremental:
        lines = _window(cfg, sid, lines)
    if not split:
        return _verse(cfg, rm_id, lines, sid, dry, commit, cwd) if rm_id else []
    added = []
    vu = {}
    connu = lambda r: vu.setdefault(r, bool(cfg.find_task(int(r))))
    for rid, seg in par_ticket(lines, defaut=rm_id, connu=connu):
        added += _verse(cfg, rid, seg, sid, dry, commit, cwd)
    return added


def hook_mode(full: bool = False) -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    sid = payload.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID")
    tp = payload.get("transcript_path") or (transcript_of(sid) if sid else None)
    if not tp or not Path(tp).is_file():
        return 0
    try:
        rid, _why = _tick_module().resolve_current_rm_id(payload.get("cwd") or os.getcwd(), str(tp))
        if rid is None:
            return 0
        run(rid, sid, tp, incremental=not full, cwd=payload.get("cwd"))   # RM3098 : --full = passe complète ; RM3100 : rid n'est que le défaut
    except SystemExit:
        pass
    except Exception as e:                       # jamais bloquer un tour pour une moisson
        try:
            from pm_log import log as _jlog
            _jlog("worklog", "warn", f"think-harvest: {e}", sid=sid)
        except Exception:
            pass
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--rm", type=int); ap.add_argument("--session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--transcript"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--no-commit", action="store_true")
    ap.add_argument("--prune", action="store_true", help="élaguer les notes en attente qui ne passent pas le critère (RM3062)")
    ap.add_argument("--all", action="store_true", help="avec --prune : tous les think du projet courant")
    ap.add_argument("--delete", action="store_true", help="avec --prune : supprimer les lignes (et celles déjà marquées élaguées) au lieu de les marquer ❌")
    ap.add_argument("--tasks-dir", help="avec --prune : dossier des fiches (tests)")
    ap.add_argument("--no-split", action="store_true",
                    help="tout verser dans --rm, sans répartir par tour (ancien comportement, RM3100)")
    ap.add_argument("--full", action="store_true",
                    help="relire TOUT le transcript sans repartir du curseur — dernier passage avant "
                         "compaction (hook PreCompact, RM3098)")
    a = ap.parse_args()
    if a.prune:
        cfg = None if a.tasks_dir else PMConfig.load()
        if a.all:
            tasks = Path(a.tasks_dir) if a.tasks_dir else Path(cfg.find_task(a.rm)).parent if a.rm else None
            if tasks is None:
                mm = Path.cwd() / ".mmi-pm"
                tasks = (mm.resolve() / "tasks") if mm.exists() else None
            if not tasks or not tasks.is_dir():
                sys.exit("--prune --all : dossier tasks/ introuvable (--tasks-dir, ou un workspace avec .mmi-pm)")
            thinks = sorted(tasks.glob("RM*.think.md"))
        else:
            if a.rm is None:
                sys.exit("--prune exige --rm <id> ou --all")
            sheet = Path(a.tasks_dir).glob(f"RM{a.rm}_*.md") if a.tasks_dir else [cfg.find_task(a.rm)]
            sheet = next((x for x in sheet if x and pm_think.is_task_sheet(str(x))), None)
            thinks = [pm_think.think_path(sheet)] if sheet else []
        total = 0
        for th in thinks:
            if not th.is_file():
                continue
            ids = prune(th, dry=a.dry_run, delete=a.delete); total += len(ids)
            if ids:
                print(f"{'(dry) ' if a.dry_run else ''}{th.name} : {len(ids)} note(s) {'supprimée(s)' if a.delete else 'élaguée(s)'} — {', '.join(ids[:10])}{'…' if len(ids) > 10 else ''}")
                if not a.dry_run and not a.no_commit:
                    pm_git.autocommit([th], f"pm(think): {pm_think.rm_id_of(th) and 'RM' + str(pm_think.rm_id_of(th)) or th.name} élagage de {len(ids)} note(s) (RM3062)", cwd=th.parent)
        print(f"{'(dry) ' if a.dry_run else ''}élagage : {total} note(s) sur {len(thinks)} think")
        return
    if a.rm is None:
        sys.exit(hook_mode(full=a.full))
    tp = a.transcript or transcript_of(a.session)
    if not tp:
        sys.exit(f"ERREUR : transcript introuvable (session {a.session})")
    added = run(a.rm, a.session, tp, dry=a.dry_run, commit=not a.no_commit, split=not a.no_split)
    # les ids portent leur ticket (`RM3015-Q004`) : la répartition se lit dans la sortie
    print(f"{'(dry) ' if a.dry_run else ''}RM{a.rm} : {len(added)} entrée(s) {'à ajouter' if a.dry_run else 'ajoutée(s)'}"
          + (" — " + ", ".join(added[:12]) if added else ""))


if __name__ == "__main__":
    main()
