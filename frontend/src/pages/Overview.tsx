import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { bytes, formatDate, getLanguageColor } from '../lib/utils';
import { Card, Metric, PageHeader, Badge, Loading } from '../components/UI';
import { Icon } from '../components/Icons';
import { useRepo } from '../main';
import './Features.css';

type FeatureItem = {
  title: string;
  description: string;
  theme: 'green' | 'yellow' | 'blue' | 'rose';
  icon: 'integration' | 'metrics' | 'alerts' | 'security';
};

const codebaseFeatures: FeatureItem[] = [
  {
    title: 'AST Semantic Indexing',
    description:
      'Extract abstract syntax trees across Python, TypeScript, Go, and Java. Parse symbols, classes, methods, and functions into deduplicated semantic chunks.',
    theme: 'green',
    icon: 'integration',
  },
  {
    title: 'Dependency Topology',
    description:
      'Map module imports, package exports, and call hierarchies into an interactive dependency graph with centrality ranking and circular loop detection.',
    theme: 'yellow',
    icon: 'metrics',
  },
  {
    title: 'AST Security Audits',
    description:
      'Run automatic static vulnerability scans detecting hardcoded credentials, SQL injection, unsafe command execution, and dangerous API sinks.',
    theme: 'rose',
    icon: 'security',
  },
  {
    title: 'Grounded RAG Copilot',
    description:
      'Synthesize high-confidence answers with exact file and line citation evidence powered by Qdrant vector embeddings and semantic search.',
    theme: 'blue',
    icon: 'alerts',
  },
];

function IntegrationIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 12.5 8.5 17 20 5.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 6.5 7 9.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function MetricsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M4 19V9M10 19V5M16 19v-7M22 19V3" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="m3 6 5-2 6 4 7-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AlertsIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18.5 4.5 20 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function SecurityIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3.5 20 6v5.7c0 4.7-3.2 7.9-8 9.8-4.8-1.9-8-5.1-8-9.8V6l8-2.5Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="m8.5 12 2.2 2.2 4.8-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function FeatureIcon({ type }: { type: FeatureItem['icon'] }) {
  if (type === 'integration') return <IntegrationIcon />;
  if (type === 'metrics') return <MetricsIcon />;
  if (type === 'alerts') return <AlertsIcon />;
  return <SecurityIcon />;
}

function PieChart() {
  return (
    <div className="phone-pie">
      <div className="phone-pie-inner">
        <span />
      </div>
    </div>
  );
}

function MiniChart({ type, value }: { type: 'green' | 'rose'; value: string }) {
  return (
    <div className={`mini-chart mini-${type}`}>
      <div className="mini-chart-top">
        <span>{value}</span>
        <span className="mini-dot" />
      </div>
      <svg viewBox="0 0 120 55" preserveAspectRatio="none">
        <defs>
          <linearGradient id={`chart-${type}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" />
            <stop offset="100%" />
          </linearGradient>
        </defs>
        <path
          className="chart-area"
          d={
            type === 'green'
              ? 'M0 42 C14 35 17 39 28 29 S43 34 54 23 S70 28 81 17 S96 24 120 8 V55 H0Z'
              : 'M0 38 C12 44 20 31 30 34 S43 19 54 27 S70 22 81 31 S98 10 120 16 V55 H0Z'
          }
        />
        <path
          className="chart-line"
          d={
            type === 'green'
              ? 'M0 42 C14 35 17 39 28 29 S43 34 54 23 S70 28 81 17 S96 24 120 8'
              : 'M0 38 C12 44 20 31 30 34 S43 19 54 27 S70 22 81 31 S98 10 120 16'
          }
        />
      </svg>
    </div>
  );
}

function ProgressBar({
  label,
  value,
  theme,
}: {
  label: string;
  value: number;
  theme: 'cyan' | 'yellow' | 'blue';
}) {
  return (
    <div className="progress-item">
      <div className="progress-label">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="progress-track">
        <div className={`progress-fill progress-${theme}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function Cube({
  theme,
  height,
  delay,
}: {
  theme: 'yellow' | 'green' | 'cyan';
  height: number;
  delay: string;
}) {
  return (
    <div
      className={`cube cube-${theme}`}
      style={
        {
          '--cube-height': `${height}px`,
          '--cube-delay': delay,
        } as React.CSSProperties
      }
    >
      <div className="cube-face cube-top" />
      <div className="cube-face cube-front" />
      <div className="cube-face cube-right" />
    </div>
  );
}

function FloatingIcon({ type, delay }: { type: 'settings' | 'clock'; delay: string }) {
  return (
    <div className={`floating-icon floating-${type}`} style={{ '--float-delay': delay } as React.CSSProperties}>
      {type === 'settings' ? (
        <svg viewBox="0 0 24 24" fill="none">
          <path d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z" stroke="currentColor" strokeWidth="1.6" />
          <path
            d="m19 13 .2-2-1.8-.8a6 6 0 0 0-.7-1.7l.6-1.9-1.5-1.3-1.8.8a6 6 0 0 0-1.8-.7L11.4 3h-2l-.8 2.1a6 6 0 0 0-1.7.7l-1.8-.7-1.5 1.3.6 1.9a6 6 0 0 0-.7 1.7l-1.8.8.2 2 1.9.6c.1.7.4 1.2.7 1.8l-.8 1.8 1.5 1.4 1.9-.8c.5.3 1.1.6 1.7.7l.8 2.1h2l.8-2.1a6 6 0 0 0 1.7-.7l1.9.8 1.5-1.4-.8-1.8c.3-.6.6-1.1.7-1.8L19 13Z"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinejoin="round"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
          <path d="M12 7v5l3.5 2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
      )}
    </div>
  );
}

function IsometricScene() {
  return (
    <div className="iso-wrapper">
      <div className="iso-shadow iso-shadow-one" />
      <div className="iso-shadow iso-shadow-two" />

      <div className="iso-scene">
        <div className="phone-glow phone-glow-one" />
        <div className="phone-glow phone-glow-two" />

        <div className="phone">
          <div className="phone-screen">
            <div className="phone-header">
              <div>
                <span className="phone-kicker">CODEBASE</span>
                <strong>Analytics</strong>
              </div>
              <div className="phone-avatar">AI</div>
            </div>

            <div className="phone-summary">
              <div>
                <span>Repository Health</span>
                <strong>98.4%</strong>
              </div>
              <span className="health-pill">+12.6%</span>
            </div>

            <PieChart />

            <div className="mini-grid">
              <MiniChart type="green" value="+32.4%" />
              <MiniChart type="rose" value="0 CVE" />
            </div>

            <div className="progress-section">
              <ProgressBar label="AST Symbols" value={88} theme="cyan" />
              <ProgressBar label="Qdrant Vectors" value={95} theme="yellow" />
              <ProgressBar label="Code Coverage" value={92} theme="blue" />
            </div>

            <div className="phone-footer">
              <span>RAG Copilot</span>
              <span className="footer-status">
                <i /> Active
              </span>
            </div>
          </div>
        </div>

        <div className="cube-row">
          <Cube theme="yellow" height={40} delay="0s" />
          <Cube theme="green" height={75} delay="-1.2s" />
          <Cube theme="cyan" height={120} delay="-2.4s" />
        </div>

        <FloatingIcon type="settings" delay="-1.8s" />
        <FloatingIcon type="clock" delay="-3.1s" />
      </div>
    </div>
  );
}

function FeatureCard({ feature }: { feature: FeatureItem }) {
  return (
    <article className={`feature-card feature-${feature.theme}`}>
      <div className="feature-icon">
        <FeatureIcon type={feature.icon} />
      </div>
      <div className="feature-copy">
        <h3>{feature.title}</h3>
        <p>{feature.description}</p>
      </div>
      <div className="feature-arrow">↗</div>
    </article>
  );
}

export function Overview() {
  const { repoId, repo, refresh } = useRepo();
  const [analysis, setAnalysis] = useState<any>();
  const [security, setSecurity] = useState<any>();
  const [arch, setArch] = useState<any>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const nav = useNavigate();

  const loadData = (id: string, showLoader = true) => {
    if (showLoader) setLoading(true);
    return Promise.allSettled([
      api.analysis(id),
      api.securitySummary(id),
      api.architectureOverview(id),
    ])
      .then(([a, s, g]) => {
        if (a.status === 'fulfilled') setAnalysis(a.value);
        if (s.status === 'fulfilled') setSecurity(s.value);
        if (g.status === 'fulfilled') setArch(g.value);
      })
      .finally(() => {
        if (showLoader) setLoading(false);
      });
  };

  useEffect(() => {
    if (!repoId) return;
    void loadData(repoId, true);
  }, [repoId]);

  const handleRefresh = async () => {
    if (!repoId || refreshing) return;
    setRefreshing(true);
    try {
      await refresh();
      await loadData(repoId, false);
    } finally {
      setRefreshing(false);
    }
  };

  // Main Intro / Landing UI when no repository is selected
  if (!repoId) {
    return (
      <main className="features-page" style={{ margin: '-24px -32px', minHeight: 'calc(100vh - 64px)' }}>
        <div className="ambient ambient-top-right" />
        <div className="ambient ambient-bottom-left" />

        <div className="features-container">
          <section className="features-intro">
            <div className="intro-eyebrow">
              <span className="eyebrow-line" />
              CODEBASE INTELLIGENCE &amp; COPILOT
            </div>

            <h1>
              AI Codebase
              <span>Assistant.</span>
            </h1>

            <p className="intro-description">
              Transform complex source code into grounded AI answers, interactive architecture dependency graphs, automated AST security audits, and developer interview knowledge.
            </p>

            <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
              <button
                type="button"
                className="primary"
                onClick={() => nav('/settings')}
                style={{ padding: '12px 24px', fontSize: 14, fontWeight: 600 }}
              >
                <Icon.Upload />
                <span>Upload Repository</span>
                <Icon.Arrow />
              </button>

              <button
                type="button"
                className="secondary"
                onClick={() => nav('/settings')}
                style={{ padding: '12px 20px', fontSize: 14 }}
              >
                <Icon.Grid />
                <span>Select Repository</span>
              </button>
            </div>

            <IsometricScene />

            <div className="scene-caption">
              <span className="caption-dot" />
              Real-time AST parsing, vector embeddings &amp; dependency topology
            </div>
          </section>

          <section className="features-panel">
            <div className="panel-heading">
              <div>
                <span className="panel-kicker">BUILT FOR DEVELOPERS</span>
                <h2>Everything you need to understand and audit your codebase.</h2>
              </div>
              <span className="panel-count">04</span>
            </div>

            <div className="feature-list">
              {codebaseFeatures.map((feature) => (
                <FeatureCard key={feature.title} feature={feature} />
              ))}
            </div>
          </section>
        </div>
      </main>
    );
  }

  if (loading || !repo) {
    return <Loading label="Loading codebase intelligence…" />;
  }

  return (
    <>
      <PageHeader
        eyebrow="REPOSITORY DASHBOARD"
        title={repo.name}
        description={`${repo.file_count.toLocaleString()} total files · ${bytes(repo.total_size_bytes)} · Indexed ${formatDate(repo.indexed_at)}`}
        actions={
          <>
            <Badge status={repo.status} />
            <button
              type="button"
              className="secondary"
              onClick={handleRefresh}
              disabled={refreshing}
              title="Refresh intelligence"
            >
              {refreshing ? (
                <span className="spinner" style={{ width: 14, height: 14 }} />
              ) : (
                <Icon.Refresh />
              )}
              <span>{refreshing ? 'Refreshing…' : 'Refresh'}</span>
            </button>
          </>
        }
      />

      {/* Top 4 Metrics */}
      <div className="metrics">
        <Metric
          label="Parsed Files"
          value={repo.parsed_file_count.toLocaleString()}
          detail={`${bytes(repo.total_size_bytes)} total size`}
          icon={Icon.File}
          accent="cyan"
        />
        <Metric
          label="Code Symbols"
          value={repo.symbol_count.toLocaleString()}
          detail={`${repo.dependency_edge_count} dependency edges`}
          icon={Icon.Code}
          accent="purple"
        />
        <Metric
          label="Semantic Chunks"
          value={repo.chunk_count.toLocaleString()}
          detail={`${repo.duplicate_chunk_count} deduped chunks`}
          icon={Icon.Grid}
          accent="blue"
        />
        <Metric
          label="Vector Embeddings"
          value={repo.vector_count.toLocaleString()}
          detail={repo.embedding_model || 'Indexed in Qdrant'}
          icon={Icon.Spark}
          accent="emerald"
        />
      </div>

      {/* 2-Column Dashboard Breakdown */}
      <div className="grid-2">
        {/* Languages Breakdown */}
        <Card>
          <div className="card-title">
            <div>
              <span className="eyebrow">COMPOSITION</span>
              <h2>Language Breakdown</h2>
            </div>
            <Badge status="info" label={`${Object.keys(repo.language_breakdown || {}).length} Languages`} />
          </div>

          <div className="bars">
            {Object.entries(repo.language_breakdown || {})
              .slice(0, 8)
              .map(([lang, count]) => {
                const num = Number(count);
                const pct = Math.max(
                  4,
                  Math.round((num / Math.max(1, repo.file_count)) * 100)
                );
                const color = getLanguageColor(lang);

                return (
                  <div className="bar-row" key={lang}>
                    <span className="bar-name">{lang}</span>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${pct}%`,
                          background: `linear-gradient(90deg, ${color}, #22D3EE)`,
                        }}
                      />
                    </div>
                    <span className="bar-count">{num} files</span>
                  </div>
                );
              })}
          </div>
        </Card>

        {/* System Health & Signals */}
        <Card>
          <div className="card-title">
            <div>
              <span className="eyebrow">INTELLIGENCE</span>
              <h2>System Signals</h2>
            </div>
            <span className="status-dot" />
          </div>

          <div className="signal-list">
            <div className="signal-item">
              <span>AST Parsing & Analysis</span>
              <Badge status={analysis?.status || repo.status} />
            </div>

            <div className="signal-item">
              <span>Vector Search Index</span>
              <Badge
                status={repo.vector_count ? 'ready' : 'pending'}
                label={repo.vector_count ? `${repo.vector_count} vectors` : 'Pending'}
              />
            </div>

            <div className="signal-item">
              <span>Security Audits</span>
              <Badge
                status={security?.latest_scan?.status || (security?.total_findings ? 'warning' : 'ready')}
                label={
                  security?.total_findings != null
                    ? `${security.total_findings} findings`
                    : 'Not Scanned'
                }
              />
            </div>

            <div className="signal-item">
              <span>Architecture Dependency Graph</span>
              <Badge
                status={arch ? 'ready' : 'pending'}
                label={arch ? 'Analyzed' : 'Pending'}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* 3 Quick Action Feature Cards */}
      <div className="grid-3">
        <Card className="action-card" onClick={() => nav('/ask')}>
          <div className="action-card-icon">
            <Icon.Message />
          </div>
          <h3>Ask Codebase</h3>
          <p>
            Query architecture, functions, and workflows with citation-grounded AI answers.
          </p>
          <span className="action-card-link">
            <span>Open Assistant</span>
            <Icon.Arrow />
          </span>
        </Card>

        <Card className="action-card" onClick={() => nav('/architecture')}>
          <div className="action-card-icon" style={{ color: 'var(--accent-violet)', borderColor: 'rgba(167, 139, 250, 0.3)', background: 'rgba(167, 139, 250, 0.08)' }}>
            <Icon.Git />
          </div>
          <h3>Explore Architecture</h3>
          <p>
            Inspect dependency relationships, circular loops, and identify high-centrality files.
          </p>
          <span className="action-card-link" style={{ color: 'var(--accent-violet)' }}>
            <span>Open Graph Explorer</span>
            <Icon.Arrow />
          </span>
        </Card>

        <Card className="action-card" onClick={() => nav('/security')}>
          <div className="action-card-icon" style={{ color: 'var(--accent-rose)', borderColor: 'rgba(244, 63, 94, 0.3)', background: 'rgba(244, 63, 94, 0.08)' }}>
            <Icon.Shield />
          </div>
          <h3>Review Security</h3>
          <p>
            Scan source code for hardcoded secrets, dangerous sinks, and vulnerability findings.
          </p>
          <span className="action-card-link" style={{ color: 'var(--accent-rose)' }}>
            <span>View Security Center</span>
            <Icon.Arrow />
          </span>
        </Card>
      </div>
    </>
  );
}
