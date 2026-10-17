'use strict';
(() => {
  const data = window.RED_COMMERCE_DATA;
  if (!data) return;
  const pct = value => `${(100 * value).toFixed(2)}%`;
  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (cls) node.className = cls;
    return node;
  };
  const barRoot = document.getElementById('model-bars');
  const tableBody = document.querySelector('#main-table tbody');
  data.main.forEach(model => {
    const row = el('div', undefined, 'bar-row');
    const label = el('div', undefined, 'bar-label');
    label.append(el('span', model.name), el('strong', pct(model.asr)));
    const track = el('div', undefined, 'bar-track');
    const fill = el('div', undefined, 'bar-fill');
    fill.style.width = `${model.asr / .5 * 100}%`;
    track.append(fill); row.append(label, track); barRoot.append(row);
    const tr = el('tr');
    const th = el('th', model.name); th.scope = 'row'; tr.append(th);
    [`${model.successes} / ${model.eligible}`, pct(model.asr), pct(model.macro_asr), model.service_excluded, model.unresolved].forEach(v => tr.append(el('td', v)));
    tableBody.append(tr);
  });
  const scale = el('div', undefined, 'bar-scale');
  ['0%', '25%', '50%'].forEach(v => scale.append(el('span', v))); barRoot.append(scale);

  const heatmap = el('table', undefined, 'heatmap');
  const caption = el('caption', 'Attack success rate by lifecycle stage (%)', 'sr-only');
  heatmap.append(caption);
  const head = el('thead'), heading = el('tr');
  ['', 'Aware.', 'Discov.', 'Engage.', 'Decision', 'Transact.', 'Fulfill.', 'Service'].forEach((name,i) => {
    const th = el('th', name); th.scope = 'col';
    if (i) th.title = data.corpus.stages[i-1];
    heading.append(th);
  });
  head.append(heading); heatmap.append(head);
  const body = el('tbody');
  data.main.forEach(model => {
    const row = el('tr'); const th = el('th', model.name); th.scope = 'row'; row.append(th);
    model.stages.forEach((stage,i) => {
      const td = el('td', stage.asr === null ? '—' : (100 * stage.asr).toFixed(1));
      const strength = Math.min(1, (stage.asr || 0) / .7);
      td.style.backgroundColor = `rgb(${Math.round(240-strength*127)}, ${Math.round(243-strength*97)}, ${Math.round(239-strength*81)})`;
      td.title = `${data.corpus.stages[i]}: ${stage.successes} successes / ${stage.eligible} evaluable`;
      row.append(td);
    });
    body.append(row);
  });
  heatmap.append(body); document.getElementById('stage-heatmap').append(heatmap);

  const filter = document.getElementById('stage-filter'), search = document.getElementById('task-search');
  data.corpus.stages.forEach((name,i) => { const option = el('option', name); option.value = String(i+1); filter.append(option); });
  const grid = document.getElementById('task-grid');
  function renderTasks() {
    const query = search.value.trim().toLowerCase();
    const matches = data.cases.filter(task => (filter.value === 'all' || String(task.stage) === filter.value)
      && `${task.title} ${task.id} ${task.instruction}`.toLowerCase().includes(query));
    grid.replaceChildren();
    document.getElementById('task-count').textContent = `${matches.length} of ${data.corpus.cases} tasks · ${matches.reduce((n,t)=>n+t.worlds,0)} variant worlds`;
    if (!matches.length) grid.append(el('p', 'No matching tasks. Try another term or lifecycle stage.', 'no-results'));
    matches.forEach(task => {
      const article = el('article', undefined, 'task-card');
      const meta = el('div', undefined, 'task-meta');
      meta.append(el('span', data.corpus.stages[task.stage-1]), el('span', `${task.worlds} worlds`));
      const detail = el('details'); detail.append(el('summary', 'Read task instructions'));
      detail.append(el('p', task.instruction, 'instruction'));
      article.append(meta, el('h3', task.title), el('p', task.id, 'task-id'), detail);
      grid.append(article);
    });
  }
  search.addEventListener('input', renderTasks); filter.addEventListener('change', renderTasks); renderTasks();
  const config = window.RED_COMMERCE_SITE || {};
  document.querySelectorAll('[data-release-link]').forEach(link => {
    const key = link.dataset.releaseLink, url = config[key];
    if (typeof url === 'string' && /^https:\/\//.test(url)) {
      link.href = url; link.removeAttribute('aria-disabled');
      link.textContent = key === 'paper' ? 'Read the paper ↗' : 'View on GitHub ↗';
    }
  });
  if (typeof config.citation === 'string' && config.citation.trim()) {
    document.getElementById('citation-block').hidden = false;
    document.getElementById('citation-text').textContent = config.citation;
    document.getElementById('copy-citation').addEventListener('click', async () => {
      const status = document.getElementById('copy-status');
      try { await navigator.clipboard.writeText(config.citation); status.textContent = 'Copied.'; }
      catch { status.textContent = 'Select the citation text to copy it.'; }
    });
  }
})();
