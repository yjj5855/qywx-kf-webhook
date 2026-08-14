# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 修复 _pkg.handlers 非空时跳过 addHandler 导致项目日志未写入 app.log
- 修复 uvicorn 启动时 _project_loggers 只含 __main__ 导致 logger 未挂文件 handler，日志未写入 app.log
- 修复 日志重复输出（uvicorn.run 传 app 替代 "main:app" 避免二次导入，关闭热重载）
- 修复 watchfiles/httpx/uvicorn 刷屏问题（设为 WARNING 级别）
- 优化 AI 调用超时从 10 秒延长到 60 秒
- 修复 SendMessageRequest 丢弃 groupName/selectList/friend 等非定义字段
- 新增 _send_raw 方法绕过 Pydantic 序列化保留原始字段
- 新增 按手机号添加好友和创建外部群 API 文档
- 新增 ADD_MEMBER 意图调用 update_group(type=207) 拉人进已有群
- 新增 update_group 方法支持拉人/踢人/改名/改公告等操作
- 优化 AI 提示词区分 ADD_MEMBER 与 CREATE_GROUP
- 优化 意图识别失败兜底策略改为告知用户而非复读
- 新增 群聊回复门控 GroupReplyGate，AI 预判是否需要回复后再执行意图识别
- 新增 OpenAI 请求体和返回体 debug 日志便于排查 AI 调用问题
- 修复 群聊门控被 at_me 前置检查拦截导致未生效
- 新增 message_id 消息去重，防止 WorkTool 重复推送
- 优化 intent 模块日志级别改为 DEBUG，确保 OpenAI 调试日志实际输出
- 重构 抽离 IntentMeta 统一意图配置，门控和识别器提示词均动态生成
- 优化 @消息跳过门控直接意图识别，意图识别携带群名和发送者上下文
- 优化 OpenAI 请求体和返回体日志 JSON 格式化输出
- 优化 对话记忆存储实际回复文案替代 AI 原始 JSON，群聊上下文支持区分发言人
- 新增 机器人使用指南文档
- 修复 部分日志文案描述不准确（未触发回复、意图识别失败等）
- 新增 回调接口日志输出完整请求参数
- 新增 图片消息 AI 识别（kimi-k2.5 视觉），图文混合和纯图片均支持
- 新增 图片本地保存并支持外网 URL 替代 base64 内联，减少请求体积

### 项目结构
- 重构 全部源码迁入 src/ 包并统一相对导入，静态目录与日志目录路径适配
- 新增 群绑定、对话记忆、会话存储等 SQLite 存储模块
- 优化 .gitignore 新增忽略 data/ 目录

### 公司信息查询
- 新增 company_info_query 动作的公司接口调用与回复文本生成
- 新增 群与公司绑定关系存储，支持 CSV 导入初始化
- 新增 按客户群列表 CSV 初始化 group_bindings 数据库

### 对话记忆与会话
- 新增 多轮对话记忆存储，按 session 保留最近 N 轮并注入 recentContext
- 新增 分离存储意图识别与客服问答的会话 ID
- 新增 记录机器人最终回复供下轮意图分类注入上下文

### 知识库导出
- 新增 群聊天记录格式化并写入群专属 Dify 知识库
- 新增 知识库增量导出定时任务，随应用生命周期启停
- 新增 为客服群创建专属 Dify 知识库并回填绑定

### API 与工作流
- 新增 群绑定管理接口
- 新增 Dify 工作流调用客户端
- 新增 Dify 工作流 YAML（客服工作流、操作工作流、聊天记录、公司信息查询）

### 文档
- 新增 worktool 客服执行文档、接口说明与客户群列表 CSV

### 意图识别
- 删除 src/intent 整个模块（recognizer/gate/actions/types），意图识别已迁移到 Dify 工作流

### 图片识别
- 删除 src/image_utils.py 图片本地保存与外网 URL 生成逻辑

### WorkTool 客户端
- 删除 好友/群管理方法（加好友/建群/拉人/改群/回调绑定），已迁移到客服操作工作流
- 删除 SendMessageRequest/BindCallbackRequest 等发送与回调配置模型

### 回调服务清理
- 删除 IntentHandler 与 SilentHandler，仅保留 Dify 主工作流处理器并以 Echo 兜底
- 删除 静态文件服务挂载与 intent 模块 DEBUG 日志配置
- 删除 旧意图识别与图片服务配置字段及 openai 依赖

---
