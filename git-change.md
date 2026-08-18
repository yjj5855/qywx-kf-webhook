# 变更记录

> 下次发布后清空此文件

## [开发中]

### 回调服务
- 调整 主工作流调用失败时不再给客户发送"服务暂时不可用"兜底文案，只记日志（避免与超时后迟到的真实回复重复）
- 重构 消息处理返回 HandleResult，区分 webhook 回复、工作流内部已发送、不回复三种情况（上版本已入，保留记录）

### 知识库导出
- 修复 create_by_text 在新版 Dify 返回 400 invalid_param：payload 补充 indexing_technique（与数据集索引方式一致）
- 改进 kb.py / init_datasets.py 的 HTTP 报错携带 Dify 响应体（code/message），便于定位 4xx/5xx 根因
- 修复 导出周期内超 20 轮对话导致知识库丢记录：append 不再裁剪，改为导出成功推进游标后只删"已导出且超出保留上限"的旧行（memory.trim_exported），未导出轮次永不删除
- 修复 群备注与群名不一致导致导不出：chat_memory 新增 group_name 列，handler 写入真实群名，exporter 按群匹配（group_name 列 + session_id 前缀双通道兼容旧行）
- 调整 知识库同步由 300s 轮询改为每日定点同步（北京时间 WT_DIFY_EXPORT_TIME 默认 01:00，空串=关闭），新增手动全量同步接口 POST /api/messages/sync

### 对话记忆（消息流水模型）
- chat_memory 由"问答对"结构改为"消息流水"：一行一条消息（role=user/bot + sender_name + content），每条群消息全量记录（含未@闲聊），机器人回复单独记 bot 行，多人穿插按时间顺序完整保留，不再强制一问一答
- 旧库启动时自动迁移：问答对逐行拆分为 user+bot 两条消息，保持先问后答顺序
- recentContext 改为最近 12 条消息（≈6 轮）的多人群聊转写；MAX_TURNS 调整为 40 条（≈20 轮）
- 知识库文档导出格式同步改为时间顺序群聊转写（角色标注），不再伪造一问一答
- /api/messages/record 支持单条消息写入（content+role），兼容旧问答对写法（拆两条写入）
