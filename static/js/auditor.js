/**
 * TemplateAudit AI — Feature 2 Controller: Audit Target PDF Against Master .MD Base
 * Supports:
 * - Real-time SSE Streaming Progress & Immediate 150 DPI Page Rendering
 * - Page Thumbnail & Issue Heatmap Rail
 * - Multi-Line Bounding Box Overlays + Table-Cell Coordinate Tags + Glassmorphic Hover Popovers
 * - Dual Reasoning Cards + Ignore/Dismiss Toggle
 * - Keyboard Triage Shortcuts (J / K / X / Space) + Master .MD Rule Comparison Drawer
 */

function bindAuditorEvents() {
  const targetInput = document.getElementById('target-pdf-input');
  const runBtn = document.getElementById('btn-run-audit');
  const sampleAuditBtn = document.getElementById('btn-run-sample-audit');
  const overlayToggle = document.getElementById('toggle-pdf-overlays');
  const exportBtn = document.getElementById('btn-export-annotated-pdf');

  targetInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      window.appState.selectedTargetFile = file;
      document.getElementById('target-pdf-label').textContent = file.name;
      runBtn.disabled = false;
    }
  });

  runBtn.addEventListener('click', handleRunUploadedAudit);
  sampleAuditBtn.addEventListener('click', handleRunSampleAudit);

  overlayToggle.addEventListener('change', () => {
    document.querySelectorAll('.bbox-overlay-layer').forEach((layer) => {
      layer.style.display = overlayToggle.checked ? 'block' : 'none';
    });
  });

  exportBtn.addEventListener('click', handleExportAnnotatedPdf);

  // Global Keyboard Triage Shortcuts when in Auditor Mode
  document.addEventListener('keydown', (e) => {
    if (window.appState.mainMode !== 'auditor') return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
    if (!window.appState.currentAudit) return;

    if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowDown') {
      e.preventDefault();
      stepIssueSelection(1);
    } else if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowUp') {
      e.preventDefault();
      stepIssueSelection(-1);
    } else if (e.key === 'x' || e.key === 'X' || e.key === 'i' || e.key === 'I') {
      if (window.appState.selectedIssueId) {
        e.preventDefault();
        toggleIgnoreIssue(window.appState.selectedIssueId);
      }
    } else if (e.key === ' ') {
      if (window.appState.selectedIssueId) {
        e.preventDefault();
        toggleMasterCompareDrawer();
      }
    }
  });
}

function showStreamProgress(percent, message) {
  const banner = document.getElementById('audit-stream-banner');
  const bar = document.getElementById('audit-stream-bar');
  const text = document.getElementById('audit-stream-text');
  if (!banner) return;
  banner.classList.remove('hidden');
  bar.style.width = `${percent}%`;
  text.textContent = message;
}

function hideStreamProgress() {
  const banner = document.getElementById('audit-stream-banner');
  if (banner) {
    setTimeout(() => banner.classList.add('hidden'), 600);
  }
}

function handleStreamingProgressEvent(evt) {
  if (!evt) return;
  showStreamProgress(evt.progress || 25, evt.message || 'Processing Target PDF...');

  if (evt.stage === 'rendered' && evt.pages) {
    // Immediately display rendered PDF pages before LLM/SymPy finishes!
    document.getElementById('pdf-empty-state').classList.add('hidden');
    const pagesStack = document.getElementById('pdf-pages-stack');
    pagesStack.classList.remove('hidden');

    if (evt.sha256) {
      const hashBadge = document.getElementById('readonly-hash-badge');
      hashBadge.classList.remove('hidden');
      hashBadge.textContent = `LOCKED READ-ONLY · SHA-256: ${evt.sha256.slice(0, 12)}...`;
    }

    window.appState.currentAudit = {
      audit_id: evt.audit_id,
      target_filename: 'Rendering...',
      template_name: document.getElementById('audit-template-select').value,
      original_sha256: evt.sha256 || '',
      pages: evt.pages,
      issues: [],
      symbol_registry: [],
    };
    renderTargetPdfPages();
  }
}

async function handleRunUploadedAudit() {
  if (!window.appState.selectedTargetFile) return;
  const templateName = document.getElementById('audit-template-select').value;
  const ollamaModel =
    document.getElementById('ollama-model-input').value.trim() || 'qwen2.5:7b-instruct';

  const runBtn = document.getElementById('btn-run-audit');
  runBtn.disabled = true;
  runBtn.textContent = 'Streaming Audit...';
  showStreamProgress(10, 'Initializing Read-Only Lock & SHA-256 Verification...');

  try {
    const data = await window.apiClient.runTargetPdfAudit(
      templateName,
      window.appState.selectedTargetFile,
      ollamaModel,
      handleStreamingProgressEvent
    );
    onAuditCompleted(data);
  } catch (err) {
    alert(`Audit Error: ${err.message}`);
  } finally {
    hideStreamProgress();
    runBtn.disabled = false;
    runBtn.textContent = 'Audit Uploaded PDF';
  }
}

async function handleRunSampleAudit() {
  const templateName =
    document.getElementById('audit-template-select').value || 'Turbine_Thermal_Standard_v1';
  const ollamaModel =
    document.getElementById('ollama-model-input').value.trim() || 'qwen2.5:7b-instruct';

  const btn = document.getElementById('btn-run-sample-audit');
  btn.disabled = true;
  btn.textContent = 'Streaming Sample Audit...';
  showStreamProgress(10, 'Locking Target_Turbine_Report_With_Errors_2026.pdf Read-Only...');

  try {
    const data = await window.apiClient.runSampleTargetAudit(
      templateName,
      ollamaModel,
      handleStreamingProgressEvent
    );
    onAuditCompleted(data);
  } catch (err) {
    alert(`Sample Audit Error: ${err.message}`);
  } finally {
    hideStreamProgress();
    btn.disabled = false;
    btn.textContent = '⚡ Load & Audit Sample Error PDF';
  }
}

function onAuditCompleted(auditData) {
  window.appState.currentAudit = auditData;
  window.appState.ignoredIssueIds = new Set();
  window.appState.selectedIssueId = auditData.issues.length > 0 ? auditData.issues[0].id : null;

  document.getElementById('pdf-empty-state').classList.add('hidden');
  const pagesStack = document.getElementById('pdf-pages-stack');
  pagesStack.classList.remove('hidden');

  const hashBadge = document.getElementById('readonly-hash-badge');
  hashBadge.classList.remove('hidden');
  hashBadge.textContent = `LOCKED READ-ONLY · SHA-256: ${auditData.original_sha256.slice(0, 12)}...`;

  const exportBtn = document.getElementById('btn-export-annotated-pdf');
  exportBtn.classList.remove('hidden');
  exportBtn.classList.add('inline-flex');

  renderTargetPdfPages();
  renderPageThumbnailRail();
  updateAuditStatsAndCards();
  updateMasterCompareDrawerContent();
}

function renderPageThumbnailRail() {
  const audit = window.appState.currentAudit;
  const rail = document.getElementById('pdf-thumbnail-rail');
  if (!rail || !audit) return;

  rail.classList.remove('hidden');
  rail.innerHTML = audit.pages
    .map((p) => {
      const pageIssues = audit.issues.filter(
        (i) => i.page_number === p.page_number && !window.appState.ignoredIssueIds.has(i.id)
      );
      const calcCnt = pageIssues.filter((i) => i.category === 'calculation').length;
      const refCnt = pageIssues.filter(
        (i) => i.category === 'missing_reference' || i.category === 'structure_mismatch'
      ).length;
      const typoCnt = pageIssues.filter((i) => i.category === 'typo').length;

      return `
        <div
          onclick="scrollToPdfPage(${p.page_number})"
          class="page-thumb-card cursor-pointer rounded-lg bg-slate-900/90 border border-slate-800 p-1.5 flex flex-col items-center gap-1"
          title="Jump to Page ${p.page_number} (${pageIssues.length} active issues)"
        >
          <div class="w-full aspect-[1/1.38] rounded overflow-hidden bg-white relative border border-slate-700">
            <img src="${p.image_url}" alt="Thumb ${p.page_number}" class="w-full h-full object-cover" />
          </div>
          <span class="text-[10px] font-mono font-bold text-slate-300">P.${p.page_number}</span>
          <div class="flex items-center gap-1 flex-wrap justify-center">
            ${calcCnt ? `<span class="w-2 h-2 rounded-full bg-red-500" title="${calcCnt} Calc"></span>` : ''}
            ${refCnt ? `<span class="w-2 h-2 rounded-full bg-amber-500" title="${refCnt} Ref/Struct"></span>` : ''}
            ${typoCnt ? `<span class="w-2 h-2 rounded-full bg-cyan-400" title="${typoCnt} Typo"></span>` : ''}
          </div>
        </div>
      `;
    })
    .join('');
}

function scrollToPdfPage(pageNumber) {
  const pageEl = document.getElementById(`target-page-anchor-${pageNumber}`);
  if (pageEl) {
    pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function renderTargetPdfPages() {
  const audit = window.appState.currentAudit;
  if (!audit) return;

  const stack = document.getElementById('pdf-pages-stack');
  stack.innerHTML = '';

  audit.pages.forEach((page) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex flex-col items-center';
    wrapper.id = `target-page-anchor-${page.page_number}`;

    const header = document.createElement('div');
    header.className = 'w-full flex items-center justify-between mb-1.5 px-1 text-[11px] text-slate-400';
    header.style.maxWidth = `${window.appState.pdfZoom}%`;
    header.innerHTML = `
      <span class="font-semibold text-slate-300">Page ${page.page_number} of ${audit.pages.length} · ${window.escapeHtml(audit.target_filename)}</span>
      <span class="font-mono">Against: ${window.escapeHtml(audit.template_name)}.md</span>
    `;

    const frame = document.createElement('div');
    frame.className = 'pdf-page-frame';
    frame.style.width = `${window.appState.pdfZoom}%`;

    const img = document.createElement('img');
    img.src = page.image_url;
    img.alt = `Target PDF Page ${page.page_number}`;
    img.className = 'w-full h-auto block select-none rounded';

    const overlay = document.createElement('div');
    overlay.className = 'bbox-overlay-layer';
    overlay.id = `bbox-layer-page-${page.page_number}`;
    overlay.style.display = document.getElementById('toggle-pdf-overlays').checked ? 'block' : 'none';

    frame.appendChild(img);
    frame.appendChild(overlay);
    wrapper.appendChild(header);
    wrapper.appendChild(frame);
    stack.appendChild(wrapper);
  });

  renderBoundingBoxOverlays();
}

function renderBoundingBoxOverlays() {
  const audit = window.appState.currentAudit;
  if (!audit) return;

  audit.pages.forEach((page) => {
    const layer = document.getElementById(`bbox-layer-page-${page.page_number}`);
    if (!layer) return;
    layer.innerHTML = '';

    const activePageIssues = audit.issues.filter(
      (iss) =>
        iss.page_number === page.page_number && !window.appState.ignoredIssueIds.has(iss.id)
    );

    activePageIssues.forEach((iss) => {
      const meta = window.CATEGORY_META[iss.category] || window.CATEGORY_META.typo;
      const isSelected = window.appState.selectedIssueId === iss.id;

      // Render multi-line bboxes if available, otherwise primary box
      const bboxList =
        iss.bboxes && iss.bboxes.length > 0
          ? iss.bboxes
          : [
              {
                left_pct: iss.left_pct,
                top_pct: iss.top_pct,
                width_pct: iss.width_pct,
                height_pct: iss.height_pct,
              },
            ];

      bboxList.forEach((b, boxIdx) => {
        const box = document.createElement('div');
        box.className = `pdf-issue-bbox ${isSelected ? 'selected' : ''}`;
        box.dataset.issueId = iss.id;

        const padX = 0.35;
        const padY = 0.25;
        box.style.left = `${Math.max(0, b.left_pct - padX)}%`;
        box.style.top = `${Math.max(0, b.top_pct - padY)}%`;
        box.style.width = `${Math.min(100, b.width_pct + padX * 2)}%`;
        box.style.height = `${Math.min(100, b.height_pct + padY * 2)}%`;

        box.style.border = `2px ${meta.dashed ? 'dashed' : 'solid'} ${meta.hex}`;
        box.style.backgroundColor = isSelected ? `${meta.hex}38` : `${meta.hex}1c`;

        if (boxIdx === 0) {
          const pill = document.createElement('div');
          pill.className = 'bbox-tag-pill';
          pill.style.backgroundColor = meta.hex;
          pill.textContent = `${iss.id} · ${iss.table_cell_ref || meta.label}`;
          box.appendChild(pill);

          // Floating Glassmorphic Hover Popover on Primary Box
          const popover = document.createElement('div');
          popover.className = 'bbox-hover-popover';
          popover.innerHTML = `
            <div class="flex items-center justify-between gap-2 mb-1">
              <span class="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded border ${meta.badge}">${iss.id} · ${meta.label}</span>
              ${iss.table_cell_ref ? `<span class="text-[9px] font-mono text-indigo-300">${window.escapeHtml(iss.table_cell_ref)}</span>` : ''}
            </div>
            <p class="text-[11px] font-semibold text-white mb-1">${window.escapeHtml(iss.title)}</p>
            ${
              iss.true_result
                ? `<div class="text-[10px] font-mono bg-slate-900/90 border border-slate-700 rounded px-2 py-1 mb-1.5 flex justify-between">
                    <span class="text-red-400 line-through">Stated: ${window.escapeHtml(iss.stated_result || '')}</span>
                    <span class="text-emerald-400 font-bold">SymPy: ${window.escapeHtml(iss.true_result)}</span>
                  </div>`
                : ''
            }
            <p class="text-[10px] text-emerald-200 mb-2">Fix: ${window.escapeHtml(iss.suggestion_to_fix)}</p>
            <div class="flex items-center justify-between gap-1.5 pt-1 border-t border-slate-800">
              <button
                type="button"
                onclick="event.stopPropagation(); openMasterCompareForIssue('${iss.id}')"
                class="px-2 py-0.5 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 text-[10px] font-semibold border border-indigo-500/40"
              >
                Compare .MD (Space)
              </button>
              <button
                type="button"
                onclick="event.stopPropagation(); toggleIgnoreIssue('${iss.id}')"
                class="px-2 py-0.5 rounded bg-slate-800 hover:bg-amber-500/30 text-amber-200 text-[10px] font-semibold border border-slate-700"
              >
                ✕ Ignore (X)
              </button>
            </div>
          `;
          box.appendChild(popover);
        }

        const underline = document.createElement('div');
        underline.className = `bbox-underline-bar ${meta.dashed ? 'dashed' : ''}`;
        underline.style.color = meta.hex;
        if (!meta.dashed) underline.style.backgroundColor = meta.hex;
        box.appendChild(underline);

        box.addEventListener('click', (e) => {
          e.stopPropagation();
          focusIssue(iss.id, { scrollCard: true, scrollPdf: false });
        });

        layer.appendChild(box);
      });
    });
  });
}

function updateAuditStatsAndCards() {
  const audit = window.appState.currentAudit;
  if (!audit) return;

  const activeIssues = audit.issues.filter(
    (i) => !window.appState.ignoredIssueIds.has(i.id)
  );
  const ignoredIssues = audit.issues.filter((i) =>
    window.appState.ignoredIssueIds.has(i.id)
  );

  document.getElementById('stat-active-total').textContent = activeIssues.length;
  document.getElementById('stat-calc-count').textContent = activeIssues.filter(
    (i) => i.category === 'calculation'
  ).length;
  document.getElementById('stat-ref-count').textContent = activeIssues.filter(
    (i) => i.category === 'missing_reference' || i.category === 'structure_mismatch'
  ).length;
  document.getElementById('stat-typo-count').textContent = activeIssues.filter(
    (i) => i.category === 'typo'
  ).length;
  document.getElementById('stat-ignored-count').textContent = ignoredIssues.length;

  document.getElementById('btn-show-active-issues').textContent =
    `Active Issues (${activeIssues.length})`;
  document.getElementById('btn-show-ignored-issues').textContent =
    `Ignored / Dismissed (${ignoredIssues.length})`;

  renderIssueCardsList();
  renderBoundingBoxOverlays();
  renderPageThumbnailRail();
  updateMasterCompareDrawerContent();
}

function setIssueListMode(mode) {
  window.appState.issueListMode = mode;
  const activeBtn = document.getElementById('btn-show-active-issues');
  const ignoredBtn = document.getElementById('btn-show-ignored-issues');

  if (mode === 'active') {
    activeBtn.className =
      'px-2.5 py-1 rounded text-[11px] font-semibold bg-indigo-600 text-white transition';
    ignoredBtn.className =
      'px-2.5 py-1 rounded text-[11px] font-semibold text-slate-400 hover:text-white transition';
  } else {
    ignoredBtn.className =
      'px-2.5 py-1 rounded text-[11px] font-semibold bg-slate-700 text-white transition';
    activeBtn.className =
      'px-2.5 py-1 rounded text-[11px] font-semibold text-slate-400 hover:text-white transition';
  }
  renderIssueCardsList();
}

function setCategoryFilter(filter) {
  window.appState.categoryFilter = filter;
  document.querySelectorAll('.cat-filter-btn').forEach((btn) => {
    if (btn.dataset.filter === filter) {
      btn.className =
        'cat-filter-btn px-2 py-0.5 rounded bg-slate-800 text-white font-semibold border border-slate-700';
    } else {
      btn.className = 'cat-filter-btn px-2 py-0.5 rounded text-slate-400 hover:text-white';
    }
  });
  renderIssueCardsList();
}

function toggleIgnoreIssue(issueId) {
  if (window.appState.ignoredIssueIds.has(issueId)) {
    window.appState.ignoredIssueIds.delete(issueId);
  } else {
    window.appState.ignoredIssueIds.add(issueId);
  }
  updateAuditStatsAndCards();
}

function getFilteredIssuesList() {
  const audit = window.appState.currentAudit;
  if (!audit) return [];

  let list = audit.issues.filter((i) =>
    window.appState.issueListMode === 'ignored'
      ? window.appState.ignoredIssueIds.has(i.id)
      : !window.appState.ignoredIssueIds.has(i.id)
  );

  if (window.appState.categoryFilter === 'calculation') {
    list = list.filter((i) => i.category === 'calculation');
  } else if (window.appState.categoryFilter === 'ref_struct') {
    list = list.filter(
      (i) => i.category === 'missing_reference' || i.category === 'structure_mismatch'
    );
  } else if (window.appState.categoryFilter === 'typo') {
    list = list.filter((i) => i.category === 'typo');
  }
  return list;
}

function stepIssueSelection(direction) {
  const list = getFilteredIssuesList();
  if (!list.length) return;
  const idx = list.findIndex((i) => i.id === window.appState.selectedIssueId);
  const nextIdx = idx === -1 ? 0 : (idx + direction + list.length) % list.length;
  focusIssue(list[nextIdx].id, { scrollCard: true, scrollPdf: true });
}

function renderIssueCardsList() {
  const container = document.getElementById('audit-issues-container');
  const audit = window.appState.currentAudit;
  if (!audit) return;

  const list = getFilteredIssuesList();

  if (list.length === 0) {
    container.innerHTML = `
      <div class="h-44 flex flex-col items-center justify-center text-center text-slate-500 p-4">
        <p class="text-xs font-medium text-slate-400">
          ${
            window.appState.issueListMode === 'ignored'
              ? 'No ignored issues yet. Click "Ignore / Dismiss" (or press X) on any issue card to hide its bounding box.'
              : 'No active issues match this filter.'
          }
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = '';

  list.forEach((iss) => {
    const meta = window.CATEGORY_META[iss.category] || window.CATEGORY_META.typo;
    const isIgnored = window.appState.ignoredIssueIds.has(iss.id);
    const isSelected = window.appState.selectedIssueId === iss.id;

    const card = document.createElement('div');
    card.id = `issue-card-${iss.id}`;
    card.className = `issue-card rounded-xl bg-slate-900/95 border border-slate-800 p-3.5 cursor-pointer ${meta.border} ${
      isSelected ? 'active-card' : ''
    }`;

    let sympyHtml = '';
    if (iss.category === 'calculation' && iss.stated_expression) {
      sympyHtml = `
        <div class="mt-2.5 p-2.5 rounded-lg bg-red-950/30 border border-red-500/30 text-[11px] font-mono space-y-1">
          <div class="flex justify-between">
            <span class="text-slate-400">Expression:</span>
            <span class="text-slate-200">${window.escapeHtml(iss.stated_expression)}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-red-300">Stated in PDF:</span>
            <span class="text-red-400 font-bold line-through">${window.escapeHtml(iss.stated_result || '')}</span>
          </div>
          <div class="flex justify-between">
            <span class="text-emerald-300">SymPy Verified:</span>
            <span class="text-emerald-400 font-bold">${window.escapeHtml(iss.true_result || '')}</span>
          </div>
        </div>
      `;
    }

    card.innerHTML = `
      <div class="flex items-center justify-between gap-2 mb-2">
        <div class="flex items-center gap-1.5 flex-wrap">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${meta.badge}">
            ${meta.label}
          </span>
          <span class="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-mono">
            Page ${iss.page_number}
          </span>
          ${
            iss.table_cell_ref
              ? `<span class="px-1.5 py-0.5 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-500/30 text-[10px] font-mono">${window.escapeHtml(iss.table_cell_ref)}</span>`
              : ''
          }
          <span class="text-[10px] font-mono text-slate-500">${iss.id}</span>
        </div>

        <div class="flex items-center gap-1.5">
          <button
            type="button"
            data-compare-btn="${iss.id}"
            title="Compare against Master .MD Standard (Shortcut: Space)"
            class="px-2 py-1 rounded-md text-[10px] font-semibold bg-indigo-500/15 hover:bg-indigo-500/30 text-indigo-300 border border-indigo-500/30 transition"
          >
            Compare .MD
          </button>

          <button
            type="button"
            data-ignore-btn="${iss.id}"
            class="px-2.5 py-1 rounded-md text-[11px] font-semibold border transition ${
              isIgnored
                ? 'bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border-emerald-500/40'
                : 'bg-slate-800 hover:bg-amber-500/20 text-slate-300 hover:text-amber-200 border-slate-700'
            }"
          >
            ${isIgnored ? '↩ Restore' : '✕ Ignore'}
          </button>
        </div>
      </div>

      <h3 class="text-xs font-bold text-white mb-1.5">${window.escapeHtml(iss.title)}</h3>

      <!-- Verbatim Snippet Located on PDF -->
      <div class="mb-2 px-2.5 py-1.5 rounded bg-slate-950 border border-slate-800/90 flex items-center justify-between gap-2">
        <span class="text-[10px] uppercase tracking-wider text-slate-500 shrink-0">PDF Anchor:</span>
        <code class="text-[11px] font-mono text-amber-300 truncate">"${window.escapeHtml(iss.verbatim_snippet)}"</code>
      </div>

      <!-- Issue Description -->
      <p class="text-xs text-slate-200 leading-relaxed">
        ${window.escapeHtml(iss.issue_description)}
      </p>

      ${sympyHtml}

      <!-- Dual Reasoning Boxes: Suggestion to Fix + Why to Ignore -->
      <div class="mt-3 grid grid-cols-1 gap-2">
        <div class="p-2.5 rounded-lg bg-emerald-950/25 border border-emerald-500/30">
          <div class="flex items-center gap-1.5 mb-1">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            <span class="text-[10px] font-bold uppercase tracking-wider text-emerald-300">Suggestion to Fix</span>
          </div>
          <p class="text-[11px] text-emerald-100/90 leading-relaxed">
            ${window.escapeHtml(iss.suggestion_to_fix)}
          </p>
        </div>

        <div class="p-2.5 rounded-lg bg-amber-950/20 border border-amber-500/25">
          <div class="flex items-center gap-1.5 mb-1">
            <span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
            <span class="text-[10px] font-bold uppercase tracking-wider text-amber-300">Why You Might Safely Ignore</span>
          </div>
          <p class="text-[11px] text-amber-100/80 leading-relaxed">
            ${window.escapeHtml(iss.why_to_ignore)}
          </p>
        </div>
      </div>
    `;

    card.addEventListener('click', (e) => {
      if (e.target.closest('[data-ignore-btn]') || e.target.closest('[data-compare-btn]')) return;
      focusIssue(iss.id, { scrollCard: false, scrollPdf: true });
    });

    const ignoreBtn = card.querySelector(`[data-ignore-btn="${iss.id}"]`);
    ignoreBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleIgnoreIssue(iss.id);
    });

    const compareBtn = card.querySelector(`[data-compare-btn="${iss.id}"]`);
    compareBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openMasterCompareForIssue(iss.id);
    });

    container.appendChild(card);
  });
}

function openMasterCompareForIssue(issueId) {
  window.appState.selectedIssueId = issueId;
  window.appState.compareDrawerOpen = true;
  focusIssue(issueId, { scrollCard: true, scrollPdf: true });
  const drawer = document.getElementById('master-compare-drawer');
  if (drawer) drawer.classList.remove('hidden');
  updateMasterCompareDrawerContent();
}

function toggleMasterCompareDrawer() {
  window.appState.compareDrawerOpen = !window.appState.compareDrawerOpen;
  const drawer = document.getElementById('master-compare-drawer');
  if (!drawer) return;
  if (window.appState.compareDrawerOpen) {
    drawer.classList.remove('hidden');
    updateMasterCompareDrawerContent();
  } else {
    drawer.classList.add('hidden');
  }
}

function updateMasterCompareDrawerContent() {
  const drawer = document.getElementById('master-compare-drawer');
  const body = document.getElementById('master-compare-body');
  const audit = window.appState.currentAudit;
  if (!drawer || !body || !audit) return;

  const iss =
    audit.issues.find((i) => i.id === window.appState.selectedIssueId) || audit.issues[0];
  if (!iss) return;

  const symbolsHtml =
    audit.symbol_registry && audit.symbol_registry.length > 0
      ? audit.symbol_registry
          .slice(0, 6)
          .map(
            (s) =>
              `<span class="px-2 py-0.5 rounded bg-slate-900 border border-slate-700 font-mono text-[10px] text-cyan-300">${window.escapeHtml(s.label)} = ${s.value} ${window.escapeHtml(s.unit)} (P.${s.page_number})</span>`
          )
          .join('')
      : '<span class="text-[10px] text-slate-500">No cross-page symbols indexed</span>';

  body.innerHTML = `
    <div class="grid grid-cols-2 gap-3 text-xs">
      <div class="p-2.5 rounded-lg bg-indigo-950/30 border border-indigo-500/40">
        <div class="text-[10px] font-mono uppercase tracking-wider text-indigo-300 font-bold mb-1">
          Master .MD Base Requirement (${window.escapeHtml(audit.template_name)}.md)
        </div>
        <pre class="text-[11px] font-mono text-indigo-100 whitespace-pre-wrap leading-relaxed">${window.escapeHtml(
          iss.master_rule_ref || 'Enforced by Master .MD Standard Section & SymPy Verifier'
        )}</pre>
      </div>
      <div class="p-2.5 rounded-lg bg-red-950/25 border border-red-500/35">
        <div class="text-[10px] font-mono uppercase tracking-wider text-red-300 font-bold mb-1">
          Target PDF Deviation (Page ${iss.page_number} ${iss.table_cell_ref ? '· ' + window.escapeHtml(iss.table_cell_ref) : ''})
        </div>
        <div class="text-[11px] font-mono text-amber-300 mb-1">"${window.escapeHtml(iss.verbatim_snippet)}"</div>
        <p class="text-[11px] text-slate-300">${window.escapeHtml(iss.issue_description)}</p>
      </div>
    </div>
    <div class="mt-2 pt-2 border-t border-slate-800 flex items-center justify-between gap-2 flex-wrap">
      <div class="flex items-center gap-1.5 flex-wrap">
        <span class="text-[10px] font-mono uppercase text-slate-400">Cross-Page Symbol Registry:</span>
        ${symbolsHtml}
      </div>
      <span class="text-[10px] font-mono text-slate-500">Match Engine: ${window.escapeHtml(iss.match_method)} · ${window.escapeHtml(iss.source_engine)}</span>
    </div>
  `;
}

function focusIssue(issueId, { scrollCard = true, scrollPdf = true } = {}) {
  const audit = window.appState.currentAudit;
  if (!audit) return;

  window.appState.selectedIssueId = issueId;
  const issue = audit.issues.find((i) => i.id === issueId);
  if (!issue) return;

  document.querySelectorAll('.issue-card').forEach((el) => {
    el.classList.toggle('active-card', el.id === `issue-card-${issueId}`);
  });

  renderBoundingBoxOverlays();
  updateMasterCompareDrawerContent();

  if (scrollCard) {
    const cardEl = document.getElementById(`issue-card-${issueId}`);
    if (cardEl) cardEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  if (scrollPdf) {
    const bboxEl = document.querySelector(`.pdf-issue-bbox[data-issue-id="${issueId}"]`);
    if (bboxEl) {
      bboxEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      const pageEl = document.getElementById(`target-page-anchor-${issue.page_number}`);
      if (pageEl) pageEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function adjustPdfZoom(delta) {
  setPdfZoom(Math.min(150, Math.max(55, window.appState.pdfZoom + delta)));
}

function setPdfZoom(val) {
  window.appState.pdfZoom = val;
  document.getElementById('pdf-zoom-label').textContent = `${val}%`;
  document.querySelectorAll('.pdf-page-frame').forEach((el) => {
    el.style.width = `${val}%`;
  });
}

async function handleExportAnnotatedPdf() {
  const audit = window.appState.currentAudit;
  if (!audit) return;

  try {
    const ignoredList = Array.from(window.appState.ignoredIssueIds);
    const blob = await window.apiClient.exportAnnotatedPdf(audit.audit_id, ignoredList);
    const baseName = audit.target_filename.replace(/\.pdf$/i, '');
    window.triggerBlobDownload(blob, `${baseName}_review_copy.pdf`);
  } catch (err) {
    alert(`Export Error: ${err.message}`);
  }
}

window.bindAuditorEvents = bindAuditorEvents;
window.setIssueListMode = setIssueListMode;
window.setCategoryFilter = setCategoryFilter;
window.stepIssueSelection = stepIssueSelection;
window.scrollToPdfPage = scrollToPdfPage;
window.toggleIgnoreIssue = toggleIgnoreIssue;
window.openMasterCompareForIssue = openMasterCompareForIssue;
window.toggleMasterCompareDrawer = toggleMasterCompareDrawer;
window.adjustPdfZoom = adjustPdfZoom;
window.setPdfZoom = setPdfZoom;
