/**
 * TemplateAudit AI — Backend REST & SSE Streaming API Client
 */

window.apiClient = {
  async checkOllamaStatus(model) {
    const res = await fetch(`/api/ollama/status?model=${encodeURIComponent(model)}`);
    return res.json();
  },

  async extractPdfToMarkdown(file) {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/templates/extract-pdf', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'PDF extraction failed');
    }
    return res.json();
  },

  async loadSamplePerfectPdf() {
    const res = await fetch('/api/templates/load-sample-perfect', { method: 'POST' });
    if (!res.ok) throw new Error('Failed to load sample Perfect PDF');
    return res.json();
  },

  async runAiAssist(markdown, instruction, ollamaModel) {
    const res = await fetch('/api/templates/ai-assist', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        markdown,
        instruction,
        ollama_model: ollamaModel,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'AI assist failed');
    }
    return res.json();
  },

  async saveMasterTemplate(name, markdown) {
    const res = await fetch('/api/templates/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, markdown }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Save failed');
    }
    return res.json();
  },

  async fetchTemplatesList() {
    const res = await fetch('/api/templates/list');
    if (!res.ok) throw new Error('Failed to list saved templates');
    return res.json();
  },

  async streamAuditRequest(endpointUrl, formData, onProgressEvent) {
    const res = await fetch(endpointUrl, { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Streaming audit failed');
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let finalResult = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split('\n\n');
      buffer = parts.pop() || '';

      for (const chunk of parts) {
        const line = chunk.trim();
        if (!line.startsWith('data:')) continue;
        const jsonStr = line.slice(5).trim();
        try {
          const evt = JSON.parse(jsonStr);
          if (onProgressEvent) onProgressEvent(evt);
          if (evt.stage === 'completed' && evt.result) {
            finalResult = evt.result;
          }
        } catch (e) {
          console.warn('SSE parse warning:', e);
        }
      }
    }
    return finalResult;
  },

  async runTargetPdfAudit(templateName, targetFile, ollamaModel, onProgressEvent = null) {
    const fd = new FormData();
    fd.append('template_name', templateName);
    fd.append('target_pdf', targetFile);
    fd.append('ollama_model', ollamaModel);

    if (onProgressEvent) {
      const streamed = await this.streamAuditRequest('/api/audit/stream', fd, onProgressEvent);
      if (streamed) return streamed;
    }

    const res = await fetch('/api/audit/run', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Audit failed');
    }
    return res.json();
  },

  async runSampleTargetAudit(templateName, ollamaModel, onProgressEvent = null) {
    const fd = new FormData();
    fd.append('template_name', templateName);
    fd.append('ollama_model', ollamaModel);

    if (onProgressEvent) {
      const streamed = await this.streamAuditRequest('/api/audit/stream-sample', fd, onProgressEvent);
      if (streamed) return streamed;
    }

    const res = await fetch('/api/audit/run-sample', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Sample audit failed');
    }
    return res.json();
  },

  async exportAnnotatedPdf(auditId, ignoredIds) {
    const res = await fetch(`/api/audit/${auditId}/export-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(ignoredIds),
    });
    if (!res.ok) throw new Error('Annotated PDF export failed');
    return res.blob();
  },
};
