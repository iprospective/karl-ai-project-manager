---
name: mmi-pm-deliver
description: Livre un ticket en UN appel — vérifie/coche les critères, exige le protocole de test, résout requires_agent_test (→ a_tester_dev ou a_tester_demandeur + réattribution), note de livraison templatée + résumé rédigé, report conso. Usage : "/mmi-pm-deliver 2364" ou "livre RM2364", "c'est prêt à tester".
allowed-tools: Bash, Read
---

# Skill : mmi-pm-deliver

Wrapper contextuel autour de `scripts/pm-task-deliver.py` (RM2364, CDC RM2316 § S3).
Encapsule la séquence canonique de livraison — la note mécanique est templatée,
l'agent ne rédige QUE le résumé (`--summary -`).

## Quand déclencher

- « livre / je livre / c'est prêt / deliver RM<id> », fin de dev d'un ticket.
- `/mmi-pm-deliver <id>`

## Invocation

```bash
scripts/pm-task-deliver.py <RM-id> --summary - <<'EOF'
<résumé de livraison rédigé : quoi, comment vérifié, points d'attention>
EOF
```

Options : `--check n,…` / `--check-all` (cocher la checklist d'abord — seulement
si le travail correspondant est réellement fait), `--protocol <texte>` si le
ticket n'a pas encore de protocole de test (le rédiger AVANT est mieux :
`pm-task-protocol.py <id> --set -`), `--no-report`.

## Gardes (rappel NORMS)

- Critères non cochés → refus : cocher n'est pas un geste administratif, c'est l'attestation que c'est fait.
- Protocole de test obligatoire : le testeur doit savoir QUOI tester (RM2229).
- `requires_agent_test=demander` → le script refuse : poser la question au demandeur, rester en_cours.
- La branche doit être poussée et la MR créée avant de livrer (`pm-mr create <id>`), sinon la merge-gate refusera la validation en aval (RM2319).
