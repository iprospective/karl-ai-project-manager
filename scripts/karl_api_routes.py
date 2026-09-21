"""karl_api_routes — alias /api/<type>/<action> → chemin historique (RM2889, L7).

GÉNÉRÉ par scripts/cockpit-gen-endpoints.py depuis deploy/karl-agent/cockpit/MIGRATION-ROUTES.tsv :
ne pas éditer à la main, régénérer. Le front (src/core/endpoints.js, `route()`) appelle les cibles ;
karl-agent.py les ramène au chemin historique avant son dispatch, et continue de servir les chemins
historiques tels quels pour les autres clients (scripts, app mobile).
"""

TARGET_TO_CURRENT = {
    "/api/auth/devices": "/auth/devices",
    "/api/auth/login": "/auth/login",
    "/api/auth/users": "/auth/users",
    "/api/auth/whoami": "/auth/whoami",
    "/api/clientnotify/dismiss": "/client-notify/dismiss",
    "/api/clientnotify/pending": "/client-notify/pending",
    "/api/clientnotify/preview": "/client-notify/preview",
    "/api/clientnotify/send": "/client-notify/send",
    "/api/clientnotify/test": "/client-notify/test",
    "/api/core/update-status": "/core/update-status",
    "/api/dashboard/alerts": "/alerts",
    "/api/dashboard/notifications": "/notifications",
    "/api/dashboard/notifications-mark": "/notifications/mark",
    "/api/dashboard/overview": "/overview",
    "/api/dashboard/snooze": "/alerts/snooze",
    "/api/doc/cdc": "/cdc",
    "/api/doc/cdc-feature": "/cdc/feature",
    "/api/doc/cdc-features": "/cdc-features",
    "/api/doc/cdc-think": "/cdc/think",
    "/api/doc/cdc-version": "/cdc/version",
    "/api/env/env-check": "/env-check",
    "/api/env/env-status": "/env-status",
    "/api/env/ssh-add": "/vault/ssh-add",
    "/api/env/unlock": "/vault/unlock",
    "/api/file/file": "/file",
    "/api/file/git/show": "/git/show",
    "/api/file/log": "/fs/log",
    "/api/file/ls": "/fs/ls",
    "/api/file/project-roots": "/project-roots",
    "/api/file/read": "/fs/file",
    "/api/file/worktrees": "/worktrees",
    "/api/git/diff": "/git/diff",
    "/api/git/log": "/git/log",
    "/api/git/show": "/git/show",
    "/api/glossary/help": "/help",
    "/api/glossary/project": "/project",
    "/api/layout/outline": "/outline",
    "/api/log/historical": "/log/historical",
    "/api/log/tail": "/log/tail",
    "/api/log/write": "/log",
    "/api/mail/create": "/mail/create",
    "/api/mail/dismiss": "/mail/dismiss",
    "/api/mail/draft": "/mail/draft",
    "/api/mail/fetch": "/mail/fetch",
    "/api/mail/queue": "/mail/queue",
    "/api/mail/route": "/mail/route",
    "/api/mail/route-set": "/mail/route-set",
    "/api/monitor/alerts": "/monitor/alerts",
    "/api/monitor/assign": "/monitor/assign",
    "/api/monitor/hosts": "/monitor/hosts",
    "/api/monitor/ticket": "/monitor/ticket",
    "/api/outline/approve": "/approve",
    "/api/outline/scroll": "/scroll",
    "/api/pm/commands": "/pm/commands",
    "/api/pm/engine-install": "/pm/engine-install",
    "/api/pm/engine-options": "/engines/options",
    "/api/pm/engines": "/pm/engines",
    "/api/pm/llm-models": "/pm/llm-models",
    "/api/pm/modules": "/modules",
    "/api/pm/modules-policy": "/modules/policy",
    "/api/pm/modules-state": "/modules/state",
    "/api/pm/provider-assign": "/pm/provider-assign",
    "/api/pm/provider-secret": "/pm/provider-secret",
    "/api/pm/provider-types": "/pm/provider-types",
    "/api/pm/providers": "/pm/providers",
    "/api/pm/run": "/pm/run",
    "/api/pm/settings": "/pm/settings",
    "/api/pm/test-queue": "/pm/test-queue",
    "/api/project/client": "/client",
    "/api/project/conf": "/conf",
    "/api/project/contact": "/contact",
    "/api/project/contacts": "/contacts",
    "/api/project/project-worktrees": "/project-worktrees",
    "/api/project/projects": "/projects",
    "/api/review/mr/deliver": "/mr/deliver",
    "/api/search/resumable": "/resumable",
    "/api/search/tags": "/tags",
    "/api/search/tickets": "/tickets/search",
    "/api/session-set/auto-yes": "/auto-yes",
    "/api/session-set/create": "/session-set/create",
    "/api/session-set/current": "/session-set/current",
    "/api/session-set/estimate": "/session-set/estimate",
    "/api/session-set/history": "/session-set/history",
    "/api/session-set/materialize": "/session-set/materialize",
    "/api/session-set/move": "/session-set/move",
    "/api/session-set/relaunch": "/session-set/relaunch",
    "/api/session-set/rename": "/session-set/rename",
    "/api/session-set/restart": "/session-set/restart",
    "/api/session-set/restore": "/session-set/restore",
    "/api/session-set/retention": "/session-set/retention",
    "/api/session-set/rule": "/session-set/rule",
    "/api/session-set/session-set": "/session-set",
    "/api/session-set/session-sets": "/session-sets",
    "/api/session/approve-all": "/approve-all",
    "/api/session/cockpit-config": "/cockpit-config",
    "/api/session/compact": "/compact",
    "/api/session/disposition": "/disposition",
    "/api/session/events": "/events",
    "/api/session/events/publish": "/events/publish",
    "/api/session/kill": "/kill",
    "/api/session/layout": "/layout",
    "/api/session/monitor": "/monitor",
    "/api/session/move-session": "/move-session",
    "/api/session/refresh": "/refresh",
    "/api/session/resume": "/resume",
    "/api/session/send": "/send",
    "/api/session/sessions": "/sessions",
    "/api/session/spawn": "/spawn",
    "/api/session/unmonitor": "/unmonitor",
    "/api/terminal/buffer": "/buffer",
    "/api/terminal/capture": "/capture",
    "/api/terminal/memdebug": "/memdebug",
    "/api/test-queue/ticket-sessions": "/ticket-sessions",
    "/api/test-queue/ticket-transitions": "/ticket-transitions",
    "/api/ticket/anteriority": "/tickets/anteriority",
    "/api/ticket/brief": "/tickets/brief",
    "/api/ticket/impact": "/ticket-impact",
    "/api/ticket/mergecheck": "/mergecheck",
    "/api/ticket/resolve": "/resolve",
    "/api/ticket/tickets": "/tickets",
    "/api/ticket/triage": "/triage",
    "/api/ticket/usage": "/usage",
    "/api/ticket/workspace-status": "/workspace-status",
    "/api/timesheet/day": "/timesheet/day",
    "/api/timesheet/month": "/timesheet/month",
    "/api/voice/caps": "/voice/caps",
    "/api/voice/question": "/question",
    "/api/voice/stt": "/stt",
    "/api/voice/tts": "/tts",
    "/api/worklog/batch": "/worklog/batch",
    "/api/worklog/mr/batch": "/mr/batch",
    "/api/worklog/mr/merge": "/mr/merge",
    "/api/worklog/request": "/worklog/request",
    "/api/worklog/worklog": "/worklog",
}

# RM3004 : la table inverse — un chemin historique appelé directement (hors cockpit) est repérable, et journalisé avant retrait.
CURRENT_TO_TARGET = {v: k for k, v in TARGET_TO_CURRENT.items()}


def historical_target(path):
    """Cible /api/… d'un chemin HISTORIQUE (sans query string), suffixe conservé ; None si ce n'est pas un chemin routé."""
    if path.startswith("/api/"):
        return None
    hit = CURRENT_TO_TARGET.get(path)
    if hit is None:
        for cur in sorted(CURRENT_TO_TARGET, key=len, reverse=True):
            if path.startswith(cur + "/"):
                hit = CURRENT_TO_TARGET[cur] + path[len(cur):]
                break
    return hit


def api_alias(path_qs):
    """Réécrit une URL cible en URL historique (la query string est conservée) ; les autres URL passent telles quelles.
    Un suffixe après la cible (identifiant : /api/auth/devices/<id>) est reporté sur le chemin historique."""
    if not path_qs.startswith("/api/"):
        return path_qs
    path, sep, qs = path_qs.partition("?")
    hit = TARGET_TO_CURRENT.get(path)
    if hit is None:
        for tgt in sorted(TARGET_TO_CURRENT, key=len, reverse=True):
            if path.startswith(tgt + "/"):
                hit = TARGET_TO_CURRENT[tgt] + path[len(tgt):]
                break
    if hit is None:
        return path_qs
    return hit + sep + qs
