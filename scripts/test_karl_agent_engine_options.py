#!/usr/bin/env python3
"""Tests RM3108 — options de lancement par moteur.

Ce que ces tests protègent, et pourquoi ça compte :

  * **spawn et resume composent la MÊME commande.** La ligne de commande d'un moteur
    se construisait à deux endroits distincts d'un fichier de 12 000 lignes. Une
    option posée dans un seul des deux donne une session neuve et une session reprise
    qui ne se comportent pas pareil — et le second cas ne se découvre qu'après coup,
    quand quelqu'un reprend une conversation.
  * **une option décochée par l'instance disparaît vraiment** de la commande ;
  * **un doublon de drapeau est REFUSÉ**, pas toléré : un drapeau que PM pose déjà
    (`--model`, `--session-id`, `--resume`) redéclaré en option ou en argument libre
    ferait sortir le CLI immédiatement, et le spawn échouerait sans raison lisible.

Lancer : python3 scripts/test_karl_agent_engine_options.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("ka", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(ka)
except SystemExit:
    pass

# — le catalogue de claude porte l'option MCP, cochée par défaut —
opts = {o["key"]: o for o in ka.engine_option_state("claude")}
check("claude propose l'option no_mcp", "no_mcp" in opts)
check("no_mcp porte le drapeau --strict-mcp-config",
      opts.get("no_mcp", {}).get("flag") == "--strict-mcp-config")
check("no_mcp est activée par défaut", opts.get("no_mcp", {}).get("enabled") is True)
check("no_mcp explique POURQUOI", bool(opts.get("no_mcp", {}).get("why")))

# — la commande porte l'option —
base = ka.engine_base_cmd("claude")
check("la commande de base porte --strict-mcp-config", "--strict-mcp-config" in base)

# — spawn et resume composent la même base : LE point du ticket —
pv = ka.engine_preview("claude")
check("le spawn porte l'option", "--strict-mcp-config" in pv["spawn_cmd"])
check("le resume porte l'option AUSSI", "--strict-mcp-config" in (pv["resume_cmd"] or ""))
check("le spawn ajoute --session-id", "--session-id" in pv["spawn_cmd"])
check("le resume ajoute --resume", "--resume" in (pv["resume_cmd"] or ""))

# — un moteur sans catalogue n'est pas cassé pour autant —
check("shell reste lançable sans options", ka.engine_base_cmd("shell") == "bash -l")
check("shell n'a pas de reprise", ka.engine_preview("shell")["resume_cmd"] is None)

# — l'instance peut décocher : l'option disparaît RÉELLEMENT —
_orig = ka._engine_conf
try:
    ka._engine_conf = lambda e, conf=None: {"options": {"no_mcp": False}} if e == "claude" else {}
    check("décochée, l'option sort de la commande",
          "--strict-mcp-config" not in ka.engine_base_cmd("claude"))
    check("décochée, l'option sort AUSSI de la reprise",
          "--strict-mcp-config" not in (ka.engine_preview("claude")["resume_cmd"] or ""))

    # — arguments libres —
    ka._engine_conf = lambda e, conf=None: {"extra_args": "--verbose --foo bar"} if e == "claude" else {}
    check("les arguments libres arrivent dans la commande",
          "--verbose" in ka.engine_base_cmd("claude") and "--foo" in ka.engine_base_cmd("claude"))

    # — refus : un drapeau que PM pose lui-même —
    ka._engine_conf = lambda e, conf=None: {"extra_args": "--session-id 42"} if e == "claude" else {}
    pb = ka.validate_engine_options("claude")
    check("un drapeau réservé dans extra_args est refusé", any("--session-id" in x for x in pb))

    # — refus : doublon avec une option déjà cochée —
    ka._engine_conf = lambda e, conf=None: {"extra_args": "--strict-mcp-config"} if e == "claude" else {}
    check("un doublon avec une option cochée est refusé",
          any("doublon" in x for x in ka.validate_engine_options("claude")))

    # — refus : option inconnue du catalogue —
    ka._engine_conf = lambda e, conf=None: {"options": {"nexiste_pas": True}} if e == "claude" else {}
    check("une option inconnue est refusée",
          any("inconnue" in x for x in ka.validate_engine_options("claude")))

    # — refus : guillemet orphelin —
    ka._engine_conf = lambda e, conf=None: {"extra_args": '--foo "pas fermé'} if e == "claude" else {}
    check("des arguments libres illisibles sont refusés",
          bool(ka.validate_engine_options("claude")))
finally:
    ka._engine_conf = _orig

# — configuration saine : aucun problème signalé —
check("la configuration livrée ne signale aucun problème",
      all(not ka.validate_engine_options(e) for e in ka.ENGINES))

# — l'aperçu couvre tous les moteurs —
names = {e["engine"] for e in ka.op_engine_options({})["engines"]}
check("l'aperçu couvre tous les moteurs", names == set(ka.ENGINES))

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — options de lancement par moteur")

# ── RM3139 : cocher depuis le cockpit — le patch de conf, et le refus avant écriture ──
print("[RM3139] réglage depuis le cockpit")
base = {"providers": {"x": 1}}
# une option identique au DÉFAUT n'est pas consignée : sinon l'instance fige l'état du jour et
# n'apprendra jamais un changement de défaut
p1 = ka.engine_conf_patch(base, "claude", {"no_mcp": True}, "")
check("cocher ce qui est déjà le défaut n'écrit rien", "engines" not in p1 and p1["providers"] == {"x": 1}, str(p1))
p2 = ka.engine_conf_patch(base, "claude", {"no_mcp": False}, "")
check("décocher un défaut, si : c'est une intention", p2["engines"]["claude"]["options"] == {"no_mcp": False}, str(p2))
p3 = ka.engine_conf_patch(p2, "claude", {"no_mcp": True}, "--verbose")
check("recocher retire l'entrée, les options libres restent",
      "options" not in p3["engines"]["claude"] and p3["engines"]["claude"]["extra_args"] == "--verbose", str(p3))
p4 = ka.engine_conf_patch(p3, "claude", {"no_mcp": True}, "")
check("plus rien à dire sur ce moteur : pas de trou laissé derrière", "engines" not in p4, str(p4))
check("les autres moteurs ne sont pas touchés",
      ka.engine_conf_patch({"engines": {"shell": {"extra_args": "-l"}}}, "claude", {"no_mcp": False}, "")["engines"]["shell"]["extra_args"] == "-l")
check("la conf d'origine n'est pas modifiée (pure)", base == {"providers": {"x": 1}})

# la route : ce qui est invalide est REFUSÉ, et rien n'est écrit
ecrits = []
_vrai_lire, _vrai_ecrire = ka._providers_local, ka._providers_ecrit_local
ka._providers_local = lambda: {}
ka._providers_ecrit_local = lambda cfg: ecrits.append(cfg)
try:
    try:
        ka.op_engine_options_set({"engine": "claude", "options": {"nexiste_pas": True}})
        check("une option inconnue est refusée", False, "aucune erreur levée")
    except ka.ApiError as e:
        check("une option inconnue est refusée, en disant laquelle", "inconnue" in e.msg and "nexiste_pas" in e.msg, e.msg)
    check("…et RIEN n'a été écrit — c'est tout l'intérêt de vérifier avant", not ecrits)
    try:
        ka.op_engine_options_set({"engine": "claude", "options": {}, "extra_args": "--session-id 42"})
        check("un drapeau que PM pose lui-même est refusé", False, "aucune erreur levée")
    except ka.ApiError as e:
        check("un drapeau que PM pose lui-même est refusé", "session-id" in e.msg, e.msg)
    try:
        ka.op_engine_options_set({"engine": "nexiste-pas", "options": {}})
        check("un moteur inconnu est refusé", False, "aucune erreur levée")
    except ka.ApiError as e:
        check("un moteur inconnu est refusé, avec la liste des connus", "connus" in e.msg, e.msg)
    check("toujours rien d'écrit après trois refus", not ecrits)
    r = ka.op_engine_options_set({"engine": "claude", "options": {"no_mcp": False}, "extra_args": "--verbose"})
    check("un réglage valide s'écrit", len(ecrits) == 1 and ecrits[0]["engines"]["claude"]["options"] == {"no_mcp": False}, str(ecrits))
    check("…et la réponse rend la commande qui sera RÉELLEMENT lancée",
          r["ok"] and "--verbose" in r["spawn_cmd"] and "--strict-mcp-config" not in r["base_cmd"], str(r))
finally:
    ka._providers_local, ka._providers_ecrit_local = _vrai_lire, _vrai_ecrire

sys.exit(1 if fails else 0)
