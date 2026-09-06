#!/usr/bin/env node
// css-stamp — inscrit en tête de cockpit.css l'empreinte des sources SCSS : `test_cockpit_runtime.js` la recalcule et refuse un build périmé
// (sans exiger sass pour tester). Lancé par `npm run build:css` après la compilation.
"use strict";
const fs = require("fs"), path = require("path"), crypto = require("crypto"); const DIR = path.join(__dirname, "..");
const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap(x => x.isDirectory() ? walk(path.join(d, x.name)) : (x.name.endsWith(".scss") ? [path.join(d, x.name)] : []));
const files = walk(path.join(DIR, "src")).sort();
const h = crypto.createHash("sha256"); for (const f of files) { h.update(path.relative(DIR, f)); h.update("\0"); h.update(fs.readFileSync(f)); h.update("\0"); }
const stamp = h.digest("hex").slice(0, 16);
const out = path.join(DIR, "cockpit.css"); const css = fs.readFileSync(out, "utf8").replace(/^\/\* cockpit\.css — GÉNÉRÉ[^\n]*\n/, "");
fs.writeFileSync(out, `/* cockpit.css — GÉNÉRÉ depuis src/styles/main.scss par \`npm run build:css\` (deploy/karl-agent/cockpit) — ne pas éditer à la main ; empreinte des sources scss : ${stamp} (${files.length} fichiers) */\n` + css);
if (process.argv.includes("--print")) console.log(stamp);
