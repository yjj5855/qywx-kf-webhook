# 变更记录

> 下次发布后清空此文件

## [开发中]

### 管理后台前端（登录后管理群绑定与会话阶段）
- 新增 frontend/ 管理后台前端（Vite + React 19 + TypeScript + Tailwind v4），含登录页、群绑定管理页、会话阶段管理页；构建产物 frontend/dist 由后端托管（生产访问 http://<host>:8000/，开发模式 Vite 8001 端口且 /api 代理到本服务）
- 登录页：用户名/密码登录，token 本地保存后带 `Authorization: Bearer <token>` 访问 /api/* 管理接口
- 群绑定管理页：查询/搜索/新增/编辑/删除群绑定；知识库 ID 留空保存时自动建库并回填
- 会话阶段管理页：分页查询/搜索/编辑 session_stage（stage 0~4）
- src/main.py 新增 SPA 兜底路由托管 frontend/dist，未知路径回退 index.html（注册在所有 API 路由之后，不吞 /health、/callback）

### 管理接口登录鉴权：用户名/密码 → Bearer token
- 新增 src/api_auth.py：POST /api/auth/login 用户名/密码（WT_ADMIN_USERNAME / WT_ADMIN_PASSWORD）校验通过后签发 HMAC-SHA256 签名 Bearer token（12 小时过期）；GET /api/auth/me 校验 token 返回当前用户名
- 未配置 WT_ADMIN_PASSWORD 时登录接口禁用（503，仍可用 X-API-Key）；未配置 WT_ADMIN_API_KEY 时整体禁用
- src/auth.py 新增 create_token/verify_token（token 签名密钥由管理密钥派生，无需额外配置）、get_current_user 依赖；require_admin 支持 X-API-Key 与 Bearer token 二选一
- 鉴权豁免列表增加 /api/auth/login；README 补充登录与 token 调用示例

### 群绑定保存自动创建群专属知识库
- POST /api/bindings 新增/编辑绑定且 memory_dataset_id 留空时，保存成功后自动调用 Dify API（POST /v1/datasets，命名 群记忆_{group_id}）创建群专属知识库并回填绑定
- 创建失败不影响绑定保存，失败原因放入响应 warning 由前端弹窗提示；未配置 WT_DIFY_DATASET_KEY 时提示手动填写

### 会话阶段分页查询接口
- 新增 GET /api/memory/stages：分页列出全部会话阶段（session_id 模糊搜索、按更新时间倒序、limit 上限 1000）
- src/memory.py 新增 ChatMemoryStore.list_stages 分页查询方法

### Dify/WorkTool 调用可选走系统代理
- 新增 WT_HTTPX_TRUST_ENV 配置（默认 false=忽略代理直连，生产内网推荐）；开发机被 TUN 代理（如 Clash）接管导致连不上局域网 Dify 时设 true 走系统代理
- dify_client / company_profile / init_datasets / kb 的 httpx 调用由 trust_env=False 改为按该配置

### 发链接后保持阶段2，客户确认交付才进3（线上已发布）
- 修复：原规则"资料齐全→发委托单链接→stage 输出 3"，只发链接就跳到签约后交付，偏早（开通后台/顾问对接/每月跟进等交付动作尚未完成）
- 阶段2 Agent 指令改为：资料齐全并发送委托单链接后【stage 保持 2】；客户明确确认材料/要求继续交付（"材料收到/可以继续/开通后台吧/安排顾问吧"）→ stage 输出 3；简单回应保持 2
- dify/开户办理-主流程.yml 已同步

### 委托单链接追加 ?uuid={开户ID}（线上已发布）
- 阶段2 Agent：material_url 末尾追加 ?uuid=【开户ID】——有 distUuid → qyfwwtd-{distUuid}.html?uuid={开户ID}；无 → qyfwwtd.html?uuid={开户ID}
- code_merge：check_url 兜底默认链接带 uuid（open_account_id 空时不加参数）
- code_final_link：接收 open_account_id，降级默认链接带 uuid；验证 404 降级/200/无链接/带不带 uuid 均正确
- dify/开户办理-主流程.yml 已同步（30 节点）

### 链接检查节点错误处理：404 降级不中断（线上已发布）
- 修复：有 distUuid 拼出的链接也可能 404；实测 Dify http 节点对 404 直接抛错（node_retry→Request failed with status code 404→分支中断，code_final_link 不执行，降级逻辑走不到）
- 修复：http_check_link 节点配置 error_strategy=default-value + default_value（status_code=404, body=""），节点失败（含404）时输出默认值、工作流继续；code_final_link 读到 status_code=404 → 降级默认链接 https://www.ibanbu.com/YQT/qyfwwtd.html
- 实测验证：404 URL → http_check_link 出错后 code_final_link 正常执行，workflow_finished 正常（分支不再中断）
- dify/开户办理-主流程.yml 已同步（30 节点）

### 阶段1按distName发9个月话术；阶段2按distUuid发链接并降级（线上已发布，30 节点）
- 阶段1（答疑转化Agent）：9个月免费福利疑问先调 getOpenAccountDetail 确认 distName，仅当 distName=="田野聚落" 才发送 9 个月免费话术；否则按通用口径回答、不发该话术
- 阶段2（签约交付Agent）：资料齐全 → 调 getOpenAccountDetail 拿 distUuid → material_url = https://www.ibanbu.com/YQT/qyfwwtd-{distUuid}.html（无 distUuid 用默认 https://www.ibanbu.com/YQT/qyfwwtd.html）；send_file 恒 false（改为发链接文本，不再发文件消息）；messages 含带链接文本；输出 JSON 增加 material_url
- 工作流新增链接检查链：code_merge（透传 material_url + check_url 兜底默认）→ http_check_link（GET 检查 status_code）→ code_final_link（200 用主链接，否则降级默认链接；消息内主链接字符串替换为最终链接）→ 发送链
- 发送链 msg/send_file/stage 来源 code_merge → code_final_link；文件链保留但不再触发（send_file 恒 false）
- 实测：http_check_link/code_final_link 正常执行无报错（status_code 绑定有效）；单测：200→主链接、404→降级、无链接→原样
- dify/开户办理-主流程.yml 已同步（30 节点 36 边）

### 区分「客服服务阶段」与「开户办理进度」（线上已发布）
- 三个业务 Agent（答疑/签约/交付）指令新增"两个进度要分清"说明：
  ① 客服服务阶段（stage 0~4）是内部状态，只用于决定话术/流程，不向客户提及、不当作开户进度回答；
  ② 开户办理进度必须调 getOpenAccountDetail（id=【开户ID】）按接口返回内容回答
- 查询触发措辞限定为【开户办理进度】（开户/开通办到哪一步、开户进度、开户信息）
- dify/开户办理-主流程.yml 已同步

### 开户ID贯通：群绑定字段 → 工作流入参 → Agent 工具传参（线上已发布）
- group_bindings 新增 open_account_id 列（迁移自动补列）：src/binding.py 增 update_open_account_id、_row_to_dict/upsert/迁移支持；BindingItem 增 open_account_id；POST /api/bindings 支持
- src/init_bindings.py 读取 CSV「开户ID」列回填（CSV 空值保留库内已有值）
- src/handler.py：_resolve_open_account_id 按群名取开户ID，_build_inputs 注入 openAccountId
- 工作流（线上已发布）：start 新增 openAccountId 输入；3 个业务 Agent query 注入【开户ID】；已绑定的真实工具 getOpenAccountDetail(id) 的调用说明更新为「id 用【开户ID】，未配置时回复开户ID未登记」（原有占位工具 queryAccountOpeningInfo/submitWorkOrder 已被替换为真实绑定工具）
- 验证：群配置 OA-2026-001 → openAccountId 注入；未配置/私聊 → 空；update_open_account_id 生效
- dify/开户办理-主流程.yml 已同步；部署需重启回调服务（表迁移 + handler 注入）

### 管理接口鉴权（/api/* 需 X-API-Key，fail-closed）
- 风险：群绑定 / workflow 配置 / 对话记忆等管理接口此前完全开放，任何人可改 workflow_app_id、看/改 app key
- 新增 src/auth.py：require_admin 依赖，所有 /api/* 管理接口（bindings / workflows / messages）请求头需 `X-API-Key: <WT_ADMIN_API_KEY>`
- fail-closed：未配置 WT_ADMIN_API_KEY 时管理接口整体 503 禁用；豁免 /callback（WorkTool 回调）、/health、/retrieval（语雀外部知识库，自带 WT_YUQUE_EXTERNAL_KEY 鉴权）
- src/config.py 新增 admin_api_key；.env.dev/.env.prod 增加 WT_ADMIN_API_KEY 配置项（需自行填强随机串并重启）
- README：配置项表 + API 接口表增加鉴权说明与调用示例
- 验证：无/错密钥 401、正确密钥 200、POST 同校验、豁免接口正常、未配置 503
- 部署注意：外部后台调 POST /api/messages/stage 设置阶段时也需带 X-API-Key

### 文本段串行保序 + 文件发送并联（线上已发布，28 节点 34 边）
- 调整：并联发送存在三段文本乱序风险（WorkTool 客户端按到达顺序执行，并行提交顺序不确定）；按需求改为 文本段 1→2→3 严格串行保序，文件发送保持独立分支并联（文件顺序与文本无关）
- 实测（console draft/run SSE）：http_send_1→http_send_2→http_send_3 严格顺序执行；code_build_file/if_need_api（文件链）与文本链并行；workflow_finished 在所有分支之后
- dify/开户办理-主流程.yml 已同步

### 发送链并联：文件+3段文本并行发送（线上已发布，28 节点 32 边）
- 优化：code_merge 之后的发送链原为串行（发文件→段1→段2→段3，每步等上一步 HTTP 完成）；改为从 code_merge 直接扇出 5 条独立分支并行执行（文件链 / 段1 / 段2 / 段3 / 立即记录），code_final_text→end 不等发送
- 实测（console draft/run SSE）：code_merge 后各分支同时启动，http_send_1/2/3 并行交错执行，workflow_finished 在所有分支之后（Dify 等待全部并行分支完成，不截断）
- 说明：三段文本并行提交依赖 WorkTool 客户端指令队列顺序执行；若实测出现三条介绍消息乱序，可把文本段改回串行（文件仍并联）
- dify/开户办理-主流程.yml 已同步

### 按 currentStage 分流为多个小 Agent（线上已发布，28 节点）
- 架构重构：单一大 Agent（四阶段话术+规则全塞一个指令，模型遵循差）→ 先按 currentStage 分流成 4 个小 Agent，每个指令短小聚焦
- 路由：if_stage_router（currentStage 1/2/3/4 分流）→ 阶段0 再按 被@/私聊 判断 → code_phase1（确定性3条介绍）/ 门控Agent
  - 门控Agent(阶段0)：未@群聊时判断是否业务相关，不推进
  - 答疑转化Agent(阶段1)：三疑问分类话术+强化价值+引导签约；明确办理意向→stage2，简单回应→保持1
  - 签约交付Agent(阶段2)：收集营业执照/法人/银行账户（多轮），资料齐→send_file+stage3
  - 交付长期Agent(阶段3-4)：开通后台/顾问/每月跟进+一般咨询
- 各 Agent 输出统一 JSON，经各自解析节点（阶段钳制 _clamp_stage + 低阶段<3 资料话术拦截）→ code_merge 聚合 → 文件链 → 3段文本发送链
- 工具（提交工单/查询开户进度占位）挂到 3 个业务 Agent；验证：分流/钳制/资料拦截/merge 聚合全部通过
- dify/开户办理-主流程.yml 已同步

### 阶段状态机代码化：钳制推进 + 低阶段资料话术拦截（线上已发布）
- 修复：实测 stage 从 0 直接跳到 3（模型看到历史"介绍一下开户流程"+"好的"，误判办理意向并输出资料收集话术+stage=3，代码未限制直接写回）
- code_parse_agent 阶段钳制（_clamp_stage）：只前进不倒退、每轮最多推进一级；0 级只能由确定性触发（被@/私聊）推进，群聊未@ 的 0 级不推进——0→3、1→3 等跳变从代码层杜绝
- 低阶段（<3）资料话术兜底拦截：回复含（营业执照/法人信息/银行账户）≥2 个特征词时替换为温和回应（"好的，您先了解…确定办理的话说一声，我马上安排签约。"）
- 验证：stage0+未@+"好的"+模型输出 stage3 → 实际 stage0+温和回应；stage1 资料话术→钳到2+温和回应；正常答疑照常；stage0+被@→第一阶段 3 条
- dify/开户办理-主流程.yml 已同步

### 阶段推进体验与外部设置（线上工作流已发布 + src/api_memory.py）
- 修复体验：客户随口"好的/嗯/知道了"等简单回应不再触发第三阶段资料收集——阶段推进规则新增「简单回应不推进、不收集资料，温和回应即可」；只有【明确表达办理意向】（签约/办理/可以开始/我要办理/好的办吧等）才进入第三阶段；第三阶段触发条件同步收紧
- 支持 0→1 由外部后台完成：src/api_memory.py 新增 POST/GET /api/messages/stage（按 session_id 设置/查询会话服务阶段，session_id 格式 roomType:chat_id 如 "1:测试二群"）；客服在其他后台完成初次触达后调该接口置 stage=1，机器人不会重复发第一阶段介绍
- dify/开户办理-主流程.yml 已同步；需重启回调服务使新接口生效

### 阶段推进确定性：stage0+被@强制第一阶段（线上已发布）
- 修复：模型看到 recentContext 历史对话后误判已过第一阶段（实测 stage 被推到 2）；阶段决策不再依赖模型解读历史
- code_parse_agent 新增确定性规则：currentStage==0 且（被@ 或 私聊）→ 强制第一阶段（代码拼装 3 条原文话术、stage 置 1），直接覆盖模型输出；历史对话再多也无法干扰 0→1 的推进
- 指令阶段0规则同步：被@/私聊首条时工作流自动发送介绍并置 stage=1
- 验证：stage0+被@（模型输出 stage=2）→ 实际 stage=1+3条话术；stage0未@群聊/私聊/阶段1被@ 均按预期
- dify/开户办理-主流程.yml 已同步

### 第一阶段确定性执行（线上已发布）
- 修复：模型反复将第一阶段合并/改写/跳阶段（实测 stage 误推到 2）；改为确定性实现
- Agent 指令：被@且 stage=0 时只需输出 {"action": "phase1_intro", "messages": [], "stage": 1}，不自己编写介绍内容、不回答客户问题
- code_parse_agent：action=phase1_intro 时由代码按常量拼装 3 条原文话术（三大服务介绍/演示链接/线上收尾，称呼按发送者首字+"总您好"，无名用"各位好"），stage 固定 1；其余情况照旧解析 messages 数组
- 输出格式增加 action 字段；验证：phase1_intro→3条+stage1、普通回复→数组、闲聊→空、解析失败→兜底
- dify/开户办理-主流程.yml 已同步

### 图片消息列为不支持类型（线上已发布）
- 消息类型规则收紧：仅支持文本类（textType 1文本/13合并记录/15带回复文本）；图片(2)与语音/视频/文件/小程序/链接等一并按不支持处理，统一回复"抱歉，暂不支持处理该类消息，请用文字描述您的需求。"
- dify/开户办理-主流程.yml 已同步

### 第一阶段强制 3 条原文话术（线上已发布）
- 修复：实测被@且 stage=0 时 Agent 只返回 1 条消息（且自行总结流程、未用原文话术）；原因是 Agent 对"输出 messages 数组"遵循不足
- 指令强化：第一阶段触发后【强制】输出 3 条 messages（动作1/动作2/动作3 各一条），逐字使用三段原文话术（仅替换 X总 称呼），禁止合并/改写/自行总结；输出格式补充第一阶段 3 条示例
- 客服 Agent 模型温度调为 0.3（提高确定性）
- dify/开户办理-主流程.yml 已同步

### 会话服务阶段（显式状态）与多段回复
- 新增 会话服务阶段显式状态（session_stage 表，src/memory.py）：get_stage/set_stage 读写 0~4 阶段（0未开始 1初次触达 2转化签约 3签约后交付 4长期服务，越界按 0 处理、写入钳制到 0-4），工作流 Agent 显式推进（只前进不倒退）、输出 stage 回写，下一轮经 currentStage 注入，不靠历史推断
- 新增 handler 多段回复支持（src/handler.py）：工作流输出 msg1/msg2/msg3 逐条记录为 bot 消息，保证知识库导出与真实发送内容一致（第一阶段连发 3 条）；缺失时回退 final_text
- 重构 dify/开户办理-主流程.yml 为四阶段服务流程（初次触达/答疑转化/签约交付/长期服务）：Agent 输出 messages(1~3条)/send_file/stage 的 JSON，代码节点解析为 msg1/msg2/msg3 + stage，新增 currentStage 输入与结束节点 stage/msg1/msg2/msg3 输出（Dify 控制台重新导出）
- 新增 src/console_workflow.py：Dify 控制台工作流编辑工具（export 导出线上 DSL / draft 本地 workflow 覆盖草稿 / publish 发布 / apply 一步到位），认证支持 --cookie（浏览器会话，可只传 session 值）或 --email/--password（控制台登录），--base-url 可指定服务地址
- .gitignore 忽略 Dify 线上工作流编辑临时目录 .dify-work/
