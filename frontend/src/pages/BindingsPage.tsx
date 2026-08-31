import {Plus, Pencil, Search, Users} from 'lucide-react';
import {useEffect, useMemo, useState} from 'react';
import {
  fetchBindings,
  fetchWorkflowApps,
  upsertBinding,
} from '../api';
import Modal from '../components/Modal';
import type {BindingItem, BindingPayload, WorkflowApp} from '../types';
import {formatBeijing, PLATFORM_OPTIONS} from '../types';

const EMPTY_FORM: BindingPayload = {
  platform: 'wecom',
  group_id: '',
  group_name: '',
  company_ids: '',
  workflow_app_id: '',
  open_account_id: '',
  memory_dataset_id: '',
};

export default function BindingsPage() {
  const [bindings, setBindings] = useState<BindingItem[]>([]);
  const [workflowApps, setWorkflowApps] = useState<WorkflowApp[]>([]);
  const [keyword, setKeyword] = useState('');
  const [companyFilter, setCompanyFilter] = useState<'' | 'has' | 'none'>('');
  const [openAccountFilter, setOpenAccountFilter] = useState<'' | 'has' | 'none'>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<BindingItem | null>(null);
  const [form, setForm] = useState<BindingPayload>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function load() {
    setLoading(true);
    setError('');
    try {
      const [b, w] = await Promise.all([fetchBindings(), fetchWorkflowApps().catch(() => [])]);
      setBindings(b);
      setWorkflowApps(w);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return bindings.filter((b) => {
      if (
        kw &&
        ![b.group_id, b.group_name, b.company_ids, b.workflow_app_id, b.open_account_id, b.memory_dataset_id]
          .some((v) => v.toLowerCase().includes(kw))
      ) {
        return false;
      }
      if (companyFilter === 'has' && !(b.company_ids || '').trim()) return false;
      if (companyFilter === 'none' && (b.company_ids || '').trim()) return false;
      if (openAccountFilter === 'has' && !(b.open_account_id || '').trim()) return false;
      if (openAccountFilter === 'none' && (b.open_account_id || '').trim()) return false;
      return true;
    });
  }, [bindings, keyword, companyFilter, openAccountFilter]);

  const workflowAppName = (appId: string): string => {
    if (!appId) return '';
    return workflowApps.find((w) => w.app_id === appId)?.name ?? '';
  };

  const platformLabel = (value: string): string =>
    PLATFORM_OPTIONS.find((p) => p.value === value)?.label ?? value;

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setFormError('');
    setModalOpen(true);
  }

  function openEdit(item: BindingItem) {
    setEditing(item);
    setForm({
      platform: item.platform,
      group_id: item.group_id,
      group_name: item.group_name,
      company_ids: item.company_ids,
      workflow_app_id: item.workflow_app_id,
      open_account_id: item.open_account_id,
      memory_dataset_id: item.memory_dataset_id,
    });
    setFormError('');
    setModalOpen(true);
  }

  async function handleSubmit() {
    if (!form.group_id.trim()) {
      setFormError('群ID（group_id）必填');
      return;
    }
    setSaving(true);
    setFormError('');
    try {
      const result = await upsertBinding({
        ...form,
        group_id: form.group_id.trim(),
        group_name: form.group_name.trim(),
      });
      setModalOpen(false);
      await load();
      if (result.warning) {
        // 绑定已保存成功，仅知识库自动创建失败/未创建，提示用户后续处理
        window.alert(`绑定已保存。${result.warning}`);
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  }

  const set = (key: keyof BindingPayload) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({...f, [key]: e.target.value}));

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-bold text-slate-800">
            <Users className="h-5 w-5 text-[#66CDB5]" aria-hidden="true" />
            群绑定关系管理
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {filtered.length === bindings.length
              ? `共 ${bindings.length} 条绑定 · 群 ↔ 公司ID / 工作流 / 知识库`
              : `筛选出 ${filtered.length} / ${bindings.length} 条绑定`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={companyFilter}
            onChange={(e) => setCompanyFilter(e.target.value as '' | 'has' | 'none')}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-600 outline-none transition-all focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            title="按是否填写公司ID筛选"
          >
            <option value="">公司ID：全部</option>
            <option value="has">公司ID：有</option>
            <option value="none">公司ID：无</option>
          </select>
          <select
            value={openAccountFilter}
            onChange={(e) => setOpenAccountFilter(e.target.value as '' | 'has' | 'none')}
            className="h-9 rounded-lg border border-slate-200 bg-white px-2.5 text-sm text-slate-600 outline-none transition-all focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            title="按是否填写开户ID筛选"
          >
            <option value="">开户ID：全部</option>
            <option value="has">开户ID：有</option>
            <option value="none">开户ID：无</option>
          </select>
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-300" aria-hidden="true" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              placeholder="搜索 群ID / 群名 / 公司ID…"
              className="w-64 rounded-lg border border-slate-200 bg-white py-2 pr-3 pl-9 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-300 focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
            />
          </div>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#66CDB5] px-4 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#5cc2a9] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[#66CDB5]/30"
          >
            <Plus size={16} aria-hidden="true" />
            新增绑定
          </button>
        </div>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-4 py-2.5 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1400px] table-fixed text-left text-sm">
            <colgroup>
              <col className="w-[56px]" />
              <col className="w-[76px]" />
              <col className="w-[110px]" />
              <col className="w-[320px]" />
              <col className="w-[248px]" />
              <col className="w-[230px]" />
              <col className="w-[120px]" />
              <col className="w-[334px]" />
              <col className="w-[128px]" />
              <col className="w-[96px]" />
            </colgroup>
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50/70 text-xs text-slate-500">
                <th className="px-4 py-3 font-semibold">ID</th>
                <th className="px-4 py-3 font-semibold">平台</th>
                <th className="px-4 py-3 font-semibold">群ID</th>
                <th className="px-4 py-3 font-semibold">群名称</th>
                <th className="px-4 py-3 font-semibold">公司ID</th>
                <th className="px-4 py-3 font-semibold">工作流应用</th>
                <th className="px-4 py-3 font-semibold">开户ID</th>
                <th className="px-4 py-3 font-semibold">知识库ID</th>
                <th className="px-4 py-3 font-semibold">更新时间</th>
                <th className="px-4 py-3 text-right font-semibold">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={10} className="px-4 py-10 text-center text-slate-400">加载中…</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={10} className="px-4 py-10 text-center text-slate-400">
                    {keyword ? '没有匹配的绑定' : '暂无绑定关系'}
                  </td>
                </tr>
              ) : (
                filtered.map((b) => (
                  <tr key={b.id} className="border-b border-slate-50 transition-colors last:border-0 hover:bg-teal-50/30">
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">{b.id}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                        {platformLabel(b.platform)}
                      </span>
                    </td>
                    <td className="truncate px-4 py-3 font-mono text-xs text-slate-700">{b.group_id}</td>
                    <td className="truncate px-4 py-3 font-medium text-slate-800" title={b.group_name || undefined}>
                      {b.group_name || <span className="text-slate-300">-</span>}
                    </td>
                    <td className="truncate px-4 py-3" title={b.company_ids || undefined}>
                      <span className="font-mono text-xs text-teal-700">{b.company_ids || '-'}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600">
                      {b.workflow_app_id ? (
                        <span className="block">
                          {workflowAppName(b.workflow_app_id) && (
                            <span className="mr-1 block truncate font-medium text-slate-700" title={workflowAppName(b.workflow_app_id)}>
                              {workflowAppName(b.workflow_app_id)}
                            </span>
                          )}
                          <span className="block truncate font-mono text-slate-400" title={b.workflow_app_id}>{b.workflow_app_id}</span>
                        </span>
                      ) : (
                        <span className="text-slate-300">-</span>
                      )}
                    </td>
                    <td className="truncate px-4 py-3 font-mono text-xs text-slate-600" title={b.open_account_id || undefined}>
                      {b.open_account_id || <span className="text-slate-300">-</span>}
                    </td>
                    <td className="truncate px-4 py-3 font-mono text-xs text-slate-500" title={b.memory_dataset_id}>
                      {b.memory_dataset_id || <span className="text-slate-300">-</span>}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-xs text-slate-400">{formatBeijing(b.updated_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={() => openEdit(b)}
                          className="inline-flex h-8 shrink-0 items-center gap-1 whitespace-nowrap rounded-lg px-2.5 text-xs font-semibold text-slate-600 transition-colors hover:bg-teal-50 hover:text-teal-700"
                        >
                          <Pencil size={13} aria-hidden="true" />
                          编辑
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {modalOpen && (
        <Modal title={editing ? `编辑绑定 · ${editing.group_name || editing.group_id}` : '新增绑定'} onClose={() => setModalOpen(false)} widthClass="max-w-xl">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-platform">平台</label>
              <select
                id="f-platform"
                value={form.platform}
                onChange={set('platform')}
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              >
                {PLATFORM_OPTIONS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-group-id">
                群ID（group_id）<span className="text-red-500">*</span>
              </label>
              <input
                id="f-group-id"
                type="text"
                value={form.group_id}
                onChange={set('group_id')}
                placeholder="如 G0001"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-group-name">群名称</label>
              <input
                id="f-group-name"
                type="text"
                value={form.group_name}
                onChange={set('group_name')}
                placeholder="群名称（回调按群名反查绑定）"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-company-ids">公司ID</label>
              <input
                id="f-company-ids"
                type="text"
                value={form.company_ids}
                onChange={set('company_ids')}
                placeholder="多个用顿号分隔，如 C1001、C1002"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-workflow">工作流应用ID</label>
              <input
                id="f-workflow"
                type="text"
                list="workflow-app-list"
                value={form.workflow_app_id}
                onChange={set('workflow_app_id')}
                placeholder="选择或输入 app_id"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
              <datalist id="workflow-app-list">
                {workflowApps.map((w) => (
                  <option key={w.app_id} value={w.app_id}>{w.name || w.app_id}</option>
                ))}
              </datalist>
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-open-account">开户ID</label>
              <input
                id="f-open-account"
                type="text"
                value={form.open_account_id}
                onChange={set('open_account_id')}
                placeholder="开户信息查询用"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1.5 block text-sm font-medium text-slate-600" htmlFor="f-dataset">知识库ID（memory_dataset_id）</label>
              <input
                id="f-dataset"
                type="text"
                value={form.memory_dataset_id}
                onChange={set('memory_dataset_id')}
                placeholder="留空则保存后自动调用 Dify 创建该群知识库并回填"
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-[#66CDB5] focus:ring-4 focus:ring-[#66CDB5]/15"
              />
              <p className="mt-1.5 text-xs text-slate-400">
                留空时：保存成功后自动调用 Dify 创建知识库「群记忆_{'{'}group_id{'}'}」并回填本字段；创建失败不影响绑定保存（会弹出提示）。
              </p>
            </div>
          </div>

          {formError && (
            <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600" role="alert">
              {formError}
            </p>
          )}

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setModalOpen(false)}
              className="inline-flex h-9 items-center rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-50"
            >
              取消
            </button>
            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={saving}
              className="inline-flex h-9 items-center rounded-lg bg-[#66CDB5] px-5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-[#5cc2a9] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? '保存中…' : '保存'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
