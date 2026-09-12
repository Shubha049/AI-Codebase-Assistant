import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuth } from '../main';
import { Icon } from '../components/Icons';

export function Auth({ mode = 'login' }: { mode?: 'login' | 'register' }) {
  const { setAuth } = useAuth();
  const nav = useNavigate();
  const [register, setRegister] = useState(mode === 'register');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      const r = register
        ? await api.register(email, password)
        : await api.login(email, password);
      setAuth(r.access_token, r.user);
      nav('/');
    } catch (err: any) {
      setError(err.message || 'Authentication failed. Please verify credentials.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        {/* Brand Header */}
        <div className="auth-header">
          <div className="brand">
            <div className="brand-mark">
              <Icon.Spark />
            </div>
            <div className="brand-text">
              <strong>AI Codebase Assistant</strong>
              <span>Developer Platform</span>
            </div>
          </div>
          <h1>{register ? 'Create Your Account' : 'Welcome Back'}</h1>
          <p>
            {register
              ? 'Get started with deep architectural reasoning and semantic code intelligence.'
              : 'Sign in to access your private repository analysis and AI assistant.'}
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${!register ? 'active' : ''}`}
            onClick={() => {
              setRegister(false);
              setError('');
            }}
          >
            Sign In
          </button>
          <button
            type="button"
            className={`auth-tab ${register ? 'active' : ''}`}
            onClick={() => {
              setRegister(true);
              setError('');
            }}
          >
            Create Account
          </button>
        </div>

        {/* Form */}
        <form className="auth-form" onSubmit={submit}>
          <div className="form-group">
            <label htmlFor="auth-email">Email Address</label>
            <input
              id="auth-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="developer@company.com"
              autoComplete="email"
            />
          </div>

          <div className="form-group">
            <label htmlFor="auth-password">
              <span>Password</span>
              {register && <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>Min 10 characters</span>}
            </label>
            <input
              id="auth-password"
              type="password"
              required
              minLength={10}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              autoComplete={register ? 'new-password' : 'current-password'}
            />
          </div>

          {error && (
            <div className="alert danger">
              <Icon.AlertTriangle style={{ width: 16, height: 16, flexShrink: 0 }} />
              <span>{error}</span>
            </div>
          )}

          <button
            type="submit"
            className="primary auth-submit"
            disabled={busy}
          >
            {busy ? (
              <>
                <span className="spinner" />
                <span>Authenticating…</span>
              </>
            ) : register ? (
              'Create Workspace Account'
            ) : (
              'Sign In to Workspace'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}

