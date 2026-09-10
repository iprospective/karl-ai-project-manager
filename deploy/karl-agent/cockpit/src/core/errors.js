// core/errors — une seule forme d'erreur, de bout en bout. RM2889, L0 (§ 9).
//
// Toute erreur qui traverse une couche porte les mêmes quatre champs, front
// comme python : `code` (stable, testable), `message` (pour l'humain),
// `detail` (pour le debug), `remedy` (ce qu'on peut FAIRE). C'est ce qui
// permet à une frontière d'erreur unique par contrôleur de remplacer les 176
// try/catch du monolithe : elle ne connaît pas les cas, elle connaît la forme.

export class AppError extends Error {
  constructor(code, message, { detail = null, remedy = null, cause = null } = {}) {
    super(message || code);
    this.name = "AppError";
    this.code = code;
    this.detail = detail;
    this.remedy = remedy;
    if (cause) this.cause = cause;
  }
  /** Forme sérialisable — journal structuré, notification, réponse JSON. */
  toJSON() {
    return { code: this.code, message: this.message, detail: this.detail, remedy: this.remedy };
  }
}

/** Erreur de transport ou de réponse HTTP. `status` en plus des quatre champs. */
export class ApiError extends AppError {
  constructor(status, message, opts = {}) {
    super(opts.code || `http.${status}`, message, opts);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Ramène n'importe quoi (Error, chaîne, objet serveur) à un AppError. */
export function asAppError(err, fallbackCode = "unknown") {
  if (err instanceof AppError) return err;
  if (err && typeof err === "object" && err.code && err.message) {
    return new AppError(err.code, err.message, { detail: err.detail, remedy: err.remedy });
  }
  const message = err && err.message ? err.message : String(err);
  return new AppError(fallbackCode, message, { cause: err });
}
