#!/usr/bin/env python3
"""Tests RM3026 — notification client à la MEP (logique pure de pm_client_notify).

Ce qui est protégé ici :
  1. l'option projet se lit tolérante (bloc absent, contacts scalaire/None) et
     n'est ACTIVE que si `actif` ET au moins un contact — sinon rien à notifier ;
  2. la mise en file est IDEMPOTENTE : re-jouer `→ en_mep` ne réinitialise pas une
     file déjà posée et ne ré-ouvre pas une notif déjà envoyée ; un NOUVEAU cycle
     (déjà envoyé puis redéployé) ré-entre bien en file ;
  3. la résolution annuaire rend l'email/tel de la ref, signale les refs orphelines
     (jamais tues), et l'email agrégé est dédoublonné ;
  4. l'email récap est UN seul mail pour N tickets, avec id/titre/lien, critères et
     protocole, et un sujet accordé en nombre.

Lancer : python3 scripts/test_pm_client_notify.py
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pm_client_notify as cn  # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── 1. option projet ─────────────────────────────────────────────────────────
check("option absente => inactif, sans contact",
      cn.parse_option({}) == {"actif": False, "contacts": [], "protocole": True})
check("contacts scalaire normalisé en liste",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": "alice"}})
      == {"actif": True, "contacts": ["alice"], "protocole": True})
check("contacts None toléré",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": None}})["contacts"] == [])
check("active ssi actif ET au moins un contact",
      cn.is_option_active({"notif_client_mep": {"actif": True, "contacts": ["alice"]}}))
check("actif mais sans contact => inactif",
      not cn.is_option_active({"notif_client_mep": {"actif": True, "contacts": []}}))
check("contacts mais actif=false => inactif",
      not cn.is_option_active({"notif_client_mep": {"actif": False, "contacts": ["alice"]}}))
# RM3052 — protocole de test dans l'email client : OPTIONNEL, activé par défaut
check("protocole absent du meta => True (défaut : on l'inclut)",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": ["s"]}})["protocole"] is True)
check("protocole: false => on ne l'inclut pas",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": ["s"], "protocole": False}})["protocole"] is False)
check("protocole: true => explicite, inclus",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": ["s"], "protocole": True}})["protocole"] is True)
check("bloc absent => protocole True (défaut) sans planter",
      cn.parse_option({})["protocole"] is True)

# ── 2. file (frontmatter ticket) — idempotence ───────────────────────────────
check("frontmatter vierge => pas en file",
      not cn.is_pending({}))
fm1, ch1 = cn.set_queued({}, "2026-09-08T10:00")
check("1re mise en file => changed + pending",
      ch1 and cn.is_pending(fm1))
fm2, ch2 = cn.set_queued(fm1, "2026-09-08T11:00")
check("re-mise en file d'un ticket déjà en attente => no-op (idempotent)",
      (not ch2) and cn.queue_state(fm2)[0] == "2026-09-08T10:00")
fm_sent = cn.mark_sent(fm1, "2026-09-08T12:00")
check("après envoi => plus en file (sent_at posé, queued_at conservé)",
      (not cn.is_pending(fm_sent)) and cn.queue_state(fm_sent) == ("2026-09-08T10:00", "2026-09-08T12:00"))
fm3, ch3 = cn.set_queued(fm_sent, "2026-09-08T13:00")
check("nouveau cycle (déjà envoyé puis redéployé) => ré-entre en file",
      ch3 and cn.is_pending(fm3) and cn.queue_state(fm3) == ("2026-09-08T13:00", None))
check("mark_sent sans queued_at préalable pose les deux",
      cn.queue_state(cn.mark_sent({}, "2026-09-08T14:00")) == ("2026-09-08T14:00", "2026-09-08T14:00"))

# RM3052 — sent_to (à QUI on a notifié) et dismiss (écarter sans notifier)
fm_to = cn.mark_sent(fm1, "2026-09-08T12:00", ["a@x.fr", "b@x.fr"])
check("mark_sent consigne sent_to = les emails notifiés",
      fm_to[cn.QUEUE_KEY]["sent_to"] == ["a@x.fr", "b@x.fr"])
check("sans emails, pas de sent_to inventé",
      "sent_to" not in cn.mark_sent(fm1, "2026-09-08T12:00")[cn.QUEUE_KEY])
fm_dis = cn.mark_dismissed(fm1, "2026-09-08T15:00")
check("dismiss => sort de la file, SANS sent_at (aucun email)",
      (not cn.is_pending(fm_dis)) and cn.dismissed_at(fm_dis) == "2026-09-08T15:00"
      and cn.queue_state(fm_dis)[1] is None)
check("dismiss conserve queued_at (trace du cycle)",
      cn.queue_state(fm_dis)[0] == "2026-09-08T10:00")
fm_re, ch_re = cn.set_queued(fm_dis, "2026-09-08T16:00")
check("redéployé après dismiss => ré-entre en file (dismissed effacé)",
      ch_re and cn.is_pending(fm_re) and cn.dismissed_at(fm_re) is None)

# ── 3. résolution annuaire + emails ──────────────────────────────────────────
ANN = {
    "alice-martin": {"ref": "alice-martin", "first_name": "Alice",
                             "last_name": "Martin", "emails": ["alice@clienta.example"],
                             "phones": ["+33 6 00 00 00 00"]},
    "sans-mail": {"ref": "sans-mail", "first_name": "Bob", "emails": [], "phones": []},
}
r = cn.resolve_recipients(ANN, ["alice-martin", "sans-mail", "inconnu"])
check("ref connue => email/tel/label résolus",
      r[0]["email"] == "alice@clienta.example" and r[0]["tel"] == "+33 6 00 00 00 00"
      and "Alice" in r[0]["label"] and not r[0]["orphan"])
check("ref sans email => email None (pas d'envoi pour elle)",
      r[1]["email"] is None and not r[1]["orphan"])
check("ref inconnue => orphan signalé (jamais tue)",
      r[2]["orphan"] and r[2]["email"] is None)
check("emails agrégés = non vides, dédoublonnés, ordre conservé",
      cn.recipient_emails(r + r) == ["alice@clienta.example"])

# un contact peut porter PLUSIEURS emails : tous deviennent destinataires (RM3026)
ANN_MULTI = {"ipro": {"ref": "ipro", "first_name": "Mathieu",
                      "emails": ["mathieu@iprospective.fr", "contact@iprospective.fr"]}}
rm = cn.resolve_recipients(ANN_MULTI, ["ipro"])
check("contact multi-emails => 1er en email, tous en emails",
      rm[0]["email"] == "mathieu@iprospective.fr"
      and rm[0]["emails"] == ["mathieu@iprospective.fr", "contact@iprospective.fr"])
check("recipient_emails prend TOUS les emails du contact (ordre + dédup)",
      cn.recipient_emails(rm + rm)
      == ["mathieu@iprospective.fr", "contact@iprospective.fr"])

# ── 4. composition de l'email ────────────────────────────────────────────────
subj1, body1 = cn.compose_email("Clienta", [
    {"id": 3025, "title": "Fix paliers", "url": "https://redmine/issues/3025",
     "criteria": ["Prix barré sur la fiche", ""], "protocol": "1. Ouvrir 438\n2. Ajouter"},
])
check("sujet singulier pour 1 ticket",
      "1 évolution mise en ligne" in subj1)
check("corps porte id + titre + lien + critère + protocole",
      "#3025" in body1 and "Fix paliers" in body1 and "issues/3025" in body1
      and "Prix barré" in body1 and "1. Ouvrir 438" in body1)
check("critère vide filtré du corps",
      "    • \n" not in body1)
subj2, _ = cn.compose_email("Clienta", [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}])
check("sujet pluriel pour 2 tickets",
      "2 évolutions mises en ligne" in subj2)
_, body3 = cn.compose_email("Clienta", [{"id": 9, "title": "Sans détail"}])
check("ticket sans critère/protocole => pas de sections vides",
      "Ce qui change" not in body3 and "Comment le vérifier" not in body3)

# ── 5. compte-rendu CLIENT (multi-projets) — RM3052 ──────────────────────────
T = lambda i, ti: {"id": i, "title": ti, "url": "https://redmine/issues/%d" % i}  # noqa: E731
s_mono, b_mono = cn.compose_client_email("Clienta", [{"project": "Site PrestaShop", "tickets": [T(1, "A"), T(2, "B")]}])
check("client mono-projet : sujet au nom du CLIENT, compte total",
      "Clienta — 2 évolutions mises en ligne" == s_mono)
check("client mono-projet : PAS d'en-tête de projet (rien d'interne dans l'email)",
      "== Site PrestaShop ==" not in b_mono and "#1" in b_mono and "#2" in b_mono)
s_multi, b_multi = cn.compose_client_email("Clienta", [
    {"project": "Site PrestaShop", "tickets": [T(1, "A")]},
    {"project": "Synchro Dolibarr", "tickets": [T(2, "B"), T(3, "C")]}])
check("client multi-projets : total tous projets confondus dans le sujet",
      "Clienta — 3 évolutions mises en ligne" == s_multi)
check("client multi-projets : un en-tête par projet, dans l'ordre donné",
      b_multi.index("== Site PrestaShop ==") < b_multi.index("== Synchro Dolibarr =="))
check("groupe sans ticket ignoré (pas de section vide)",
      "== Vide ==" not in cn.compose_client_email("C", [{"project": "Vide", "tickets": []},
                                                        {"project": "P", "tickets": [T(1, "A")]}])[1])
check("un seul groupe NON vide parmi plusieurs => on retombe en mono (pas d'en-tête)",
      "==" not in cn.compose_client_email("C", [{"project": "Vide", "tickets": []},
                                                {"project": "P", "tickets": [T(1, "A")]}])[1])
check("sujet au singulier pour 1 ticket",
      cn.compose_client_email("C", [{"project": "P", "tickets": [T(1, "A")]}])[0]
      == "C — 1 évolution mise en ligne")
_, b_det = cn.compose_client_email("C", [{"project": "P", "tickets": [
    {"id": 9, "title": "T", "criteria": ["Le prix s'affiche"], "protocol": "1. Ouvrir"}]}])
check("critères et protocole rendus comme dans le récap projet (même bloc)",
      "Ce qui change" in b_det and "Le prix s'affiche" in b_det
      and "Comment le vérifier" in b_det and "1. Ouvrir" in b_det)
check("aucune sélection => email vide mais bien formé (0 évolution)",
      cn.compose_client_email("C", [])[0] == "C — 0 évolution mise en ligne")

# ── 6. rendu HTML (RM3052) — un email lisible chez le client ─────────────────
# Le protocole de test est du markdown à TABLEAUX : recopié en texte brut il arrive en
# bouillie. L'email part donc en multipart, et c'est la partie HTML que le client lit.
MD = "## Bandes\n\n| Cas | Attendu |\n|---|---|\n| A1 | Prix barré | \n\n- puce\n"
h = cn.render_markdown(MD)
check("un tableau markdown devient un vrai <table> (le cœur de la demande)",
      "<table style=" in h and "<th style=" in h and "|---" not in h)
check("titres et listes rendus, pas recopiés",
      "<h2 style=" in h and "<ul style=" in h and "## Bandes" not in h)
check("styles EN LIGNE (les clients mail jettent les feuilles <style>)",
      "<table>" not in h and "<td>" not in h)
check("les cases d'atelier deviennent lisibles pour un client",
      cn.render_markdown("- [x] fait\n- [ ] à faire").count("✔") == 1
      and "☐" in cn.render_markdown("- [ ] à faire"))
check("aucun HTML brut ne traverse (le markdown source est échappé)",
      "&lt;script&gt;" in cn.render_markdown("<script>alert(1)</script>")
      and "<script>" not in cn.render_markdown("<script>alert(1)</script>"))
check("protocole vide => rien du tout (pas de bloc fantôme)", cn.render_markdown("   ") == "")

# Lisibilité — les deux défauts constatés sur le premier envoi HTML (2026-09-09) :
# 1. un `>` échappé cassait les citations ; 2. le YAML replie les lignes du frontmatter, si
#    bien qu'une énumération rédigée sur dix lignes revenait en un pavé d'un seul tenant.
check("une citation markdown reste une citation (le `>` n'est plus échappé)",
      "<blockquote style=" in cn.render_markdown("> Tracé de recette"))
check("…mais aucune balise ne traverse pour autant",
      "&lt;script&gt;" in cn.render_markdown("<script>x</script>")
      and "<script>" not in cn.render_markdown("<script>x</script>"))
LONG = "Produits testés : " + " · ".join("**A%d** p%d (cas de bande %d)" % (i, 40 + i, i) for i in range(1, 12))
check("une LONGUE énumération « · » repasse à la ligne (le pavé illisible)",
      cn.render_markdown(LONG).count("<br") >= 10)
check("une énumération COURTE est laissée tranquille",
      "<br" not in cn.render_markdown("A · B"))
check("les lignes d'un tableau ne sont jamais recoupées",
      "<br" not in cn.render_markdown("| " + " · ".join(["x" * 40] * 6) + " | y |\n|---|---|\n| a | b |").split("<table")[1][:200])
check("un retour à la ligne voulu par l'auteur en reste un (nl2br)",
      cn.render_markdown("étape une\nétape deux").count("<br") == 1)

T_HTML = {"id": 3025, "title": "Paliers & <prix>", "url": "https://r/3025",
          "criteria": ["Prix barré"], "protocol": MD}
sh, hh = cn.compose_client_email_html("Clienta", [{"project": "Site", "tickets": [T_HTML]}])
check("le sujet HTML est IDENTIQUE au sujet texte (un multipart ne se contredit pas)",
      sh == cn.compose_client_email("Clienta", [{"project": "Site", "tickets": [T_HTML]}])[0])
check("document HTML complet et autonome",
      hh.startswith("<!DOCTYPE html>") and hh.rstrip().endswith("</html>"))
check("titre et lien du ticket présents, le titre étant ÉCHAPPÉ",
      'href="https://r/3025"' in hh and "Paliers &amp; &lt;prix&gt;" in hh)
check("les critères sortent en liste, le protocole en tableau",
      "Ce qui change" in hh and "<li style=" in hh and "Comment le vérifier" in hh and "<table style=" in hh)
# Un protocole peut contenir ses propres titres : on cherche le NOM du projet, pas « <h2 ».
T_PLAIN = {"id": 7, "title": "Sans protocole"}
_, hh_multi = cn.compose_client_email_html("C", [{"project": "Site vitrine", "tickets": [T_PLAIN]},
                                                 {"project": "Synchro ERP", "tickets": [T_PLAIN]}])
check("multi-projets : un intitulé par projet, comme en texte",
      "Site vitrine" in hh_multi and "Synchro ERP" in hh_multi)
_, hh_mono = cn.compose_client_email_html("C", [{"project": "Site vitrine", "tickets": [T_PLAIN]}])
check("mono-projet : aucun intitulé de projet (rien d'interne chez le client)",
      "Site vitrine" not in hh_mono)
_, hh_proj = cn.compose_email_html("Site PrestaShop", [T_HTML])
check("pendant HTML du récap PROJET", hh_proj.startswith("<!DOCTYPE html>") and "Site PrestaShop" in hh_proj)
_, hh_sans = cn.compose_client_email_html("C", [{"project": "P", "tickets": [{"id": 1, "title": "T"}]}])
check("ticket sans critère ni protocole : pas de section vide",
      "Ce qui change" not in hh_sans and "Comment le vérifier" not in hh_sans)

# ── 7. rattrapage à la FERMETURE (RM3087) — sans jamais annoncer deux fois ───
# Le défaut : la file se remplissait à la TRANSITION `en_mep`. Un ticket mis en prod
# autrement (recette puis fermeture directe — le cas RM3079) n'était jamais proposé au
# compte-rendu. Mais rattraper avec `set_queued` seul rouvrirait un cycle sur un ticket
# DÉJÀ annoncé : c'est le double envoi que Mathieu a explicitement écarté. D'où une
# condition plus stricte à la fermeture : « jamais mis en file », et non « pas en attente ».
check("ticket vierge => à mettre en file à la fermeture", cn.never_queued({}))
check("frontmatter sans bloc client_notify => idem", cn.never_queued({"title": "x"}))
_q, _ = cn.set_queued({}, "2026-09-11T09:00")
check("déjà EN FILE => on ne le remet pas (set_queued est de toute façon idempotent)",
      not cn.never_queued(_q))
check("déjà ANNONCÉ => surtout pas de seconde annonce",
      not cn.never_queued(cn.mark_sent(_q, "2026-09-11T10:00", ["a@x.fr"])))
check("ÉCARTÉ volontairement => ne revient pas par la fermeture",
      not cn.never_queued(cn.mark_dismissed(_q, "2026-09-11T10:00")))
check("bloc vide (fiche bricolée) => traité comme jamais vu, pas comme annoncé",
      cn.never_queued({cn.QUEUE_KEY: {}}))

# ── 8. le DEMANDEUR du ticket (RM3092) ──────────────────────────────────────
# `creator` porte un identifiant court, l'annuaire des refs complètes. On accepte la ref
# exacte, son premier segment, ou le prénom — mais JAMAIS une correspondance multiple :
# prévenir la mauvaise personne ne se rattrape pas.
ANN_R = {
    "iprospective": {"ref": "iprospective", "first_name": "Mathieu", "emails": ["m@ipro.fr"]},
    "alice-martin": {"ref": "alice-martin", "first_name": "Alice",
                             "emails": ["s@clienta.example"]},
    "hugo-clientc": {"ref": "hugo-clientc", "first_name": "Hugo", "emails": ["y@clientc.example"]},
    "sans-mail": {"ref": "sans-mail", "first_name": "Bob", "emails": []},
}
r = cn.resolve_requester(ANN_R, "iprospective")
check("ref exacte résolue", r["found"] and r["emails"] == ["m@ipro.fr"])
r = cn.resolve_requester(ANN_R, "alice")
check("identifiant court => ref complète (alice → alice-martin)",
      r["found"] and r["ref"] == "alice-martin")
r = cn.resolve_requester(ANN_R, "Hugo")
check("casse indifférente, résolution par prénom", r["found"] and r["emails"] == ["y@clientc.example"])
r = cn.resolve_requester(ANN_R, "inconnu")
check("demandeur inconnu => non résolu, SIGNALÉ (pas d'email inventé)",
      not r["found"] and not r["ambiguous"] and r["emails"] == [])
r = cn.resolve_requester(ANN_R, "bob")
check("fiche sans email => non résolu plutôt que faussement trouvé", not r["found"])
AMB = dict(ANN_R, **{"alice-durand": {"ref": "alice-durand", "first_name": "Alice",
                                         "emails": ["s2@x.fr"]}})
r = cn.resolve_requester(AMB, "alice")
check("DEUX Alice => ambigu, on ne tire pas au sort", r["ambiguous"] and not r["found"])
check("creator vide toléré", not cn.resolve_requester(ANN_R, "")["found"])

G = cn.group_by_requester([
    {"id": 1, "creator": "alice"}, {"id": 2, "creator": "iprospective"},
    {"id": 3, "creator": "alice"}, {"id": 4, "creator": ""}])
check("groupement par demandeur, ordre d'apparition conservé",
      [c for c, _ in G] == ["alice", "iprospective", ""])
check("…chacun ne voit QUE ses tickets",
      [t["id"] for t in G[0][1]] == [1, 3] and [t["id"] for t in G[1][1]] == [2])
check("liste vide tolérée", cn.group_by_requester([]) == [])

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
