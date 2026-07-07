const _activeTimer = JSON.parse(sessionStorage.getItem('examTimer') || 'null');
if (_activeTimer) {
  const btn = document.getElementById('active-btn');
  btn.href      = `/student/${_activeTimer.email}`;
  btn.innerHTML = `<i class="bi bi-stopwatch"></i> ${_activeTimer.name || _activeTimer.email}`;
  btn.classList.remove('d-none');
}

document.querySelectorAll('[data-bs-toggle="tab"]').forEach(btn => {
  btn.addEventListener('shown.bs.tab', () => {
    const iframe = document.querySelector(btn.dataset.bsTarget + ' iframe');
    if (!iframe.src || iframe.src === window.location.href) iframe.src = iframe.dataset.src;
  });
});

const first = document.querySelector('.tab-pane.active iframe');
if (first) first.src = first.dataset.src;
