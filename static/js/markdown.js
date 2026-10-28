/**
 * TemplateAudit AI — Markdown Preview Renderer (with YAML Frontmatter Card) & File Download Helper
 */

window.renderMarkdownPreviewHtml = function renderMarkdownPreviewHtml(md) {
  let content = md || '';
  let html = '';

  // Render YAML Frontmatter Contract block if present at top of file
  const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
  if (fmMatch) {
    const fmBody = fmMatch[1].trim();
    content = content.slice(fmMatch[0].length);
    const ruleLines = fmBody
      .split('\n')
      .map(
        (ln) =>
          `<div class="text-[11px] font-mono text-indigo-200"><span class="text-indigo-400">▸</span> ${window.escapeHtml(ln)}</div>`
      )
      .join('');
    html += `
      <div class="mb-4 p-3 rounded-xl bg-indigo-950/35 border border-indigo-500/40">
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-[10px] font-mono uppercase tracking-wider text-indigo-300 font-bold">
            YAML Machine Contract (Frontmatter Schema)
          </span>
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-200">Active</span>
        </div>
        <div class="space-y-0.5">${ruleLines}</div>
      </div>
    `;
  }

  const lines = content.split('\n');
  let tableRows = [];

  const flushTable = () => {
    if (!tableRows.length) return;
    html += '<table>';
    tableRows.forEach((cells, rIdx) => {
      if (cells.every((c) => /^[:\-\s]+$/.test(c))) return;
      const tag = rIdx === 0 ? 'th' : 'td';
      html +=
        '<tr>' +
        cells.map((c) => `<${tag}>${window.escapeHtml(c.trim())}</${tag}>`).join('') +
        '</tr>';
    });
    html += '</table>';
    tableRows = [];
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      tableRows.push(line.slice(1, -1).split('|'));
      continue;
    } else {
      flushTable();
    }
    if (line.startsWith('### ')) {
      html += `<h3 class="text-sm font-bold text-cyan-300 mt-3">${window.escapeHtml(line.slice(4))}</h3>`;
    } else if (line.startsWith('## ')) {
      html += `<h2 class="text-base font-bold text-white mt-4 pb-1 border-b border-slate-800">${window.escapeHtml(line.slice(3))}</h2>`;
    } else if (line.startsWith('# ')) {
      html += `<h1 class="text-lg font-bold text-white mb-2">${window.escapeHtml(line.slice(2))}</h1>`;
    } else if (line.startsWith('> ')) {
      html += `<blockquote class="border-l-2 border-amber-400 pl-3 py-1 my-2 text-amber-200 bg-amber-950/20 rounded">${window.escapeHtml(line.slice(2))}</blockquote>`;
    } else if (line.startsWith('- [x] ')) {
      html += `<div class="ml-2 my-1 flex items-start gap-2 text-emerald-300 text-xs"><span class="text-emerald-400 font-bold">✓</span><span>${window.escapeHtml(line.slice(6))}</span></div>`;
    } else if (line.startsWith('- ')) {
      html += `<div class="ml-3 text-slate-300">• ${window.escapeHtml(line.slice(2))}</div>`;
    } else if (line === '---') {
      html += `<hr class="border-slate-800 my-3" />`;
    } else if (line) {
      html += `<p class="text-slate-300">${window.escapeHtml(line)}</p>`;
    }
  }
  flushTable();
  return html;
};

window.triggerBlobDownload = function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};
