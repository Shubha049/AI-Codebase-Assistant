import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Card, Empty, PageHeader, Badge } from '../components/UI';
import { Icon } from '../components/Icons';
import { useRepo } from '../main';

function getStageDescription(status?: string): string {
  switch (status) {
    case 'uploading':
      return 'Uploading repository archive…';
    case 'extracting':
      return 'Extracting archive files…';
    case 'scanning':
      return 'Scanning repository file tree for analyzable source files…';
    case 'scanned':
      return 'Scan complete, queuing AST parser…';
    case 'parsing':
      return 'Extracting AST symbols, imports, and building dependency topology…';
    case 'analyzed':
      return 'Analysis complete, queuing semantic chunker…';
    case 'chunking':
      return 'Generating deduplicated semantic chunks from code symbols…';
    case 'chunked':
      return 'Semantic chunks generated, queuing vector embedding model…';
    case 'indexing':
      return 'Computing vector embeddings and upserting points into Qdrant…';
    default:
      return 'Indexing repository pipeline in progress…';
  }
}

export function Ask() {
  const { repoId, repo, refresh } = useRepo();
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [reindexing, setReindexing] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [conversation, setConversation] = useState<string>();

  const isIndexing = Boolean(repo && repo.status !== 'ready' && repo.status !== 'failed');
  const isFailed = Boolean(repo && repo.status === 'failed');
  const isReady = Boolean(repo && repo.status === 'ready' && (repo.vector_count ?? 0) > 0);
  const hasZeroVectors = Boolean(repo && repo.status === 'ready' && (repo.vector_count ?? 0) === 0);

  useEffect(() => {
    if (!isIndexing) return;
    const interval = setInterval(() => {
      refresh().catch(() => {});
    }, 1500);
    return () => clearInterval(interval);
  }, [isIndexing, refresh]);

  const handleReindex = async () => {
    if (!repoId || reindexing) return;
    setReindexing(true);
    try {
      await api.reindex(repoId, true);
      await refresh();
    } catch (e: any) {
      alert(e.message || 'Re-index failed');
    } finally {
      setReindexing(false);
    }
  };

  const ask = async () => {
    if (!repoId || !q.trim() || busy || !isReady) return;
    const currentQ = q.trim();
    setBusy(true);
    try {
      const r = await api.ask({
        repository_id: repoId,
        question: currentQ,
        conversation_id: conversation,
        top_k: 3,
      });
      setConversation(r.conversation_id);
      setHistory((h) => [...h, { q: currentQ, r }]);
      setQ('');
    } catch (e: any) {
      setHistory((h) => [
        ...h,
        {
          q: currentQ,
          error: e.message || 'Error generating grounded answer.',
          canReindex: e.message?.includes('vector') || e.message?.includes('index'),
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  if (!repoId) {
    return (
      <Empty
        title="Select a Repository"
        description="Choose a repository from the workspace selector to begin asking grounded questions about your code."
      />
    );
  }

  return (
    <>
      <PageHeader
        eyebrow="AI COPILOT"
        title="Ask Codebase Assistant"
        description="Answers are synthesized from AST semantic chunks and vector embeddings with exact file and line citations."
        actions={
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Badge
              status={isReady ? 'ready' : isFailed ? 'danger' : isIndexing ? 'pending' : 'warning'}
              label={
                isIndexing
                  ? `Indexing (${repo?.status})`
                  : isFailed
                  ? 'Indexing Failed'
                  : isReady
                  ? `${repo?.vector_count} Vectors Indexed`
                  : '0 Vectors Found'
              }
            />
            <button
              type="button"
              className="secondary"
              disabled={reindexing || isIndexing}
              onClick={handleReindex}
              title="Rebuild chunks and vector embeddings"
            >
              {reindexing ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14 }} />
                  <span>Re-indexing…</span>
                </>
              ) : (
                <>
                  <Icon.Refresh />
                  <span>Re-index</span>
                </>
              )}
            </button>
          </div>
        }
      />

      {/* Indexing in Progress Alert */}
      {isIndexing && (
        <div
          className="alert info"
          style={{
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            padding: '14px 18px',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span className="spinner" style={{ width: 18, height: 18, flexShrink: 0 }} />
            <div>
              <strong>Indexing in Progress ({repo?.status}):</strong> {getStageDescription(repo?.status)}
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Querying will unlock automatically as soon as vector indexing completes in Qdrant.
              </div>
            </div>
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-cyan)' }}>Auto-syncing…</span>
        </div>
      )}

      {/* Indexing Failed Alert */}
      {isFailed && (
        <div
          className="alert danger"
          style={{
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            padding: '14px 18px',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Icon.AlertTriangle style={{ width: 20, height: 20, flexShrink: 0 }} />
            <div>
              <strong>Indexing Pipeline Failed:</strong> {repo?.error_message || 'An unknown error occurred during indexing.'}
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Please review repository contents and trigger a re-index.
              </div>
            </div>
          </div>
          <button
            type="button"
            className="secondary"
            disabled={reindexing}
            onClick={handleReindex}
            style={{ flexShrink: 0 }}
          >
            {reindexing ? 'Re-indexing…' : 'Re-index Repository'}
          </button>
        </div>
      )}

      {/* 0 Vectors Warning */}
      {hasZeroVectors && (
        <div
          className="alert warning"
          style={{
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            padding: '14px 18px',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Icon.AlertTriangle style={{ width: 20, height: 20, flexShrink: 0 }} />
            <div>
              <strong>No Searchable Vectors Found:</strong> The repository analysis completed, but 0 vector embeddings were stored.
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
                Ensure the repository contains supported source files (.py, .js, .ts, etc.) and trigger a re-index.
              </div>
            </div>
          </div>
          <button
            type="button"
            className="secondary"
            disabled={reindexing}
            onClick={handleReindex}
            style={{ flexShrink: 0 }}
          >
            {reindexing ? 'Re-indexing…' : 'Re-index Repository'}
          </button>
        </div>
      )}

      <div className="chat-layout">
        <Card className="chat-card">
          {/* Chat Header */}
          <div className="chat-head">
            <div className="chat-head-title">
              <strong>{repo?.name} Intelligence Assistant</strong>
              <span>
                Model: {repo?.embedding_model || 'semantic-vectors'} · {repo?.vector_count ?? 0} Vectors · Top-K Grounding
              </span>
            </div>
            <div className="api-status-badge">
              <span className="status-dot" />
              <span>Grounded Evidence Mode</span>
            </div>
          </div>

          {/* Messages Stream */}
          <div className="messages">
            {history.length === 0 ? (
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <Icon.Spark />
                </div>
                <h3>What would you like to explore?</h3>
                <p>
                  Query architectural decisions, service boundaries, data flows, or security mechanisms across {repo?.name}.
                </p>

                <div className="suggestions">
                  <button
                    type="button"
                    className="suggestion-btn"
                    disabled={!isReady}
                    onClick={() => setQ('How is the overall application architecture and directory structure organized?')}
                  >
                    <span>How is the architecture organized?</span>
                    <Icon.Arrow />
                  </button>
                  <button
                    type="button"
                    className="suggestion-btn"
                    disabled={!isReady}
                    onClick={() => setQ('Where is the authentication and authorization flow implemented?')}
                  >
                    <span>Where is authentication implemented?</span>
                    <Icon.Arrow />
                  </button>
                  <button
                    type="button"
                    className="suggestion-btn"
                    disabled={!isReady}
                    onClick={() => setQ('What are the key services and their primary responsibilities?')}
                  >
                    <span>What are the key services?</span>
                    <Icon.Arrow />
                  </button>
                  <button
                    type="button"
                    className="suggestion-btn"
                    disabled={!isReady}
                    onClick={() => setQ('What security controls or potential risks are present in the codebase?')}
                  >
                    <span>What security controls or risks exist?</span>
                    <Icon.Arrow />
                  </button>
                </div>
              </div>
            ) : (
              history.map((m, i) => (
                <div key={i} className="message-pair">
                  {/* User Bubble */}
                  <div className="bubble user">{m.q}</div>

                  {/* Assistant or Error Bubble */}
                  {m.error ? (
                    <div className="bubble error" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div><strong>Query Error:</strong> {m.error}</div>
                      {m.canReindex && (
                        <button
                          type="button"
                          className="secondary"
                          style={{ alignSelf: 'flex-start', marginTop: 4, padding: '4px 10px', fontSize: 12 }}
                          disabled={reindexing}
                          onClick={handleReindex}
                        >
                          {reindexing ? 'Re-indexing…' : 'Trigger Re-index'}
                        </button>
                      )}
                    </div>
                  ) : (
                    <div className="assistant-block">
                      <div className="answer">
                        <div className="answer-header">
                          <span className="answer-tag">
                            <Icon.Spark />
                            <span>Grounded Answer</span>
                          </span>
                          <Badge
                            status={m.r.confidence === 'High' ? 'ready' : m.r.confidence === 'Medium' ? 'warning' : 'info'}
                            label={`${m.r.confidence || 'Grounded'} Confidence`}
                            size="sm"
                          />
                        </div>
                        <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{m.r.answer}</p>
                      </div>

                      {/* Source Citations */}
                      {m.r.sources && m.r.sources.length > 0 && (
                        <div className="sources-box">
                          <div className="sources-box-title">
                            <Icon.Book style={{ width: 13, height: 13 }} />
                            <span>Referenced Evidence ({m.r.sources.length} sources)</span>
                          </div>

                          <div className="sources-grid">
                            {m.r.sources.map((s: any) => (
                              <div className="source-item" key={s.source_id}>
                                <span className="source-num">#{s.source_id}</span>
                                <div className="source-details">
                                  <b>{s.file}</b>
                                  <small>
                                    Lines {s.start_line}–{s.end_line} · Similarity {(s.similarity_score * 100).toFixed(0)}%
                                  </small>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
            {busy && (
              <div className="message-pair" style={{ animation: 'fadeIn 0.2s ease-in-out' }}>
                <div className="assistant-block" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px', borderRadius: 'var(--radius-md)', background: 'rgba(255, 255, 255, 0.03)', border: '1px dashed var(--border-color)' }}>
                  <span className="spinner" style={{ width: 18, height: 18, flexShrink: 0 }} />
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                      Generating Grounded Answer…
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                      Retrieving top AST chunks & reasoning over repository evidence
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="composer">
            <textarea
              value={q}
              disabled={!isReady || busy}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  ask();
                }
              }}
              placeholder={
                isIndexing
                  ? `Repository indexing in progress (${repo?.status})… queries will unlock when ready.`
                  : isFailed
                  ? 'Repository indexing failed. Please re-index to enable queries.'
                  : hasZeroVectors
                  ? 'No searchable vectors indexed. Please re-index the repository.'
                  : `Ask a question about ${repo?.name}…`
              }
            />

            <button
              type="button"
              className="send-btn"
              disabled={busy || !q.trim() || !isReady}
              onClick={ask}
              aria-label="Send message"
            >
              {busy ? <span className="spinner" /> : <Icon.Arrow />}
            </button>

            <div className="composer-hint">
              {isReady ? (
                <>Press <strong>Enter</strong> to send, <strong>Shift + Enter</strong> for new line</>
              ) : isIndexing ? (
                <span>Indexing pipeline running in background — polling for completion…</span>
              ) : (
                <span>Querying is locked until repository vectors are indexed.</span>
              )}
            </div>
          </div>
        </Card>
      </div>
    </>
  );
}
