# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 新增 FastAPI 回调接口，接收 WorkTool 消息推送
- 新增异步消息处理机制，避免阻塞回调响应
- 新增 WorkToolClient 异步客户端，支持发送消息和回调配置管理
- 新增 MessageHandler 处理器抽象，支持 Echo/Silent 两种默认处理器
- 新增 Pydantic 数据模型，规范回调请求和API交互
- 新增配置管理，支持环境变量
- 新增 EchoHandler 增加 atMe 判断，仅当消息@机器人时才回复
