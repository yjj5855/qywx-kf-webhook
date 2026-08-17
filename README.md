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
| `WT_DIFY_BASE_URL` | Dify 服务地址 | — |
| `WT_DIFY_WORKFLOW_KEY` | 主工作流 API Key | — |
| `WT_DIFY_TIMEOUT` | 工作流调用超时（秒） | `30` |
| `WT_DIFY_DB_PATH` | SQLite 存储路径 | `./data/app.db` |
| `WT_COMPANY_API_BASE_URL` | 公司数据网关地址 | — |
| `WT_COMPANY_API_KEY` | 公司数据网关密钥 | — |
| `WT_DIFY_DATASET_KEY` | 知识库（数据集）权限 Key | — |
| `WT_DIFY_EXPORT_INTERVAL` | 知识库增量导出间隔（秒），0=关闭 | `300` |
| `WT_DIFY_DATASET_INDEXING` | 知识库索引方式：`economy`（关键词）/ `high_quality`（向量，需 Embedding 模型） | `economy` |

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
| POST | `/api/messages/export` | 导出群对话到知识库 |

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
