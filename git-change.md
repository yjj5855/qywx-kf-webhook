# 变更记录

> 下次发布后清空此文件

## [开发中]

### 会话服务阶段（显式状态）与多段回复
- 新增 会话服务阶段显式状态（session_stage 表，src/memory.py）：get_stage/set_stage 读写 0~4 阶段（0未开始 1初次触达 2转化签约 3签约后交付 4长期服务，越界按 0 处理、写入钳制到 0-4），工作流 Agent 显式推进（只前进不倒退）、输出 stage 回写，下一轮经 currentStage 注入，不靠历史推断
- 新增 handler 多段回复支持（src/handler.py）：工作流输出 msg1/msg2/msg3 逐条记录为 bot 消息，保证知识库导出与真实发送内容一致（第一阶段连发 3 条）；缺失时回退 final_text
- 重构 dify/开户办理-主流程.yml 为四阶段服务流程（初次触达/答疑转化/签约交付/长期服务）：Agent 输出 messages(1~3条)/send_file/stage 的 JSON，代码节点解析为 msg1/msg2/msg3 + stage，新增 currentStage 输入与结束节点 stage/msg1/msg2/msg3 输出（Dify 控制台重新导出）
- 新增 src/console_workflow.py：Dify 控制台工作流编辑工具（export 导出线上 DSL / draft 本地 workflow 覆盖草稿 / publish 发布 / apply 一步到位），认证支持 --cookie（浏览器会话，可只传 session 值）或 --email/--password（控制台登录），--base-url 可指定服务地址
- .gitignore 忽略 Dify 线上工作流编辑临时目录 .dify-work/
