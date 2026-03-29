// ── Mobile sidebar toggle ──────────────────────────────────────────────────
function toggleSidebar() {
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebar-overlay');
  const isOpen   = sidebar.classList.contains('open');
  if (isOpen) {
    closeSidebar();
  } else {
    sidebar.classList.add('open');
    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeSidebar() {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  sidebar.classList.remove('open');
  overlay.classList.remove('active');
  document.body.style.overflow = '';
}

// Close sidebar when a nav link is tapped on mobile
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('.sidebar a').forEach(link => {
    link.addEventListener('click', () => {
      if (window.innerWidth <= 768) closeSidebar();
    });
  });
});

// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(phaseId, secKey) {
  document.querySelectorAll(`[id^="stab-${phaseId}-"]`).forEach(t => t.classList.remove('active'));
  document.querySelectorAll(`[id^="spanel-${phaseId}-"]`).forEach(p => p.classList.remove('active'));
  const tab   = document.getElementById(`stab-${phaseId}-${secKey}`);
  const panel = document.getElementById(`spanel-${phaseId}-${secKey}`);
  if (tab)   tab.classList.add('active');
  if (panel) panel.classList.add('active');
}

// ── Add-item form — clear input after HTMX swap ───────────────────────────
function clearInput(form) {
  // delay so htmx can read the value first
  setTimeout(() => {
    const inp = form.querySelector('input[name="text"]');
    if (inp) inp.value = '';
  }, 50);
}

// ── Modal helpers ─────────────────────────────────────────────────────────
function closeModal(id) {
  document.getElementById(id).style.display = 'none';
}

// Close modal on backdrop click
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('modal-backdrop')) {
    e.target.style.display = 'none';
  }
});

// Close modal on Escape
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-backdrop').forEach(m => m.style.display = 'none');
  }
});

// ── Color palette picker ──────────────────────────────────────────────────
function selectColor(el, paletteId, hiddenId) {
  document.querySelectorAll(`#${paletteId} .palette-swatch`).forEach(s => s.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById(hiddenId).value = el.dataset.color;
}

// ── Phase jump nav smooth scroll ──────────────────────────────────────────
document.querySelectorAll('.pjn-item').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute('href'));
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

// ── Highlight active phase in jump nav on scroll ──────────────────────────
const blocks = document.querySelectorAll('.phase-block');
if (blocks.length) {
  const obs = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        document.querySelectorAll('.pjn-item').forEach(l => {
          const active = l.getAttribute('href') === `#${id}`;
          l.style.borderColor = active ? 'var(--c)' : '';
          l.style.color       = active ? 'var(--c)' : '';
        });
      }
    });
  }, { threshold: 0.3 });
  blocks.forEach(b => obs.observe(b));
}