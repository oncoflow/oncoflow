"use strict";

// Interface de vérification : tout passe par l'API locale, aucune ressource externe.

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, props = {}, ...children) => {
  const node = Object.assign(document.createElement(tag), props);
  for (const child of children) node.append(child);
  return node;
};

const state = {
  config: null,
  docs: [],
  doc: null, // { id, name, markdown, entities, pages, status }
  view: "annotate",
  hiddenLabels: new Set(),
  focus: -1, // index dans state.doc.entities
  undo: [],
  lastLabel: "NOM",
  locations: {},
  zoom: 1,
  saveTimer: null,
};

// --- API ---------------------------------------------------------------------------

async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch { /* corps non JSON */ }
    throw new Error(detail);
  }
  const type = response.headers.get("content-type") || "";
  return type.includes("json") ? response.json() : response.text();
}

function toast(message, { error = false, action = null, timeout = 3500 } = {}) {
  const node = el("div", { className: "toast" + (error ? " error" : "") }, message);
  if (action) {
    const button = el("button", { textContent: action.label });
    button.onclick = () => { action.run(); node.remove(); };
    node.append(button);
  }
  $("#toasts").append(node);
  setTimeout(() => node.remove(), timeout);
}

// --- Documents -----------------------------------------------------------------------

const STATUS_TEXT = { a_verifier: "À vérifier", en_cours: "En cours", valide: "Validé" };

async function loadDocs() {
  state.docs = await api("/api/documents");
  const list = $("#doc-list");
  list.replaceChildren();
  if (!state.docs.length) list.append(el("p", { className: "muted", textContent: "Aucun document." }));
  for (const doc of state.docs) {
    const item = el(
      "div",
      { className: "doc-item" + (state.doc?.id === doc.id ? " active" : ""), title: doc.name },
      el("span", { className: "dot " + doc.status }),
      el("span", { className: "name", textContent: doc.name }),
      el("span", {
        className: "sub",
        textContent: `${STATUS_TEXT[doc.status]} · ${doc.entities} entités` + (doc.manual ? ` · ${doc.manual} ajoutées` : ""),
      }),
    );
    item.onclick = () => openDoc(doc.id);
    list.append(item);
  }
}

async function openDoc(id) {
  closePopover();
  const doc = await api(`/api/documents/${id}`);
  state.doc = doc;
  state.undo = [];
  state.focus = -1;
  state.locations = {};
  location.hash = id;
  $("#empty").hidden = true;
  for (const sel of ["#text-pane", "#splitter", "#pdf-pane"]) $(sel).hidden = false;
  $("#doc-title").textContent = `${doc.name} · conversion ${doc.engine}`;
  renderAll();
  renderPdf();
  refreshLocations();
  loadDocs();
}

async function upload(files) {
  const zone = $("#dropzone");
  zone.classList.add("busy");
  let lastId = null;
  for (const file of files) {
    const form = new FormData();
    form.append("file", file);
    toast(`Conversion et analyse de « ${file.name} »…`, { timeout: 2500 });
    try {
      lastId = (await api("/api/documents", { method: "POST", body: form })).id;
    } catch (error) {
      toast(`${file.name} : ${error.message}`, { error: true, timeout: 6000 });
    }
  }
  zone.classList.remove("busy");
  await loadDocs();
  if (lastId) openDoc(lastId);
}

// --- Rendu du texte --------------------------------------------------------------------

function renderAll() {
  renderLegend();
  if (state.view === "annotate") renderText();
  else renderPreview();
  updateValidateButton();
}

function renderLegend() {
  const counts = {};
  for (const e of state.doc.entities) if (e.state !== "rejected") counts[e.label] = (counts[e.label] || 0) + 1;
  const legend = $("#legend");
  legend.replaceChildren();
  for (const [label, name] of Object.entries(state.config.labels)) {
    if (!counts[label]) continue;
    const chip = el(
      "span",
      { className: "chip" + (state.hiddenLabels.has(label) ? " off" : ""), title: "Afficher / masquer" },
      el("span", { className: "sw", style: `background: var(--${label})` }),
      name,
      el("span", { className: "count", textContent: counts[label] }),
    );
    chip.onclick = () => {
      state.hiddenLabels.has(label) ? state.hiddenLabels.delete(label) : state.hiddenLabels.add(label);
      renderAll();
    };
    legend.append(chip);
  }
  const rejected = state.doc.entities.filter((e) => e.state === "rejected").length;
  const added = state.doc.entities.filter((e) => e.state === "added").length;
  if (added) legend.append(el("span", { className: "chip stat", textContent: `✚ ${added} ajoutée(s)` }));
  if (rejected) legend.append(el("span", { className: "chip stat", textContent: `✕ ${rejected} rejetée(s)` }));
}

// Chaque morceau de texte porte sa position (data-s) pour retrouver les offsets d'une sélection.
function textChunk(text, start) {
  const frag = document.createDocumentFragment();
  const re = /\||\*\*|<br>/g;
  let cursor = 0;
  let match;
  const push = (from, to, cls) => {
    if (to <= from) return;
    const span = el("span", { textContent: text.slice(from, to) });
    span.dataset.s = start + from;
    if (cls) span.className = cls;
    frag.append(span);
  };
  while ((match = re.exec(text))) {
    push(cursor, match.index);
    push(match.index, match.index + match[0].length, match[0] === "|" ? "pipe" : "dim");
    cursor = match.index + match[0].length;
  }
  push(cursor, text.length);
  return frag;
}

function renderText() {
  const md = $("#md");
  const text = state.doc.markdown;
  const frag = document.createDocumentFragment();
  let cursor = 0;
  state.doc.entities.forEach((entity, index) => {
    if (entity.start < cursor) return;
    frag.append(textChunk(text.slice(cursor, entity.start), cursor));
    const mark = el("mark", { className: `ent ${entity.state}` });
    mark.style.setProperty("--c", `var(--${entity.label})`);
    if (state.hiddenLabels.has(entity.label)) mark.classList.add("hidden-label");
    if (index === state.focus) mark.classList.add("focus");
    mark.dataset.i = index;
    mark.title = `${state.config.labels[entity.label]} — ${state.config.sources[entity.source] || entity.source}`;
    mark.append(textChunk(text.slice(entity.start, entity.end), entity.start));
    frag.append(mark);
    cursor = entity.end;
  });
  frag.append(textChunk(text.slice(cursor), cursor));
  md.replaceChildren(frag);
  $("#md").hidden = false;
  $("#preview").hidden = true;
}

async function renderPreview() {
  const strategy = $("#strategy").value;
  const output = await api(`/api/documents/${state.doc.id}/output?strategy=${strategy}`);
  const pre = $("#preview");
  pre.replaceChildren();
  // Mise en évidence des remplacements « [ETIQUETTE] ».
  const re = /\[(?:[A-Z_]+)\]/g;
  let cursor = 0;
  let match;
  while ((match = re.exec(output))) {
    pre.append(output.slice(cursor, match.index), el("mark", { textContent: match[0] }));
    cursor = match.index + match[0].length;
  }
  pre.append(output.slice(cursor));
  $("#md").hidden = true;
  pre.hidden = false;
}

function setView(view) {
  state.view = view;
  for (const button of document.querySelectorAll(".segmented button")) {
    button.classList.toggle("active", button.dataset.view === view);
  }
  $("#strategy").hidden = view !== "preview";
  closePopover();
  if (state.doc) renderAll();
}

// --- Sélection et offsets ------------------------------------------------------------

function offsetOf(node, offset) {
  // Remonte jusqu'à l'élément portant data-s (morceau de texte).
  let element = node.nodeType === Node.TEXT_NODE ? node.parentElement : node;
  if (node.nodeType !== Node.TEXT_NODE) {
    const child = node.childNodes[offset] || node.lastChild;
    if (child && child !== node) return offsetOf(child, 0);
  }
  while (element && element.dataset?.s === undefined) element = element.parentElement;
  if (!element) return null;
  return Number(element.dataset.s) + (node.nodeType === Node.TEXT_NODE ? offset : 0);
}

// Étend la sélection aux mots entiers et retire espaces / séparateurs de bord.
function snap(start, end) {
  const text = state.doc.markdown;
  const word = /[\p{L}\p{N}'’@._-]/u;
  while (start > 0 && word.test(text[start - 1]) && word.test(text[start])) start--;
  while (end < text.length && word.test(text[end]) && word.test(text[end - 1])) end++;
  while (start < end && /[\s|*:;,]/.test(text[start])) start++;
  while (end > start && /[\s|*:;,.]/.test(text[end - 1])) end--;
  return [start, end];
}

function onSelection(event) {
  if (state.view !== "annotate") return;
  const selection = window.getSelection();
  if (!selection.rangeCount || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  if (!$("#md").contains(range.commonAncestorContainer)) return;
  let start = offsetOf(range.startContainer, range.startOffset);
  let end = offsetOf(range.endContainer, range.endOffset);
  if (start === null || end === null) return;
  [start, end] = snap(Math.min(start, end), Math.max(start, end));
  if (end <= start) return;
  showLabelPicker({ start, end }, event);
  probePdf(start, end);
}

// --- Popovers ---------------------------------------------------------------------------

let popoverKeys = null;

function closePopover() {
  $("#popover").hidden = true;
  popoverKeys = null;
  document.querySelectorAll(".box.probe").forEach((b) => b.remove());
}

function placePopover(x, y) {
  const pop = $("#popover");
  pop.hidden = false;
  const { width, height } = pop.getBoundingClientRect();
  pop.style.left = `${Math.min(Math.max(8, x - width / 2), innerWidth - width - 8)}px`;
  pop.style.top = `${y + 12 + height > innerHeight ? Math.max(8, y - height - 12) : y + 12}px`;
}

function labelGrid(current, onPick) {
  const grid = el("div", { className: "label-grid" });
  const keys = {};
  Object.entries(state.config.labels).forEach(([label, name], i) => {
    const key = i < 9 ? String(i + 1) : i === 9 ? "0" : "";
    const button = el(
      "button",
      { className: "label-btn" + (label === current ? " current" : "") },
      el("span", { className: "sw" }),
      name,
    );
    button.style.setProperty("--c", `var(--${label})`);
    if (key) { button.append(el("kbd", { textContent: key })); keys[key] = label; }
    button.onclick = () => onPick(label);
    grid.append(button);
  });
  return { grid, keys };
}

function showLabelPicker(range, event) {
  const text = state.doc.markdown.slice(range.start, range.end);
  const pop = $("#popover");
  const pick = (label) => {
    state.lastLabel = label;
    addEntity(range.start, range.end, label);
    window.getSelection().removeAllRanges();
    closePopover();
  };
  const { grid, keys } = labelGrid(state.lastLabel, pick);
  pop.replaceChildren(
    el("div", { className: "quote", textContent: text }),
    grid,
    el("div", {
      className: "hint",
      innerHTML: `<kbd>Entrée</kbd> ${state.config.labels[state.lastLabel]} · <kbd>Échap</kbd> annuler`,
    }),
  );
  popoverKeys = { ...keys, Enter: state.lastLabel, pick };
  const rect = window.getSelection().getRangeAt(0).getBoundingClientRect();
  placePopover(rect.left + rect.width / 2 || event.clientX, rect.bottom || event.clientY);
}

function showEntityPopover(index) {
  const entity = state.doc.entities[index];
  setFocus(index, { scrollText: false });
  const pop = $("#popover");
  const relabel = (label) => { changeLabel(index, label); closePopover(); };
  const { grid, keys } = labelGrid(entity.label, relabel);
  const actions = el("div", { className: "actions" });
  if (entity.state === "rejected") {
    const restore = el("button", { className: "btn", textContent: "Rétablir (X)" });
    restore.onclick = () => { toggleReject(index); closePopover(); };
    actions.append(restore);
  } else {
    const reject = el("button", {
      className: "btn danger",
      textContent: entity.state === "added" ? "Supprimer (X)" : "Pas identifiant (X)",
    });
    reject.onclick = () => { toggleReject(index); closePopover(); };
    actions.append(reject);
  }
  pop.replaceChildren(
    el("div", { className: "quote", textContent: entity.text }),
    el("div", { className: "source", textContent: state.config.sources[entity.source] || entity.source }),
    grid,
    actions,
  );
  popoverKeys = { ...keys, pick: relabel, x: () => { toggleReject(index); closePopover(); } };
  const mark = $(`#md mark[data-i="${index}"]`);
  const rect = mark ? mark.getBoundingClientRect() : { left: innerWidth / 2, width: 0, bottom: 120 };
  placePopover(rect.left + rect.width / 2, rect.bottom);
}

// --- Modifications ----------------------------------------------------------------------

function snapshot() {
  state.undo.push(JSON.stringify(state.doc.entities));
  if (state.undo.length > 100) state.undo.shift();
}

function addEntity(start, end, label) {
  snapshot();
  const overlaps = (e) => e.start < end && start < e.end;
  state.doc.entities = state.doc.entities.filter((e) => !overlaps(e));
  const text = state.doc.markdown.slice(start, end);
  state.doc.entities.push({ start, end, label, source: "manuel", state: "added", text, auto_label: label });
  state.doc.entities.sort((a, b) => a.start - b.start);
  afterChange(`« ${text} » masqué (${state.config.labels[label]}) et ajouté au lexique`);
  setFocus(state.doc.entities.findIndex((e) => e.start === start && e.end === end), { scrollText: false });
}

function toggleReject(index) {
  const entity = state.doc.entities[index];
  if (!entity) return;
  snapshot();
  let message;
  if (entity.state === "added") {
    state.doc.entities.splice(index, 1);
    message = "Annotation supprimée";
  } else if (entity.state === "rejected") {
    entity.state = "detected";
    message = `« ${entity.text} » de nouveau masqué`;
  } else {
    entity.state = "rejected";
    message = `« ${entity.text} » ne sera plus masqué`;
  }
  afterChange(message);
}

function changeLabel(index, label) {
  const entity = state.doc.entities[index];
  if (!entity || entity.label === label) return;
  snapshot();
  entity.label = label;
  if (entity.state === "rejected") entity.state = "detected";
  state.lastLabel = label;
  afterChange(`Étiquette : ${state.config.labels[label]}`);
}

function undo() {
  const previous = state.undo.pop();
  if (!previous) return toast("Rien à annuler");
  state.doc.entities = JSON.parse(previous);
  afterChange("Modification annulée", { learn: false });
}

function annotationsPayload() {
  const pick = ({ start, end, label, source }) => ({ start, end, label, source });
  const entities = state.doc.entities;
  return {
    added: entities.filter((e) => e.state === "added").map(pick),
    rejected: entities.filter((e) => e.state === "rejected").map(pick),
    relabeled: entities.filter((e) => e.state !== "added" && e.label !== e.auto_label).map(pick),
  };
}

function afterChange(message, { learn = true } = {}) {
  renderAll();
  refreshLocations();
  $("#save-state").textContent = "Enregistrement…";
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(() => save(learn), 250);
  if (message) {
    toast(message, { action: learn ? { label: "Annuler", run: undo } : null });
  }
}

async function save(learn = true) {
  const id = state.doc.id;
  try {
    const result = await api(`/api/documents/${id}/annotations?learn=${learn}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(annotationsPayload()),
    });
    if (state.doc.id !== id) return;
    state.doc.entities = result.entities;
    $("#save-state").textContent = "Enregistré ✓";
    renderAll();
    loadDocs();
  } catch (error) {
    $("#save-state").textContent = "";
    toast(`Échec de l'enregistrement : ${error.message}`, { error: true });
  }
}

// --- Navigation -------------------------------------------------------------------------

function setFocus(index, { scrollText = true } = {}) {
  const entities = state.doc.entities;
  if (!entities.length) return;
  state.focus = (index + entities.length) % entities.length;
  document.querySelectorAll("#md mark.focus").forEach((m) => m.classList.remove("focus"));
  const mark = $(`#md mark[data-i="${state.focus}"]`);
  if (mark) {
    mark.classList.add("focus");
    if (scrollText) mark.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  highlightBoxes(entities[state.focus].start, true);
}

async function validate() {
  if (!state.doc) return;
  const status = state.doc.status === "valide" ? "en_cours" : "valide";
  const meta = await api(`/api/documents/${state.doc.id}/status/${status}`, { method: "PUT" });
  state.doc.status = meta.status;
  updateValidateButton();
  loadDocs();
  if (status === "valide") {
    toast("Document validé : ses annotations seront incluses dans l'export d'entraînement");
    const next = state.docs.find((d) => d.status !== "valide" && d.id !== state.doc.id);
    if (next) toast(`Document suivant : ${next.name}`, { action: { label: "Ouvrir", run: () => openDoc(next.id) } });
  }
}

function updateValidateButton() {
  const button = $("#btn-validate");
  const done = state.doc?.status === "valide";
  button.textContent = done ? "Validé ✓" : "Valider le document";
  button.classList.toggle("done", done);
}

// --- PDF ------------------------------------------------------------------------------

function renderPdf() {
  const scroll = $("#pdf-scroll");
  scroll.replaceChildren();
  if (!state.doc.pages.length) {
    scroll.append(el("div", { className: "no-pdf", textContent: "Aperçu natif disponible pour les PDF uniquement." }));
    return;
  }
  const width = Math.round((scroll.clientWidth - 64) * state.zoom);
  state.doc.pages.forEach((page, number) => {
    const container = el("div", { className: "pdf-page" });
    container.dataset.page = number;
    container.style.width = `${width}px`;
    container.style.aspectRatio = `${page.width} / ${page.height}`;
    container.append(
      el("img", { src: `/api/documents/${state.doc.id}/pages/${number}.png?zoom=2`, loading: "lazy", alt: `Page ${number + 1}` }),
      el("span", { className: "page-num", textContent: number + 1 }),
    );
    scroll.append(container);
  });
  drawBoxes();
}

async function refreshLocations() {
  if (!state.doc?.pages.length) return;
  const id = state.doc.id;
  try {
    const locations = await api(`/api/documents/${id}/locations`);
    if (state.doc.id !== id) return;
    state.locations = locations;
    drawBoxes();
  } catch { /* aperçu facultatif */ }
}

function boxNode(rect, page, cls) {
  const node = el("div", { className: `box ${cls}` });
  node.style.left = `${(rect.x0 / page.width) * 100}%`;
  node.style.top = `${(rect.y0 / page.height) * 100}%`;
  node.style.width = `${((rect.x1 - rect.x0) / page.width) * 100}%`;
  node.style.height = `${((rect.y1 - rect.y0) / page.height) * 100}%`;
  return node;
}

function drawBoxes() {
  document.querySelectorAll(".box:not(.probe)").forEach((b) => b.remove());
  const pages = document.querySelectorAll(".pdf-page");
  state.doc.entities.forEach((entity, index) => {
    for (const rect of state.locations[entity.start] || []) {
      const container = pages[rect.page];
      if (!container) continue;
      const node = boxNode(rect, state.doc.pages[rect.page], entity.state);
      node.style.setProperty("--c", `var(--${entity.label})`);
      node.dataset.start = entity.start;
      node.title = `${entity.text} — ${state.config.labels[entity.label]}`;
      node.onmouseenter = () => hoverEntity(index, true);
      node.onmouseleave = () => hoverEntity(index, false);
      node.onclick = () => {
        const mark = $(`#md mark[data-i="${index}"]`);
        mark?.scrollIntoView({ block: "center", behavior: "smooth" });
        mark?.classList.add("flash");
        setTimeout(() => showEntityPopover(index), 250);
      };
      container.append(node);
    }
  });
}

function highlightBoxes(start, scroll) {
  document.querySelectorAll(".box.hover").forEach((b) => b.classList.remove("hover"));
  const boxes = document.querySelectorAll(`.box[data-start="${start}"]`);
  boxes.forEach((b) => b.classList.add("hover"));
  if (scroll && boxes.length && $("#follow").checked) boxes[0].scrollIntoView({ block: "center", behavior: "smooth" });
}

function hoverEntity(index, on) {
  const mark = $(`#md mark[data-i="${index}"]`);
  mark?.classList.toggle("hover", on);
  if (on) highlightBoxes(state.doc.entities[index].start, false);
  else document.querySelectorAll(".box.hover").forEach((b) => b.classList.remove("hover"));
}

async function probePdf(start, end) {
  if (!state.doc.pages.length) return;
  try {
    const rects = await api(`/api/documents/${state.doc.id}/locate?start=${start}&end=${end}`);
    const pages = document.querySelectorAll(".pdf-page");
    rects.forEach((rect, i) => {
      const node = boxNode(rect, state.doc.pages[rect.page], "probe");
      pages[rect.page]?.append(node);
      if (i === 0 && $("#follow").checked) node.scrollIntoView({ block: "center", behavior: "smooth" });
    });
  } catch { /* sans incidence */ }
}

// --- Lexique ----------------------------------------------------------------------------

async function openLexicon() {
  const lexicon = await api("/api/lexicon");
  const body = $("#lexicon-body");
  body.replaceChildren();
  const section = (title, entries, remove, empty) => {
    body.append(el("h4", { textContent: title }));
    if (!entries.length) body.append(el("p", { className: "muted", textContent: empty }));
    for (const [key, value] of entries) {
      const button = el("button", { className: "icon-btn", textContent: "×", title: "Retirer" });
      button.onclick = async () => { remove(key); await api("/api/lexicon", putJson(lexicon)); openLexicon(); };
      body.append(el("div", { className: "lex-row" }, el("span", { textContent: key }), el("span", { className: "muted", textContent: value }), button));
    }
  };
  section("Toujours masquer", Object.entries(lexicon.always), (k) => delete lexicon.always[k], "Sélectionnez un identifiant oublié pour l'ajouter.");
  section("Ne jamais masquer", lexicon.never.map((k) => [k, ""]), (k) => (lexicon.never = lexicon.never.filter((x) => x !== k)), "Marquez une détection « pas identifiante » pour l'ajouter.");
  section("Libellés de champ appris", Object.entries(lexicon.cues), (k) => delete lexicon.cues[k], "Appris quand vous annotez la valeur d'un champ (« Libellé : valeur »).");
  $("#lexicon-drawer").hidden = false;
}

const putJson = (data) => ({ method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify(data) });

async function redetectAll() {
  const result = await api("/api/redetect", { method: "POST" });
  toast(`${result.documents} document(s) ré-analysé(s) avec le lexique appris`);
  if (state.doc) openDoc(state.doc.id);
  else loadDocs();
}

// --- Événements ----------------------------------------------------------------------------

function bindEvents() {
  $("#md").addEventListener("mouseup", (event) => setTimeout(() => onSelection(event), 0));
  $("#md").addEventListener("click", (event) => {
    const mark = event.target.closest("mark.ent");
    if (mark && window.getSelection().isCollapsed) showEntityPopover(Number(mark.dataset.i));
  });
  $("#md").addEventListener("mouseover", (event) => {
    const mark = event.target.closest("mark.ent");
    if (mark) hoverEntity(Number(mark.dataset.i), true);
  });
  $("#md").addEventListener("mouseout", (event) => {
    const mark = event.target.closest("mark.ent");
    if (mark) hoverEntity(Number(mark.dataset.i), false);
  });
  document.addEventListener("mousedown", (event) => {
    if (!$("#popover").hidden && !event.target.closest("#popover")) closePopover();
  });

  for (const button of document.querySelectorAll(".segmented button")) button.onclick = () => setView(button.dataset.view);
  $("#strategy").onchange = () => state.doc && renderPreview();
  $("#btn-validate").onclick = validate;
  $("#btn-download").onclick = () => {
    if (!state.doc) return;
    const link = el("a", {
      href: `/api/documents/${state.doc.id}/output?strategy=${$("#strategy").value}`,
      download: state.doc.name.replace(/\.[^.]+$/, "") + ".pseudonymise.md",
    });
    link.click();
  };
  $("#btn-help").onclick = () => ($("#help").hidden = false);
  $("#btn-lexicon").onclick = openLexicon;
  $("#btn-redetect-all").onclick = redetectAll;
  $("#toggle-sidebar").onclick = () => $("#sidebar").classList.toggle("collapsed");
  for (const close of document.querySelectorAll("[data-close]")) {
    close.onclick = () => (close.closest(".drawer, .modal").hidden = true);
  }
  $("#zoom-in").onclick = () => { state.zoom = Math.min(state.zoom + 0.2, 2.4); renderPdf(); };
  $("#zoom-out").onclick = () => { state.zoom = Math.max(state.zoom - 0.2, 0.4); renderPdf(); };

  const zone = $("#dropzone");
  $("#file-input").onchange = (event) => upload([...event.target.files]);
  for (const target of [zone, document.body]) {
    target.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("over"); });
    target.addEventListener("dragleave", () => zone.classList.remove("over"));
    target.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("over");
      upload([...event.dataTransfer.files]);
    });
  }

  // Séparateur redimensionnable entre texte et PDF.
  const splitter = $("#splitter");
  splitter.addEventListener("mousedown", (event) => {
    event.preventDefault();
    splitter.classList.add("drag");
    const workspace = $("#workspace").getBoundingClientRect();
    const move = (e) => {
      const ratio = Math.min(Math.max((e.clientX - workspace.left) / workspace.width, 0.25), 0.8);
      $("#text-pane").style.flex = `0 0 ${ratio * 100}%`;
      $("#pdf-pane").style.flex = "1 1 0";
    };
    const up = () => {
      splitter.classList.remove("drag");
      removeEventListener("mousemove", move);
      removeEventListener("mouseup", up);
      if (state.doc) renderPdf();
    };
    addEventListener("mousemove", move);
    addEventListener("mouseup", up);
  });

  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, select, textarea")) return;
    if (event.key === "Escape") {
      closePopover();
      for (const sel of ["#help", "#lexicon-drawer"]) $(sel).hidden = true;
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      return undo();
    }
    if (popoverKeys) {
      const label = popoverKeys[event.key];
      if (event.key === "x" && popoverKeys.x) { event.preventDefault(); return popoverKeys.x(); }
      if (label) { event.preventDefault(); return popoverKeys.pick(label); }
      return;
    }
    if (!state.doc || event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toLowerCase();
    if (key === "?") $("#help").hidden = false;
    else if (key === "j") setFocus(state.focus + 1);
    else if (key === "k") setFocus(state.focus - 1);
    else if (key === "x" && state.focus >= 0) toggleReject(state.focus);
    else if (key === "v") validate();
    else if (key === "enter" && state.focus >= 0) showEntityPopover(state.focus);
    else return;
    event.preventDefault();
  });
  addEventListener("resize", () => state.doc && renderPdf());
}

async function main() {
  state.config = await api("/api/config");
  bindEvents();
  await loadDocs();
  const id = location.hash.slice(1);
  if (id && state.docs.some((d) => d.id === id)) openDoc(id);
}

main().catch((error) => toast(error.message, { error: true, timeout: 10000 }));
