// core/markdown — mini-rendu markdown auto-suffisant et SÛR (RM2309). RM2889 : sorti du monolithe tel quel.
// Tout le texte est échappé AVANT toute transformation, les liens sont limités à http(s)/mailto. Couverture
// volontairement bornée : titres, gras/italique/barré, code inline et blocs ```, listes (+ cases à cocher),
// citations, tableaux, hr, frontmatter YAML (bloc code discret). Le reste passe en paragraphes tels quels.
export function mdToHtml(md) {
  const E = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const inline = s => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[\s(«])\*([^*\s][^*]*)\*/g, "$1<i>$2</i>")
    .replace(/~~([^~]+)~~/g, "<s>$1</s>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) =>
      /^(https?:|mailto:)/i.test(u) ? '<a href="' + u + '" target="_blank" rel="noopener">' + t + '</a>' : m);
  const li = s => s
    .replace(/^\[ \]\s+/, "☐ ")
    .replace(/^\[[xX]\]\s+/, "☑ ");
  let src = String(md == null ? "" : md).replace(/\r\n/g, "\n");
  const out = [];
  const fm = /^---\n([\s\S]*?)\n---\n?/.exec(src);
  if (fm) { out.push('<pre class="mdfm">' + E(fm[1]) + '</pre>'); src = src.slice(fm[0].length); }
  const lines = src.split("\n");
  const para = [];
  const flush = () => { if (para.length) { out.push("<p>" + inline(E(para.join(" "))) + "</p>"); para.length = 0; } };
  let i = 0, m;
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {                                    // bloc de code clôturé
      flush(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      out.push("<pre>" + E(buf.join("\n")) + "</pre>");
      continue;
    }
    if ((m = /^(#{1,6})\s+(.*)$/.exec(l))) {                 // titres
      flush(); const n = m[1].length;
      out.push("<h" + n + ">" + inline(E(m[2])) + "</h" + n + ">"); i++; continue;
    }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(l)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length     // tableau |…| + séparateur
        && /^\s*\|[\s\-:|]+\|\s*$/.test(lines[i + 1])) {
      flush();
      const cells = r => r.trim().replace(/^\||\|$/g, "").split("|").map(c => inline(E(c.trim())));
      let h = "<table><thead><tr>" + cells(l).map(c => "<th>" + c + "</th>").join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
        h += "<tr>" + cells(lines[i]).map(c => "<td>" + c + "</td>").join("") + "</tr>"; i++;
      }
      out.push(h + "</tbody></table>"); continue;
    }
    if ((m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(l))) {       // listes (plat)
      flush();
      const tag = /^\d/.test(m[1]) ? "ol" : "ul";
      let h = "<" + tag + ">";
      while (i < lines.length && (m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]))
             && (/^\d/.test(m[1]) ? "ol" : "ul") === tag) {
        h += "<li>" + inline(li(E(m[2]))) + "</li>"; i++;
      }
      out.push(h + "</" + tag + ">"); continue;
    }
    if (/^>/.test(l)) {                                      // citation
      flush(); const buf = [];
      while (i < lines.length && (m = /^>\s?(.*)$/.exec(lines[i]))) { buf.push(m[1]); i++; }
      out.push("<blockquote>" + inline(E(buf.join(" "))) + "</blockquote>"); continue;
    }
    if (!l.trim()) { flush(); i++; continue; }
    para.push(l); i++;
  }
  flush();
  return '<div class="mdview">' + out.join("") + "</div>";
}
