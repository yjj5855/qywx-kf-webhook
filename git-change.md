# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 新增 intent 模块，支持 OpenAI 兼容接口的意图识别
- 新增 IntentRecognizer 使用 AsyncOpenAI 库简化调用
- 新增 ConversationMemory 按 session_id 维护多轮对话历史
- 新增 IntentHandler 根据意图路由到对应 Action
- 新增 InviteToGroupAction 处理拉人入群意图
- 新增 session_id 属性，按群/人唯一标识会话
- 新增 intent_base_url、intent_api_key、intent_model 配置项
- 优化日志输出改为 session_id 标识
- 新增 openai 依赖
