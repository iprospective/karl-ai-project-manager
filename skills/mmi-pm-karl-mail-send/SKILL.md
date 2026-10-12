---
name: mmi-pm-karl-mail-send
description: Envoie un email depuis karl@iprospective.fr via SMTP iProspective (Postfix, port 465), et copie le message envoyé dans le dossier Sent via IMAP APPEND. Credentials Vaultwarden, jamais loggués. Append automatique au .log.md du ticket si RM-id fourni. Usage : "/mmi-pm-karl-mail-send --to a@b.fr --subject 'X' --body 'Y'", ou langage naturel "envoie un mail à client@x.fr depuis karl pour dire que RM1234 est livré".
allowed-tools: Bash, Read, AskUserQuestion
---

# Skill : mmi-pm-karl-mail-send

Wrapper contextuel autour de `scripts/karl-mail-send.py`. Suit la convention `mmi-pm-<entité>-<action>` (cf. `memory/feedback_mmi_pm_skill_naming`).

## Quand déclencher

- "envoie un mail à <addr> ...", "préviens <addr> par mail que ..."
- "mail à <addr> depuis karl ...", "réponds au client par mail ..."
- "envoie un compte-rendu de RM<id> par mail à ..."
- `/mmi-pm-karl-mail-send --to ...`

## Pré-requis

- **Vault déverrouillé** : socket `vault-agentd.sock` actif. Si non, l'utilisateur doit lancer `scripts/unlock-vault.sh [-i <instance>]` (secret humain requis — master password ou passphrase —, l'agent ne demande jamais).
- **Item du vault** : `secret://vw-ipro/iprospective-agents/karl-mail` doit exister avec `username` et `password` (la forme `vaultwarden://…` reste valide).

Si le vault est locked au moment de l'appel, le script abort avec un message clair → relayer à l'utilisateur.

## Désambiguïsation systématique

Avant le premier envoi d'une session, **toujours demander** via `AskUserQuestion` :

1. Le contenu exact du `--body` / `--markdown` (relire avant envoi — un mail est irréversible) et les pièces jointes
2. Le `--subject` (et confirmer le préfixe `[RM<id>]` si lié à un ticket)
3. Si `--cc` ou `--bcc` sont pertinents (par défaut aucun)

Ne **jamais** envoyer en confiance sans relecture. Un mail mal formé représente l'iProspective côté client.

## Invocation

```bash
scripts/karl-mail-send.py \
  --to <addr> [--to <addr2>] [--cc <addr>] [--bcc <addr>] \
  --subject "<sujet>" (--body "<corps>" [--html-file <f.html>] | --markdown <f.md>) \
  [--attach <fichier> ...] \
  [--rm-id <id>] [--reply-to <addr>] [--in-reply-to <message-id>] [--dry-run]
```

Le `--body -` lit depuis stdin (utile pour les corps multilignes via heredoc).

**Corps riche et pièces jointes (RM3440)** :
- `--markdown <f.md>` — le texte du mail est le markdown, la version HTML en est le rendu
  (tableaux, titres, listes, gras/italique, liens ; styles en ligne, même rendu que les
  notifications client). **À préférer dès que le contenu a des tableaux** : en texte brut
  ils arrivent illisibles. Exclusif de `--body` et `--html-file`.
- `--html-file <f.html>` — alternative HTML fournie telle quelle, `--body` restant le repli texte (RM3052).
- `--attach <fichier>` — pièce jointe, répétable ; type deviné depuis l'extension, nom
  accentué encodé correctement. Total plafonné à 20 Mo (`PM_MAIL_ATTACH_MAX_MB`) : refus
  AVANT envoi, comme pour un fichier absent.
- `--dry-run` montre alors la **structure MIME** (parties, types, tailles) et le corps texte, sans le base64.

## Exemples

```bash
# Envoi minimal
./karl-mail-send.py --to client@x.fr --subject "Suivi RM1234" --body "Texte..."

# Lié à un ticket — append au .log.md
./karl-mail-send.py --to client@x.fr --subject "Avancement" --body "..." --rm-id 1234

# Corps multilignes via heredoc
./karl-mail-send.py --to c@x.fr --subject S --body - <<'EOF'
Bonjour,

Plusieurs paragraphes ici.

Cordialement,
Karl
EOF

# Réponse en thread RFC (chainage In-Reply-To/References)
./karl-mail-send.py --to c@x.fr --subject "Re: question" \
  --in-reply-to "<abc@example.com>" --body "Réponse..."

# Rapport markdown (tableaux) + tableur en pièce jointe
./karl-mail-send.py --to c@x.fr --subject "Rapport" --markdown rapport.md \
  --attach ecarts.csv --rm-id 1234

# Test sans envoi réel (pas besoin du vault)
./karl-mail-send.py --to test@x.fr --subject T --body "..." --dry-run
```

## Notes

- `From:` est toujours `Karl (iProspective Agent) <karl@iprospective.fr>` (l'agent ne peut pas se faire passer pour quelqu'un d'autre)
- `BCC` n'apparaît pas dans les headers reçus (comme attendu RFC) mais est listé dans le `.log.md` local
- Subject auto-préfixé `[RM<id>]` si `--rm-id` (sauf si déjà préfixé)
- Après l'envoi SMTP, le message est ré-appendé dans le dossier `Sent` du compte via IMAP (mêmes credentials). Non bloquant : un échec d'APPEND ne fait pas échouer l'envoi, juste un warning sur stderr (le mail est déjà parti).
- Le `.log.md` du ticket journalise la partie TEXTE et la liste des pièces jointes (nom, taille), pas le HTML.
- Pas de réception ici : la relève IMAP est `karl-mail-fetch.py` (RM2668).
