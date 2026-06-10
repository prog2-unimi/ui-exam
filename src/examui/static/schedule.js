function renderMark(vm, cm) {
  const KIND_CLS = { pass: 'bg-success', tilde: 'bg-primary', RE: 'bg-danger', RI: 'bg-warning text-dark' };
  let html = '';
  if (vm) html += `<span class="badge ${KIND_CLS[vm.kind] ?? 'bg-secondary'}">${vm.value}</span> `;
  if (cm === '??') html += `<span class="badge bg-secondary">??</span>`;
  else if (cm && cm !== 'AS') html += `<span class="badge bg-warning text-dark">${cm}</span>`;
  return html;
}

function fmtSlot(slot) {
  if (!slot) return '';
  // YYMMDD-HHMM → DD/MM/YY HH:MM
  const d = slot.slice(0, 6);
  const t = slot.slice(7);
  return `${d.slice(4)}-${d.slice(2, 4)}-${d.slice(0, 2)} ${t.slice(0, 2)}:${t.slice(2)}`;
}

function mkBadge(val, okVal) {
  const ok = val === okVal;
  return `<span class="badge ${ok ? 'bg-success' : 'bg-danger'}">${val}</span>`;
}

const table = new DataTable('#schedule-table', {
  data: CFG.rows,
  pageLength: 50,
  order: [[0, 'asc']],
  layout: {
    topStart: null,
    topEnd: null,
    bottomStart: 'info',
    bottomEnd: 'paging',
  },
  columns: [
    { data: 'slot',    render: fmtSlot },
    { data: 'name',
      render: (d, _, row) => `<a href="/student/${row.email}">${d}</a>` },
    { data: null, orderable: false,
      render: (_, __, row) => renderMark(row.verbali_mark, row.current_mark) },
    { data: 'tests',   render: (d) => mkBadge(d, 'SUCCESS') },
    { data: 'javadoc', render: (d) => mkBadge(d, 'SUCCESS') },
    { data: 'cyclic',  render: (d) => mkBadge(d, 'NO') },
    { data: 'code',    className: 'text-end' },
    { data: 'docs',    className: 'text-end' },
    { data: 'file',    className: 'text-end' },
    { data: 'num',     className: 'text-end' },
  ],
});

DataTable.ext.search.push((_settings, _data, _idx, row) => {
  if (!document.getElementById('today-filter').checked) return true;
  return row.slot.startsWith(CFG.today);
});

table.draw();

document.getElementById('today-filter').addEventListener('change', () => table.draw());

document.getElementById('dt-search').addEventListener('input', function() {
  table.search(this.value).draw();
});

document.getElementById('page-len').addEventListener('change', function() {
  table.page.len(parseInt(this.value)).draw();
});

window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });
