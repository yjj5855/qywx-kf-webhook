# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
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
