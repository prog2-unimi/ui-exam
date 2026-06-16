document.querySelectorAll('[data-bs-toggle="tab"]').forEach(btn => {
  btn.addEventListener('shown.bs.tab', () => {
    const iframe = document.querySelector(btn.dataset.bsTarget + ' iframe');
    if (!iframe.src || iframe.src === window.location.href) iframe.src = iframe.dataset.src;
  });
});

const first = document.querySelector('.tab-pane.active iframe');
if (first) first.src = first.dataset.src;
