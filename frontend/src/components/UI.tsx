import type { ReactNode } from 'react';
import { statusTone } from '../lib/utils';
import { Icon } from './Icons';

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        {eyebrow && (
          <div className="eyebrow">
            <span className="eyebrow-dot" />
            {eyebrow}
          </div>
        )}
        <h1>{title}</h1>
        {description && <p className="page-header-desc">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

export function Card({
  children,
  className = '',
  onClick,
  style,
}: {
  children: ReactNode;
  className?: string;
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className={`card ${className}`}
      onClick={onClick}
      style={style}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={(event) => {
        if (onClick && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          onClick();
        }
      }}
    >
      {children}
    </div>
  );
}

export function Badge({
  status,
  label,
  size = 'md',
}: {
  status: string;
  label?: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  const tone = statusTone(status);
  const displayLabel = label || status.replaceAll('_', ' ');

  return (
    <span className={`badge badge-${tone} badge-${size}`}>
      <span className="badge-dot" />
      <span className="badge-label">{displayLabel}</span>
    </span>
  );
}

export function Metric({
  label,
  value,
  detail,
  icon: IconComp,
  accent,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  icon?: any;
  accent?: 'cyan' | 'blue' | 'purple' | 'emerald' | 'amber' | 'rose';
}) {
  return (
    <div className={`metric ${accent ? `metric-${accent}` : ''}`}>
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        {IconComp && (
          <div className="metric-icon-wrap">
            <IconComp />
          </div>
        )}
      </div>
      <strong className="metric-value">{value}</strong>
      {detail && <div className="metric-detail">{detail}</div>}
    </div>
  );
}

export function Empty({
  title,
  description,
  action,
  icon: IconComp = Icon.Spark,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: any;
}) {
  return (
    <div className="empty">
      <div className="empty-icon-wrap">
        <IconComp />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}

export function Loading({
  label = 'Loading repository intelligence…',
}: {
  label?: string;
}) {
  return (
    <div className="loading">
      <div className="loading-spinner-wrap">
        <div className="spinner-ring" />
        <div className="spinner-glow" />
      </div>
      <span className="loading-label">{label}</span>
    </div>
  );
}