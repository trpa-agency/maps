/* TRPA Maps — gallery renderer.
   Each page sets window.GALLERY_CONFIG = { base: '' | '..', category: null | 'slug' }
   before loading this script. Apps live in apps.json at the repo root. */
(function () {
  const cfg = Object.assign({ base: '', category: null }, window.GALLERY_CONFIG || {});
  const base = cfg.base ? cfg.base.replace(/\/$/, '') + '/' : '';

  function hostOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ''); }
    catch (e) { return ''; }
  }

  function resolveUrl(url) {
    // Absolute URLs pass through; repo-relative URLs get the page's base prefix
    return /^[a-z]+:\/\//i.test(url) ? url : base + url;
  }

  function cardHTML(app, catColor) {
    const thumb = app.thumbnail
      ? `<div class="thumb" style="--cat-color:${catColor}; background-image:url('${base}${app.thumbnail}')"></div>`
      : `<div class="thumb placeholder" style="--cat-color:${catColor}">${app.title.charAt(0)}</div>`;
    const tags = (app.tags || []).map(t => `<span class="tag">${t}</span>`).join('');
    const isAbsolute = /^[a-z]+:\/\//i.test(app.url);
    const host = isAbsolute ? hostOf(app.url) : location.hostname.replace(/^www\./, '');
    return `<a class="app-card" href="${resolveUrl(app.url)}" target="_blank" rel="noopener" data-search="${(app.title + ' ' + app.description + ' ' + (app.tags || []).join(' ')).toLowerCase()}">
      ${thumb}
      <div class="card-body">
        <h3>${app.title}${app.beta ? ' <span class="beta-pill">Beta</span>' : ''}</h3>
        <p>${app.description}</p>
      </div>
      <div class="card-footer">
        <span>${tags}</span>
        <span class="host">${host}</span>
      </div>
    </a>`;
  }

  function sectionHTML(cat, apps, linkHeading) {
    const heading = linkHeading
      ? `<a href="${base}${cat.slug}/">${cat.name}</a><span class="view-all">View section &rsaquo;</span>`
      : cat.name;
    const cards = apps.map(a => cardHTML(a, cat.color)).join('');
    const body = apps.length
      ? `<div class="card-grid">${cards}</div>`
      : `<p class="empty-note">Apps coming soon.</p>`;
    return `<section class="category-section" style="--cat-color:${cat.color}" data-category="${cat.slug}">
      <h2>${heading}</h2>
      <p class="cat-desc">${cat.description}</p>
      ${body}
    </section>`;
  }

  function wireSearch() {
    const input = document.getElementById('app-search');
    if (!input) return;
    input.addEventListener('calciteInputInput', function () {
      const q = (input.value || '').trim().toLowerCase();
      document.querySelectorAll('.app-card').forEach(card => {
        card.style.display = !q || card.dataset.search.includes(q) ? '' : 'none';
      });
      document.querySelectorAll('.category-section').forEach(sec => {
        const anyVisible = [...sec.querySelectorAll('.app-card')].some(c => c.style.display !== 'none');
        sec.style.display = anyVisible || !q ? '' : 'none';
      });
    });
  }

  fetch(base + 'apps.json')
    .then(r => r.json())
    .then(data => {
      const target = document.getElementById('gallery');
      if (!target) return;

      const cats = cfg.category
        ? data.categories.filter(c => c.slug === cfg.category)
        : data.categories;

      target.innerHTML = cats.map(cat => {
        const apps = data.apps.filter(a => a.category === cat.slug);
        return sectionHTML(cat, apps, !cfg.category);
      }).join('');

      // Category nav pills on the home page
      const pills = document.getElementById('cat-pills');
      if (pills && !cfg.category) {
        pills.innerHTML = data.categories.map(c =>
          `<a class="cat-pill" style="--pill-color:${c.color}" href="${base}${c.slug}/">${c.name}</a>`
        ).join('');
      }

      wireSearch();
    })
    .catch(err => {
      const target = document.getElementById('gallery');
      if (target) target.innerHTML = '<p class="empty-note">Unable to load the app list. Please try again later.</p>';
      console.error('Failed to load apps.json', err);
    });
})();
