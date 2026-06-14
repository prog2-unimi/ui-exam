const fmtDate = (d) => d || '';

const _activeEmail = (JSON.parse(sessionStorage.getItem('examTimer') || 'null') || {}).email || null;

const table = new DataTable('#students-table', {
  data: CFG.students,
  pageLength: 50,
  order: [[0, 'asc']],
  layout: {
    topStart: null,
    topEnd: null,
    bottomStart: 'info',
    bottomEnd: 'paging',
  },
  createdRow: (row, data) => { if (data.email === _activeEmail) row.classList.add('table-warning'); },
  columns: [
    { data: 'name' },
    { data: 'email',
      render: (d) => `<a href="/student/${d}">${d}</a>` },
    { data: 'matricola' },
    { data: 'attempts',       className: 'text-end' },
    { data: 'first',          render: fmtDate },
    { data: 'last',           render: fmtDate },
    { data: 'first_attempt',  render: fmtDate },
    { data: null, orderable: false,
      render: (_, __, row) => renderMark(row.summary_mark, row.in_current ? '' : undefined) },
  ],
});

const FILTER_KEY = 'history-filters';

function saveFilters() {
  sessionStorage.setItem(FILTER_KEY, JSON.stringify({
    date:    document.getElementById('date-filter').value,
    kind:    document.getElementById('kind-filter').value,
    order:   table.order(),
    search:  table.search(),
    pageLen: table.page.len(),
  }));
}

function restoreFilters() {
  const saved = sessionStorage.getItem(FILTER_KEY);
  if (!saved) return;
  try {
    const f = JSON.parse(saved);
    document.getElementById('date-filter').value  = f.date  ?? '';
    document.getElementById('kind-filter').value  = f.kind  ?? '';
    if (f.order)   table.order(f.order);
    if (f.search)  { document.getElementById('dt-search').value = f.search; table.search(f.search); }
    if (f.pageLen) { document.getElementById('page-len').value  = f.pageLen; table.page.len(f.pageLen); }
  } catch (_) {}
}

DataTable.ext.search.push((_settings, _data, _idx, row) => {
  const date = document.getElementById('date-filter').value;
  if (date && !row.dates.includes(date)) return false;
  const kind = document.getElementById('kind-filter').value;
  if (kind === 'nuovo')        { if (!(row.in_current && !row.summary_mark)) return false; }
  else if (kind === 'assente') { if (row.summary_mark !== null) return false; }
  else if (kind)               { if (row.summary_mark?.kind !== kind) return false; }
  return true;
});

restoreFilters();
table.draw();

function onChange() { saveFilters(); table.draw(); }
document.getElementById('date-filter').addEventListener('change', onChange);
document.getElementById('kind-filter').addEventListener('change', onChange);
table.on('order.dt', saveFilters);

document.getElementById('dt-search').addEventListener('input', function() {
  table.search(this.value).draw();
  saveFilters();
});

document.getElementById('page-len').addEventListener('change', function() {
  table.page.len(parseInt(this.value)).draw();
  saveFilters();
});

// Re-apply filters on bfcache restore
window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });

if (_activeEmail) {
  const btn = document.getElementById('active-btn');
  const s   = CFG.students.find(s => s.email === _activeEmail);
  btn.href      = `/student/${_activeEmail}`;
  btn.innerHTML = `<i class="bi bi-stopwatch"></i> ${s ? s.name : _activeEmail}`;
  btn.classList.remove('d-none');
}
