/** 后端统一响应：{code: 0, message, data}；code != 0 视为业务失败。 */
export interface ApiResp<T> {
  code: number;
  message: string;
  data: T;
  /** 部分成功提示（如知识库自动创建失败），code 仍为 0 */
  warning?: string;
}

/** group_bindings 表记录（群绑定关系） */
export interface BindingItem {
  id: number;
  platform: string;
  group_id: string;
  group_name: string;
  company_ids: string;
  workflow_app_id: string;
  open_account_id: string;
  memory_dataset_id: string;
  kb_last_export_id: number;
  status: number;
  created_at: string;
  updated_at: string;
}

/** 新增/编辑群绑定的表单载荷（POST /api/bindings） */
export interface BindingPayload {
  platform: string;
  group_id: string;
  group_name: string;
  company_ids: string;
  workflow_app_id: string;
  open_account_id: string;
  memory_dataset_id: string;
}

/** session_stage 表记录（会话服务阶段） */
export interface StageRow {
  session_id: string;
  stage: number;
  updated_at: string;
}

/** GET /api/messages/stages 分页结果 */
export interface StagePage {
  total: number;
  items: StageRow[];
  limit: number;
  offset: number;
}

/** workflow_apps 表记录（Dify 工作流应用注册表） */
export interface WorkflowApp {
  id: number;
  app_id: string;
  name: string;
  api_key: string;
  created_at: string;
  updated_at: string;
}

export const STAGE_LABELS: Record<number, string> = {
  0: '未开始',
  1: '初次触达',
  2: '转化签约',
  3: '签约后交付',
  4: '长期服务',
};

export const STAGE_OPTIONS = [0, 1, 2, 3, 4] as const;

export const PLATFORM_OPTIONS = [
  {value: 'wecom', label: '企业微信'},
  {value: 'feishu', label: '飞书'},
  {value: 'dingtalk', label: '钉钉'},
] as const;

/** UTC ISO 时间 → 北京时间（YYYY-MM-DD HH:MM），解析失败原样返回 */
export function formatBeijing(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const bj = new Date(d.getTime() + 8 * 3600 * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${bj.getUTCFullYear()}-${pad(bj.getUTCMonth() + 1)}-${pad(bj.getUTCDate())} ${pad(bj.getUTCHours())}:${pad(bj.getUTCMinutes())}`;
}

/** session_id 形如 "1:群备注名"，去掉 roomType 前缀展示群名 */
export function sessionChatId(sessionId: string): string {
  const idx = sessionId.indexOf(':');
  return idx >= 0 ? sessionId.slice(idx + 1) : sessionId;
}
