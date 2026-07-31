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
- 新增 私聊场景忽略@判断，全部消息均回复
- 新增 scene 属性描述 room_type 场景描述
- 优化 日志收到消息时增加 scene 场景描述
- 修复 env_file 改为绝对路径避免 CWD 变化导致配置读取失败
- 修复 temperature 硬编码 0.1 导致 kimi-k2.5 返回 400 降级为复读
- 修复 日志配到根 logger 避免子模块错误丢失到 stdout
- 新增 ADD_FRIEND 意图按手机号添加好友
- 新增 CreateGroupAction 建群前先加好友的完整流程
- 新增 WorkToolClient 的 add_friend_by_phone 和 create_group 方法
- 优化 AI 提示词支持多实体提取
- 删除 INVITE_TO_GROUP 统一为 CREATE_GROUP
- 新增 非流式输出显式声明
