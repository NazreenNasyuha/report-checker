/**
 * TemplateAudit AI — Centralized State Store & Visual Theme Tokens
 */

window.appState = {
  mainMode: 'builder',           // 'builder' | 'auditor'
  templates: [],                 // List from GET /api/templates/list
  editorViewMode: 'split',       // 'raw' | 'split' | 'preview'
  editorHistory: [],             // Stack of previous Markdown snapshots for Undo
  lastAiDiff: null,              // Latest AIAssistResponse diff payload
  selectedTargetFile: null,
  currentAudit: null,            // AuditRunResponse from POST /api/audit/run
  ignoredIssueIds: new Set(),    // Set of dismissed/ignored issue IDs
  issueListMode: 'active',       // 'active' | 'ignored'
  categoryFilter: 'all',         // 'all' | 'calculation' | 'ref_struct' | 'typo'
  selectedIssueId: null,
  compareDrawerOpen: false,      // Master .MD comparison drawer toggle (Spacebar)
  pdfZoom: 92,
};

window.CATEGORY_META = {
  calculation: {
    label: 'CALCULATION ERROR',
    hex: '#ef4444',
    badge: 'bg-red-500/20 text-red-300 border-red-500/40',
    border: 'border-l-4 border-l-red-500',
    dashed: false,
  },
  missing_reference: {
    label: 'MISSING REFERENCE',
    hex: '#f59e0b',
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    border: 'border-l-4 border-l-amber-500',
    dashed: true,
  },
  structure_mismatch: {
    label: 'STRUCTURE DEVIATION',
    hex: '#f59e0b',
    badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
    border: 'border-l-4 border-l-amber-500',
    dashed: true,
  },
  typo: {
    label: 'TYPO / TERMINOLOGY',
    hex: '#06b6d4',
    badge: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
    border: 'border-l-4 border-l-cyan-400',
    dashed: false,
  },
};

window.escapeHtml = function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};
