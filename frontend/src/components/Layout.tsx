import { useState } from 'react';
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Icon } from './Icons';
import { useRepo, useAuth } from '../main';
import { cn } from '../lib/utils';

const nav = [
  { to: '/home', label: 'Home', icon: Icon.Home, end: true },
  { to: '/', label: 'Overview', icon: Icon.Grid, end: true },
  { to: '/ask', label: 'AI Assistant', icon: Icon.Message },
  { to: '/architecture', label: 'Architecture', icon: Icon.Git },
  { to: '/security', label: 'Security', icon: Icon.Shield },
  { to: '/documentation', label: 'Documentation', icon: Icon.Book },
  { to: '/interview', label: 'Interview Prep', icon: Icon.Spark },
];

export function Layout() {
  const { repos, repoId, setRepoId, refresh } = useRepo();
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const activeRepo = repos.find((r) => r.id === repoId);
  const currentNav = nav.find((n) =>
    n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)
  );

  const handleSync = async () => {
    if (syncing) return;
    setSyncing(true);
    try {
      await refresh();
    } finally {
      setSyncing(false);
    }
  };

  const handleSignOut = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="app-shell">
      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div
          className="drawer"
          onClick={() => setMobileMenuOpen(false)}
          style={{ zIndex: 35 }}
        />
      )}

      {/* Sidebar */}
      <aside className={cn('sidebar', mobileMenuOpen && 'open')}>
        {/* Brand */}
        <div className="brand">
          <div className="brand-mark">
            <Icon.Spark />
          </div>
          <div className="brand-text">
            <strong>AI Assistant</strong>
            <span>Codebase Intelligence</span>
          </div>
        </div>

        {/* Workspace / Repository Switcher */}
        <div className="repo-switch">
          <div className="repo-switch-label">
            <span>Active Repository</span>
            {activeRepo && <span className="status-dot" />}
          </div>
          <div className="repo-select-wrap">
            <select
              value={repoId || ''}
              onChange={(e) => {
                setRepoId(e.target.value);
                navigate('/');
                setMobileMenuOpen(false);
              }}
            >
              <option value="">Choose a repository…</option>
              {repos.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
            <div className="repo-select-icon">
              <Icon.ChevronDown />
            </div>
          </div>
        </div>

        {/* Primary Navigation */}
        <nav>
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setMobileMenuOpen(false)}
              className={({ isActive }) =>
                cn('nav-item', isActive && 'active')
              }
            >
              <n.icon />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Sidebar Bottom */}
        <div className="sidebar-bottom">
          <button
            type="button"
            className="nav-item ghost"
            onClick={handleSync}
            disabled={syncing}
            title="Refresh repository cache"
          >
            {syncing ? (
              <span className="spinner" style={{ width: 16, height: 16 }} />
            ) : (
              <Icon.Refresh />
            )}
            <span>{syncing ? 'Syncing…' : 'Sync Workspace'}</span>
          </button>

          <NavLink
            to="/settings"
            onClick={() => setMobileMenuOpen(false)}
            className={({ isActive }) =>
              cn('nav-item ghost', isActive && 'active')
            }
          >
            <Icon.Settings />
            <span>Repositories & Settings</span>
          </NavLink>

          <div className="user-badge">
            <div className="user-info">
              <div className="user-avatar">{user?.email ? user.email.slice(0, 2).toUpperCase() : 'AI'}</div>
              <span className="user-email">{user?.email || 'Developer Workspace'}</span>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={handleSignOut}
              title="Sign out of session"
              style={{ width: 28, height: 28 }}
            >
              <Icon.LogOut />
            </button>
          </div>
        </div>
      </aside>

      {/* Main Area */}
      <main className="main">
        {/* Top Navigation Bar */}
        <header className="topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="mobile-menu-btn icon-btn"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle navigation menu"
            >
              {mobileMenuOpen ? <Icon.Close /> : <Icon.Menu />}
            </button>

            <div className="crumb">
              <span>Platform</span>
              <Icon.Chevron />
              {activeRepo ? (
                <>
                  <span>{activeRepo.name}</span>
                  <Icon.Chevron />
                  <strong>{currentNav?.label || 'Dashboard'}</strong>
                </>
              ) : (
                <strong>Workspace Overview</strong>
              )}
            </div>
          </div>

          <div className="topbar-right">
            <button
              type="button"
              className="icon-btn"
              onClick={handleSync}
              disabled={syncing}
              title="Refresh intelligence"
            >
              {syncing ? (
                <span className="spinner" style={{ width: 14, height: 14 }} />
              ) : (
                <Icon.Refresh />
              )}
            </button>

            <button
              type="button"
              className="icon-btn"
              onClick={handleSignOut}
              title="Sign out"
            >
              <Icon.LogOut />
            </button>
          </div>
        </header>

        {/* Content View */}
        <section className="content">
          <Outlet />
        </section>
      </main>
    </div>
  );
}

