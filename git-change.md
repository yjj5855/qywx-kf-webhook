# 变更记录

> 下次发布后清空此文件

## [开发中]

### 会话阶段改为开户客服流程六阶段模型（0~6），推进由客服在管理后台操作（线上已发布）
- Dify「开户办理-主流程」重构为六阶段对话模型并发布：0未开始 1签约阶段 2企业注册阶段 3银行开户阶段 4服务准备阶段 5服务启动阶段 6首月服务结算（参考 docs/开户客服流程.md）
- 工作流不再做任何阶段推进：解析层把 stage 硬性回显为 currentStage（不前进不回退），空回复也回带当前阶段避免误清零
- 删除 0→1 的确定性自动介绍节点（code_phase1 / 开户详情整理等）；未开始(0)仅保留门控 Agent 简短应答，不发整段销售介绍
- 阶段推进改由客服在管理后台「会话阶段管理」网页操作（stage 0~6）
- 保留：签约阶段 9 个月免费话术（distName=田野聚落 判定）；注册委托书/委托单链接生成 + 自动可用性检查与降级（qyfwwtd 带 ?uuid=开户ID）

### 后端/前端会话阶段枚举 0~4 → 0~6 同步
- src/memory.py：set_stage 取值范围放宽到 0~6 并更新注释（session_stage 存储语义=开户客服流程六阶段）
- src/handler.py：工作流回写 stage 校验范围放宽到 0~6；注释同步
- src/api_memory.py：SetStageRequest 及接口注释/文案同步六阶段语义
- frontend/src/types.ts：STAGE_LABELS 改六阶段名称、STAGE_OPTIONS 扩到 0..6
- frontend/src/pages/StagesPage.tsx：阶段徽章配色补 5/6、页面副标题同步
- README.md：会话阶段表/接口说明同步 0~6
- 注：session_stage 库内旧 0~4 数值未做迁移，语义变化后可在管理后台人工核对调整
