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
| Units systemd | `deploy/karl-agent/{karl-agent,karl-agent-tunnel,ttyd}.service` |
| Cockpit web (RM1873) | `deploy/karl-agent/cockpit/{index.html,attach-karl.sh}` |
| Installeur | `deploy/karl-agent/install.sh` |
| Désinstalleur | `deploy/karl-agent/uninstall.sh` |
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
| GET | `/` `/cockpit` | — | `text/html` (cockpit web v0) — **public** |
| GET | `/cockpit-config` | — | `{ttyd_base, auth_required}` — **public** |
| GET | `/health` | — | `{status, sessions, tmux}` |
| GET | `/sessions` | `?engine=&client=&project=` | `{sessions:[{rm_id, tmux, created, attached, engine?, session_id?, client?, project?, state}]}` — enrichi via l'index sessions⇄tickets (RM1939) ; `state` ∈ `working|attention|idle` (heuristique capture-pane, intérim RM1874 — RM2140) |
| GET | `/resumable` | `?engine=&client=&project=&status=wip\|done\|not-done&q=&limit=` | `{resumable:[{engine, session_id, title, mark, cwd, mtime, client, project, tickets, live}]}` — sessions reprenables découvertes dans les stores claude (`KARL_AGENT_CLAUDE_STORES`, défaut `~/.claude/projects`) ; `mark` = marqueur `[WIP]`/`[DONE]` posé par `/session-mark` ; projet déduit du `.mmi-pm` du cwd (RM1939) |
| POST | `/resume` | `{session_id?, rm_id?, n?, prompt?}` | `201 {rm_id, tmux, engine, session_id, cwd, resumed}` — relance `claude --resume <sid>` dans un tmux neuf au cwd d'origine ; ancrage : ticket `RM<id>` = idéal (jonction écrite), slug accepté, ABSENT = dernier ticket lié sinon slug auto dérivé du titre (RM2144). 409 si tmux vivant, 410 si transcript purgé/cwd invalide (RM1939) |
| POST | `/session-set` | `{group?="default"}` | `{user, group, count, saved_at, entries}` — enregistre un **instantané des sessions vivantes** dans le jeu (user, groupe) ; écrase le groupe en préservant `autostart` ; plafond `SESSION_SET_MAX` (RM2395) |
| GET | `/session-set` | `?group=default` | `{user, group, exists, saved_at, autostart, count, entries:[{sid, engine, session_id, cwd, model, alive}]}` — relit le jeu + état `alive` par entrée (RM2395) |
| POST | `/session-set/relaunch` | `{group?="default", spawn?=false}` | `{user, group, counts, report:[{sid, action, error?}]}` — relance en lot **idempotente** : `skipped` (déjà vivante) / `resumed` (reprise native) / `spawned` (fallback neuf, **opt-in** `spawn:true` seulement) / `failed`. Séquentiel + temporisé (RM2395) |
| POST | `/session-set/autostart` | `{group?="default", autostart}` | `{user, group, autostart}` — (dé)marque le jeu pour relance au démarrage ; ne re-snapshote pas (RM2395) |
| DELETE | `/session-set` | `?group=default` | `{user, group, deleted}` — efface le jeu (RM2395) |
| GET | `/resolve/<rm_id>` | — | `{found, client, project, cwd, prompt, title, status, task_file}` — résout depuis le MD local (RM1893 §1) |
| GET | `/tickets/search` | `?q=&status=&client=&project=&tag=` | `{results:[…]}` — recherche sur les MD locaux (RM1893 §7) |
| GET | `/projects` | — | `{projects:[{client, project, value}]}` (RM1893 §8) |
| POST | `/tickets` | `{title, type, priority, project, description?, tags?}` | `201 {created, rm_id}` — wrappe `pm-task-add` (creds Redmine hérités du `.env`), entrées en argv = pas d'injection (RM1893 §8) |
| POST | `/spawn` | `{rm_id, cwd?, engine?, model?, prompt?, width?, height?}` | `201 {rm_id, tmux, engine, model, model_source, cwd, session_id?, created}` — pour claude, le `session_id` est FIXÉ au lancement (`--session-id`) et l'index sessions⇄tickets écrit immédiatement (RM1939) |
| POST | `/send` | `{rm_id, msg, enter?=true}` | `{rm_id, sent}` |
| GET | `/capture/<rm_id>` | `?lines=N` (historique) | `text/plain` (snapshot du pane) |
| GET | `/stream/<rm_id>` | — | `text/event-stream` (tail du pipe-pane, SSE) |
| POST | `/monitor` | `{rm_id, preset, orientation?=h\|v}` | `201 {added}` — pane moniteur via `split-window`, commande issue du catalogue serveur (RM1893 §3) |
| POST | `/unmonitor` | `{rm_id}` | `{closed, remaining}` — ferme le moniteur actif (cliqué) ou le dernier ajouté ; ne touche jamais au pane de l'agent (flag `@karl_mon`) |
| POST | `/layout` | `{rm_id, layout}` | `{layout}` — `even-horizontal\|even-vertical\|main-vertical\|main-horizontal\|tiled` |
| POST | `/kill` | `{rm_id}` | `{rm_id, killed}` |

- `engine` ∈ `{claude, opencode, vibe, shell}` (templates serveur ; défaut
  `claude`). Chaque moteur définit sa commande (surchargée par
  `KARL_AGENT_<MOTEUR>_CMD`) et ses **marqueurs de readiness** (sous-chaînes du pane
  signalant « TUI prêt » avant d'injecter le prompt) — cf. `ENGINES` dans le daemon.
  opencode et vibe sont des TUI pilotés en tmux exactement comme claude (RM1921) ;
  `vibe` est lancé avec `--trust` (confie le cwd déjà validé). `shell` (`bash -l`)
  n'a pas de marqueur → simple délai.
- `prompt` est livré **après** le spawn via `send-keys` (jamais concaténé dans la
  ligne de commande lancée par tmux), même pour opencode/vibe qui sauraient le
  prendre à l'invocation — invariant sécu #4 (pas d'entrée client en argv).
- `model` (RM1941) : `""`/absent = défaut du moteur ; **`"ticket"`** = modèle
  prescrit par le frontmatter **`ai_model`** de la tâche (cascade : tâche →
  `project/overview.md` du projet ; rien de prescrit ou moteur sans support →
  défaut sans erreur) ; sinon une **clé du catalogue serveur** (défauts dans le
  daemon, surchargeables via `cockpit/models.json` `{"<engine>": {"clé": "valeur"}}`)
  — la valeur cliente n'est **jamais** interpolée brute (même modèle de sécurité
  que les moniteurs), clé inconnue → 400. Application par moteur : claude/opencode
  `--model <valeur>` ; vibe env `VIBE_ACTIVE_MODEL` (le modèle doit être déclaré
  dans `[[models]]` du `~/.vibe/config.toml`). `ai_model` contient la valeur
  **native du moteur visé** (alias claude, `provider/model` opencode, nom vibe) ;
  champ pas encore dans le schéma NORMS — convention documentée ici, extension
  NORMS à proposer si l'usage se confirme.
- Codes : `400` (entrée invalide), `401` (token manquant), `404` (session absente),
  `409` (session déjà active), `500` (échec tmux).

### Nommage des sessions (RM2144)

L'ancrage **ticket** est l'IDÉAL : tmux `karl-RM<id>`, jonction n-m écrite,
resolve/workspace-status/groupement projet complets. Un **slug** est accepté
(`karl-<slug>`, `^[a-z0-9][a-z0-9_-]{1,40}$`, hors espace `rm<n>`) — cas type :
reprise d'une session interactive sans ticket évident. Le champ `rm_id` de
l'API porte indifféremment l'un ou l'autre (`is_ticket` dans `/sessions`) ;
l'index clé-tmux (`~/.local/state/karl-agent/keys/`) garde (engine, session_id,
cwd) pour toutes les sessions, jonction tickets⇄sessions réservée aux tickets.

### Reprise de session — modèle n-m (RM1939)

Store **instance-local** (jamais committé) sous `~/.local/state/karl-agent/` :
`sessions/<engine>/<session_id>.json` (entité session, projet-agnostique — clé
de resume : cwd, last_seen) + `tasks/<client>/<projet>/RM<id>-<n>.json`
(jonction : une session traverse plusieurs tickets, un ticket est repris dans
plusieurs sessions ; `n` = occurrence de prise en charge). Le même couple
(ticket, session) réutilise sa jonction — un resume ne crée pas d'occurrence.
Itération 1 : moteur **claude** uniquement (session-id fixé au spawn) ; la
découverte scanne aussi les sessions HORS karl-agent (interactives) via leurs
transcripts, avec leurs marqueurs `[WIP]`/`[DONE]` (`/session-mark`).

### Jeux de sessions enregistrés (RM2395)

Un **jeu** = un instantané des sessions vivantes qu'on veut pouvoir relancer d'un
clic après un redémarrage. Store instance-local (jamais committé)
`~/.local/state/karl-agent/session-set.json` — un `session_id` n'a de sens que sur
cette machine. Schéma **user + groupe** (anticipe le multi-utilisateur et les
groupes nommés) :

```json
{"version": 1, "users": {"superadmin": {"groups": {"default": {
    "saved_at": 1753, "autostart": false,
    "entries": [{"sid": "2395", "engine": "claude",
                 "session_id": "<uuid>", "cwd": "/zfs/…", "model": null}]}}}}}
```

Résolution des clés : **user** = `auth_ctx["user"]` (RM2334) sinon `superadmin`
(auth ouverte / secret partagé) ; **groupe** = param `group` sinon `default`. v1
n'exerce que le couple par défaut, mais la clé transite de bout en bout → le
multi-jeux / multi-utilisateur est une extension sans migration. La relance
(`/session-set/relaunch`) s'appuie sur `/resume` (donc claude ; `skipped` pour une
entrée déjà vivante — idempotent) ; le fallback **spawn neuf** est **opt-in** (pas
d'agent vierge qui consomme des tokens sans qu'on l'ait demandé). Le modèle choisi
au spawn est mémorisé par entrée (`_record_key`, RM1941) pour un fallback fidèle.

**Autostart au démarrage** (`autostart` par jeu, posé via `/session-set/autostart`) :
au lancement du daemon, un thread de fond rejoue les jeux marqués — **`resume` seul,
jamais spawn, jamais de prompt** (arbitrage : pas d'agent lancé sans opérateur).
Ne mord qu'après un **reboot** / `tmux kill-server` (`KillMode=process` fait
survivre les tmux au simple redémarrage du daemon) ; l'idempotence rend le rejeu à
chaque démarrage inoffensif. Coupe-circuit : `KARL_AGENT_AUTOSTART=0`. Gestion depuis
la **carte « Sessions enregistrées »** du panneau 🚀 sessions (liste + état par
entrée, cases autostart & fallback spawn, Effacer).

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

## Cockpit web v0 (RM1873)

Première UI web du système PM — **seed de RM1679**. Donne *lancer + superviser +
reprise de main* dans le navigateur, sur l'API karl-agent existante.

- **UI servie en même origine** par le daemon (`GET /`), HTML/JS auto-contenu
  (`deploy/karl-agent/cockpit/index.html`) : pas de CORS, pas de build, pas de
  dépendance. Liste les sessions (poll `/sessions`), formulaire de lancement
  (`/spawn`), boutons Attach / Kill.
- **Terminal web = ttyd** (`ttyd.service`), un seul process, lancé writable (`-W`)
  avec `-a` : le cockpit passe le `rm_id` en argument d'URL (`?arg=<id>`) ; le
  wrapper `cockpit/attach-karl.sh` **valide** `rm_id` (`^[0-9]+$`) puis fait
  `exec tmux attach -t karl-RM<id>`. Multiples onglets = multiples viewers du
  même tmux (mirroring natif). C'est la reprise de main, mais dans le navigateur.

```bash
# Accès LOCAL (port-forward des deux ports depuis le laptop) :
ssh -L 9876:localhost:9876 -L 7681:localhost:7681 dev.lxc
# puis navigateur → http://localhost:9876/
```

> **Piège apt (vécu sur dev).** `sudo apt install ttyd` installe **et active tout
> seul** un service **système** `ttyd.service` (paquet) qui lance `ttyd -O login`
> sur 7681 → il squatte le port, notre ttyd *user* ne peut plus binder, et le
> navigateur affiche un `<host> login:` au lieu du TUI de l'agent. À neutraliser
> juste après l'install : `sudo systemctl disable --now ttyd.service && sudo
> systemctl mask ttyd.service`. (Homonymie volontaire à connaître : le service du
> paquet = scope *système* ; le nôtre = scope *user*.) `install.sh` le détecte.

> **INVARIANT SÉCU.** Le cockpit reste **LOCAL** (port-forward SSH / tunnel mmi),
> jamais en écoute publique, **tant que l'auth (oauth2-proxy→GitLab, RM1845)
> n'est pas en place**. ttyd bind `127.0.0.1` en dur (`-i 127.0.0.1`), comme le
> daemon. Ne PAS exposer un cockpit de *lancement* d'agents sans ce gate.

Les pages `/` et `/cockpit-config` sont **publiques** (pas de token) pour que la
page puisse charger et qu'on y saisisse le token si `KARL_AGENT_TOKEN` est défini ;
les routes d'action (`/sessions`, `/spawn`, …) restent protégées. L'enrichissement
(badges working/blocked/idle, « besoin d'aide », chat structuré) viendra avec la
**boucle hooks→état du superviseur v2 (RM1874)**.

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
| `KARL_AGENT_OPENCODE_CMD` | `opencode` | Commande du moteur `opencode`. |
| `KARL_AGENT_VIBE_CMD` | `vibe --trust` | Commande du moteur `vibe` (Mistral Vibe). |
| `KARL_AGENT_DEFAULT_ENGINE` | `claude` | Moteur par défaut au spawn. |
| `KARL_AGENT_ALLOWED_ROOTS` | `/zfs/workspaces` | Racines autorisées pour `cwd` (`:`-séparées). |
| `KARL_AGENT_DEFAULT_CWD` | _(repo)_ | cwd si non fourni au spawn. |
| `KARL_AGENT_WIDTH` / `_HEIGHT` | `200` / `50` | Géométrie du pane tmux. |
| `KARL_AGENT_LOG_DIR` | `~/.local/state/karl-agent` | Logs pipe-pane (alimente `/stream`) + store des jeux (`session-set.json`, RM2395). |
| `KARL_AGENT_AUTOSTART` | `1` | `0` = coupe la relance auto des jeux marqués `autostart` au démarrage (RM2395). |
| `KARL_AGENT_TTYD_URL` | _(vide)_ | Base URL du ttyd du cockpit ; vide → le client la déduit (`location.hostname:7681`). |

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

### Désinstallation

```bash
bash deploy/karl-agent/uninstall.sh                  # stop + disable + retire les units
bash deploy/karl-agent/uninstall.sh --kill-sessions  # + ferme les tmux karl-RM* vivants
bash deploy/karl-agent/uninstall.sh --disable-linger # + retire le linger utilisateur
```

Idempotent et symétrique de l'installeur. Par défaut il **conserve** les sessions
tmux `karl-RM*` (un humain peut y être attaché) et le linger (d'autres services
user peuvent en dépendre) — il faut les flags pour les retirer. Le code et les logs
(`~/.local/state/karl-agent/`) ne sont jamais touchés.

### deploy_actions (manuel, une fois)

- [ ] Installer sur `dev` : `tmux`, `autossh`, et au moins un moteur (`claude`,
      `opencode`, `vibe`). `python3` est déjà présent. (`sudo apt install tmux autossh`)
- [ ] **Moteurs multi (RM1921)** : chaque moteur doit être *résolvable et
      authentifié* dans l'environnement du service. Sur `dev` :
      `claude` et `vibe` sont dans `~/.local/bin` (dans le PATH du service) ;
      **`opencode` est dans `~/.opencode/bin` (hors PATH)** → définir
      `KARL_AGENT_OPENCODE_CMD=/home/mathieu/.opencode/bin/opencode` dans `.env`.
      **`vibe` exige un onboarding première-exécution** (clé API Mistral via le
      wizard `vibe`/`vibe --setup`, stockée dans `~/.vibe/config.toml`) — sinon le
      TUI reste bloqué sur « Welcome to Mistral Vibe ». Auth analogue à claude/opencode.
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
| Cockpit : `<host> login:` au lieu du TUI | le service **système** `ttyd.service` du paquet apt squatte 7681 (lance `ttyd -O login`). `sudo systemctl disable --now ttyd.service && sudo systemctl mask ttyd.service`, puis `systemctl --user restart ttyd.service`. |
| `ttyd.service` (user) en `activating`/`failed` | port 7681 déjà pris (`EADDRINUSE`) — souvent le ttyd système du paquet (ci-dessus). `journalctl --user -u ttyd.service`. |

## Pistes / évolutions (hors v1)

- **`/stream` structuré** : aujourd'hui `/stream` tail le pipe-pane (octets de
  terminal bruts, ANSI). Pour une vue « chat » propre côté web, exposer le flux
  structuré du moteur (`claude --output-format stream-json` : events
  system/init / assistant / result) plutôt que parser l'écran. Décider du modèle
  d'entrée (TUI interactif pour l'attach **vs** stdin stream-json headless) — non
  conciliables sur un même process : à arbitrer avec RM1669/RM1679.
- **Détection « session bloquée »** : poller `claude agents --json` (champ
  `waitingFor`) pour le relais permission/aide → brique RM1824.
- **Multi-moteur — lancement TUI : FAIT (RM1921).** opencode et vibe (Mistral Vibe)
  sont des moteurs `ENGINES` à part entière, lancés/attachés/pilotés en tmux comme
  claude (prompt via send-keys, readiness par marqueurs). Reste la **supervision
  enrichie** (badges working/blocked/idle), dont le substrat diffère par moteur :
  - **opencode** : `opencode serve` (API `/event` SSE, `/question` + `/permission`
    structurés, attach natif, autonomie par PermissionRuleset). Attention :
    `opencode run` headless **hang** si une permission est « ask » (GH #16367/#17516)
    → imposer des rulesets allow/deny. Voie programmatique = SDK JS/TS.
  - **vibe** : pas de bus de hooks comme Claude Code ; flux structuré seulement en
    mode programmatique (`vibe -p --output streaming`, NDJSON par message), non
    conciliable avec le TUI attachable. Budgets natifs `--max-turns/-price/-tokens`.
  → à traiter en extension de la boucle hooks→état du superviseur v2 (RM1874).
