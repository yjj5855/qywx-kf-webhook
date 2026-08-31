import type {ApiResp, BindingItem, BindingPayload, StagePage, StageRow, WorkflowApp} from './types';

const TOKEN_KEY = 'qywx_kf_admin_token';
const USERNAME_KEY = 'qywx_kf_admin_username';

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? '';
}

export function getUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? '';
}

export function saveSession(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

/** 401 → 清理会话并跳回登录页 */
function handleUnauthorized(): never {
  clearSession();
  if (window.location.hash !== '#/login') {
    window.location.hash = '#/login';
  }
  throw new Error('登录已过期，请重新登录');
}

async function requestRaw<T>(path: string, options: RequestInit = {}): Promise<ApiResp<T>> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const res = await fetch(path, {...options, headers});
  if (res.status === 401) handleUnauthorized();
  let body: ApiResp<T> | {detail?: string} | null = null;
  try {
    body = (await res.json()) as ApiResp<T> | {detail?: string};
  } catch {
    body = null;
  }
  if (!res.ok) {
    const detail = body && 'detail' in body ? (body as {detail?: string}).detail : undefined;
    throw new Error(detail || `请求失败（HTTP ${res.status}）`);
  }
  const data = body as ApiResp<T> | null;
  if (!data || data.code !== 0) {
    throw new Error(data?.message || '请求失败');
  }
  return data;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return (await requestRaw<T>(path, options)).data;
}

// ---- 认证 ----

export interface LoginResult {
  token: string;
  username: string;
  expires_in: number;
}

export async function login(username: string, password: string): Promise<LoginResult> {
  const data = await request<LoginResult>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({username, password}),
  });
  return data;
}

export async function fetchMe(): Promise<{username: string}> {
  return request<{username: string}>('/api/auth/me');
}

// ---- 群绑定关系 ----

export async function fetchBindings(): Promise<BindingItem[]> {
  return request<BindingItem[]>('/api/bindings');
}

export interface UpsertBindingResult {
  binding: BindingItem;
  /** 部分成功提示（如知识库自动创建失败） */
  warning?: string;
}

export async function upsertBinding(payload: BindingPayload): Promise<UpsertBindingResult> {
  const resp = await requestRaw<BindingItem>('/api/bindings', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  return {binding: resp.data, warning: resp.warning};
}

export async function deleteBinding(platform: string, groupId: string): Promise<void> {
  await request<void>(`/api/bindings?platform=${encodeURIComponent(platform)}&group_id=${encodeURIComponent(groupId)}`, {
    method: 'DELETE',
  });
}

// ---- 会话服务阶段 ----

export async function fetchStages(params: {sessionId?: string; limit?: number} = {}): Promise<StagePage> {
  const query = new URLSearchParams();
  if (params.sessionId) query.set('session_id', params.sessionId);
  if (params.limit) query.set('limit', String(params.limit));
  return request<StagePage>(`/api/messages/stages${query.toString() ? `?${query.toString()}` : ''}`);
}

export async function setStage(sessionId: string, stage: number): Promise<StageRow> {
  return request<StageRow>('/api/messages/stage', {
    method: 'POST',
    body: JSON.stringify({session_id: sessionId, stage}),
  });
}

// ---- 工作流应用（编辑绑定时的下拉选项） ----

export async function fetchWorkflowApps(): Promise<WorkflowApp[]> {
  return request<WorkflowApp[]>('/api/workflows');
}
