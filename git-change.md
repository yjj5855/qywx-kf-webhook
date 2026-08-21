# 变更记录

> 下次发布后清空此文件

## [开发中]

### 客服主流程（意图提示词）
- 调整 意图识别与门控提示词中硬编码的操作、咨询、公司查询描述改为引用环境变量（WT_INTENT_WORKTOOL_DESC / WT_INTENT_QA_DESC / WT_COMPANY_OP_DESC）
- 新增 公司 API 支持操作范围说明，明确客服咨询走 QA 检索、WorkTool 操作不属本助理范围

### 知识库设置批量更新（换 Embedding 模型 / 开自动摘要）
- 新增 src/update_kb_settings.py：Dify 知识库在创建时固化当时的 Embedding 模型，改系统默认模型不影响已有库；脚本通过控制台 API 逐库 PATCH 更新 embedding_model/embedding_model_provider（触发 Dify 后台自动重嵌入）并写入 summary_index_setting（enable + 摘要 LLM + 自定义提示词，默认"描述解决的问题,以中文生成,去除 think 内容"），重嵌入完成后自动调用 generate-summary 给已有文档补生成摘要
- 认证支持 --cookie（浏览器会话）或 --email/--password（控制台登录）；--dry-run 预览；--only-embedding / --only-summary 单独执行；--dataset-ids 追加群绑定表外的知识库（如制度库）
- dry-run 改为服务端 API 读取当前配置（embedding 模型 / 索引方式 / 摘要设置），无需控制台会话即可预览现状
- 新增 --skip-summary-trigger：先批量 PATCH 全部知识库配置（换模型+摘要设置），等重嵌入完成后再用 --only-summary 统一触发摘要生成，避免逐库等待
- 摘要默认提示词改为"用中文描述这段内容解决的问题，要求简洁、一两句话概括，不要使用编号列表或要点，不要输出思考过程、推理内容或 think 标签"（适配 qwen3.7-plus 摘要模型，避免编号要点式冗长输出）
- README 增加"更换知识库 Embedding 模型 / 开启自动摘要（批量）"一节

### 群公司档案（客服手写公司描述 → 群知识库）
- 新增 src/company_profile.py：构建「群-公司档案」文本（群信息 + 每公司一块，块首为完整自然语言句，适配向量索引 high_quality / semantic_search）并同步进群知识库（文档名固定 `群档案_{group_id}`，先删同名旧文档再重建，幂等；档案文件被清空 = 从知识库移除）
- 新增 src/sync_company_profiles.py：`--init` 为已绑定公司ID且缺档案的群生成模板（公司名从群名启发式预填）；默认同步已有档案文件到群知识库；`--force` 覆盖模板 / `--dry-run` 预览 / `--prune` 清理档案文件已删除的残留文档
- 新增配置 WT_COMPANY_PROFILE_DIR（默认 docs/公司档案，客服按 `{group_id}.md` 维护描述）
- POST /api/bindings 绑定变更后自动尝试同步该群档案（缺档案/未绑定知识库则跳过，异步不阻塞接口）
- 新增 docs/公司档案写作规范.md：对客服的档案写作要求（块首完整句、全称/简称/别名、每块 100~300 字、块间空行、多公司编号固定、敏感信息不写、自查清单、好/坏示例）
- 修复 模板首行一级标题被 Dify 剥掉：Dify 解析文档时会去掉行首单个 "# " 标记（"##"/"###" 不受影响），模板改为普通段落开场（文档名本身即标题），写作规范同步更新（src/company_profile.py、docs/公司档案写作规范.md）
- 修复 create_by_text 响应取不到 id：部分 Dify 版本返回 {"document": {...}}，kb.py 归一化为文档对象，调用方统一从顶层取 id
- 修复 DELETE 文档成功但返回空 body 时误报 JSONDecodeError：company_profile.delete_document 容忍空响应体（HTTP 200 即成功）

### 对话记忆
- 修复 recentContext 包含当前消息：当前消息已由 spoken 单独传给主工作流，不应再出现在历史上下文里；memory.to_context 新增 exclude_latest 参数（多取一条再丢弃最新，历史仍保留最多 12 条），handler._build_inputs 构建 recentContext 时启用（src/memory.py、src/handler.py）

### 知识库检索修复
- 修复 QA 子工作流检索知识库报 400（Dify ≥ 1.14 对 POST /v1/datasets/{id}/retrieve 的 retrieval_model 做 pydantic 校验，reranking_enable / top_k / score_threshold_enabled / search_method 为必填）：子工作流-QA问答.yml 的「检索制度知识库」「检索群记忆知识库」两个 HTTP 节点请求体补充 reranking_enable=false 与 score_threshold_enabled=true（true 时 score_threshold=0.3 才生效）；需在 Dify 控制台同步更新这两个节点或重新导入该 yml
- 修复 检索返回空结果：知识库「服务知识库」(429c5dd2) 为 high_quality（向量）索引，keyword_search 在该库上永远命中不到（实测「退休」「男性」「女 1977-07 什么时候退休」均返回空 records，semantic_search 正常返回分数 0.55+ 的记录）；两个 HTTP 节点检索方式由 keyword_search 改为 semantic_search（阈值 0.3 语义检索可正常过滤）；注意若某知识库为 economy（关键词）索引则 semantic_search 会报错，需按库的索引方式选择检索方式

### 语雀外部知识库胶水服务
- 新增 POST /retrieval（src/api_yuque.py）：Dify「连接外部知识库」适配端点，按 Dify 外部知识库 API 规范实现（Authorization: Bearer 鉴权、records 返回 content/score/title/metadata），实现语雀检索（GET /api/v2/search，type=doc）→ 拉取文档 Markdown 正文（搜索自带 body 或二次调详情接口，asyncio 并发）→ 组装 Dify 响应
- 新增配置：WT_YUQUE_TOKEN（语雀团队令牌）、WT_YUQUE_EXTERNAL_KEY（Dify 端 API Key）、WT_YUQUE_API_BASE（支持企业版域名）、WT_YUQUE_SCOPE（默认搜索范围）、WT_YUQUE_KB_SCOPES（外部知识库 ID → 语雀知识库范围映射，JSON）
- score 按搜索排名估算（第 1 名 0.95 逐名递减 0.1），支持 Dify 的 score_threshold 过滤；metadata 恒为对象避免 Dify 报错
- 文档更新：README 增加配置项、API 表与 Dify 接入步骤

### 回调服务
- 调整 主工作流调用失败时不再给客户发送"服务暂时不可用"兜底文案，只记日志（避免与超时后迟到的真实回复重复）
- 新增 回调防抖（src/debouncer.py）：同一会话窗口内（WT_DEBOUNCE_SECONDS 默认 1 秒）多条消息合并为一次工作流调用、只处理最新一条；处理期间到达的消息串行排队不并发；所有消息先在回调层全量入库（用户消息记录从 handler 移到 main.py），知识库/上下文不丢
- 修复 图片消息（textType=2，spoken 为空）触发主工作流 start.spoken 必填校验失败：_build_inputs 传 "[图片]" 占位（rawSpoken 同步兜底）
- 重构 消息处理返回 HandleResult，区分 webhook 回复、工作流内部已发送、不回复三种情况（上版本已入，保留记录）

### 知识库导出
- 修复 create_by_text 在新版 Dify 返回 400 invalid_param：payload 补充 indexing_technique（与数据集索引方式一致）
- 改进 kb.py / init_datasets.py 的 HTTP 报错携带 Dify 响应体（code/message），便于定位 4xx/5xx 根因
- 修复 导出周期内超 20 轮对话导致知识库丢记录：append 不再裁剪，改为导出成功推进游标后只删"已导出且超出保留上限"的旧行（memory.trim_exported），未导出轮次永不删除
- 修复 群备注与群名不一致导致导不出：chat_memory 新增 group_name 列，handler 写入真实群名，exporter 按群匹配（group_name 列 + session_id 前缀双通道兼容旧行）
- 调整 知识库同步由 300s 轮询改为每日定点同步（北京时间 WT_DIFY_EXPORT_TIME 默认 23:30，使文档名日期与当天聊天一致；空串=关闭），新增手动全量同步接口 POST /api/messages/sync
- 调整 知识库文档命名带北京时间日期（群对话_{群名}_{YYYYMMDD}），避免同名文档堆积混淆（仍为追加模式，每次同步新建增量文档）

### QA 双知识库检索（静态制度库 + 动态群记忆库）
- handler._build_inputs 新增 datasetId（按群名反查 group_bindings.memory_dataset_id，非群聊/未绑定为空），供主流程透传 QA 子工作流
- QA 子工作流（子工作流-QA问答.yml）接入知识检索：新增环境变量 DIFY_BASE_URL / DIFY_DATASET_KEY / DIFY_STATIC_KB_ID（制度库 ID）；并行检索静态制度库与动态群记忆库（/v1/datasets/{id}/retrieve，keyword_search top_k=4 threshold=0.3）；code_merge 合并为【制度资料】+【群聊记录】；LLM system prompt 增加参考资料使用规则（制度库为权威依据、群聊记录仅作背景）；未绑定群记忆库时跳过动态检索
- 新增 检索前置守卫（先判断再调用）：code_check_config 检查 DIFY_BASE_URL / DIFY_DATASET_KEY / DIFY_STATIC_KB_ID / datasetId，if_static_ok / if_dynamic_ok 分别拦截未配置的检索分支（不再构造 /datasets//retrieve 非法请求），未命中分支由 code_no_static / code_no_dynamic 输出空 body 供合并节点兼容
- 修正 子工作流-QA问答 app.description 为真实逻辑（原误用 WORKTOOL_OP 的描述）
- 注：主流程 start 新增 datasetId 输入与 QA tool 节点透传由用户在 Dify 控制台配置

### 对话记忆（消息流水模型）
- chat_memory 由"问答对"结构改为"消息流水"：一行一条消息（role=user/bot + sender_name + content），每条群消息全量记录（含未@闲聊），机器人回复单独记 bot 行，多人穿插按时间顺序完整保留，不再强制一问一答
- 旧库启动时自动迁移：问答对逐行拆分为 user+bot 两条消息，保持先问后答顺序
- recentContext 改为最近 12 条消息（≈6 轮）的多人群聊转写；MAX_TURNS 调整为 40 条（≈20 轮）
- 知识库文档导出格式同步改为时间顺序群聊转写（角色标注），不再伪造一问一答
- /api/messages/record 支持单条消息写入（content+role），兼容旧问答对写法（拆两条写入）

### 版本控制
- 停止跟踪 data/app-prod.db（生产数据库不再入库，.gitignore 忽略 data/*，本地文件保留）
