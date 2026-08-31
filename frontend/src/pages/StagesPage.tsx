import {Layers, Plus, RefreshCw, Search} from 'lucide-react';
import {useEffect, useState} from 'react';
import {fetchStages, setStage} from '../api';
import type {StageRow} from '../types';
import {formatBeijing, sessionChatId, STAGE_LABELS, STAGE_OPTIONS} from '../types';

const STAGE_BADGE: Record<number, string> = {
  0: 'bg-slate-100 text-slate-500',
  1: 'bg-sky-50 text-sky-700',
  2: 'bg-amber-50 text-amber-700',
  3: 'bg-violet-50 text-violet-700',
  4: 'bg-teal-50 text-teal-700',
};

export default function StagesPage() {
  const [items, setItems] = useState<StageRow[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState('');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 新增/设置阶段表单
  const [newSession, setNewSession] = useState('');
  const [newStage, setNewStage] = useState<number>(1);
  const [newSaving, setNewSaving] = useState(false);
  const [newError, setNewError] = useState('');

  async function load(q = query) {
    setLoading(true);
    setError('');
    try {
      const page = await fetchStages({sessionId: q, limit: 500});
      setItems(page.items);
      setTotal(page.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleChangeStage(row: StageRow, stage: number) {
    try {
      await setStage(row.session_id, stage);
      setItems((prev) => prev.map((r) => (r.session_id === row.session_id ? {...r, stage} : r)));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '设置失败');
    }
  }

  async function handleAddStage() {
    if (!newSession.trim()) {
      setNewError('请输入会话ID（session_id）');
      return;
    }
    setNewSaving(true);
    setNewError('');
    try {
      await setStage(newSession.trim(), newStage);
      setNewSession('');
      await load();
    } catch (err) {
      setNewError(err instanceof Error ? err.message : '设置失败');
    } finally {
      setNewSaving(false);
    }
  }

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    setQuery(keyword.trim());
    void load(keyword.trim());
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-slate-800">
            <Layers className="h-5 w-5 text-[#66CDB5]" aria-hidden="true" />
            会话服务阶段管理
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            共 {total} 个会话 · session_stage 表 · 0未开始 / 1初次触达 / 2转化签约 / 3签约后交付 / 4长期服务
          </p>
        </div>
        <div className="flex items-center gap-2">
          <form onSubmit={submitSearch} className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-300" aria-hidden="true" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="按 会话ID / 群名 搜索…"
              className="w-64 rounded-lg border border-slate-200 bg-white py-2 pr-3 pl-9 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-300 focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            />
          </form>
          <button
            type="button"
            onClick={() => {
              setKeyword('');
              setQuery('');
              void load('');
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
          >
            <RefreshCw size={15} aria-hidden="true" />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      {/* 新增/设置阶段 */}
      <div className="mb-5 rounded-xl border border-teal-100 bg-teal-50/50 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-64 flex-1">
            <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="new-session">
              会话ID（格式 roomType:chat_id，如 1:测试二群）
            </label>
            <input
              id="new-session"
              type="text"
              value={newSession}
              onChange={(e) => setNewSession(e.target.value)}
              placeholder="1:群备注名 或 2:联系人"
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="new-stage">阶段</label>
            <select
              id="new-stage"
              value={newStage}
              onChange={(e) => setNewStage(Number(e.target.value))}
              className="w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            >
              {STAGE_OPTIONS.map((s) => (
                <option key={s} value={s}>{s} · {STAGE_LABELS[s]}</option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={() => void handleAddStage()}
            disabled={newSaving}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#66CDB5] px-4 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#5cc2a9] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Plus size={15} aria-hidden="true" />
            {newSaving ? '保存中…' : '设置阶段'}
          </button>
        </div>
        {newError && (
          <p className="mt-2 text-sm text-red-600" role="alert">{newError}</p>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1000px] table-fixed text-left text-sm">
            <colgroup>
              <col className="w-[340px]" />
              <col className="w-auto" />
              <col className="w-[140px]" />
              <col className="w-[170px]" />
              <col className="w-[160px]" />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/70 text-xs text-slate-500">
                <th className="px-4 py-3 font-semibold">会话ID（session_id）</th>
                <th className="px-4 py-3 font-semibold">群名</th>
                <th className="px-4 py-3 font-semibold">当前阶段</th>
                <th className="px-4 py-3 font-semibold">阶段调整</th>
                <th className="px-4 py-3 font-semibold">更新时间（北京时间）</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">加载中…</td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                    {query ? '没有匹配的会话阶段' : '暂无会话阶段记录，可在上方输入会话ID设置'}
                  </td>
                </tr>
              ) : (
                items.map((row) => (
                  <tr key={row.session_id} className="border-b border-slate-50 transition-colors last:border-0 hover:bg-teal-50/30">
                    <td className="truncate px-4 py-3 font-mono text-xs text-slate-700" title={row.session_id}>{row.session_id}</td>
                    <td className="truncate px-4 py-3 font-medium text-slate-800" title={sessionChatId(row.session_id)}>{sessionChatId(row.session_id)}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ${STAGE_BADGE[row.stage] ?? STAGE_BADGE[0]}`}>
                        {row.stage} · {STAGE_LABELS[row.stage] ?? row.stage}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={row.stage}
                        onChange={(e) => void handleChangeStage(row, Number(e.target.value))}
                        className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
                        title="修改该会话的阶段"
                      >
                        {STAGE_OPTIONS.map((s) => (
                          <option key={s} value={s}>{s} · {STAGE_LABELS[s]}</option>
                        ))}
                      </select>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{formatBeijing(row.updated_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
