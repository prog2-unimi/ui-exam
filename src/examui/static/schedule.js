
function fmtSlot(slot) {
  if (!slot) return '<i class="bi bi-exclamation-triangle-fill text-warning"></i>';
  const d = new Date(slot);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${dd}/${mm} ${hh}:${mi}`;
}

function iconFail(val) {
  return val
    ? '<i class="bi bi-x-circle-fill text-danger"></i>'
    : '<i class="bi bi-check-circle-fill text-success"></i>';
}

function iconCycles(val) {
  return val ? '<i class="bi bi-exclamation-triangle-fill text-danger"></i>' : '';
}

const _activeEmail = (JSON.parse(sessionStorage.getItem('examTimer') || 'null') || {}).email || null;

const selectedEmails = new Set();

function syncCheckboxes() {
  document.querySelectorAll('.bcc-check').forEach(cb => {
    cb.checked = selectedEmails.has(cb.dataset.email);
  });
  document.getElementById('actions-btn').disabled = selectedEmails.size === 0;
  const giustifica = document.getElementById('giustifica-action');
  const singleWithSlot = selectedEmails.size === 1 &&
    CFG.rows.some(r => selectedEmails.has(r.email) && r.slot);
  if (singleWithSlot) giustifica.classList.remove('disabled');
  else giustifica.classList.add('disabled');
  const sifa = document.getElementById('sifa-action');
  if (selectedEmails.size > 0) sifa.classList.remove('disabled');
  else sifa.classList.add('disabled');
}

const table = new DataTable('#schedule-table', {
  data: CFG.rows,
  paging: false,
  order: [[1, 'asc']],
  layout: {
    topStart: null,
    topEnd: null,
    bottomStart: null,
    bottomEnd: null,
  },
  createdRow: (row, data) => { if (data.email === _activeEmail) row.classList.add('table-warning'); },
  drawCallback: syncCheckboxes,
  columns: [
    { data: 'email', orderable: false, searchable: false,
      render: email => `<input type="checkbox" class="bcc-check" data-email="${email}">` },
    { data: 'slot', render: (d, type) => type === 'sort' ? (d || '9999') : fmtSlot(d) },
    { data: 'name',
      render: (d, _, row) => {
        const icon = row.is_current ? '<i class="bi bi-caret-right-fill text-primary me-1"></i>'
                   : row.is_next    ? '<i class="bi bi-caret-right text-secondary me-1"></i>'
                   : '';
        return `${icon}<a href="/student/${row.email}">${d}</a>`;
      }},
    { data: 'matricola' },
    { data: null, orderable: false,
      render: (_, __, row) => renderMark(row.summary_mark, row.current_mark) },
    { data: 'tests_fail',   className: 'text-center', render: iconFail },
    { data: 'javadoc_fail', className: 'text-center', render: iconFail },
    { data: 'has_cycles',   className: 'text-center', render: iconCycles },
    { data: 'main_sloc',    className: 'text-end' },
    { data: 'main_docs',    className: 'text-end' },
    { data: 'main_files',   className: 'text-end' },
    { data: 'client_sloc',  className: 'text-end' },
    { data: 'client_files', className: 'text-end' },
  ],
});

table.on('draw.dt', () => {
  document.getElementById('row-count').textContent = table.rows({ search: 'applied' }).count();
});

DataTable.ext.search.push((_settings, _data, _idx, row) => {
  const date = document.getElementById('date-filter').value;
  if (date === '__unbooked__' && row.slot) return false;
  else if (date && date !== '__unbooked__' && !(row.slot && row.slot.startsWith(date))) return false;
  if (document.getElementById('new-filter').checked && row.summary_mark !== null) return false;
  return true;
});

const FILTER_KEY = 'schedule-filters';

function saveFilters() {
  sessionStorage.setItem(FILTER_KEY, JSON.stringify({
    date:    document.getElementById('date-filter').value,
    newOnly: document.getElementById('new-filter').checked,
    order:   table.order(),
    search:  table.search(),
  }));
}

function restoreFilters() {
  const saved = sessionStorage.getItem(FILTER_KEY);
  if (!saved) return;
  try {
    const f = JSON.parse(saved);
    document.getElementById('date-filter').value = f.date ?? '';
    document.getElementById('new-filter').checked = f.newOnly ?? false;
    if (f.order)  table.order(f.order);
    if (f.search) { document.getElementById('dt-search').value = f.search; table.search(f.search); }
  } catch (_) {}
}

restoreFilters();
table.draw();

function onChange() { saveFilters(); table.draw(); }
document.getElementById('date-filter').addEventListener('change', onChange);
document.getElementById('new-filter').addEventListener('change', onChange);
table.on('order.dt', saveFilters);

document.getElementById('dt-search').addEventListener('input', function() {
  table.search(this.value).draw();
  saveFilters();
});

document.getElementById('schedule-table').addEventListener('click', e => {
  const cb = e.target.closest('.bcc-check');
  if (!cb) return;
  if (cb.checked) selectedEmails.add(cb.dataset.email);
  else selectedEmails.delete(cb.dataset.email);
  syncCheckboxes();
});

document.getElementById('select-all').addEventListener('change', function() {
  document.querySelectorAll('.bcc-check').forEach(cb => {
    cb.checked = this.checked;
    if (this.checked) selectedEmails.add(cb.dataset.email);
    else selectedEmails.delete(cb.dataset.email);
  });
  syncCheckboxes();
});

document.getElementById('giustifica-action').addEventListener('click', e => {
  e.preventDefault();
  const email = [...selectedEmails][0];
  const row = CFG.rows.find(r => r.email === email);
  if (!row || !row.slot) return;
  const slot = new Date(row.slot);
  const fmt = d => `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  const endSlot = new Date(slot.getTime() + CFG.slotMinutes * 60000);
  document.getElementById('giustifica-inizio').value = fmt(slot);
  document.getElementById('giustifica-fine').value = fmt(endSlot);
  new bootstrap.Modal(document.getElementById('giustifica-modal')).show();
});

document.getElementById('giustifica-round').addEventListener('click', () => {
  const floorHour = v => { const [h] = v.split(':'); return `${h.padStart(2,'0')}:00`; };
  const ceilHour  = v => { const [h, m] = v.split(':').map(Number);
    return m === 0 ? v : `${String((h + 1) % 24).padStart(2,'0')}:00`; };
  const ini = document.getElementById('giustifica-inizio');
  const fin = document.getElementById('giustifica-fine');
  if (ini.value) ini.value = floorHour(ini.value);
  if (fin.value) fin.value = ceilHour(fin.value);
});

document.getElementById('giustifica-confirm').addEventListener('click', () => {
  const email = [...selectedEmails][0];
  const params = new URLSearchParams({
    titolo: document.getElementById('titolo-select').value,
    inizio: document.getElementById('giustifica-inizio').value,
    fine:   document.getElementById('giustifica-fine').value,
  });
  window.open(`/student/${email}/giustifica?${params}`, '_blank');
  bootstrap.Modal.getInstance(document.getElementById('giustifica-modal')).hide();
});

document.getElementById('bcc-action').addEventListener('click', e => {
  e.preventDefault();
  const bcc = [...selectedEmails]
    .map(e => CFG.emailDomain ? `${e}@${CFG.emailDomain}` : e)
    .join(',');
  const to = CFG.teacherName ? `${CFG.teacherName} <${CFG.teacherEmail}>` : CFG.teacherEmail;
  const qs = `to=${encodeURIComponent(to)}&bcc=${encodeURIComponent(bcc)}&subject=${encodeURIComponent(CFG.subjectPrefix)}`;
  window.location.href = `mailto:?${qs}`;
});

document.getElementById('sifa-action').addEventListener('click', e => {
  e.preventDefault();
  const rows = CFG.rows.filter(r => selectedEmails.has(r.email) && r.current_mark);
  if (!rows.length) return;
  const fmtDate = slot => {
    const d = new Date(slot || CFG.examDate);
    const p = n => String(n).padStart(2, '0');
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`;
  };
  const csv = rows.map(r => `${r.matricola},${r.current_mark},${fmtDate(r.slot)}`).join('\n');
  const now = new Date();
  const p = n => String(n).padStart(2, '0');
  const fname = `sifa-${now.getFullYear()}${p(now.getMonth()+1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}.csv`;
  const a = Object.assign(document.createElement('a'), {
    href: URL.createObjectURL(new Blob([csv], {type: 'text/csv'})),
    download: fname,
  });
  a.click();
  URL.revokeObjectURL(a.href);
});

window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });

if (_activeEmail) {
  const btn = document.getElementById('active-btn');
  const s   = CFG.rows.find(r => r.email === _activeEmail);
  btn.href      = `/student/${_activeEmail}`;
  btn.innerHTML = `<i class="bi bi-stopwatch"></i> ${s ? s.name : _activeEmail}`;
  btn.classList.remove('d-none');
}
