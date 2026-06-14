
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
  createdRow: (row, data) => { if (data.email === _activeEmail) row.classList.add('table-warning'); },
  columns: [
    { data: 'slot',    render: fmtSlot },
    { data: 'name',
      render: (d, _, row) => {
        const icon = row.is_current ? '<i class="bi bi-caret-right-fill text-primary me-1"></i>'
                   : row.is_next    ? '<i class="bi bi-caret-right text-secondary me-1"></i>'
                   : '';
        return `${icon}<a href="/student/${row.email}">${d}</a>`;
      }},
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

DataTable.ext.search.push((_settings, _data, _idx, row) => {
  if (document.getElementById('today-filter').checked && !(row.slot && row.slot.startsWith(CFG.today))) return false;
  if (document.getElementById('new-filter').checked && row.summary_mark !== null) return false;
  return true;
});

table.draw();

document.getElementById('today-filter').addEventListener('change', () => table.draw());
document.getElementById('new-filter').addEventListener('change', () => table.draw());

document.getElementById('dt-search').addEventListener('input', function() {
  table.search(this.value).draw();
});

document.getElementById('page-len').addEventListener('change', function() {
  table.page.len(parseInt(this.value)).draw();
});

window.addEventListener('pageshow', e => { if (e.persisted) table.draw(); });

if (_activeEmail) {
  const btn = document.getElementById('active-btn');
  const s   = CFG.rows.find(r => r.email === _activeEmail);
  btn.href      = `/student/${_activeEmail}`;
  btn.innerHTML = `<i class="bi bi-stopwatch"></i> ${s ? s.name : _activeEmail}`;
  btn.classList.remove('d-none');
}
