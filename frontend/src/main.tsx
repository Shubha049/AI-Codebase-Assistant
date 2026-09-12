import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import ReactDOM from 'react-dom/client';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
} from 'react-router-dom';

import { api, onAuthChange } from './lib/api';
import type { Repository } from './lib/api';

import { Layout } from './components/Layout';

import { Overview } from './pages/Overview';
import { Ask } from './pages/Ask';
import { Architecture } from './pages/Architecture';
import { Security } from './pages/Security';
import { Documentation } from './pages/Documentation';
import { Interview } from './pages/Interview';
import { Settings } from './pages/Settings';
import { Auth } from './pages/Auth';
import { Home } from './pages/Home';

import './styles/global.css';


/* =========================================================
   Authentication Context
   ========================================================= */

export interface AuthUser {
  id: string;
  email: string;
}

interface AuthContextValue {
  token: string | null;
  user: AuthUser | null;
  setAuth: (token: string, user?: AuthUser) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider');
  }

  return context;
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => api.getToken());
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    return onAuthChange((newToken) => {
      setTokenState(newToken);
      if (!newToken) {
        setUser(null);
      }
    });
  }, []);

  useEffect(() => {
    if (token) {
      api
        .me()
        .then((u: AuthUser) => setUser(u))
        .catch(() => {
          api.clearToken();
        });
    } else {
      setUser(null);
    }
  }, [token]);

  const setAuth = (newToken: string, newUser?: AuthUser) => {
    api.setToken(newToken);
    setTokenState(newToken);
    if (newUser) setUser(newUser);
  };

  const logout = () => {
    api.clearToken();
    setTokenState(null);
    setUser(null);
  };

  const value = useMemo(
    () => ({ token, user, setAuth, logout }),
    [token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}


/* =========================================================
   Repository Context
   ========================================================= */

interface RepoContextValue {
  repos: Repository[];
  repoId: string;
  repo: Repository | undefined;
  setRepoId: (id: string) => void;
  refresh: () => Promise<void>;
}

const RepoContext = createContext<RepoContextValue | null>(null);

export const useRepo = (): RepoContextValue => {
  const context = useContext(RepoContext);

  if (!context) {
    throw new Error(
      'useRepo must be used inside the RepoContext provider'
    );
  }

  return context;
};


/* =========================================================
   Protected Application Route Guard
   ========================================================= */

function Protected() {
  const { token } = useAuth();
  if (!token) {
    return <Navigate to="/login" replace />;
  }
  return <Provider />;
}

function PublicOnly({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  if (token) {
    return <Navigate to="/" replace />;
  }
  return <>{children}</>;
}


/* =========================================================
   Repository Provider
   ========================================================= */

function Provider() {
  const [repos, setRepos] = useState<Repository[]>([]);

  const [repoId, setRepoIdState] = useState<string>(
    () => localStorage.getItem('activeRepo') || ''
  );

  const [repo, setRepo] = useState<Repository | undefined>(
    undefined
  );


  /* -------------------------------------------------------
     Refresh repositories
     ------------------------------------------------------- */

  const refresh = async (): Promise<void> => {
    try {
      const response = await api.repos();
      setRepos(response.repositories);

      if (repoId) {
        const found = response.repositories.find(
          (repository: Repository) => repository.id === repoId
        );
        if (found) {
          try {
            const detailed = await api.repo(repoId);
            setRepo(detailed);
          } catch {
            setRepo(found);
          }
        } else {
          setRepoIdState('');
          setRepo(undefined);
        }
      }
    } catch {
      // Handled at caller / API layer
    }
  };


  /* -------------------------------------------------------
     Initial repository loading
     ------------------------------------------------------- */

  useEffect(() => {
    refresh().catch(() => {
      /*
       * Authentication/network errors are handled by the
       * individual API layer. Avoid crashing the application
       * during initial loading.
       */
    });
  }, []);


  /* -------------------------------------------------------
     Load selected repository
     ------------------------------------------------------- */

  useEffect(() => {
    if (!repoId) {
      localStorage.removeItem('activeRepo');
      setRepo(undefined);
      return;
    }

    localStorage.setItem('activeRepo', repoId);

    api
      .repo(repoId)
      .then((repository: Repository) => {
        setRepo(repository);
      })
      .catch(() => {
        setRepo(undefined);
      });
  }, [repoId]);

  /* -------------------------------------------------------
     Live SSE stream for active repository indexing progress
     ------------------------------------------------------- */

  useEffect(() => {
    if (!repoId || !repo || repo.status === 'ready' || repo.status === 'failed') {
      return;
    }

    const unsubscribe = api.streamEvents(
      repoId,
      (event) => {
        setRepo((prev) => (prev ? { ...prev, ...event } : prev));
        if (event.status === 'ready' || event.status === 'failed') {
          void refresh();
        }
      },
      () => {
        void refresh();
      }
    );

    return () => {
      unsubscribe();
    };
  }, [repoId, repo?.status]);


  /* -------------------------------------------------------
     Change active repository
     ------------------------------------------------------- */

  const setRepoId = (id: string): void => {
    setRepoIdState(id);
  };


  /* -------------------------------------------------------
     Context value
     ------------------------------------------------------- */

  const value = useMemo<RepoContextValue>(
    () => ({
      repos,
      repoId,
      repo,
      setRepoId,
      refresh,
    }),
    [repos, repoId, repo]
  );


  return (
    <RepoContext.Provider value={value}>
      <Layout />
    </RepoContext.Provider>
  );
}


/* =========================================================
   Application Routes
   ========================================================= */

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>

          {/* Public routes */}
          <Route
            path="/login"
            element={
              <PublicOnly>
                <Auth />
              </PublicOnly>
            }
          />

          <Route
            path="/register"
            element={
              <PublicOnly>
                <Auth mode="register" />
              </PublicOnly>
            }
          />


          {/* Protected application */}
          <Route element={<Protected />}>

            <Route
              path="/"
              element={<Overview />}
            />

            <Route
              path="/home"
              element={<Home />}
            />

            <Route
              path="/ask"
              element={<Ask />}
            />

            <Route
              path="/architecture"
              element={<Architecture />}
            />

            <Route
              path="/security"
              element={<Security />}
            />

            <Route
              path="/documentation"
              element={<Documentation />}
            />

            <Route
              path="/interview"
              element={<Interview />}
            />

            <Route
              path="/settings"
              element={<Settings />}
            />

          </Route>

          {/* Fallback route */}
          <Route path="*" element={<Navigate to="/" replace />} />

        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}


/* =========================================================
   React Application Bootstrap
   ========================================================= */

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error(
    'Root element #root was not found in index.html'
  );
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);