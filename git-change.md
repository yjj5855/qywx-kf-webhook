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
