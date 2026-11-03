#!/usr/bin/env node
// DataSyntis design system — WCAG 2.2 contrast check of tokens.css (zero dependency).
// Usage: node web/scripts/check-contrast.mjs   (exit code 1 if any pair fails)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const cssPath = fileURLToPath(new URL("../public/css/tokens.css", import.meta.url));
const css = readFileSync(cssPath, "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function block(selector) {
  const start = css.indexOf(selector);
  if (start < 0) throw new Error(`selector not found: ${selector}`);
  const open = css.indexOf("{", start);
  let depth = 1, i = open + 1;
  while (depth) { if (css[i] === "{") depth++; else if (css[i] === "}") depth--; i++; }
  const vars = {};
  for (const m of css.slice(open + 1, i - 1).matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[m[1]] = m[2].trim();
  return vars;
}

const light = block(":root");
const dark = { ...light, ...block(':root[data-theme="dark"]') };

function resolve(vars, name, depth = 0) {
  let v = vars[name];
  if (v === undefined) throw new Error(`unknown token ${name}`);
  const ref = v.match(/^var\((--[\w-]+)\)$/);
  if (ref && depth < 10) return resolve(vars, ref[1], depth + 1);
  return v;
}

const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
function luminance(hex) {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => lin(parseInt(h.slice(i, i + 2), 16) / 255));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function ratio(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground token, background token, minimum]  4.5 = text, 3 = UI/graphics
const TEXT = 4.5, UI = 3;
const pairs = [
  ["--ds-color-text", "--ds-color-canvas", TEXT],
  ["--ds-color-text", "--ds-color-surface", TEXT],
  ["--ds-color-text", "--ds-color-surface-sunken", TEXT],
  ["--ds-color-text-muted", "--ds-color-canvas", TEXT],
  ["--ds-color-text-muted", "--ds-color-surface", TEXT],
  ["--ds-color-text-muted", "--ds-color-surface-sunken", TEXT],
  ["--ds-color-text-subtle", "--ds-color-surface", TEXT],
  ["--ds-color-border-strong", "--ds-color-surface", UI],
  ["--ds-color-on-primary", "--ds-color-primary", TEXT],
  ["--ds-color-on-primary", "--ds-color-primary-hover", TEXT],
  ["--ds-color-primary-text", "--ds-color-surface", TEXT],
  ["--ds-color-primary-text", "--ds-color-canvas", TEXT],
  ["--ds-color-primary-text", "--ds-color-primary-soft", TEXT],
  ["--ds-color-primary", "--ds-color-surface", UI],
  ["--ds-color-focus", "--ds-color-surface", UI],
  ["--ds-color-focus", "--ds-color-canvas", UI],
  ["--ds-color-on-danger", "--ds-color-danger", TEXT],
  ["--ds-color-on-danger", "--ds-color-danger-hover", TEXT],
  ["--ds-color-danger-text", "--ds-color-surface", TEXT],
  ["--ds-color-danger-text", "--ds-color-danger-bg", TEXT],
  ["--ds-color-danger-fg", "--ds-color-danger-bg", TEXT],
  ["--ds-color-danger", "--ds-color-surface", UI],
  ["--ds-color-success-fg", "--ds-color-success-bg", TEXT],
  ["--ds-color-success-fg", "--ds-color-surface", TEXT],
  ["--ds-color-success", "--ds-color-surface", UI],
  ["--ds-color-warning-fg", "--ds-color-warning-bg", TEXT],
  ["--ds-color-warning-fg", "--ds-color-surface", TEXT],
  ["--ds-color-warning", "--ds-color-surface", UI],
  ["--ds-color-info-fg", "--ds-color-info-bg", TEXT],
  ["--ds-color-info-fg", "--ds-color-surface", TEXT],
  ["--ds-color-neutral-fg", "--ds-color-neutral-bg", TEXT],
  ["--ds-color-neutral", "--ds-color-surface", UI],
  ["--ds-orientation-adapt-fg", "--ds-orientation-adapt-bg", TEXT],
  ["--ds-manual-fg", "--ds-manual-bg", TEXT],
  ["--ds-manual", "--ds-color-surface", UI],
  ["--ds-specialty-fg", "--ds-specialty-bg", TEXT],
  ["--ds-domain-onco-fg", "--ds-domain-onco-bg", TEXT],
  ["--ds-domain-sma-fg", "--ds-domain-sma-bg", TEXT],
  ["--ds-sidebar-text", "--ds-sidebar-bg", TEXT],
  ["--ds-sidebar-text-muted", "--ds-sidebar-bg", TEXT],
  ["--ds-sidebar-active-text", "--ds-sidebar-active-bg", TEXT],
  ["--ds-sidebar-text", "--ds-sidebar-bg-hover", TEXT],
  ["--ds-sidebar-brand-accent", "--ds-sidebar-bg", TEXT], // "Syntis" wordmark in sidebar
  ["--ds-table-header-text", "--ds-table-header-bg", TEXT],
];

let failures = 0;
for (const [theme, vars] of [["light", light], ["dark", dark]]) {
  console.log(`\n## ${theme}`);
  for (const [fg, bg, min] of pairs) {
    const f = resolve(vars, fg), b = resolve(vars, bg);
    const r = ratio(f, b);
    const ok = r >= min;
    if (!ok) failures++;
    console.log(`${ok ? "PASS" : "FAIL"} ${r.toFixed(2).padStart(5)}:1 (≥${min})  ${fg} ${f}  on  ${bg} ${b}`);
  }
}
console.log(`\n${failures} failure(s)`);
process.exit(failures ? 1 : 0);
