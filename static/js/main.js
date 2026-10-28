/**
 * TemplateAudit AI — Application Bootstrapper & Mode Navigation
 */

function switchMainMode(mode) {
  window.appState.mainMode = mode;
  const builderView = document.getElementById('view-builder');
  const auditorView = document.getElementById('view-auditor');
  const tabBuilder = document.getElementById('nav-tab-builder');
  const tabAuditor = document.getElementById('nav-tab-auditor');

  if (mode === 'builder') {
    builderView.classList.remove('hidden');
    auditorView.classList.add('hidden');
    tabBuilder.classList.add('active');
    tabAuditor.classList.remove('active');
  } else {
    builderView.classList.add('hidden');
    auditorView.classList.remove('hidden');
    tabBuilder.classList.remove('active');
    tabAuditor.classList.add('active');
  }
}

async function checkOllamaHealth() {
  const model =
    document.getElementById('ollama-model-input')?.value || 'qwen2.5:7b-instruct';
  const dot = document.getElementById('ollama-dot');
  const text = document.getElementById('ollama-status-text');

  try {
    const data = await window.apiClient.checkOllamaStatus(model);
    if (data.connected) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-400';
      text.textContent = `Ollama Ready (${model})`;
    } else {
      dot.className = 'w-2 h-2 rounded-full bg-amber-400';
      text.textContent = 'SymPy + Hybrid Rules Active';
    }
  } catch {
    dot.className = 'w-2 h-2 rounded-full bg-amber-400';
    text.textContent = 'SymPy + Hybrid Rules Active';
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  window.bindBuilderEvents();
  window.bindAuditorEvents();
  await window.loadTemplatesList();
  await checkOllamaHealth();
});

window.switchMainMode = switchMainMode;
window.checkOllamaHealth = checkOllamaHealth;
