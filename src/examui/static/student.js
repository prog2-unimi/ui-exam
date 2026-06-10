// ── Slot timer ───────────────────────────────────────────────────────────────
const TIMER_KEY = 'examTimer';
let _timerInterval = null;

function _fmtMs(ms) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function _tickTimer() {
  const stored = JSON.parse(sessionStorage.getItem(TIMER_KEY) || 'null');
  if (!stored || stored.email !== CFG.email) return;

  const elapsed = Date.now() - stored.startMs;
  const pct     = Math.min(elapsed / stored.slotMs * 100, 100);
  const remain  = Math.max(0, stored.slotMs - elapsed);

  document.getElementById('timer-display').textContent =
    `${_fmtMs(elapsed)} / ${_fmtMs(stored.slotMs)}`;

  const bar = document.getElementById('timer-bar');
  bar.style.width = pct + '%';
  if (pct >= 90) {
    bar.className = 'progress-bar bg-danger progress-bar-striped' + (pct >= 95 ? ' progress-bar-animated' : '');
  } else if (pct >= 80) {
    bar.className = 'progress-bar bg-warning';
  } else {
    bar.className = 'progress-bar bg-success';
  }

  const badge = document.getElementById('timer-badge');
  const remMin = Math.ceil(remain / 60000);
  if (pct >= 90) {
    badge.textContent = `⚠ ${remMin} min left`;
    badge.className = 'badge bg-danger';
  } else if (pct >= 80) {
    badge.textContent = `⚠ ${remMin} min left`;
    badge.className = 'badge bg-warning text-dark';
  } else {
    badge.className = 'badge d-none';
  }
}

function _startTimerUI() {
  document.getElementById('timer-btn').textContent = 'Reset';
  _timerInterval = setInterval(_tickTimer, 500);
  _tickTimer();
}

function startTimer() {
  const slotMin = parseInt(document.getElementById('slot-input').value) || CFG.slotMinutes;
  sessionStorage.setItem(TIMER_KEY, JSON.stringify({
    email:   CFG.email,
    startMs: Date.now(),
    slotMs:  slotMin * 60000,
  }));
  _startTimerUI();
}

function resetTimer() {
  clearInterval(_timerInterval);
  _timerInterval = null;
  sessionStorage.removeItem(TIMER_KEY);
  const slotMin = parseInt(document.getElementById('slot-input').value) || CFG.slotMinutes;
  document.getElementById('timer-btn').textContent = 'Start';
  document.getElementById('timer-display').textContent = `0:00 / ${slotMin}:00`;
  document.getElementById('timer-bar').className = 'progress-bar bg-success';
  document.getElementById('timer-bar').style.width = '0%';
  document.getElementById('timer-badge').className = 'badge d-none';
}

if (document.getElementById('timer-btn')) {
  document.getElementById('timer-btn').addEventListener('click', () => {
    const stored = JSON.parse(sessionStorage.getItem(TIMER_KEY) || 'null');
    if (stored && stored.email === CFG.email) resetTimer();
    else startTimer();
  });

  // Restore timer if one is already running for this student
  (function loadTimer() {
    const stored = JSON.parse(sessionStorage.getItem(TIMER_KEY) || 'null');
    if (!stored || stored.email !== CFG.email) return;
    document.getElementById('slot-input').value = Math.round(stored.slotMs / 60000);
    _startTimerUI();
  })();
}

// ── Note save (short + long, single endpoint) ─────────────────────────────────
const longNoteEditor  = document.getElementById('long-note-editor');
const shortNoteInput  = document.getElementById('short-note-input');
const noteStatus      = document.getElementById('note-status');
let savedLongNote     = longNoteEditor ? longNoteEditor.value : '';
let savedShortNote    = shortNoteInput ? shortNoteInput.value : '';
let noteTimer         = null;

function setNoteStatus(text, color) {
  if (!noteStatus) return;
  noteStatus.textContent = text;
  noteStatus.style.color = color;
}

function saveNote() {
  if (!longNoteEditor) return;
  if (longNoteEditor.value === savedLongNote && shortNoteInput.value === savedShortNote) return;
  const fd = new FormData();
  fd.append('long_note',  longNoteEditor.value);
  fd.append('short_note', shortNoteInput ? shortNoteInput.value : '');
  fetch(CFG.urls.saveNote, { method: 'POST', body: fd })
    .then(() => {
      savedLongNote  = longNoteEditor.value;
      savedShortNote = shortNoteInput ? shortNoteInput.value : '';
      setNoteStatus('✓', 'var(--bs-success)');
      setTimeout(() => setNoteStatus('', ''), 1500);
    });
}

if (longNoteEditor) {
  longNoteEditor.addEventListener('input', () => {
    setNoteStatus('•', 'var(--bs-secondary)');
    clearTimeout(noteTimer);
    noteTimer = setTimeout(saveNote, 2000);
  });
  longNoteEditor.addEventListener('blur', () => { clearTimeout(noteTimer); saveNote(); });
}

if (shortNoteInput) {
  shortNoteInput.addEventListener('input', () => {
    setNoteStatus('•', 'var(--bs-secondary)');
    clearTimeout(noteTimer);
    noteTimer = setTimeout(saveNote, 2000);
  });
  shortNoteInput.addEventListener('blur', () => { clearTimeout(noteTimer); saveNote(); });
  shortNoteInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); shortNoteInput.blur(); } });
}

// ── Mark save ────────────────────────────────────────────────────────────────
const markInput  = document.getElementById('mark-input');
const markStatus = document.getElementById('mark-status');

if (markInput) {
  function saveMark() {
    const fd = new FormData();
    fd.append('mark', markInput.value.trim());
    fetch(CFG.urls.saveMark, { method: 'POST', body: fd })
      .then(r => {
        markStatus.textContent = r.ok ? '✓' : '✗';
        markStatus.style.color = r.ok ? 'var(--bs-success)' : 'var(--bs-danger)';
        if (r.ok) setTimeout(() => { markStatus.textContent = ''; }, 1500);
      });
  }
  markInput.addEventListener('blur', saveMark);
  markInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); markInput.blur(); } });
}

// ── Source navigator ─────────────────────────────────────────────────────────
const SYM_SEARCH_MIN_LEN = 3;
let allSymbols  = [];
let _activeFile = null;

function renderTree(nodes, depth=0) {
  let html = `<ul class="list-unstyled mb-0${depth ? ' ms-3' : ''}">`;
  for (const n of nodes) {
    if (n.type === 'dir') {
      html += `<li>
        <div class="d-flex align-items-center gap-1 text-muted py-0" style="user-select:none;">
          <i class="bi bi-folder2-open" style="font-size:.75rem;"></i>
          <span>${n.name}</span>
        </div>
        ${renderTree(n.children, depth + 1)}
      </li>`;
    } else {
      html += `<li>
        <div class="source-file d-flex align-items-center gap-1 px-1 rounded py-0"
             data-path="${n.path}" role="button">
          <i class="bi bi-filetype-java text-primary" style="font-size:.75rem;"></i>
          <span>${n.name}</span>
        </div>
      </li>`;
    }
  }
  return html + '</ul>';
}

function filterNodes(nodes, mode) {
  if (mode === 'all') return nodes;
  const wantTrivial = mode === 'trivial';
  return nodes.flatMap(n => {
    if (n.type === 'file') return n.trivial === wantTrivial ? [n] : [];
    if (n.trivial)         return wantTrivial ? [n] : [];
    const children = filterNodes(n.children ?? [], mode);
    return children.length ? [{ ...n, children }] : [];
  });
}

let _fullTree = [];

function applyTree() {
  const el   = document.getElementById('source-tree');
  const mode = document.getElementById('tree-filter').value;
  const tree = filterNodes(_fullTree, mode);
  if (!tree.length) { el.textContent = 'No files.'; return; }
  el.innerHTML = renderTree(tree);
  el.querySelectorAll('.source-file').forEach(div => {
    div.addEventListener('click', () => loadSourceFile(div.dataset.path, div));
  });
  if (_activeFile) {
    const active = el.querySelector(`.source-file[data-path="${_activeFile}"]`);
    if (active) active.classList.add('active');
  }
}

async function loadSourceTree() {
  const resp = await fetch(CFG.urls.sourceTree);
  _fullTree  = await resp.json();
  applyTree();
  document.getElementById('tree-filter').addEventListener('change', applyTree);
}

async function loadAllSymbols() {
  const resp = await fetch(CFG.urls.sourceSymbols);
  allSymbols = await resp.json();
}

function renderSymbolSearch(query) {
  const el      = document.getElementById('source-tree');
  const q       = query.toLowerCase();
  const matches = allSymbols.filter(s => s.name.toLowerCase().includes(q));

  if (!matches.length) {
    el.innerHTML = '<div class="px-2 py-1 text-muted small">No symbols found.</div>';
    return;
  }

  const byFile = new Map();
  for (const sym of matches) {
    if (!byFile.has(sym.file)) byFile.set(sym.file, []);
    byFile.get(sym.file).push(sym);
  }

  let html = '<ul class="list-unstyled mb-0">';
  for (const [file, syms] of byFile) {
    const basename = file.split('/').pop();
    html += `<li>
      <div class="source-file d-flex align-items-center gap-1 px-1 rounded py-0"
           data-path="${file}" role="button" title="${file}" style="font-weight:500;">
        <i class="bi bi-filetype-java text-primary" style="font-size:.75rem;"></i>
        <span>${basename}</span>
      </div>
      <ul class="list-unstyled mb-0 ms-3">`;
    for (const sym of syms) {
      html += `<li>
        <div class="source-file d-flex align-items-center gap-1 px-1 rounded py-0"
             data-path="${file}" data-line="${sym.line}" role="button">
          <span class="text-muted" style="font-size:.7rem; min-width:3.2rem;">[${sym.kind}]</span>
          <span>${sym.name}</span>
        </div>
      </li>`;
    }
    html += `</ul></li>`;
  }
  html += '</ul>';
  el.innerHTML = html;

  el.querySelectorAll('.source-file[data-line]').forEach(div => {
    div.addEventListener('click', () => openSymbol(div.dataset.path, parseInt(div.dataset.line)));
  });
  el.querySelectorAll('.source-file:not([data-line])').forEach(div => {
    div.addEventListener('click', () => openSymbol(div.dataset.path, null));
  });
}

async function openSymbol(relpath, line) {
  bootstrap.Tab.getOrCreateInstance(
    document.querySelector('[data-bs-target="#tab-source"]')
  ).show();
  await loadSourceFile(relpath, null);
  if (line !== null) scrollToLine(line);
}

document.getElementById('sym-search').addEventListener('input', function() {
  const q = this.value.trim();
  if (q.length >= SYM_SEARCH_MIN_LEN) renderSymbolSearch(q);
  else applyTree();
});

async function loadSourceFile(relpath, clickedEl) {
  _activeFile = relpath;
  document.querySelectorAll('.source-file').forEach(d => d.classList.remove('active'));
  if (clickedEl) clickedEl.classList.add('active');

  document.getElementById('src-filename').textContent = relpath;
  document.getElementById('source-code').innerHTML =
    '<div class="p-3 text-muted">Loading…</div>';

  const resp = await fetch(CFG.urls.sourceFile + '?path=' + encodeURIComponent(relpath));
  const data = await resp.json();

  const jdBase = relpath.endsWith('.java')
    ? CFG.urls.javadoc + relpath.slice(0, -5) + '.html'
    : null;
  const symLines  = new Map(data.symbols.map(s => [s.line, s]));
  const TYPE_KINDS = new Set(['class', 'interface', 'enum', 'record']);

  const linesHtml = data.lines.map((lineHtml, i) => {
    const n   = i + 1;
    const sym = symLines.get(n);
    const hasJdLink = sym && jdBase && (sym.anchor || TYPE_KINDS.has(sym.kind));
    const gutter = hasJdLink
      ? `<span class="src-gutter"><i class="bi bi-book src-jd" data-jd="${jdBase}${sym.anchor ? '#' + sym.anchor : ''}" title="${sym.name}"></i></span>`
      : `<span class="src-gutter"></span>`;
    return `<div id="src-L${n}" class="src-line"><span class="src-ln">${n}</span>${gutter}<span class="src-code">${lineHtml}</span></div>`;
  }).join('');

  document.getElementById('source-code').innerHTML =
    `<div class="src"><div class="src-pre">${linesHtml}</div></div>`;
  applyFontSize();

  document.querySelectorAll('.src-jd').forEach(icon => {
    icon.addEventListener('click', () => openJavadoc(icon.dataset.jd));
  });

  const sel = document.getElementById('sym-select');
  if (data.symbols.length) {
    sel.style.display = '';
    sel.innerHTML = data.symbols
      .map(s => `<option value="${s.line}">[${s.kind}] ${s.name}</option>`)
      .join('');
    sel.onchange = () => scrollToLine(parseInt(sel.value));
  } else {
    sel.style.display = 'none';
  }
}

function openJavadoc(url) {
  const frame  = document.getElementById('javadoc-frame');
  const tabBtn = document.getElementById('javadoc-tab-btn');
  if (!frame || !tabBtn) return;
  const pane = document.getElementById('tab-javadoc');
  if (pane.classList.contains('show')) {
    frame.src = url;
  } else {
    tabBtn.addEventListener('shown.bs.tab', () => { frame.src = url; }, { once: true });
    bootstrap.Tab.getOrCreateInstance(tabBtn).show();
  }
}

function scrollToLine(line) {
  const el = document.getElementById('src-L' + line);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ── Font size ────────────────────────────────────────────────────────────────
const fsEl  = document.getElementById('src-fontsize');
const fsKey = 'oral-src-font-size';
const saved = localStorage.getItem(fsKey);
if (saved) { fsEl.value = saved; document.documentElement.style.setProperty('--src-font-size', saved + 'px'); }

function applyFontSize() {
  document.documentElement.style.setProperty('--src-font-size', fsEl.value + 'px');
}
fsEl.addEventListener('change', () => { localStorage.setItem(fsKey, fsEl.value); applyFontSize(); });

// Load tree + symbol index the first time the Source tab is shown
document.querySelector('[data-bs-target="#tab-source"]')
  .addEventListener('shown.bs.tab', function onFirst() {
    loadSourceTree();
    loadAllSymbols();
    this.removeEventListener('shown.bs.tab', onFirst);
  });

// ── Dependency graph ─────────────────────────────────────────────────────────
async function loadDepsGraph() {
  const container = document.getElementById('deps-container');
  const loading   = document.getElementById('deps-loading');
  loading.style.display = '';

  const resp = await fetch(CFG.urls.sourceDeps);
  const data = await resp.json();
  loading.style.display = 'none';

  if (!data.svg) {
    container.innerHTML = '<p class="text-muted p-3">No dependency data.</p>';
    return;
  }

  container.innerHTML = data.svg;

  const svgEl = container.querySelector('svg');
  if (svgEl) {
    const vb = svgEl.viewBox?.baseVal;
    if (vb && vb.width && vb.height) {
      const pad = 16;
      const scale = Math.min(
        (container.clientWidth  - pad) / vb.width,
        (container.clientHeight - pad) / vb.height
      );
      svgEl.setAttribute('width',  Math.round(vb.width  * scale));
      svgEl.setAttribute('height', Math.round(vb.height * scale));
    }
  }

  Object.entries(data.paths).forEach(([nid, relpath]) => {
    const el = document.getElementById(nid);
    if (!el) return;
    el.style.cursor = 'pointer';
    el.addEventListener('click', () => {
      loadSourceFile(relpath, null);
      bootstrap.Tab.getOrCreateInstance(
        document.querySelector('[data-bs-target="#tab-source"]')
      ).show();
    });
  });
}

document.getElementById('deps-tab-btn')
  .addEventListener('shown.bs.tab', function onFirst() {
    loadDepsGraph();
    this.removeEventListener('shown.bs.tab', onFirst);
  });
