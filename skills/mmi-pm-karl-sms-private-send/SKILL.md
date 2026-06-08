---
name: mmi-pm-karl-sms-private-send
description: Envoie un SMS de notification PRIVÉ (uniquement vers la ligne Free Mobile du compte, pas de destinataire arbitraire) via l'API Free Mobile. Canal de secours pour alerter sans Data. Secrets dans .env, jamais loggués. Append au .log.md du ticket si RM-id fourni. Usage : "/mmi-pm-karl-sms-private-send -m 'alerte'", ou langage naturel "envoie-moi un SMS pour dire que le build est KO", "préviens-moi par SMS quand X".
allowed-tools: Bash, Read
---

# Skill : mmi-pm-karl-sms-private-send

Wrapper contextuel autour de `scripts/karl-sms-private-send.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Nature : connecteur PRIVÉ

L'API Free Mobile n'envoie **que vers la ligne Free Mobile du compte** (celle de Mathieu). Il n'y a **pas de destinataire** à fournir : c'est un canal de notification vers soi, par construction. Pour un SMS vers un tiers (client, etc.), c'est un autre connecteur à venir (API OVH ou autre) — ne pas détourner celui-ci.

## Quand déclencher

- "envoie-moi un SMS ...", "préviens-moi par SMS que ...", "SMS d'alerte ..."
- "alerte-moi par SMS quand <condition>" (penser à coupler avec `/loop` ou un hook si surveillance)
- `/mmi-pm-karl-sms-private-send -m ...`

Cas d'usage typique : **urgence / canal de secours sans Data** (le SMS passe par le réseau opérateur, pas par Internet côté destinataire).

## Pré-requis

- `.env` du repo PM contient `SMS_FREE_USER` (identifiant Free à 8 chiffres) **et** `SMS_FREE_TOKEN` (clé générée).
- Le service « Notifications par SMS » doit être activé dans l'espace abonné Free Mobile, sinon l'API renvoie **403**.

Si une variable manque, le script abort avec un message clair → relayer à l'utilisateur.

## Invocation

```bash
scripts/karl-sms-private-send.py \
  --message "<texte>" [--rm-id <id>] [--dry-run]
```

- `--message` / `-m` : texte du SMS, ou `-` pour lire stdin (corps multiligne via heredoc).
- `--rm-id` : append une entrée au `.log.md` du ticket.
- `--dry-run` : n'envoie rien, affiche ce qui serait envoyé (utile pour vérifier que les creds sont lues).

## Exemples

```bash
# Alerte simple
./karl-sms-private-send.py -m "Build prod KO, intervention requise"

# Lié à un ticket — append au .log.md
./karl-sms-private-send.py -m "RM1234 livré en prod" --rm-id 1234

# Multiligne via heredoc
./karl-sms-private-send.py -m - <<'EOF'
Cron de sauvegarde en échec.
Voir /var/log/backup.log
EOF

# Vérif sans envoi
./karl-sms-private-send.py -m "test" --dry-run
```

## Notes

- **Rate-limit Free** : l'API renvoie **402** si trop de SMS rapprochés. Réserver aux vraies notifications/urgences, ne pas spammer.
- Codes d'erreur gérés avec message clair : 400 (param manquant), 402 (rate-limit), 403 (service non activé / clé invalide), 500 (serveur Free).
- Free tronque au-delà d'~1000 caractères (le script avertit sans bloquer).
- Pas de Vaultwarden ici (secrets en `.env`, contrairement au connecteur mail).
