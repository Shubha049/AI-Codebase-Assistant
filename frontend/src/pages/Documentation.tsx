import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useRepo } from '../main';
import { Card, Empty, Loading, PageHeader, Badge } from '../components/UI';
import { Icon } from '../components/Icons';

export function Documentation() {
  const { repoId } = useRepo();

  const [doc, setDoc] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [generateMode, setGenerateMode] = useState<'structural' | 'llm'>('structural');

  const load = async (): Promise<void> => {
    if (!repoId) {
      setDoc(undefined);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const result = await api.docsLatest(repoId);
      setDoc(result);
    } catch {
      setDoc(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, [repoId]);

  if (!repoId) {
    return (
      <Empty
        title="Select a Repository"
        description="Auto-generated technical documentation is scoped to the active repository."
      />
    );
  }

  if (loading) {
    return <Loading label="Loading repository documentation…" />;
  }

  const handleGenerate = async (): Promise<void> => {
    setBusy(true);
    try {
      const useLlm = generateMode === 'llm';
      const result = await api.docsGenerate(repoId, useLlm);
      setDoc(result);
      setTimeout(() => {
        void load();
      }, 1000);
    } finally {
      setBusy(false);
    }
  };

  const handleCopy = (): void => {
    if (doc?.content) {
      void navigator.clipboard.writeText(doc.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="DOCUMENTATION ENGINE"
        title="Auto-Generated Tech Docs"
        description="Structural or LLM-enhanced documentation synthesized from AST symbols, architecture graphs, and indexed source evidence."
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {/* Generation mode toggle */}
            <div className="mode-pills">
              <button
                type="button"
                className={generateMode === 'structural' ? 'mode-pill active' : 'mode-pill'}
                onClick={() => setGenerateMode('structural')}
              >
                <Icon.Code />
                Structural
              </button>
              <button
                type="button"
                className={generateMode === 'llm' ? 'mode-pill active' : 'mode-pill'}
                onClick={() => setGenerateMode('llm')}
              >
                <Icon.Spark />
                LLM Enhanced
              </button>
            </div>

            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() => { void handleGenerate(); }}
            >
              {busy ? (
                <>
                  <span className="spinner" />
                  <span>Generating…</span>
                </>
              ) : (
                <>
                  <Icon.Book />
                  <span>Generate Docs</span>
                </>
              )}
            </button>
          </div>
        }
      />

      {!doc ? (
        <Card>
          <Empty
            title="No Documentation Yet"
            description="Click Generate Docs above to synthesize a comprehensive technical reference from repository analysis data."
          />
        </Card>
      ) : (
        <Card className="doc-card">
          {/* Doc Card Header */}
          <div className="doc-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <Badge
                status={doc.status}
                label={doc.status}
              />
              <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>
                {doc.used_llm ? '✦ LLM-enhanced' : '⌘ Structural generation'}
                {doc.format && ` · ${doc.format.toUpperCase()}`}
              </span>
            </div>

            <button
              type="button"
              className="secondary"
              onClick={handleCopy}
              disabled={!doc.content}
              style={{ minWidth: 140 }}
            >
              {copied ? (
                <>
                  <Icon.Check />
                  <span>Copied!</span>
                </>
              ) : (
                <>
                  <Icon.Copy />
                  <span>Copy Markdown</span>
                </>
              )}
            </button>
          </div>

          {/* Error Alert */}
          {doc.error_message && (
            <div className="alert danger" style={{ marginBottom: 20 }}>
              <Icon.AlertTriangle />
              {doc.error_message}
            </div>
          )}

          {/* Markdown Preview */}
          <div className="markdown-preview-wrapper">
            <pre className="markdown-preview">
              {doc.content || 'Documentation is still being generated…'}
            </pre>
          </div>
        </Card>
      )}
    </>
  );
}