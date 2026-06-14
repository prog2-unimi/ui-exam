const MARK_CSS = {
  passato:   'bg-success',
  rifiutato: 'bg-primary',
  respinto:  'bg-danger',
  ritirato:  'bg-orange',
};

const MARK_LABEL = {
  respinto: 'RE',
  ritirato: 'RI',
};

function updateClock() {
  const el = document.getElementById('wall-clock');
  if (!el) return;
  const now = new Date();
  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  el.textContent = `${hh}:${mm}`;
}

updateClock();
setInterval(updateClock, 1000);

function updatePaceBadge() {
  fetch('/api/pace')
    .then(r => r.json())
    .then(d => {
      const el = document.getElementById('pace-badge');
      if (!el || !d.has_slots) return;
      if (d.done === d.total || (d.expected === 0 && d.done === 0)) {
        el.className = 'd-none badge fs-6';
        return;
      }
      const abs = Math.abs(d.delta);
      const [prefix, cls] = d.delta >= 0
        ? ['+', 'badge fs-6 bg-success']
        : ['-', 'badge fs-6 bg-danger'];
      el.className = cls;
      el.textContent = `${prefix}${abs}m`;
    })
    .catch(() => {});
}

updatePaceBadge();
setInterval(updatePaceBadge, 60000);

function renderMark(vm, cm) {
  const inSchedule = cm !== undefined;
  const hasProvisional = inSchedule && !!cm;

  if (hasProvisional) {
    return `<span class="badge bg-warning text-dark">${cm}</span>`;
  }
  if (vm) {
    const label = MARK_LABEL[vm.kind] ?? String(vm.value);
    return `<span class="badge ${MARK_CSS[vm.kind] ?? 'bg-secondary'}">${label}</span>`;
  }
  if (inSchedule) {
    return `<span class="badge bg-info" style="min-width:2.2em;">&nbsp;</span>`;
  }
  return '';
}
