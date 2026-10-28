/**
 * TemplateAudit AI — Feature 1 Controller: Master .MD Base Builder
 * Supports:
 * - Reference PDF extraction via pymupdf4llm + YAML Frontmatter Machine Contract
 * - 3-Mode Editor (Raw .MD | Side-by-Side Split View | Rendered Preview)
 * - AI-Assisted Rule Injection with GitHub-style Red/Green Inline Diff & Undo Stack
 * - Saving & managing Master .MD Standards in ./templates/
 */

function bindBuilderEvents() {
  const perfectInput = document.getElementById('perfect-pdf-input');
  const dropzone = document.getElementById('perfect-dropzone');
  const sampleBtn = document.getElementById('btn-load-sample-perfect');
  const editor = document.getElementById('md-editor-textarea');
  const aiBtn = document.getElementById('btn-run-ai-assist');
  const saveBtn = document.getElementById('btn-save-template');
  const dlBtn = document.getElementById('btn-download-builder-md');
  const undoBtn = document.getElementById('btn-undo-md-edit');

  perfectInput.addEventListener('change', async (e) => {
    const file = e.target.files[0];
    if (file) await handleUploadPerfectPdf(file);
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('border-indigo-400', 'bg-indigo-950/30');
  });
  dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('border-indigo-400', 'bg-indigo-950/30');
  });
  dropzone.addEventListener('drop', async (e) => {
    e.preventDefault();
    dropzone.classList.remove('border-indigo-400', 'bg-indigo-950/30');
    const file = e.dataTransfer.files[0];
    if (file) await handleUploadPerfectPdf(file);
  });

  sampleBtn.addEventListener('click', handleLoadSamplePerfectPdf);

  editor.addEventListener('input', () => {
    updateEditorCharStats();
    refreshLiveMarkdownPreview();
  });

  aiBtn.addEventListener('click', handleRunAiAssist);
  saveBtn.addEventListener('click', handleSaveMasterTemplate);
  if (undoBtn) {
    undoBtn.addEventListener('click', undoEditorChange);
  }

  dlBtn.addEventListener('click', () => {
    const md = editor.value || '';
    const name = (document.getElementById('template-save-name').value || 'Master_Standard').trim();
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    window.triggerBlobDownload(blob, `${name}.md`);
  });

  setEditorViewMode(window.appState.editorViewMode || 'split');
}

function pushEditorHistorySnapshot(mdText) {
  if (!mdText) return;
  const hist = window.appState.editorHistory;
  if (hist.length === 0 || hist[hist.length - 1] !== mdText) {
    hist.push(mdText);
    if (hist.length > 25) hist.shift();
  }
  updateUndoButtonState();
}

function updateUndoButtonState() {
  const undoBtn = document.getElementById('btn-undo-md-edit');
  if (!undoBtn) return;
  const count = window.appState.editorHistory.length;
  undoBtn.disabled = count === 0;
  undoBtn.textContent = count > 0 ? `↩ Undo (${count})` : '↩ Undo';
}

function undoEditorChange() {
  const hist = window.appState.editorHistory;
  if (!hist.length) return;
  const prev = hist.pop();
  const editor = document.getElementById('md-editor-textarea');
  editor.value = prev;
  closeAiDiffDrawer();
  updateEditorCharStats();
  refreshLiveMarkdownPreview();
  updateUndoButtonState();
}

function setEditorViewMode(mode) {
  window.appState.editorViewMode = mode;
  const editor = document.getElementById('md-editor-textarea');
  const previewDiv = document.getElementById('md-rendered-preview');

  document.querySelectorAll('.editor-mode-btn').forEach((btn) => {
    if (btn.dataset.mode === mode) {
      btn.className =
        'editor-mode-btn px-2.5 py-1 rounded text-[11px] font-semibold bg-indigo-600 text-white transition';
    } else {
      btn.className =
        'editor-mode-btn px-2.5 py-1 rounded text-[11px] font-medium text-slate-400 hover:text-white transition';
    }
  });

  if (mode === 'raw') {
    editor.classList.remove('hidden', 'w-1/2', 'border-r', 'border-slate-800');
    editor.classList.add('w-full');
    previewDiv.classList.add('hidden');
  } else if (mode === 'preview') {
    editor.classList.add('hidden');
    previewDiv.classList.remove('hidden', 'w-1/2');
    previewDiv.classList.add('w-full');
    refreshLiveMarkdownPreview();
  } else {
    // Side-by-side Split View
    editor.classList.remove('hidden', 'w-full');
    editor.classList.add('w-1/2', 'border-r', 'border-slate-800');
    previewDiv.classList.remove('hidden', 'w-full');
    previewDiv.classList.add('w-1/2');
    refreshLiveMarkdownPreview();
  }
}

function refreshLiveMarkdownPreview() {
  const editor = document.getElementById('md-editor-textarea');
  const previewDiv = document.getElementById('md-rendered-preview');
  if (!editor || !previewDiv) return;
  if (window.appState.editorViewMode !== 'raw') {
    previewDiv.innerHTML = window.renderMarkdownPreviewHtml(editor.value);
  }
}

function renderAiDiffDrawer(diffData) {
  const drawer = document.getElementById('ai-diff-drawer');
  const body = document.getElementById('ai-diff-lines');
  const summaryEl = document.getElementById('ai-diff-summary');
  if (!drawer || !body) return;

  const lines = diffData.diff_lines || [];
  const addedCount = lines.filter((l) => l.type === 'added').length;
  const removedCount = lines.filter((l) => l.type === 'removed').length;

  summaryEl.innerHTML = `
    <span class="font-semibold text-white">${window.escapeHtml(diffData.summary)}</span>
    <span class="ml-2 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-mono text-[10px]">+${addedCount} added</span>
    <span class="ml-1 px-1.5 py-0.5 rounded bg-red-500/20 text-red-300 font-mono text-[10px]">-${removedCount} removed</span>
  `;

  body.innerHTML = lines
    .map((item) => {
      const prefix = item.type === 'added' ? '+' : item.type === 'removed' ? '-' : ' ';
      const cls =
        item.type === 'added'
          ? 'diff-line-added'
          : item.type === 'removed'
          ? 'diff-line-removed'
          : 'diff-line-unchanged';
      const lnBadge = item.line_num ? String(item.line_num).padStart(3, ' ') : '   ';
      return `<div class="px-3 py-0.5 font-mono text-[11px] whitespace-pre-wrap ${cls}"><span class="opacity-50 select-none mr-2">${lnBadge} ${prefix}</span>${window.escapeHtml(item.content)}</div>`;
    })
    .join('');

  drawer.classList.remove('hidden');
}

function closeAiDiffDrawer() {
  const drawer = document.getElementById('ai-diff-drawer');
  if (drawer) drawer.classList.add('hidden');
}

function setAiPromptPreset(text) {
  document.getElementById('ai-assist-input').value = text;
  document.getElementById('ai-assist-input').focus();
}

function updateEditorCharStats() {
  const val = document.getElementById('md-editor-textarea').value || '';
  const lines = val ? val.split('\n').length : 0;
  document.getElementById('md-char-stats').textContent =
    `${lines} lines · ${val.length.toLocaleString()} chars`;
}

async function handleUploadPerfectPdf(file) {
  const statusEl = document.getElementById('extract-pdf-status');
  statusEl.classList.remove('hidden');
  statusEl.textContent = `Extracting structured Markdown from "${file.name}" via pymupdf4llm...`;

  try {
    const editor = document.getElementById('md-editor-textarea');
    if (editor.value.trim()) pushEditorHistorySnapshot(editor.value);

    const data = await window.apiClient.extractPdfToMarkdown(file);
    editor.value = data.markdown;
    document.getElementById('template-save-name').value = data.suggested_name;
    document.getElementById('editor-source-badge').textContent =
      `${data.filename} (${data.page_count} pages)`;
    updateEditorCharStats();
    refreshLiveMarkdownPreview();
    statusEl.textContent = `✓ Extracted ${data.page_count} pages into editable .MD standard with YAML contract.`;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

async function handleLoadSamplePerfectPdf() {
  const statusEl = document.getElementById('extract-pdf-status');
  statusEl.classList.remove('hidden');
  statusEl.textContent = 'Extracting Perfect_Reference_Turbine_Report_2026.pdf via pymupdf4llm...';

  try {
    const editor = document.getElementById('md-editor-textarea');
    if (editor.value.trim()) pushEditorHistorySnapshot(editor.value);

    const data = await window.apiClient.loadSamplePerfectPdf();
    editor.value = data.markdown;
    document.getElementById('template-save-name').value = data.suggested_name;
    document.getElementById('editor-source-badge').textContent =
      `${data.filename} (${data.page_count} pages)`;
    updateEditorCharStats();
    refreshLiveMarkdownPreview();
    statusEl.textContent = `✓ Loaded sample Perfect PDF (${data.page_count} pages). Try AI-Assisted Rule Injection below!`;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  }
}

async function handleRunAiAssist() {
  const editor = document.getElementById('md-editor-textarea');
  const promptEl = document.getElementById('ai-assist-input');
  const statusEl = document.getElementById('ai-assist-status');
  const btn = document.getElementById('btn-run-ai-assist');

  const markdown = editor.value.trim();
  const instruction = promptEl.value.trim();
  const model = document.getElementById('ollama-model-input').value.trim() || 'qwen2.5:7b-instruct';

  if (!instruction) {
    statusEl.classList.remove('hidden');
    statusEl.textContent = 'Please enter an instruction or click one of the preset chips above.';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Injecting Rules & Syncing YAML...';
  statusEl.classList.remove('hidden');
  statusEl.textContent = `Calling Ollama (${model}) to update Master .MD & YAML contract...`;

  try {
    pushEditorHistorySnapshot(editor.value);
    const data = await window.apiClient.runAiAssist(markdown, instruction, model);
    window.appState.lastAiDiff = data;
    editor.value = data.markdown;
    updateEditorCharStats();
    refreshLiveMarkdownPreview();
    renderAiDiffDrawer(data);
    statusEl.textContent = `✓ ${data.summary} (Engine: ${data.engine_used}) — Review inline diff on the right!`;
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Apply with Ollama AI';
  }
}

async function handleSaveMasterTemplate() {
  const name = document.getElementById('template-save-name').value.trim();
  const markdown = document.getElementById('md-editor-textarea').value.trim();
  const feedbackEl = document.getElementById('save-template-feedback');

  if (!name || !markdown) {
    feedbackEl.classList.remove('hidden');
    feedbackEl.textContent = 'Please provide both a Template Name and non-empty Markdown content.';
    return;
  }

  try {
    const saved = await window.apiClient.saveMasterTemplate(name, markdown);
    feedbackEl.classList.remove('hidden');
    feedbackEl.textContent = `✓ Saved to ./templates/${saved.filename} (${saved.size_bytes.toLocaleString()} bytes)`;
    await loadTemplatesList(saved.name);
  } catch (err) {
    feedbackEl.classList.remove('hidden');
    feedbackEl.textContent = `Error: ${err.message}`;
  }
}

async function loadTemplatesList(selectName = null) {
  try {
    const data = await window.apiClient.fetchTemplatesList();
    window.appState.templates = data.templates || [];

    const listContainer = document.getElementById('saved-templates-list');
    document.getElementById('saved-templates-count').textContent = window.appState.templates.length;

    if (window.appState.templates.length === 0) {
      listContainer.innerHTML = `<p class="text-xs text-slate-500">No saved templates yet.</p>`;
    } else {
      listContainer.innerHTML = window.appState.templates
        .map(
          (t) => `
        <div class="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800 hover:border-indigo-500/40 transition flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="text-xs font-semibold text-white truncate font-mono">${window.escapeHtml(t.filename)}</p>
            <p class="text-[10px] text-slate-400">${(t.size_bytes / 1024).toFixed(1)} KB · Updated ${new Date(t.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
          </div>
          <button
            onclick="loadTemplateIntoEditor('${window.escapeHtml(t.name)}')"
            class="px-2 py-1 rounded bg-slate-800 hover:bg-indigo-600/30 text-[11px] text-indigo-300 border border-slate-700 shrink-0 transition"
          >
            Load
          </button>
        </div>
      `
        )
        .join('');
    }

    const selectEl = document.getElementById('audit-template-select');
    const currentVal = selectName || selectEl.value;
    selectEl.innerHTML = window.appState.templates
      .map(
        (t) =>
          `<option value="${window.escapeHtml(t.name)}">${window.escapeHtml(t.filename)}</option>`
      )
      .join('');

    if (currentVal && window.appState.templates.some((t) => t.name === currentVal)) {
      selectEl.value = currentVal;
    }

    const editor = document.getElementById('md-editor-textarea');
    if (!editor.value.trim() && window.appState.templates.length > 0) {
      loadTemplateIntoEditor(window.appState.templates[0].name);
    }
  } catch (err) {
    console.error('Failed to load templates list:', err);
  }
}

function loadTemplateIntoEditor(name) {
  const found = window.appState.templates.find((t) => t.name === name);
  if (!found) return;
  const editor = document.getElementById('md-editor-textarea');
  if (editor.value.trim()) pushEditorHistorySnapshot(editor.value);
  editor.value = found.markdown;
  document.getElementById('template-save-name').value = found.name;
  document.getElementById('editor-source-badge').textContent = `./templates/${found.filename}`;
  closeAiDiffDrawer();
  updateEditorCharStats();
  refreshLiveMarkdownPreview();
}

window.bindBuilderEvents = bindBuilderEvents;
window.setAiPromptPreset = setAiPromptPreset;
window.setEditorViewMode = setEditorViewMode;
window.undoEditorChange = undoEditorChange;
window.closeAiDiffDrawer = closeAiDiffDrawer;
window.loadTemplatesList = loadTemplatesList;
window.loadTemplateIntoEditor = loadTemplateIntoEditor;
