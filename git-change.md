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
