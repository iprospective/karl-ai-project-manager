#!/usr/bin/env python3
"""pm_partner — liens vers les tickets d'un gestionnaire PARTENAIRE (N0, RM2654).

Lot L1 du chantier RM2626 ([[Cdc-rm2626-tickets-partenaires]]). Deux clients réels le
motivent : **Pisceen** (un autre prestataire tient ses tickets sur son Redmine ; on
rattache à la demande, y compris rétroactivement) et **MatNat** (tout ce qu'on fait pour
eux doit être rattaché à un ticket de leur Redmine).

**Ce que ce module fait — et ne fait pas.** Il modélise le **lien** : quel ticket de quel
partenaire correspond à ce ticket PM. Il ne synchronise aucun contenu (le pull est L2,
le push L3) et **ne touche jamais l'état du ticket** — statut, priorité, assignation
restent au primaire, seule source de vérité (cf. `pm_registry` § primaire/secondaire).

Modèle — un item de `refs[]` du frontmatter, typé `partner_issue` :

```yaml
refs:
  - type: partner_issue
    instance: redmine-matnat      # DOIT être un secondaire déclaré du projet
    issue_id: 1234
    url: https://tasks.materiaux-naturels.fr/issues/1234
    role: mirror                  # mirror | upstream | related
    last_seen_journal_id: null    # pointeur de pull, par lien (L2) — jamais global
    added: 2026-08-12
```

`role` dit ce qu'est le ticket distant, pas ce qu'on en fait :
  * `mirror`   — c'est mon ticket vu de chez eux (1↔1, cas MatNat) ;
  * `upstream` — leur ticket est la demande d'origine ;
  * `related`  — simple voisinage (n de leurs tickets ↔ 1 des miens, cas Pisceen).
Un seul lien peut porter `mirror` : deux miroirs, c'est une ambiguïté, pas une richesse.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_registry import Registry, RegistryError, secondaries
from pm_task import get_task_provider

REF_TYPE = "partner_issue"
ROLES = ("mirror", "upstream", "related")
_UNIQUE_ROLES = ("mirror",)          # rôles dont un seul exemplaire a du sens


class PartnerError(Exception):
    """Lien partenaire incohérent (instance non déclarée, doublon, rôle inconnu…)."""


# ── lecture du frontmatter ────────────────────────────────────────────────

def partner_refs(fm):
    """Liens partenaires d'une tâche (liste, éventuellement vide).

    Tolérant : les `refs` d'un autre type (commit, url libre…) sont ignorés, jamais
    une erreur — `refs` est un champ libre par contrat NORMS (`task-links`).
    """
    out = []
    for ref in (fm or {}).get("refs") or []:
        if isinstance(ref, dict) and ref.get("type") == REF_TYPE:
            out.append(ref)
    return out


def find_ref(fm, instance=None, issue_id=None):
    """Premier lien correspondant à (instance, issue_id) — l'un ou l'autre suffit."""
    for ref in partner_refs(fm):
        if instance and ref.get("instance") != instance:
            continue
        if issue_id is not None and str(ref.get("issue_id")) != str(issue_id):
            continue
        return ref
    return None


def mirror_ref(fm):
    """Le lien `mirror` de la tâche (celui qui la représente chez le partenaire)."""
    for ref in partner_refs(fm):
        if ref.get("role") == "mirror":
            return ref
    return None


# ── résolution des secondaires déclarés ───────────────────────────────────

def declared_secondaries(project_meta, registry, axis="task"):
    """{nom d'instance: Resolution} des providers secondaires du projet."""
    return {r.instance.name: r for r in secondaries(project_meta or {}, axis, registry)}


def resolve_secondary(project_meta, registry, instance_name, axis="task"):
    """Resolution du secondaire `instance_name` — erreur explicite s'il n'en est pas un.

    Refuser ici est délibéré : un lien vers une instance non déclarée serait un lien
    qu'aucun outil ne saurait ensuite ni lire ni synchroniser (même esprit que le
    tripwire « résolution projet→Redmine précise », NORMS).
    """
    known = declared_secondaries(project_meta, registry, axis)
    if instance_name in known:
        return known[instance_name]
    if not known:
        raise PartnerError(
            f"aucun provider secondaire déclaré sur l'axe '{axis}' de ce projet — "
            f"ajouter l'instance dans son meta.yml (providers.{axis}[] avec "
            f"role: secondary) avant de rattacher un ticket partenaire")
    raise PartnerError(
        f"instance {instance_name!r} n'est pas un secondaire déclaré de ce projet "
        f"(déclarés : {', '.join(sorted(known))})")


# ── construction / validation d'un lien ───────────────────────────────────

def issue_url(resolution, issue_id):
    """URL humaine du ticket distant, d'après l'URL d'instance du registre."""
    base = (resolution.instance.url or "").rstrip("/")
    return f"{base}/issues/{issue_id}" if base else ""


def build_ref(resolution, issue_id, role="related", url=None, added=None):
    """Construit un item `refs[]` typé `partner_issue` (sans l'écrire)."""
    if role not in ROLES:
        raise PartnerError(f"role {role!r} inconnu (attendus : {', '.join(ROLES)})")
    try:
        iid = int(issue_id)
    except (TypeError, ValueError):
        raise PartnerError(f"issue_id doit être un entier (reçu : {issue_id!r})")
    return {
        "type": REF_TYPE,
        "instance": resolution.instance.name,
        "issue_id": iid,
        "url": url or issue_url(resolution, iid),
        "role": role,
        "last_seen_journal_id": None,
        "added": (added or date.today().isoformat()),
    }


def check_addition(fm, new_ref):
    """Vérifie qu'ajouter `new_ref` garde la liste cohérente. Lève `PartnerError`.

    Deux règles :
      * pas deux fois le même (instance, issue_id) — un lien n'a pas de multiplicité ;
      * pas deux `mirror` — « mon ticket vu de chez eux » est unique par construction.
    """
    for ref in partner_refs(fm):
        same = (ref.get("instance") == new_ref["instance"]
                and str(ref.get("issue_id")) == str(new_ref["issue_id"]))
        if same:
            raise PartnerError(
                f"lien déjà présent : {new_ref['instance']}#{new_ref['issue_id']}")
        if new_ref["role"] in _UNIQUE_ROLES and ref.get("role") == new_ref["role"]:
            raise PartnerError(
                f"un lien '{new_ref['role']}' existe déjà "
                f"({ref.get('instance')}#{ref.get('issue_id')}) — un ticket n'a qu'un "
                f"miroir ; utiliser role=related pour un lien supplémentaire")


def validate_refs(fm, project_meta=None, registry=None, axis="task"):
    """Contrôle les `partner_issue` d'une tâche → liste de messages d'erreur.

    Sans registre/meta, ne valide que la **forme** (champs, types, unicité) : c'est ce
    que fait `validate-task.py`, qui travaille fichier par fichier sans contexte projet.
    """
    errs = []
    refs = partner_refs(fm)
    seen, mirrors = set(), 0
    for i, ref in enumerate(refs):
        where = f"refs[{i}] (partner_issue)"
        inst = ref.get("instance")
        if not inst:
            errs.append(f"{where} : champ 'instance' obligatoire")
        iid = ref.get("issue_id")
        if iid is None or (isinstance(iid, bool)) or not str(iid).lstrip("-").isdigit():
            errs.append(f"{where} : 'issue_id' doit être un entier (reçu : {iid!r})")
        role = ref.get("role", "related")
        if role not in ROLES:
            errs.append(f"{where} : role invalide {role!r} (attendus : {', '.join(ROLES)})")
        if role == "mirror":
            mirrors += 1
        key = (inst, str(iid))
        if key in seen:
            errs.append(f"{where} : lien en double ({inst}#{iid})")
        seen.add(key)
        if registry is not None:
            try:
                resolve_secondary(project_meta, registry, inst, axis)
            except (PartnerError, RegistryError) as e:
                errs.append(f"{where} : {e}")
    if mirrors > 1:
        errs.append(f"refs : {mirrors} liens 'mirror' — un ticket n'a qu'un miroir")
    return errs


# ── note de rattachement chez le partenaire ───────────────────────────────

def link_note(rm_id, title, url=""):
    """Note posée chez le partenaire au rattachement — **gabarit fermé**.

    Volontairement pauvre : identité du ticket, titre, URL. Rien d'interne (chemin,
    hôte, branche, secret) ne doit sortir du périmètre iProspective — une note poussée
    chez un tiers ne se rattrape pas (CDC RM2626 § pièges).
    """
    line = f"Suivi iProspective : RM{rm_id} — {title}".rstrip(" —")
    return f"{line}\n{url}".strip() if url else line


def post_link_note(resolution, issue_id, rm_id, title, url="", dry_run=False):
    """Poste la note de rattachement sur le ticket distant. Retourne le texte posté.

    Best-effort par contrat : l'appelant décide quoi faire de l'échec — un partenaire
    injoignable ne doit jamais empêcher de poser le lien de notre côté.
    """
    note = link_note(rm_id, title, url)
    if dry_run:
        return note
    provider = get_task_provider(instance=resolution.instance)
    provider.add_note(issue_id, note)
    return note


# ── pull : ce qui se dit chez le partenaire (N1, RM2655) ──────────────────
#
# Lecture SEULE, et le résultat n'atterrit QUE dans le `.log.md` : le statut, la
# priorité et l'assignation restent au provider primaire. Un partenaire ne décide de
# rien chez nous — il informe.

_NOTE_MAX = 2000          # au-delà, la note importée est tronquée (le journal reste lisible)


def pull_enabled(resolution):
    """(notes, status) — ce que le secondaire autorise à importer.

    Défaut permissif sur les notes (c'est l'intérêt du rattachement) et sur le statut :
    les deux sont de la lecture pure. Un projet coupe explicitement via
    `sync.pull: {notes: false, status: false}`.
    """
    pull = (resolution.sync or {}).get("pull")
    if pull is None:
        return True, True
    if pull is False:
        return False, False
    return bool(pull.get("notes", True)), bool(pull.get("status", True))


def fetch_remote(resolution, issue_id, provider=None):
    """Ticket distant, journaux inclus. `provider` injectable (tests hors réseau)."""
    provider = provider or get_task_provider(instance=resolution.instance)
    return provider.fetch_issue(issue_id, include="journals")


def extract_updates(issue, since_journal_id=None, last_status=None):
    """Nouveautés d'un ticket distant depuis le dernier passage.

    Retourne `{notes, last_journal_id, status, status_changed}` :
      * `notes` — journaux **porteurs d'un commentaire** et plus récents que le
        pointeur ; les journaux purement techniques (changement de champ) sont ignorés,
        ils ne nous apprennent rien d'utile ;
      * `last_journal_id` — nouveau pointeur (max des journaux vus, y compris ceux sans
        note : sinon on les relirait à chaque passage) ;
      * `status` / `status_changed` — statut **brut** du partenaire (leur libellé, pas
        un état NORMS : leurs workflows ne sont pas les nôtres).
    """
    journals = sorted((issue.get("journals") or []), key=lambda j: j.get("id") or 0)
    since = since_journal_id or 0
    fresh = [j for j in journals if (j.get("id") or 0) > since]
    notes = [j for j in fresh if (j.get("notes") or "").strip()]
    last_id = max([j.get("id") or 0 for j in journals] + [since]) or None
    status = ((issue.get("status") or {}).get("name") or "").strip()
    return {
        "notes": notes,
        "last_journal_id": last_id,
        "status": status,
        "status_changed": bool(status) and status != (last_status or ""),
    }


def format_pull_entry(ref, updates, remote_title=""):
    """Rend l'entrée `.log.md` d'un pull — ou `""` s'il n'y a rien à écrire.

    Le contenu venu de chez le partenaire est **cité** (`> `) et l'en-tête nomme
    l'instance : en relisant le journal, on doit voir d'un coup d'œil ce qui vient de
    nous et ce qui vient d'ailleurs.
    """
    if not updates["notes"] and not updates["status_changed"]:
        return ""
    who = f"{ref.get('instance')}#{ref.get('issue_id')}"
    lines = [f"Source : **{who}** (gestionnaire partenaire, lecture seule)"]
    if remote_title:
        lines.append(f"Ticket distant : {remote_title}")
    if updates["status_changed"]:
        lines.append(f"Statut chez eux : **{updates['status']}** "
                     f"(brut — non répercuté sur le statut NORMS)")
    for j in updates["notes"]:
        author = ((j.get("user") or {}).get("name") or "?").strip()
        when = (j.get("created_on") or "")[:16].replace("T", " ")
        lines.append("")
        lines.append(f"Note #{j.get('id')} — {author}{f' — {when}' if when else ''} :")
        text = (j.get("notes") or "").strip()
        if len(text) > _NOTE_MAX:
            text = text[:_NOTE_MAX] + f"\n… (tronqué, {len(j['notes'])} caractères)"
        for nl in text.splitlines():
            lines.append(f"> {nl}" if nl else ">")
    return "\n".join(lines) + "\n"


def pull_ref(resolution, ref, provider=None):
    """Pull d'UN lien → `(updates, remote_title)`. N'écrit rien (l'appelant décide)."""
    notes_ok, status_ok = pull_enabled(resolution)
    issue = fetch_remote(resolution, ref.get("issue_id"), provider=provider)
    updates = extract_updates(issue,
                              since_journal_id=ref.get("last_seen_journal_id"),
                              last_status=ref.get("last_seen_status"))
    if not notes_ok:
        updates["notes"] = []
    if not status_ok:
        updates["status"], updates["status_changed"] = "", False
    return updates, (issue.get("subject") or "").strip()


def apply_pointers(ref, updates):
    """Avance les pointeurs du lien après un pull réussi. Retourne True si modifié.

    Le pointeur vit **dans le lien**, jamais dans `redmine_last_journal_id` : ce dernier
    suit l'instance primaire, et les deux boucles se marcheraient dessus.
    """
    changed = False
    if updates.get("last_journal_id") and \
            updates["last_journal_id"] != ref.get("last_seen_journal_id"):
        ref["last_seen_journal_id"] = updates["last_journal_id"]
        changed = True
    if updates.get("status") and updates["status"] != ref.get("last_seen_status"):
        ref["last_seen_status"] = updates["status"]
        changed = True
    return changed


# ── politique de rattachement (link.policy) ───────────────────────────────

def required_secondaries(project_meta, registry, axis="task"):
    """Secondaires dont `link.policy == required` — tout ticket doit y être rattaché."""
    return [r for r in secondaries(project_meta or {}, axis, registry)
            if (r.link or {}).get("policy") == "required"]


def missing_links(fm, project_meta, registry, axis="task"):
    """Instances `required` auxquelles cette tâche n'est PAS rattachée.

    Alimente `pm-doctor` : c'est le contrôle qui rend `policy: required` opérant
    (cas MatNat — « tout ce que je fais doit être rattaché chez eux »).
    """
    linked = {ref.get("instance") for ref in partner_refs(fm)}
    return [r.instance.name for r in required_secondaries(project_meta, registry, axis)
            if r.instance.name not in linked]
