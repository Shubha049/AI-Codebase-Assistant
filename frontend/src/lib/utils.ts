export function cn(...v: Array<string | false | null | undefined>) {
  return v.filter(Boolean).join(' ');
}

export function bytes(n: number): string {
  if (!n || n <= 0) return '0 B';
  const u = ['B', 'KB', 'MB', 'GB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), 3);
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}

export function shortId(id: string): string {
  return id ? id.slice(0, 8) : '';
}

export function statusTone(s: string): 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'neutral' {
  if (!s) return 'neutral';
  const x = s.toLowerCase();
  if (['ready', 'completed', 'done', 'success', 'grounded', 'low', 'easy'].includes(x)) {
    return 'success';
  }
  if (['failed', 'error', 'critical', 'high', 'danger'].includes(x)) {
    return 'danger';
  }
  if (['running', 'processing', 'pending', 'analyzing', 'chunking', 'embedding', 'queued', 'medium', 'warning', 'warn', 'partial'].includes(x)) {
    return 'warning';
  }
  if (['indexed', 'indexing', 'info', 'scanned'].includes(x)) {
    return 'info';
  }
  if (['ai', 'hard', 'ast', 'llm', 'architecture'].includes(x)) {
    return 'purple';
  }
  return 'neutral';
}

export function formatDate(v: string | null | undefined): string {
  if (!v) return '—';
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(v));
  } catch {
    return String(v);
  }
}

export function getLanguageColor(language: string): string {
  const colors: Record<string, string> = {
    Python: '#3B82F6',
    TypeScript: '#22D3EE',
    JavaScript: '#FACC15',
    Go: '#06B6D4',
    Rust: '#F97316',
    Java: '#EC4899',
    'C++': '#8B5CF6',
    C: '#64748B',
    'C#': '#10B981',
    Ruby: '#F43F5E',
    PHP: '#A855F7',
    Markdown: '#A1A1B5',
    JSON: '#94A3B8',
    YAML: '#CBD5E1',
    HTML: '#FB923C',
    CSS: '#38BDF8',
  };
  return colors[language] || '#8B5CF6';
}

