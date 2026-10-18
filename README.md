# McOpt-X｜可解释的多人决策与盲盒推荐

用预算、热量和口味约束筛选麦当劳餐品，解释推荐原因；多人需求冲突时提供可讨论的最小放宽方案。只读推荐，不下单、不领券、不修改账户。

## 启动

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

默认使用 `tests/fixtures` 的菜单、营养快照。当前快照有 8 款菜单项，其中 6 款具备可匹配营养信息并参与推荐。快照不是实时价格，单次结果是一款餐品，不是完整套餐优化。

## 功能

- **Personal**：综合最优、最便宜、营养优先；展示口味、营养、性价比、优惠的原始分数、权重及加权贡献。不同目标沿用现有权重设置。
- **Group**：2–6 人共同选一款餐品，显示每位成员、平均及最低满意度；`group score = 0.6 × mean + 0.4 × min`。无共同可行项时，在预算、热量以及两者同时放宽的方向中，各选当前菜单放宽代价最小的候选，始终保留忌口。
- **Blind Box**：会话保存最近 50 次抽取，默认避免最近 3 次重复。若所有可行项都在最近 3 次中，明确提示允许重复，不放宽其他限制。显示本次条件概率、新颖性、多样性及 Utility 分项。刷新页面组件不会重复记账，支持清空历史。
- **MCP Live Refresh**：侧栏输入门店编码，点击“刷新真实麦当劳数据”。仅查询菜单和营养，经现有 adapter 转换；失败时完整回退本地快照。三个 Tab 共用数据源和载入时间。

探索模式沿用原算法 Utility / Novelty / Diversity 权重：conservative 70/20/10、balanced 50/30/20、adventurous 30/40/30。没有历史时新颖性、多样性使用原算法默认值；三档不会保证抽中不同餐品。

妥协代价为各成员 `预算增量 / max(原预算,1) + 热量增量 / max(原热量上限,1)` 之和；相同代价按改动数量、group score、价格排序。这是透明的产品启发式，只保证当前菜单内、各方向按该代价最小，不代表人的真实妥协意愿。候选不会自动修改输入。满意度是模型分数，不是用户调查结果。

## 实时数据配置

详见 [MCP_INTEGRATION.md](MCP_INTEGRATION.md)。优先读取 `MCD_MCP_TOKEN` 环境变量；否则读取本机 Cursor / WorkBuddy 的 `mcd-mcp` 配置，不复制凭据。示例 [mcp-config.example.json](mcp-config.example.json) 仅含占位符，不可直接用于认证。

## 验证

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_personal.py tests/test_group.py tests/test_blind_box.py tests/test_mcp_adapter.py tests/test_enhancements.py
```

2026-10-18：29 项通过，包括三个页面交互、分项重构总分、妥协候选、历史避重、探索概率、实时数据成功/失败模拟与只读工具限制。核心 `scoring.py`、`personal.py`、`group.py`、`blind_box.py`、`mcp_adapter.py` 未改动。

真实联网验证仍未完成：当前环境连接 MCP 时曾出现远端断开；随后使用用户提供的门店编码 `3390143` 执行实际刷新，调用未成功并自动回退到 6 款本地快照餐品。该编码有效性尚未确认，不能声称真实菜单刷新成功。模拟响应验证不替代真实服务验收。

## 目录与提交准备

- `app.py`：统一数据源、解释及交互。
- `src/mcopt/presentation.py`：评分解释、妥协搜索、盲盒条件抽样。
- `src/mcopt/live_data.py`：只读 MCP 客户端、数据校验及回退。
- `tests/test_enhancements.py`：必要回归与 UI 测试。
- [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)：等待粘贴官方模板，尚不可作为最终声明提交。
- [workbuddy.md](workbuddy.md)：已核实配置与待补使用记录。

发布前仍需：在可用网络下确认门店编码并验证真实刷新；补齐官方声明和真实 WorkBuddy 使用证据；人工核对比赛要求与仓库内容，然后自行提交 Git、上传 GitHub、报名。本次未执行上述发布操作。

## 限制

营养匹配沿用名称/别名策略，不具备完整配料及过敏原数据；数据不完整的餐品被排除。实时价格对应所填门店的到店自取场景，页面时间是载入时间。历史仅在当前 Streamlit 会话内保留。每次网络请求有 15 秒超时，刷新涉及多个顺序请求。未开展在线部署或多人并发压力测试。
