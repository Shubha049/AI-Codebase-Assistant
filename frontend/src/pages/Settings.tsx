import { useCallback, useRef, useState } from 'react';
import { api } from '../lib/api';
import { bytes } from '../lib/utils';
import { Card, Empty, PageHeader, Badge } from '../components/UI';
import { Icon } from '../components/Icons';
import { useRepo } from '../main';

export function Settings() {
  const { repos, repoId, setRepoId, refresh } = useRepo();

  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState<'success' | 'error'>('success');
  const [dragging, setDragging] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  /* ── Upload ZIP ─────────────────────────────────────── */
  const upload = async (file?: File): Promise<void> => {
    if (!file) return;
    setBusy(true);
    setMessage('Uploading and indexing repository…');
    setMessageType('success');
    try {
      const r = await api.upload(file);
      await refresh();
      setRepoId(r.id);
      setMessage(`✓ Successfully indexed "${r.name}"`);
      setMessageType('success');
    } catch (e: any) {
      setMessage(e.message || 'Upload failed. Please try again.');
      setMessageType('error');
    } finally {
      setBusy(false);
    }
  };

  /* ── Drag & Drop ─────────────────────────────────────── */
  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file?.name.endsWith('.zip')) {
        void upload(file);
      } else {
        setMessage('Please drop a valid .zip file.');
        setMessageType('error');
      }
    },
    [],
  );

  /* ── Delete Repository ───────────────────────────────── */
  const handleDelete = async (id: string, name: string): Promise<void> => {
    if (!window.confirm(`Remove "${name}" from workspace?`)) return;
    setDeletingId(id);
    try {
      await api.deleteRepo(id);
      if (repoId === id) setRepoId('');
      await refresh();
    } catch (e: any) {
      setMessage(e.message || 'Delete failed.');
      setMessageType('error');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="WORKSPACE MANAGEMENT"
        title="Repositories & Workspaces"
        description="Upload repository archives, switch active workspaces, and manage indexed codebases."
      />

      <div className="settings-grid">
        {/* ── ZIP Upload Card ──────────────────────────── */}
        <Card className="upload-card">
          <div
            className={dragging ? 'dropzone dragging' : 'dropzone'}
            onClick={() => !busy && input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
          >
            <input
              ref={input}
              hidden
              type="file"
              accept=".zip"
              onChange={(e) => void upload(e.target.files?.[0])}
            />

            <div className="dropzone-icon">
              {busy ? (
                <span className="spinner" style={{ width: 36, height: 36 }} />
              ) : (
                <Icon.Upload />
              )}
            </div>

            <h2>{busy ? 'Uploading…' : 'Upload Repository'}</h2>
            <p>
              {dragging
                ? 'Drop your ZIP file now…'
                : 'Drag & drop a .zip archive here, or click to browse.'}
            </p>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
              Files are parsed, chunked, and vector-indexed automatically.
            </p>

            <button
              type="button"
              className="secondary"
              disabled={busy}
              style={{ marginTop: 20, pointerEvents: 'none' }}
            >
              <Icon.Upload />
              {busy ? 'Processing…' : 'Choose ZIP File'}
            </button>
          </div>

          {/* Upload Message */}
          {message && (
            <div
              className={messageType === 'error' ? 'alert danger' : 'alert success'}
              style={{ marginTop: 16 }}
            >
              {messageType === 'error' ? <Icon.AlertTriangle /> : <Icon.Check />}
              {message}
            </div>
          )}
        </Card>

        {/* ── Repository List Card ─────────────────────── */}
        <Card>
          <div className="card-title">
            <div>
              <span className="eyebrow">WORKSPACE</span>
              <h2>Indexed Repositories</h2>
            </div>
            <span className="count-pill">{repos.length}</span>
          </div>

          {!repos.length ? (
            <Empty
              title="No Repositories Yet"
              description="Upload your first ZIP file to create a workspace and begin analysis."
            />
          ) : (
            <div className="repo-list">
              {repos.map((r) => (
                <div
                  key={r.id}
                  className={`repo-row${repoId === r.id ? ' selected' : ''}`}
                >
                  {/* Avatar + Info */}
                  <button
                    type="button"
                    className="repo-row-btn"
                    onClick={() => setRepoId(r.id)}
                    aria-pressed={repoId === r.id}
                  >
                    <div className="repo-avatar">
                      {r.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div className="repo-info">
                      <b>{r.name}</b>
                      <small>
                        {r.file_count?.toLocaleString() ?? 0} files
                        {' · '}
                        {bytes(r.total_size_bytes ?? 0)}
                      </small>
                    </div>
                    <Badge status={r.status} label={r.status} size="sm" />
                  </button>

                  {/* Delete Button */}
                  <button
                    type="button"
                    className="icon-btn danger-btn"
                    title={`Delete ${r.name}`}
                    disabled={deletingId === r.id}
                    onClick={() => void handleDelete(r.id, r.name)}
                  >
                    {deletingId === r.id ? (
                      <span className="spinner" style={{ width: 14, height: 14 }} />
                    ) : (
                      <Icon.Trash />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
