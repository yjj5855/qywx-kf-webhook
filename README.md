# qywx-kf-webhook

企业微信（WorkTool）客服消息回调服务。接收 WorkTool 推送的群聊/私聊消息，转发到 Dify 工作流做意图识别与客服问答，并维护群与公司的绑定关系、多轮对话记忆，以及把群聊天记录导出到 Dify 知识库。

## 技术栈

- Python 3.11
- FastAPI + uvicorn
- SQLite（本地存储）
- httpx + pydantic-settings
- Dify（工作流 / 知识库）

## 目录结构

```
src/
  main.py              # FastAPI 入口（/callback、/health）
  config.py            # 配置加载（WT_* 前缀，按 APP_ENV 选 .env 文件）
  handler.py           # 消息处理器（Dify 主工作流 + Echo 兜底）
  dify_client.py       # Dify 工作流客户端
  client.py            # WorkTool API 客户端（发送消息）
  binding.py           # 群绑定存储（群 ↔ 公司ID / 知识库 / 工作流）
  memory.py            # 对话记忆存储
  session_store.py     # 会话 ID 存储
  company.py           # 公司信息查询
  kb.py                # 知识库文档写入
  exporter.py          # 知识库增量导出定时任务
  models.py            # 数据模型
  api_bindings.py      # 群绑定管理接口
  api_memory.py        # 对话记忆 / 知识库导出接口
  api_yuque.py         # 语雀外部知识库检索接口（Dify 外部知识库胶水服务）
  init_bindings.py     # 从 CSV 初始化群绑定
  init_kb_bindings.py  # 回填群知识库 dataset id
  init_datasets.py     # 批量创建群专属知识库
  sync_kb_ids_to_csv.py# 把知识库/工作流 ID 回填到 CSV
dify/                 # Dify 工作流 YAML
docs/                 # 文档、客户群 CSV、执行文档
data/                 # SQLite 数据库（gitignore）
logs/                 # 运行日志（gitignore）
```

## 快速开始

### 1. 安装依赖

```bash
cd qywx-kf-webhook
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 配置环境

环境配置按 `APP_ENV` 环境变量选择对应的 `.env.{APP_ENV}` 文件（默认 `dev`，指定文件不存在时回退 `.env`）：

| 文件 | 用途 |
|------|------|
| `.env.dev` | 开发环境配置 |
| `.env.prod` | 生产环境配置 |

```bash
cp .env.dev .env.prod   # 复制一份并填入生产环境的值
```

### 3. 初始化数据库

首次运行前，从客户群 CSV 初始化群绑定关系：

```bash
python -m src.init_bindings docs/客户群列表_去重_公司ID回填.csv
```

### 4. 启动服务

**开发环境**

```bash
python -m src.main
```

**生产环境**

```bash
APP_ENV=prod python -m src.main
```

**后台常驻运行（生产）**

```bash
APP_ENV=prod nohup .venv/bin/python -m src.main > logs/prod.log 2>&1 &
```

**健康检查**

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 配置项

所有配置以 `WT_` 为前缀，写在 `.env.dev` / `.env.prod` 中：

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `WT_HOST` | 监听地址 | `0.0.0.0` |
| `WT_PORT` | 监听端口 | `8000` |
| `WT_API_BASE_URL` | WorkTool API 地址 | `https://api.worktool.ymdyes.cn` |
| `WT_DEBOUNCE_SECONDS` | 回调防抖窗口（秒）：同一会话窗口内多条消息合并为一次工作流调用，全部消息仍入库 | `1.0` |
| `WT_DIFY_BASE_URL` | Dify 服务地址 | — |
| `WT_DIFY_WORKFLOW_KEY` | 主工作流 API Key | — |
| `WT_DIFY_TIMEOUT` | 工作流调用超时（秒） | `30` |
| `WT_DIFY_DB_PATH` | SQLite 存储路径 | `./data/app.db` |
| `WT_COMPANY_API_BASE_URL` | 公司数据网关地址 | — |
| `WT_COMPANY_API_KEY` | 公司数据网关密钥 | — |
| `WT_DIFY_DATASET_KEY` | 知识库（数据集）权限 Key | — |
| `WT_DIFY_EXPORT_TIME` | 知识库每日同步时间（北京时间 HH:MM，如 23:30 使文档名日期=当天聊天日期），空串=关闭定时同步（仅手动） | `23:30` |
| `WT_DIFY_DATASET_INDEXING` | 知识库索引方式：`economy`（关键词）/ `high_quality`（向量，需 Embedding 模型） | `economy` |
| `WT_YUQUE_TOKEN` | 语雀团队令牌（[获取地址](https://www.yuque.com/settings/tokens)），语雀外部知识库检索用 | — |
| `WT_YUQUE_EXTERNAL_KEY` | Dify「连接外部知识库」时填写的 API Key，本服务 `/retrieval` 鉴权用 | — |
| `WT_YUQUE_API_BASE` | 语雀开放 API 基础地址（企业版改成 `https://{企业域名}.yuque.com/api/v2`） | `https://www.yuque.com/api/v2` |
| `WT_YUQUE_SCOPE` | 默认搜索范围，形如 `团队login/知识库slug`（如 `myteam/mywiki`）；留空=搜索全部可见内容 | — |
| `WT_YUQUE_KB_SCOPES` | 外部知识库 ID → 语雀搜索范围映射（JSON），如 `{"yuque-wiki": "myteam/mywiki"}`；未匹配回退 `WT_YUQUE_SCOPE` | `{}` |

> 环境选择变量 `APP_ENV` 不带 `WT_` 前缀，只用于决定加载哪个 `.env` 文件，不是业务配置项。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/callback?robotId=xxx` | 接收 WorkTool 消息回调 |
| GET | `/health` | 健康检查 |
| GET | `/api/bindings` | 列出全部群绑定 |
| GET | `/api/bindings/query` | 查询单个绑定（`platform`、`group_id`） |
| POST | `/api/bindings` | 新增/更新绑定 |
| DELETE | `/api/bindings` | 删除绑定（软删除） |
| POST | `/api/messages/record` | 记录对话记忆 |
| GET | `/api/messages/history` | 查询对话历史（`session_id`） |
| POST | `/api/messages/export` | 导出单个群对话到知识库（`session_id` + `since_id` 增量） |
| POST | `/api/messages/sync` | 手动全量同步所有绑定知识库的群（与每日定时同步同逻辑） |
| POST | `/retrieval` | 语雀外部知识库检索（Dify「连接外部知识库」适配端点） |

### 语雀外部知识库接入 Dify

1. 在 `.env` 配置 `WT_YUQUE_TOKEN`（语雀团队令牌，[获取地址](https://www.yuque.com/settings/tokens)）和 `WT_YUQUE_EXTERNAL_KEY`（自定义强密码）；如需限定搜索范围，配置 `WT_YUQUE_SCOPE` 或 `WT_YUQUE_KB_SCOPES`。
2. 重启服务后，进入 **Dify 后台 > 知识库 > 连接外部知识库**：
   - **API 端点**：填 `http://<本服务地址>:8000/retrieval`（新版本 Dify 会自动在填写的地址后追加 `/retrieval`，两者皆可）；
   - **API Key**：填 `WT_YUQUE_EXTERNAL_KEY` 的值；
   - **外部知识库 ID**：填一个自定义 ID（如 `yuque-wiki`），若配置了 `WT_YUQUE_KB_SCOPES` 映射，该 ID 会决定检索哪个语雀知识库。
3. 在应用内选择该外部知识库即可检索语雀文档（返回内容为 Markdown 正文）。

> 说明：语雀搜索不返回相关性分数，`score` 按排名估算（第 1 名 0.95，逐名递减 0.1），Dify 侧可据此做阈值过滤与排序；语雀 API 有频率限制，每次检索会按 `top_k` 并发拉取正文（每文档一次详情请求，搜索结果自带正文时不再请求）。

### 回调测试示例

```bash
curl -s -X POST "http://localhost:8000/callback?robotId=wtgxpt9udc4pb4hgj0rnn139gfwcc6ls" \
  -H "Content-Type: application/json" \
  -d '{
    "groupName": "测试二群",
    "atMe": "false",
    "spoken": "拉人进群",
    "textType": 1,
    "rawSpoken": "拉人进群",
    "receivedName": "杨佳军",
    "roomType": 1
  }'
```

## 运维脚本

| 脚本 | 说明 | 用法 |
|------|------|------|
| `init_bindings.py` | 从 CSV 初始化群绑定 | `python -m src.init_bindings [csv路径]` |
| `init_kb_bindings.py` | 按已有 `群记忆_*` 知识库回填 dataset id | `python -m src.init_kb_bindings [csv路径]` |
| `init_datasets.py` | 批量创建群专属知识库 | `python -m src.init_datasets [--with-company]` |
| `sync_kb_ids_to_csv.py` | 把知识库/工作流 ID 回填到 CSV | `python -m src.sync_kb_ids_to_csv [csv路径]` |

生产环境执行脚本需带 `APP_ENV=prod`：

```bash
APP_ENV=prod python -m src.init_datasets --with-company
```

## 日志

- 应用日志写入 `logs/app.log`（2MB 轮转，保留 5 份）
- uvicorn 访问日志走 stdout，后台运行时建议重定向到 `logs/prod.log`

## 注意事项

- HTTP 客户端均设置 `trust_env=False` 直连内部服务，忽略本机代理环境变量，避免 socks 代理导致 `socksio` 缺失报错。
- `data/`、`logs/`、`.env.*` 均已被 gitignore，不提交密钥与本地数据。
- 知识库使用 `high_quality` 索引前，需在 Dify 控制台配置并设为默认的 Embedding 模型。
