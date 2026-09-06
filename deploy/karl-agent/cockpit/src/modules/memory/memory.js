// modules/memory/memory — le panneau « mémoire » (RM3007) : fonctions PURES — préférence d'activation, lignes par module, courbe. Aucun DOM.
import { rendersPerMin } from "../../core/probe.js";

export const INTERVALS = [5, 10, 30, 60];   // secondes
export const KEY_ON = "karlProbe", KEY_INTERVAL = "karlProbeInterval";

export function readOn(storage) { try { return !!storage && storage.getItem(KEY_ON) === "1"; } catch (e) { return false; } }
export function writeOn(storage, on) { try { if (storage) { if (on) storage.setItem(KEY_ON, "1"); else storage.removeItem(KEY_ON); } } catch (e) { /* mode privé */ } }
export function readInterval(storage) { try { const v = Number(storage && storage.getItem(KEY_INTERVAL)); return INTERVALS.includes(v) ? v : 10; } catch (e) { return 10; } }
export function writeInterval(storage, s) { try { if (storage) storage.setItem(KEY_INTERVAL, String(s)); } catch (e) { /* mode privé */ } }

/** Points d'une polyline SVG (w×h) pour une série ; vide si moins de deux valeurs. */
export function sparkline(values, w = 120, h = 24) {
  const v = (values || []).map(Number); if (v.length < 2) return "";
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  return v.map((x, i) => `${(i / (v.length - 1) * w).toFixed(1)},${(h - 2 - (x - min) / span * (h - 4)).toFixed(1)}`).join(" ");
}

/** La tendance d'une série sur ses derniers points : ↗ hausse, ↘ baisse, → stable. */
export function trend(values) {
  const v = values || []; if (v.length < 2) return "→";
  const a = v[Math.max(0, v.length - 4)], b = v[v.length - 1];
  return b > a ? "↗" : b < a ? "↘" : "→";
}

/** Une ligne par module, à partir de la sonde (dernier échantillon, séries, alertes). Triées par nœuds décroissants. */
export function rowsFor(probe) {
  const cur = probe.latest; if (!cur) return [];
  const leaks = probe.alerts();
  return probe.modules().map(m => {
    const d = cur.modules[m] || { mounted: 0, nodes: 0, pending: 0, entries: 0, subscribers: 0 };
    const nodes = probe.series(m, "nodes"), pending = probe.series(m, "pending");
    return { module: m, mounted: d.mounted, nodes: d.nodes, pending: d.pending, entries: d.entries, subscribers: d.subscribers,
             rate: rendersPerMin(probe.previous, cur, m), trend: trend(nodes), pendingTrend: trend(pending), spark: sparkline(nodes),
             leaks: leaks.filter(l => l.module === m).map(l => `${l.counter} ${l.from}→${l.to}`) };
  }).sort((a, b) => b.nodes - a.nodes || a.module.localeCompare(b.module));
}

export function fmtHeap(bytes) { return bytes == null ? "" : bytes >= 1 << 20 ? (bytes / (1 << 20)).toFixed(1) + " Mo" : Math.round(bytes / 1024) + " ko"; }
