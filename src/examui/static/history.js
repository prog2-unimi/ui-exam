const fmtDate = (d) => d ? `${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4)}` : '';

function renderMark(vm, cm) {
  const KIND_CLS = { pass: 'bg-success', tilde: 'bg-primary', RE: 'bg-danger', RI: 'bg-warning text-dark' };
  let html = '';
  if (vm) html += `<span class="badge ${KIND_CLS[vm.kind] ?? 'bg-secondary'}">${vm.value}</span>`;
  if (!vm && cm && cm !== 'AS') html += `<span class="badge bg-warning text-dark">${cm}</span>`;
  return html;
}

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
  columns: [
    { data: 'name' },
    { data: 'email',
      render: (d) => `<a href="/${d}">${d}</a>` },
    { data: 'matricola' },
    { data: 'n', className: 'text-end' },
    { data: 'first',      render: fmtDate },
    { data: 'last',       render: fmtDate },
    { data: 'first_eval', render: fmtDate },
    { data: null, orderable: false,
      render: (_, __, row) => renderMark(row.verbali_mark, row.current_mark) },
  ],
});

const FILTER_KEY = 'history-filters';

function saveFilters() {
  sessionStorage.setItem(FILTER_KEY, JSON.stringify({
    date:       document.getElementById('date-filter').value,
    refused:    document.getElementById('refused-filter').checked,
    examSource: document.getElementById('exam-source-filter').checked,
    order:      table.order(),
    search:     table.search(),
    pageLen:    table.page.len(),
  }));
}

function restoreFilters() {
  const saved = sessionStorage.getItem(FILTER_KEY);
  if (!saved) return;
  try {
    const f = JSON.parse(saved);
    document.getElementById('date-filter').value          = f.date       ?? '';
    document.getElementById('refused-filter').checked     = f.refused    ?? false;
    document.getElementById('exam-source-filter').checked = f.examSource ?? false;
    if (f.order)   table.order(f.order);
    if (f.search)  { document.getElementById('dt-search').value = f.search; table.search(f.search); }
    if (f.pageLen) { document.getElementById('page-len').value  = f.pageLen; table.page.len(f.pageLen); }
  } catch (_) {}
}

DataTable.ext.search.push((_settings, _data, _idx, row) => {
  const date = document.getElementById('date-filter').value;
  if (date && !row.dates.includes(date)) return false;
  if (document.getElementById('refused-filter').checked && !row.has_refused) return false;
  if (document.getElementById('exam-source-filter').checked) {
    if (!row.dates.includes(CFG.examDate) || !row.has_source) return false;
  }
  return true;
});

restoreFilters();
table.draw();

function onChange() { saveFilters(); table.draw(); }
document.getElementById('date-filter').addEventListener('change', onChange);
document.getElementById('refused-filter').addEventListener('change', onChange);
document.getElementById('exam-source-filter').addEventListener('change', function() {
  if (this.checked) document.getElementById('date-filter').value = CFG.examDate;
  onChange();
});
table.on('order.dt', saveFilters);

document.getElementById('dt-search').addEventListener('input', function() {
  table.search(this.value).draw();
  saveFilters();
});

document.getElementById('page-len').addEventListener('change', function() {
  table.page.len(parseInt(this.value)).draw();
  saveFilters();
});

// Re-apply filters on bfcache restore (browser back/forward without full reload)
window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });
