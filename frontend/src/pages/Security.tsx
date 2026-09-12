import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import {
  Card,
  Empty,
  Loading,
  Metric,
  PageHeader,
  Badge,
} from '../components/UI';
import { Icon } from '../components/Icons';
import { useRepo } from '../main';

export function Security() {
  const { repoId } = useRepo();
  const [data, setData] = useState<any>();
  const [busy, setBusy] = useState(false);

  /* Load latest security summary */
  const load = async (): Promise<void> => {
    if (!repoId) {
      setData(undefined);
      return;
    }

    try {
      const result = await api.securitySummary(repoId);
      setData(result);
    } catch {
      setData(undefined);
    }
  };

  useEffect(() => {
    void load();
  }, [repoId]);

  if (!repoId) {
    return (
      <Empty
        title="Select a Repository"
        description="Security vulnerability scans and AST static analysis findings are scoped to the active repository."
      />
    );
  }

  if (!data) {
    return <Loading label="Retrieving AST security scanner results…" />;
  }

  const counts = data.counts || {};

  /* Run security scan */
  const runScan = async (): Promise<void> => {
    setBusy(true);
    try {
      await api.securityScan(repoId);
      setTimeout(() => {
        void load();
      }, 1000);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="SECURITY AUDIT"
        title="Static Vulnerability Center"
        description={
          data.scanner_scope ||
          'Automated AST pattern detection for hardcoded secrets, unsafe deserialization, SQLi, and risky sinks.'
        }
        actions={
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => {
              void runScan();
            }}
          >
            {busy ? (
              <>
                <span className="spinner" />
                <span>Scanning AST…</span>
              </>
            ) : (
              <>
                <Icon.Shield />
                <span>Trigger New Scan</span>
              </>
            )}
          </button>
        }
      />

      {/* Security Metrics */}
      <div className="metrics">
        <Metric
          label="Critical Severity"
          value={counts.critical || 0}
          icon={Icon.AlertTriangle}
          accent="rose"
        />
        <Metric
          label="High Severity"
          value={counts.high || 0}
          icon={Icon.Shield}
          accent="amber"
        />
        <Metric
          label="Medium Severity"
          value={counts.medium || 0}
          icon={Icon.Code}
          accent="blue"
        />
        <Metric
          label="Total Findings"
          value={data.total_findings || 0}
          icon={Icon.Grid}
          accent={data.total_findings > 0 ? 'rose' : 'emerald'}
        />
      </div>

      {/* Findings Container Card */}
      <Card>
        <div className="card-title">
          <div>
            <span className="eyebrow">AUDIT STATUS</span>
            <h2>
              {data.latest_scan?.status
                ? `Latest Scan: ${data.latest_scan.status.toUpperCase()}`
                : 'No Previous Scan'}
            </h2>
          </div>

          {data.latest_scan && (
            <Badge
              status={data.latest_scan.status}
              label={data.latest_scan.status}
            />
          )}
        </div>

        {!data.findings?.length ? (
          <Empty
            icon={Icon.CheckCircle2}
            title="Clean Codebase — No Vulnerabilities Detected"
            description="All scanned source files adhere to current security rules. Trigger a new scan anytime to audit new commits."
          />
        ) : (
          <div className="findings">
            {data.findings.map((finding: any) => (
              <div className="finding" key={finding.id}>
                {/* Severity Badge */}
                <div className="finding-severity">
                  <Badge status={finding.severity} />
                </div>

                {/* Finding Body */}
                <div className="finding-body">
                  <div className="finding-title-row">
                    <b>{finding.title}</b>
                    <code className="rule-code">{finding.rule_id}</code>
                  </div>

                  <p>{finding.description}</p>

                  {/* Finding Metadata */}
                  <div className="finding-meta">
                    <span>
                      <Icon.File />
                      <code>{finding.file_path}</code>
                    </span>
                    <span>Line {finding.line_number}</span>
                    <span>{finding.confidence} confidence</span>
                  </div>

                  {/* Remediation Accordion */}
                  {finding.remediation && (
                    <details className="remediation-details">
                      <summary>Recommended Remediation & Fix</summary>
                      <div className="remediation-box">
                        <p>{finding.remediation}</p>
                      </div>
                    </details>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </>
  );
}