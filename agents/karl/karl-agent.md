# karl-agent — superviseur de sessions (backend karl-pm)

> Ticket : **RM1771** (enfant de l'épic RM1802). Couche 2 de l'archi 3-couches du
> système PM (façade web RM1679 · **superviseur RM1771** · orchestrateur RM1669).
> Design validé par le POC du spike RM1803.

## Rôle

`karl-agent` héberge chaque **session d'agent** (un chef de projet travaillant sur
un ticket) dans une **session tmux nommée** `karl-RM<id>`. tmux sert d'hôte
universel : il donne gratuitement la persistance, la **reprise de main humaine**
(`tmux attach`), l'injection d'entrée (`send-keys`) et la lecture d'écran
(`capture-pane`). Le daemon expose une petite API HTTP au-dessus de ces primitives.

C'est un **superviseur de cycle de vie de sessions**, pas l'orchestrateur :
il ne sérialise aucune écriture sur le repo PM (ça, c'est RM1669) et ne décide pas
quoi lancer (à terme, dispatcher RM1824). Il exécute des ordres `spawn/send/...`.

## Emplacements

| Quoi | Chemin |
|---|---|
| Daemon | `scripts/karl-agent.py` (stdlib-only, aucune dépendance) |
| Units systemd | `deploy/karl-agent/{karl-agent,karl-agent-tunnel}.service` |
| Installeur | `deploy/karl-agent/install.sh` |
| Logs pipe-pane | `$XDG_STATE_HOME/karl-agent/karl-RM<id>.log` (déf. `~/.local/state/karl-agent/`) |
| Logs daemon | `journalctl --user -u karl-agent -f` |

## Où ça tourne

- **Daemon** : dans le LXC `dev` (MathouDell), service systemd **user** de `mathieu`.
  Bind `127.0.0.1:9876`.
- **Tunnel** : `karl-agent-tunnel.service` (autossh) ouvre un **reverse tunnel**
  `dev → mmi` qui réexpose le port sur `127.0.0.1:9876` **côté mmi** — d'où la
  façade web / le bot Telegram (hébergés sur l'infra OVH) peuvent piloter les
  sessions sans bind public.

## API (JSON, `http://127.0.0.1:9876`)

| Méthode | Route | Corps / params | Réponse |
|---|---|---|---|
| GET | `/health` | — | `{status, sessions, tmux}` |
| GET | `/sessions` | — | `{sessions:[{rm_id, tmux, created, attached}]}` |
| POST | `/spawn` | `{rm_id, cwd?, engine?, prompt?, width?, height?}` | `201 {rm_id, tmux, engine, cwd, created}` |
| POST | `/send` | `{rm_id, msg, enter?=true}` | `{rm_id, sent}` |
| GET | `/capture/<rm_id>` | `?lines=N` (historique) | `text/plain` (snapshot du pane) |
| GET | `/stream/<rm_id>` | — | `text/event-stream` (tail du pipe-pane, SSE) |
| POST | `/kill` | `{rm_id}` | `{rm_id, killed}` |

- `engine` ∈ `{claude, shell}` (templates serveur ; défaut `claude`). Le moteur
  réel de `claude` est `KARL_AGENT_SPAWN_CMD` (déf. `claude`).
- `prompt` est livré **après** le spawn via `send-keys` (jamais concaténé dans la
  ligne de commande lancée par tmux).
- Codes : `400` (entrée invalide), `401` (token manquant), `404` (session absente),
  `409` (session déjà active), `500` (échec tmux).

### Exemples

```bash
curl -s http://127.0.0.1:9876/health
curl -s -X POST http://127.0.0.1:9876/spawn \
  -d '{"rm_id":"1669","cwd":"/zfs/workspaces/ai/project-management","engine":"claude"}'
curl -s -X POST http://127.0.0.1:9876/send -d '{"rm_id":"1669","msg":"traite la tâche RM1669"}'
curl -s "http://127.0.0.1:9876/capture/1669?lines=200"
curl -sN http://127.0.0.1:9876/stream/1669      # SSE live
curl -s -X POST http://127.0.0.1:9876/kill -d '{"rm_id":"1669"}'
# reprise de main humaine, directement sur dev :
tmux attach -t karl-RM1669
```

## Sécurité — invariants

1. **Bind `127.0.0.1` EN DUR.** `HOST` n'est pas configurable vers une adresse
   publique (critère d'acceptation RM1771). L'exposition vers `mmi` passe
   uniquement par le tunnel SSH.
2. **Bind distant `127.0.0.1` côté mmi.** L'unit tunnel utilise
   `-R 127.0.0.1:9876:127.0.0.1:9876` — jamais `-R 9876:...` (qui, selon
   `GatewayPorts`, pourrait binder `0.0.0.0`).
3. **Pas d'injection.** `rm_id` validé `^[0-9]+$` avant interpolation dans le nom
   de session ; `/send` utilise `send-keys -l --` (texte littéral, aucune
   interprétation de noms de touches) ; `cwd` est `realpath`-é et contraint sous
   `KARL_AGENT_ALLOWED_ROOTS` (déf. `/zfs/workspaces`).
4. **Pas de commande shell arbitraire client.** La commande lancée vient d'un
   template serveur sélectionné par `engine`.
5. **Token partagé optionnel.** Si `KARL_AGENT_TOKEN` est défini (dans le `.env`
   gitignored du repo), toute requête doit porter l'en-tête `X-Karl-Token`.
   Défense en profondeur côté `mmi` où le port est sur le localhost partagé.

## Variables d'environnement

Chargées depuis `<repo>/.env` (gitignored) ou l'environnement du service.

| Variable | Défaut | Rôle |
|---|---|---|
| `KARL_AGENT_PORT` | `9876` | Port d'écoute (toujours sur 127.0.0.1). |
| `KARL_AGENT_TOKEN` | _(vide)_ | Si défini, exige l'en-tête `X-Karl-Token`. |
| `KARL_AGENT_SPAWN_CMD` | `claude` | Commande du moteur `claude`. |
| `KARL_AGENT_DEFAULT_ENGINE` | `claude` | Moteur par défaut au spawn. |
| `KARL_AGENT_ALLOWED_ROOTS` | `/zfs/workspaces` | Racines autorisées pour `cwd` (`:`-séparées). |
| `KARL_AGENT_DEFAULT_CWD` | _(repo)_ | cwd si non fourni au spawn. |
| `KARL_AGENT_WIDTH` / `_HEIGHT` | `200` / `50` | Géométrie du pane tmux. |
| `KARL_AGENT_LOG_DIR` | `~/.local/state/karl-agent` | Logs pipe-pane (alimente `/stream`). |

## Installation (sur le LXC `dev`)

```bash
ssh mathieu@dev.lxc
cd /zfs/workspaces/ai/project-management
bash deploy/karl-agent/install.sh
```

L'installeur : vérifie les prérequis, teste l'alias `ssh mmi`, copie les units dans
`~/.config/systemd/user/`, active le **linger** (`loginctl enable-linger mathieu`,
pour survivre aux reboots sans session ouverte), puis `enable --now` les deux
services.

### deploy_actions (manuel, une fois)

- [ ] Installer sur `dev` : `tmux`, `autossh`, et un moteur (`claude` ou `opencode`).
      `python3` est déjà présent. (`sudo apt install tmux autossh`)
- [ ] Configurer l'alias SSH `mmi` + clé autorisée **dans le `~/.ssh/config` de
      `dev`** (l'host MathouDell l'a déjà ; le conteneur `dev` est distinct).
- [ ] `loginctl enable-linger mathieu` sur `dev` (fait par l'installeur ; peut
      nécessiter root une fois).
- [ ] (Optionnel) Définir `KARL_AGENT_TOKEN=<aléa>` dans `<repo>/.env` pour activer
      l'auth par en-tête.

## Troubleshooting

| Symptôme | Piste |
|---|---|
| `/health` KO en local | `journalctl --user -u karl-agent -f` ; le service est-il `active` ? |
| `tmux:false` dans `/health` | `tmux` absent du PATH du service. |
| `curl` depuis mmi KO | tunnel : `systemctl --user status karl-agent-tunnel` ; `ssh mmi` marche-t-il depuis `dev` ? |
| Service mort après reboot | linger pas activé : `loginctl enable-linger mathieu`. |
| `409` au spawn | session déjà active — `/kill` d'abord, ou `/send` dessus. |
| `400 cwd hors racines` | le `cwd` demandé n'est pas sous `KARL_AGENT_ALLOWED_ROOTS`. |
| Tunnel se rebind sur 0.0.0.0 | vérifier `-R 127.0.0.1:9876:...` (et `GatewayPorts` côté sshd mmi). |

## Pistes / évolutions (hors v1)

- **`/stream` structuré** : aujourd'hui `/stream` tail le pipe-pane (octets de
  terminal bruts, ANSI). Pour une vue « chat » propre côté web, exposer le flux
  structuré du moteur (`claude --output-format stream-json` : events
  system/init / assistant / result) plutôt que parser l'écran. Décider du modèle
  d'entrée (TUI interactif pour l'attach **vs** stdin stream-json headless) — non
  conciliables sur un même process : à arbitrer avec RM1669/RM1679.
- **Détection « session bloquée »** : poller `claude agents --json` (champ
  `waitingFor`) pour le relais permission/aide → brique RM1824.
- **Moteur opencode** : `opencode serve` (API `/event` SSE, `/question` +
  `/permission` structurés, attach natif, autonomie par PermissionRuleset).
  Attention : `opencode run` headless **hang** si une permission est « ask »
  (GH #16367/#17516) → imposer des rulesets allow/deny. Voie programmatique = SDK JS/TS.
