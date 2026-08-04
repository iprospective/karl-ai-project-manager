#!/usr/bin/env python3
"""pm-task-deliver — livraison d'un ticket en UN appel (RM2364, CDC RM2316 § S3).

Compose la séquence canonique « je livre » (aujourd'hui 3–5 appels) :

  1. critères d'acceptation : vérifie qu'ils sont tous cochés
     (--check n,… / --check-all pour cocher d'abord via pm-task-description-update) ;
  2. protocole de test : exigé (frontmatter test_protocol) — sinon le fournir
     via --protocol - (stdin, posé par pm-task-protocol) ;
  3. résolution requires_agent_test (tâche → défaut projet → défaut système
     `non`) → transition a_tester_dev ou a_tester_demandeur, avec la
     réattribution NORMS portée par pm-task-status-update ;
  4. note de livraison : partie mécanique templatée (livrables outputs[],
     branche/MR, protocole posé) + la partie RÉDIGÉE via --summary - (stdin)
     — la seule que l'agent écrit ;
  5. report conso (pm-task-report --apply), sauf --no-report.

`demander` non résolu en mode non interactif → refus explicite (règle NORMS).

Usage :
    pm-task-deliver.py <RM-id> --summary -                # résumé sur stdin
    pm-task-deliver.py <RM-id> --check-all --summary - --protocol -
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
from pm_markdown import checklist_lines

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def run_step(label, cmd, stdin_text=None, required=True):
    r = subprocess.run([sys.executable] + cmd, capture_output=True, text=True,
                       input=stdin_text)
    detail = "\n".join(s.rstrip() for s in (r.stdout, r.stderr) if s and s.strip())
    out.info(detail)
    if r.returncode != 0 and required:
        out.fail(f"{label} (exit {r.returncode}) :\n{detail}",
                 remede="reprendre l'étape avec le script unitaire (--verbose pour le détail)")
    return r


def load(cfg, rm_id):
    md = cfg.find_task(rm_id)
    if not md:
        out.fail(f"fichier RM{rm_id}_*.md introuvable")
    m = FM_RE.match(md.read_text(encoding="utf-8"))
    return md, (yaml.safe_load(m.group(1)) or {}), m.group(2)


def resolve_agent_test(fm, md):
    v = str(fm.get("requires_agent_test") or "default")
    if v == "default":
        try:  # défaut projet : project/overview.md :: defaults.requires_agent_test
            ov = md.parent.parent / "project" / "overview.md"
            m = FM_RE.match(ov.read_text(encoding="utf-8"))
            v = str(((yaml.safe_load(m.group(1)) or {}).get("defaults") or {})
                    .get("requires_agent_test") or "non")
        except Exception:
            v = "non"
    return v


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--summary", required=True,
                    help="Résumé de livraison rédigé ('-' = stdin) — la partie sémantique de la note")
    ap.add_argument("--check", metavar="N[,N…]", help="Cocher ces items de checklist d'abord")
    ap.add_argument("--check-all", action="store_true", help="Cocher toute la checklist d'abord")
    ap.add_argument("--protocol", help="Protocole de test ('-' = stdin) si absent du ticket")
    ap.add_argument("--no-report", action="store_true", help="Ne pas pousser le report conso")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    summary = sys.stdin.read().strip() if args.summary == "-" else args.summary
    if not summary:
        out.fail("--summary vide : la note de livraison exige un résumé rédigé")

    cfg = PMConfig.load()
    md, fm, body = load(cfg, args.rm_id)

    # 1. checklist
    if args.check or args.check_all:
        cmd = [str(here / "pm-task-description-update.py"), str(args.rm_id)]
        cmd += ["--check-all"] if args.check_all else ["--check", args.check]
        run_step("pm-task-description-update", cmd)
        md, fm, body = load(cfg, args.rm_id)
    # Mêmes règles que le cochage (RM2540) : une case citée dans un bloc de code
    # n'est pas un critère, et bloquerait la livraison sans que personne puisse
    # la cocher.
    unchecked = [m.group(3)[1:].strip()          # group(3) = « ]texte »
                 for _, m in checklist_lines(body) if m.group(2) == " "]
    if unchecked:
        out.fail(f"{len(unchecked)} critère(s) non coché(s) : "
                 + " ; ".join(t[:50] for t in unchecked[:3]),
                 remede=f"pm-task-deliver.py {args.rm_id} --check <n,…> (ou --check-all) après vérification")

    # 2. protocole de test
    if str(fm.get("test_protocol") or "").strip() in ("", "None"):
        if not args.protocol:
            out.fail("pas de protocole de test sur le ticket",
                     remede=f"relancer avec --protocol - (stdin) ou pm-task-protocol.py {args.rm_id} --set -")
        proto = sys.stdin.read().strip() if args.protocol == "-" and args.summary != "-" \
            else (args.protocol if args.protocol != "-" else None)
        if proto is None:
            out.fail("--protocol - et --summary - sont exclusifs (un seul stdin) — passer le protocole en argument ou le poser avant via pm-task-protocol")
        run_step("pm-task-protocol", [str(here / "pm-task-protocol.py"), str(args.rm_id), "--set", proto])

    # 3. résolution du routage de test
    v = resolve_agent_test(fm, md)
    if v == "demander":
        out.fail("requires_agent_test=demander : le demandeur doit trancher la voie de test",
                 remede="rester en en_cours et poser la question (règle NORMS § passe agent-testeur)")
    target = "a_tester_dev" if v == "oui" else "a_tester_demandeur"

    # 4. note de livraison : bloc mécanique templaté + résumé rédigé
    git = fm.get("git") or {}
    outputs = fm.get("outputs") or []
    lines = [summary, ""]
    if outputs:
        lines.append("Livrables : " + " · ".join(str(o) for o in outputs))
    if git.get("branch") or git.get("mr_url"):
        lines.append(f"Git : branche={git.get('branch') or '—'} MR={git.get('mr_url') or '—'}")
    lines.append("Protocole de test : sur le ticket (CF « Protocole de test »).")
    note = "\n".join(lines)

    run_step("pm-task-status-update", [str(here / "pm-task-status-update.py"),
                                       str(args.rm_id), target, "--note", note])
    out.op("livraison", rm=args.rm_id, extra=f"→ {target} (agent_test={v})")

    # 5. report conso
    if not args.no_report:
        run_step("pm-task-report", [str(here / "pm-task-report.py"),
                                    "--rm-id", str(args.rm_id), "--apply"], required=False)


if __name__ == "__main__":
    main()
