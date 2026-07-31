# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 修复 日志重复问题（propagate=False + 仅项目模块挂 handler）
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
