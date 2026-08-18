# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 兼容新版 Dify 响应结构，结束节点输出在 data.outputs 而非顶层 result
- 重构 消息处理返回 HandleResult，区分 webhook 回复、工作流内部已发送、不回复三种情况
- 新增 _extract_reply_text 解包工作流返回的 JSON 字符串回复
- 优化 项目日志模块名补充 src. 前缀，确保以 python -m src.main 运行时 app.log 完整

### 客服工作流
- 调整 key-value 节点类型 raw-text 改为 text
- 兼容新版 Dify 输出字段解析（优先 data.outputs，回退顶层 result）

### 知识库绑定
- 新增 init_kb_bindings 脚本，从客户群 CSV 回填群专属知识库 dataset id 与公司 ID
- 新增 sync_kb_ids_to_csv 脚本，把数据库 memory_dataset_id 与工作流 AppID 回填到 CSV
- 更新 客户群列表 CSV 新增知识库ID 与 工作流AppID 列

### 配置管理
- 新增 APP_ENV 环境变量按需加载 .env.dev / .env.prod，默认 dev，指定文件不存在时回退 .env
- 新增 .gitignore 忽略 .env.*，避免环境密钥被提交
- 更新 客服执行文档 §11 配置项说明

### HTTP 客户端
- 修复 本机 socks 代理导致 httpx 缺 socksio 报错，所有客户端加 trust_env=False 直连内部服务
- 涉及 client.py / company.py / dify_client.py / kb.py / init_datasets.py / init_kb_bindings.py

### 知识库初始化
- 调整 新建知识库 permission 从 only_me 改为 all_team_members，团队所有成员可见

### 文档
- 新增 README.md，涵盖启动方式、配置项、API 接口与运维脚本说明

### 版本控制
- 调整 .gitignore 忽略 .DS_Store，并例外跟踪 data/app-prod.db
- 新增 data/app-prod.db 生产群绑定数据库纳入版本控制

### 公司信息查询
- 删除 src/company.py 应用层公司接口调用模块
- 删除 config.py 中 company_api_base_url / company_api_key 配置
- 新增 handler 按群名反查绑定 company_ids，作为 companyIds 传入主工作流
- 调整 客服工作流 start 节点新增 companyIds 输入变量

### 会话管理
- 删除 src/session_store.py 会话 ID 存储模块
- 调整 handler 不再持久化 qaConversationId，会话由工作流侧自行管理
- 更新 main.py / init_bindings.py / api_bindings.py / dify_client.py 移除相关引用与注释
