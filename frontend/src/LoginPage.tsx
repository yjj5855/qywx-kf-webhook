import {Headset, Loader2, LogIn} from 'lucide-react';
import {FormEvent, useState} from 'react';
import {login, saveSession} from './api';

interface Props {
  onSuccess: () => void;
}

export default function LoginPage({onSuccess}: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('请输入用户名和密码');
      return;
    }
    setError('');
    setLoading(true);
    try {
      const result = await login(username.trim(), password);
      saveSession(result.token, result.username);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-slate-50 via-white to-teal-50 px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#66CDB5] text-white shadow-lg shadow-teal-200">
            <Headset className="h-7 w-7" strokeWidth={2.2} aria-hidden="true" />
          </div>
          <div className="text-center">
            <h1 className="text-xl font-bold tracking-tight text-slate-800">企业微信客服 · 管理后台</h1>
            <p className="mt-1 text-sm text-slate-400">群绑定关系与会话阶段管理</p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
        >
          <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="username">
            用户名
          </label>
          <input
            id="username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="请输入用户名"
            className="mb-4 w-full rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-800 outline-none transition-all placeholder:text-slate-300 focus:border-[#66CDB5] focus:bg-white focus:ring-4 focus:ring-[#66CDB5]/15"
          />

          <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="password">
            密码
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="请输入密码"
            className="mb-5 w-full rounded-lg border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-800 outline-none transition-all placeholder:text-slate-300 focus:border-[#66CDB5] focus:bg-white focus:ring-4 focus:ring-[#66CDB5]/15"
          />

          {error && (
            <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[#66CDB5] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#5cc2a9] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#66CDB5]/30 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <LogIn className="h-4 w-4" aria-hidden="true" />}
            {loading ? '登录中…' : '登 录'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-400">
          凭据在服务端 .env 配置（WT_ADMIN_USERNAME / WT_ADMIN_PASSWORD）
        </p>
      </div>
    </div>
  );
}
