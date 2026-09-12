/**
 * Home.tsx — Dedicated landing / intro page at /home.
 *
 * Always renders the premium Advanced Analytics intro design regardless of
 * whether a repository is currently selected.
 *
 * "Upload Repository" and "Select Repository" navigate to /settings.
 */
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Icon } from '../components/Icons';
import './Features.css';

/* ------------------------------------------------------------------ */
/* Static Feature Data                                                  */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Icon helpers                                                         */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Isometric 3-D scene                                                 */
/* ------------------------------------------------------------------ */

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
          <linearGradient id={`home-chart-${type}`} x1="0" x2="0" y1="0" y2="1">
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

function ProgressBar({ label, value, theme }: { label: string; value: number; theme: 'cyan' | 'yellow' | 'blue' }) {
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

function Cube({ theme, height, delay }: { theme: 'yellow' | 'green' | 'cyan'; height: number; delay: string }) {
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
      <div className="feature-arrow">&#8599;</div>
    </article>
  );
}

/* ------------------------------------------------------------------ */
/* Page Export                                                          */
/* ------------------------------------------------------------------ */

export function Home() {
  const nav = useNavigate();

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
            Transform complex source code into grounded AI answers, interactive architecture dependency graphs,
            automated AST security audits, and developer interview knowledge.
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
