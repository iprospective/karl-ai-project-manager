// core/endpoints — table unique des routes du front. RM2889, lot L0.
//
// GÉNÉRÉ depuis MIGRATION-ROUTES.tsv : ne pas éditer à la main, régénérer.
//
// Une route ne s'écrit plus en dur dans un service : elle se nomme. C'est ce
// qui rend le lot L7 mécanique — basculer `current` sur `target` (grammaire
// /api/<type>/<action>, § 10.4) se fait ici, une fois, pour tous les appelants.
// Les routes actuelles restent servies en alias jusqu'à L7.

export const ROUTES = {
  "auth.devices": { current: "/auth/devices", target: "/api/auth/devices", lot: "L0", callers: 3 },
  "auth.login": { current: "/auth/login", target: "/api/auth/login", lot: "L0", callers: 1 },
  "auth.users": { current: "/auth/users", target: "/api/auth/users", lot: "L0", callers: 5 },
  "auth.whoami": { current: "/auth/whoami", target: "/api/auth/whoami", lot: "L2", callers: 1 },
  "core.update_status": { current: "/core/update-status", target: "/api/core/update-status", lot: "L0", callers: 1 },
  "dashboard.alerts": { current: "/alerts", target: "/api/dashboard/alerts", lot: "L4", callers: 1 },
  "dashboard.overview": { current: "/overview", target: "/api/dashboard/overview", lot: "L4", callers: 2 },
  "dashboard.snooze": { current: "/alerts/snooze", target: "/api/dashboard/snooze", lot: "L4", callers: 1 },
  "env.env_check": { current: "/env-check", target: "/api/env/env-check", lot: "L5", callers: 1 },
  "env.env_status": { current: "/env-status", target: "/api/env/env-status", lot: "L5", callers: 1 },
  "env.ssh_add": { current: "/vault/ssh-add", target: "/api/env/ssh-add", lot: "L2", callers: 1 },
  "env.unlock": { current: "/vault/unlock", target: "/api/env/unlock", lot: "L2", callers: 1 },
  "file.file": { current: "/file", target: "/api/file/file", lot: "L4,L5", callers: 2 },
  "file.file__fs_file": { current: "/fs/file", target: "/api/file/file", lot: "L4", callers: 4 },
  "file.git.show": { current: "/git/show", target: "/api/file/git/show", lot: "L4", callers: 2 },
  "file.log": { current: "/fs/log", target: "/api/file/log", lot: "L4", callers: 1 },
  "file.ls": { current: "/fs/ls", target: "/api/file/ls", lot: "L4", callers: 3 },
  "file.project_roots": { current: "/project-roots", target: "/api/file/project-roots", lot: "L4", callers: 1 },
  "file.worktrees": { current: "/worktrees", target: "/api/file/worktrees", lot: "L4", callers: 1 },
  "git.diff": { current: "/git/diff", target: "/api/git/diff", lot: "L4", callers: 1 },
  "git.log": { current: "/git/log", target: "/api/git/log", lot: "L4", callers: 1 },
  "glossary.help": { current: "/help", target: "/api/glossary/help", lot: "L5", callers: 1 },
  "glossary.project": { current: "/project", target: "/api/glossary/project", lot: "L5", callers: 2 },
  "layout.outline": { current: "/outline", target: "/api/layout/outline", lot: "L5", callers: 1 },
  "mail.queue": { current: "/mail/queue", target: "/api/mail/queue", lot: "L4,L5", callers: 2 },
  "outline.approve": { current: "/approve", target: "/api/outline/approve", lot: "L5", callers: 1 },
  "outline.scroll": { current: "/scroll", target: "/api/outline/scroll", lot: "L5", callers: 2 },
  "pm.commands": { current: "/pm/commands", target: "/api/pm/commands", lot: "L5", callers: 1 },
  "pm.run": { current: "/pm/run", target: "/api/pm/run", lot: "L3", callers: 1 },
  "pm.settings": { current: "/pm/settings", target: "/api/pm/settings", lot: "L2,L5", callers: 2 },
  "pm.test_queue": { current: "/pm/test-queue", target: "/api/pm/test-queue", lot: "L3", callers: 1 },
  "project.client": { current: "/client", target: "/api/project/client", lot: "L4", callers: 1 },
  "project.conf": { current: "/conf", target: "/api/project/conf", lot: "L4", callers: 1 },
  "project.project_worktrees": { current: "/project-worktrees", target: "/api/project/project-worktrees", lot: "L4", callers: 1 },
  "project.projects": { current: "/projects", target: "/api/project/projects", lot: "L3", callers: 1 },
  "review.mr.deliver": { current: "/mr/deliver", target: "/api/review/mr/deliver", lot: "L3", callers: 1 },
  "search.resumable": { current: "/resumable", target: "/api/search/resumable", lot: "L3", callers: 1 },
  "search.tags": { current: "/tags", target: "/api/search/tags", lot: "L3", callers: 1 },
  "session.approve_all": { current: "/approve-all", target: "/api/session/approve-all", lot: "L2", callers: 1 },
  "session.cockpit_config": { current: "/cockpit-config", target: "/api/session/cockpit-config", lot: "L2", callers: 1 },
  "session.disposition": { current: "/disposition", target: "/api/session/disposition", lot: "L2", callers: 1 },
  "session.kill": { current: "/kill", target: "/api/session/kill", lot: "L2", callers: 1 },
  "session.layout": { current: "/layout", target: "/api/session/layout", lot: "L2", callers: 1 },
  "session.monitor": { current: "/monitor", target: "/api/session/monitor", lot: "L2", callers: 1 },
  "session.move_session": { current: "/move-session", target: "/api/session/move-session", lot: "L2", callers: 1 },
  "session.refresh": { current: "/refresh", target: "/api/session/refresh", lot: "L2", callers: 1 },
  "session.resume": { current: "/resume", target: "/api/session/resume", lot: "L2", callers: 2 },
  "session.send": { current: "/send", target: "/api/session/send", lot: "L2,L3,L5", callers: 4 },
  "session.sessions": { current: "/sessions", target: "/api/session/sessions", lot: "L0,L3", callers: 2 },
  "session.spawn": { current: "/spawn", target: "/api/session/spawn", lot: "L2,L3", callers: 3 },
  "session.unmonitor": { current: "/unmonitor", target: "/api/session/unmonitor", lot: "L2", callers: 1 },
  "session_set.auto_yes": { current: "/auto-yes", target: "/api/session-set/auto-yes", lot: "L2", callers: 1 },
  "session_set.create": { current: "/session-set/create", target: "/api/session-set/create", lot: "L2", callers: 2 },
  "session_set.current": { current: "/session-set/current", target: "/api/session-set/current", lot: "L2", callers: 2 },
  "session_set.estimate": { current: "/session-set/estimate", target: "/api/session-set/estimate", lot: "L2", callers: 1 },
  "session_set.history": { current: "/session-set/history", target: "/api/session-set/history", lot: "L2", callers: 1 },
  "session_set.materialize": { current: "/session-set/materialize", target: "/api/session-set/materialize", lot: "L2", callers: 1 },
  "session_set.move": { current: "/session-set/move", target: "/api/session-set/move", lot: "L2", callers: 1 },
  "session_set.relaunch": { current: "/session-set/relaunch", target: "/api/session-set/relaunch", lot: "L2", callers: 1 },
  "session_set.rename": { current: "/session-set/rename", target: "/api/session-set/rename", lot: "L2", callers: 1 },
  "session_set.restart": { current: "/session-set/restart", target: "/api/session-set/restart", lot: "L2", callers: 1 },
  "session_set.restore": { current: "/session-set/restore", target: "/api/session-set/restore", lot: "L2", callers: 2 },
  "session_set.retention": { current: "/session-set/retention", target: "/api/session-set/retention", lot: "L2", callers: 1 },
  "session_set.rule": { current: "/session-set/rule", target: "/api/session-set/rule", lot: "L2", callers: 1 },
  "session_set.session_set": { current: "/session-set", target: "/api/session-set/session-set", lot: "L2", callers: 6 },
  "session_set.session_sets": { current: "/session-sets", target: "/api/session-set/session-sets", lot: "L2", callers: 1 },
  "terminal.buffer": { current: "/buffer", target: "/api/terminal/buffer", lot: "L2", callers: 1 },
  "terminal.capture": { current: "/capture", target: "/api/terminal/capture", lot: "L2,L5", callers: 2 },
  "terminal.memdebug": { current: "/memdebug", target: "/api/terminal/memdebug", lot: "L2", callers: 1 },
  "test_queue.ticket_sessions": { current: "/ticket-sessions", target: "/api/test-queue/ticket-sessions", lot: "L3", callers: 1 },
  "test_queue.ticket_transitions": { current: "/ticket-transitions", target: "/api/test-queue/ticket-transitions", lot: "L3", callers: 1 },
  "ticket.brief": { current: "/tickets/brief", target: "/api/ticket/brief", lot: "L3", callers: 1 },
  "ticket.mergecheck": { current: "/mergecheck", target: "/api/ticket/mergecheck", lot: "L3", callers: 1 },
  "ticket.resolve": { current: "/resolve", target: "/api/ticket/resolve", lot: "L3,L5", callers: 2 },
  "ticket.tickets": { current: "/tickets", target: "/api/ticket/tickets", lot: "L2,L3", callers: 2 },
  "ticket.triage": { current: "/triage", target: "/api/ticket/triage", lot: "L3", callers: 1 },
  "ticket.usage": { current: "/usage", target: "/api/ticket/usage", lot: "L3", callers: 1 },
  "ticket.workspace_status": { current: "/workspace-status", target: "/api/ticket/workspace-status", lot: "L3", callers: 1 },
  "voice.caps": { current: "/voice/caps", target: "/api/voice/caps", lot: "L5", callers: 1 },
  "voice.question": { current: "/question", target: "/api/voice/question", lot: "L5", callers: 2 },
  "voice.stt": { current: "/stt", target: "/api/voice/stt", lot: "L5", callers: 1 },
  "voice.tts": { current: "/tts", target: "/api/voice/tts", lot: "L5", callers: 1 },
  "worklog.batch": { current: "/worklog/batch", target: "/api/worklog/batch", lot: "L3,L4", callers: 3 },
  "worklog.mr.batch": { current: "/mr/batch", target: "/api/worklog/mr/batch", lot: "L3", callers: 2 },
  "worklog.mr.merge": { current: "/mr/merge", target: "/api/worklog/mr/merge", lot: "L3", callers: 1 },
  "worklog.worklog": { current: "/worklog", target: "/api/worklog/worklog", lot: "L3", callers: 1 },
};

/** Chemin à appeler aujourd'hui pour une route nommée. Lève si le nom est inconnu. */
export function route(name) {
  const e = ROUTES[name];
  if (!e) throw new Error(`route inconnue : ${name}`);
  return e.current;
}

/** Chemin cible (§ 10.4), pour les tests de dérive et la bascule L7. */
export function targetRoute(name) {
  const e = ROUTES[name];
  if (!e) throw new Error(`route inconnue : ${name}`);
  return e.target;
}
