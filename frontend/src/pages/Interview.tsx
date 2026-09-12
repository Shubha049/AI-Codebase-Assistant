import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { useRepo } from '../main';
import {
  Card,
  Empty,
  Loading,
  PageHeader,
  Badge,
} from '../components/UI';
import { Icon } from '../components/Icons';

const DIFFICULTIES = [
  { value: 'easy', label: 'Easy', accent: 'var(--accent-emerald)' },
  { value: 'medium', label: 'Medium', accent: 'var(--accent-amber)' },
  { value: 'hard', label: 'Hard', accent: 'var(--accent-rose)' },
];

const COUNTS = [5, 10, 15, 20];

export function Interview() {
  const { repoId } = useRepo();

  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [difficulty, setDifficulty] = useState('medium');
  const [count, setCount] = useState(10);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const load = async (): Promise<void> => {
    if (!repoId) {
      setData(undefined);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const result = await api.interviewLatest(repoId);
      setData(result);
    } catch {
      setData(null);
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
        description="Interview questions are grounded in your repository's symbols, patterns, and architectural decisions."
      />
    );
  }

  if (loading) {
    return <Loading label="Loading interview question bank…" />;
  }

  const generate = async (): Promise<void> => {
    setBusy(true);
    setExpandedIds(new Set());
    try {
      const result = await api.interviewGenerate(repoId, {
        count,
        difficulty,
        use_llm: false,
      });
      setData(result);
      setTimeout(() => {
        void load();
      }, 1000);
    } finally {
      setBusy(false);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <>
      <PageHeader
        eyebrow="INTERVIEW PREP"
        title="Codebase-Grounded Q&A Bank"
        description="Questions synthesized from repository symbols, architecture patterns, security findings, and real code evidence."
        actions={
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => { void generate(); }}
          >
            {busy ? (
              <>
                <span className="spinner" />
                <span>Generating…</span>
              </>
            ) : (
              <>
                <Icon.Spark />
                <span>Generate Questions</span>
              </>
            )}
          </button>
        }
      />

      {/* Filter Toolbar */}
      <div className="interview-toolbar">
        {/* Question count selector */}
        <div className="toolbar-group">
          <span className="toolbar-label">Questions</span>
          <div className="count-pills">
            {COUNTS.map((n) => (
              <button
                key={n}
                type="button"
                className={count === n ? 'count-pill active' : 'count-pill'}
                onClick={() => setCount(n)}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        {/* Difficulty selector */}
        <div className="toolbar-group">
          <span className="toolbar-label">Difficulty</span>
          <div className="difficulty-pills">
            {DIFFICULTIES.map((d) => (
              <button
                key={d.value}
                type="button"
                className={difficulty === d.value ? 'diff-pill active' : 'diff-pill'}
                style={
                  difficulty === d.value
                    ? { borderColor: d.accent, color: d.accent }
                    : {}
                }
                onClick={() => setDifficulty(d.value)}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Questions List or Empty State */}
      {!data?.questions?.length ? (
        <Card>
          <Empty
            title="No Question Set Yet"
            description="Configure the difficulty and count above, then click Generate Questions to build a personalized interview bank."
          />
        </Card>
      ) : (
        <div className="questions-grid">
          {data.questions.map((q: any, i: number) => {
            const qKey = q.id || String(i);
            const isExpanded = expandedIds.has(qKey);

            return (
              <Card key={qKey} className="question-card">
                {/* Question header */}
                <div className="question-meta-row">
                  <span className="q-number">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <Badge status={q.difficulty} label={q.difficulty} size="sm" />
                  {q.question_type && (
                    <span className="q-type-tag">
                      {q.question_type.replaceAll('_', ' ')}
                    </span>
                  )}
                </div>

                {/* Question text */}
                <h3 className="question-text">{q.question}</h3>

                {/* Source file chips */}
                {q.sources?.length > 0 && (
                  <div className="q-sources">
                    {q.sources.slice(0, 4).map((s: any, j: number) => {
                      const file = s.file_path || s.file || '';
                      const line = s.start_line ? `:${s.start_line}-${s.end_line}` : (s.line ? `:${s.line}` : '');
                      const sym = s.symbol ? ` · ${s.symbol}` : '';
                      const depCount = s.dependencies?.length ? ` · ${s.dependencies.length} deps` : '';
                      const rule = s.rule_id ? ` · ${s.rule_id}` : '';
                      return (
                        <span key={j} className="source-chip" title={file}>
                          <Icon.File />
                          <span>{file}{line}{sym}{depCount}{rule}</span>
                        </span>
                      );
                    })}
                  </div>
                )}

                {/* Expandable Answer Section */}
                <div className="answer-section">
                  <button
                    type="button"
                    className="reveal-btn"
                    onClick={() => toggleExpand(qKey)}
                  >
                    {isExpanded ? (
                      <>
                        <Icon.ChevronDown style={{ transform: 'rotate(180deg)' }} />
                        Hide Expected Answer
                      </>
                    ) : (
                      <>
                        <Icon.ChevronDown />
                        Reveal Expected Answer
                      </>
                    )}
                  </button>

                  {isExpanded && (
                    <div className="answer-body">
                      <p>{q.expected_answer}</p>

                      {q.explanation && (
                        <div className="explanation-block">
                          <span className="explanation-label">Why this matters</span>
                          <p>{q.explanation}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}