import {Headset, Link2, LogOut, RefreshCw} from 'lucide-react';
import {useEffect, useState} from 'react';
import {clearSession, fetchMe, getToken, getUsername} from './api';
import LoginPage from './LoginPage';
import BindingsPage from './pages/BindingsPage';
import StagesPage from './pages/StagesPage';

type AuthState = 'loading' | 'authed' | 'unauthed';

/** 极简 hash 路由：#/bindings、#/stages，默认 → #/bindings */
function useHashRoute(): string {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  const route = hash.replace(/^#/, '') || '/';
  if (route === '/login') return '/login';
  if (route.startsWith('/stages')) return '/stages';
  return '/bindings';
}

const NAV_ITEMS = [
  {path: '/bindings', label: '群绑定管理', icon: Link2},
  {path: '/stages', label: '会话阶段', icon: RefreshCw},
];

export default function App() {
  const route = useHashRoute();
  const [auth, setAuth] = useState<AuthState>('loading');

  // 页面加载时校验本地 token 是否有效
  useEffect(() => {
    if (!getToken()) {
      setAuth('unauthed');
      return;
    }
    let cancelled = false;
    fetchMe()
      .then(() => !cancelled && setAuth('authed'))
      .catch(() => {
        clearSession();
        if (!cancelled) setAuth('unauthed');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (auth === 'loading') {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-400">
        正在加载…
      </div>
    );
  }

  if (auth === 'unauthed' || route === '/login') {
    return <LoginPage onSuccess={() => { setAuth('authed'); window.location.hash = '#/bindings'; }} />;
  }

  return (
    <div className="min-h-screen">
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-slate-100 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1760px] items-center justify-between px-5">
          <a href="#/bindings" className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#66CDB5] text-white">
              <Headset className="h-5 w-5" strokeWidth={2.5} aria-hidden="true" />
            </div>
            <span className="text-lg font-bold tracking-tight text-slate-800">
              企业微信客服
              <span className="ml-1 font-medium text-slate-400">· 管理后台</span>
            </span>
          </a>

          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map(({path, label, icon: Icon}) => {
              const active = route === path;
              return (
                <a
                  key={path}
                  href={`#${path}`}
                  className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3.5 text-sm font-semibold transition-all ${
                    active
                      ? 'bg-teal-50 text-teal-700 ring-1 ring-teal-200/70'
                      : 'text-slate-500 hover:bg-slate-50 hover:text-slate-700'
                  }`}
                >
                  <Icon size={15} aria-hidden="true" />
                  {label}
                </a>
              );
            })}
            <div className="mx-2 h-5 w-px bg-slate-200" aria-hidden="true" />
            <span className="text-sm font-medium text-slate-500">{getUsername() || 'admin'}</span>
            <button
              type="button"
              onClick={() => {
                clearSession();
                window.location.hash = '#/login';
              }}
              className="ml-1 inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-slate-500 transition-all hover:bg-red-50 hover:text-red-600"
              title="退出登录"
            >
              <LogOut size={15} aria-hidden="true" />
              退出
            </button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-[1760px] px-5 pt-24 pb-12">
        {route === '/stages' ? <StagesPage /> : <BindingsPage />}
      </main>
    </div>
  );
}
