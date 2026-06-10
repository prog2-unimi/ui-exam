const fmtDate = (d) => d ? `${d.slice(0,2)}-${d.slice(2,4)}-${d.slice(4)}` : '';

const table = new DataTable('#students-table', {
  data: CFG.students,
  pageLength: 50,
  order: [[0, 'asc']],
  columns: [
    { data: 'name' },
    { data: 'email',
      render: (d) => `<a href="/history/${d}">${d}</a>` },
    { data: 'matricola' },
    { data: 'n', className: 'text-end' },
    { data: 'first',      render: fmtDate },
    { data: 'last',       render: fmtDate },
    { data: 'first_eval', render: fmtDate },
  ],
});

const FILTER_KEY = 'history-filters';

function saveFilters() {
  sessionStorage.setItem(FILTER_KEY, JSON.stringify({
    date:       document.getElementById('date-filter').value,
    refused:    document.getElementById('refused-filter').checked,
    examSource: document.getElementById('exam-source-filter').checked,
    order:      table.order(),
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
    if (f.order) table.order(f.order);
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
document.getElementById('exam-source-filter').addEventListener('change', onChange);
table.on('order.dt', saveFilters);

// Re-apply filters on bfcache restore (browser back/forward without full reload)
window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });
