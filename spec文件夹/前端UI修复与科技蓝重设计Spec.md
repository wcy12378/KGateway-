# KGateway 前端 UI 修复与科技蓝重设计 Spec

## 1. 目标

在不改变现有后端契约、业务功能和页面信息架构的前提下，分阶段完成：

1. 阅读并核验 `kgateway-frontend-fix-tasks.md` 中的修复任务。
2. 修复 `frontend` 中仍真实存在的功能、部署、错误处理和可用性问题。
3. 从 GitHub 安装适合现有项目重设计的 Taste Skill。
4. 将当前黑白红 CRT 工业终端风，升级为以蓝色为主色的现代科技控制台风格。
5. 完成桌面端和移动端浏览器验证。
6. 每个阶段完成后单独汇报成果、验证结果和下一阶段动作。

本文件是执行前审查文档。你确认后才开始修改代码和安装 skill。

## 2. 当前项目判断

### 2.1 当前技术栈

- React 19
- TypeScript 6
- Vite 8
- Tailwind CSS 4
- Zustand
- React Router
- Recharts
- Lucide React

### 2.2 当前视觉状态

当前设计系统位于 `frontend/src/index.css`，主要特征：

- 黑色背景和灰白文字。
- 红色作为主要交互强调色。
- 全局强制 `border-radius: 0`。
- CRT 扫描线和 SVG noise 覆盖全页面。
- 字号大量集中在 `7px-11px`。
- 页面强调工业终端和监控仪表感。
- 信息密度较高，但视觉层级、可读性和移动端适配不足。

### 2.3 目标视觉方向

目标不是营销型科技官网，而是现代 AI 基础设施控制台：

- 视觉温度：冷静、专业、可信、精密。
- 信息密度：中高密度，但避免所有内容都同权重。
- 主色：科技蓝。
- 基础背景：深蓝黑，而不是纯黑。
- 卡片与面板：轻层级、细边框、小圆角。
- 数据状态：蓝色负责主交互，绿色/黄色/红色只表示状态。
- 动效：短时、克制、服务于状态变化。
- 桌面端优先，同时保证移动端不溢出、不遮挡。

## 3. 原任务清单核验

### T1：生产环境 API base URL

状态：仍需要修复，但应按当前架构调整。

任务文档建议在各页面分别拼接 `API_BASE`，当前项目已经将接口集中到：

- `frontend/src/lib/gateway.ts`

根因方案：

1. 在 `gateway.ts` 中集中读取 `VITE_API_BASE`。
2. 增加安全的路径拼接函数，处理尾部 `/`。
3. 所有 endpoint 和 builder 统一基于该 base。
4. 页面和 hook 继续只依赖 `GATEWAY_ENDPOINTS`。
5. 增加 `.env.development` 和 `.env.production.example`。

不建议将生产地址固定写为 `http://localhost:8000/api`，因为该地址只适合本机。

### T2：TracesPage 后端接口缺失

状态：已经解决，不应按旧任务重新添加重复路由。

当前后端已有：

- `GET /api/v1/monitor/traces`

当前前端已通过 `tracesEndpoint()` 调用该接口，trace 详情包含在列表记录的
`spans` 中，目前不需要额外的 `GET /traces/:id`。

本阶段动作：

- 仅做真实联调验证。
- 如果列表响应与类型不一致，再修契约。
- 不新增重复 `/api/v1/gateway/traces` 路由。

### T3：chunkSizeWarningLimit

状态：任务文档中的单位判断不正确，需要改为根因优化。

Vite 的 `chunkSizeWarningLimit` 单位是 kB，当前 `600` 表示约 600kB，不是
600 bytes。当前构建警告的真正原因是 `vendor-core` 约 938kB。

根因方案：

1. 不把阈值改为 `600000` 来隐藏警告。
2. 对页面使用路由级 `lazy()` 和 `Suspense`。
3. 检查 `manualChunks` 是否把过多第三方依赖聚合进 `vendor-core`。
4. 必要时按 React、Markdown、图表、虚拟列表进一步拆包。
5. 构建后验证主要 chunk 体积和初始加载资源。

### T4：HTTP 错误响应体解析

状态：仍需要修复。

当前 `useSSE.ts` 仍只显示 `statusText`，Dashboard、Breaker、Traces 对失败
响应多为静默处理。

根因方案：

1. 新增统一的 HTTP 请求/错误解析工具。
2. 支持 JSON `detail`、`error`、`message` 和纯文本错误体。
3. SSE 和普通 JSON 请求共用错误解析规则。
4. 页面提供明确错误状态和重试入口。
5. 不再使用无反馈的空 `catch`。

## 4. 新发现的潜在问题

### P0：缺少统一请求层

当前 endpoint 已集中，但 fetch、错误解析、超时、返回类型仍散落在页面。

处理：

- 新增 `frontend/src/lib/http.ts`。
- 提供 `requestJson()`、`readErrorMessage()` 等能力。
- 页面不再手写重复的 `response.ok` 判断。

### P1：页面错误状态被静默吞掉

涉及：

- Dashboard
- Breaker
- Traces

处理：

- 页面增加 `loading / error / empty / success` 状态。
- 错误提示使用统一 Alert 组件。
- 刷新操作失败时保留旧数据，同时展示非阻塞错误。

### P1：移动端布局存在溢出风险

当前固定宽度侧边栏、参数面板和宽表格在窄屏下可能压缩或溢出。

处理：

- 侧边栏在移动端改为抽屉。
- Chat 参数面板在移动端改为 overlay/drawer。
- Trace 表格提供横向滚动或响应式字段收敛。
- Dashboard 控件在小屏换行。
- Breaker 三列统计在小屏改为单列或双列。

### P1：可访问性和可读性不足

问题：

- 大量 `7px-9px` 文字。
- 部分 icon-only 按钮只有 `title`。
- focus 状态不统一。
- 全局纯黑背景和低对比灰字影响阅读。

处理：

- 正文最低建议 `12px`，辅助标签最低 `10px`。
- icon-only 按钮增加 `aria-label` 和 tooltip。
- 增加统一 `focus-visible`。
- 保证文本和状态色对比度。

### P1：设计系统过度全局化

问题：

- `border-radius: 0 !important` 阻止组件建立层级。
- 扫描线和 noise 全页面覆盖，影响图表、文本和输入体验。
- 红色同时承担主交互与危险状态，语义冲突。

处理：

- 移除全局强制零圆角。
- 取消扫描线和 SVG noise。
- 蓝色作为主交互色。
- 红色仅保留错误、熔断和危险操作。

### P2：主题状态未形成完整设计能力

当前存在 `theme` store，但页面设计基本固定为 dark。

本轮建议：

- 先完成稳定的深色科技蓝主题。
- 暂不承诺完整 light theme。
- 保留未来主题扩展的 token 边界。

## 5. Taste Skill 安装方案

### 5.1 来源

GitHub：

- `https://github.com/Leonxlnx/taste-skill`

仓库为 MIT License，并提供多个不同用途的 skill。

### 5.2 推荐安装项

优先安装：

- `redesign-existing-projects`

理由：

- 当前任务是已有 React 项目的审查与重设计。
- 该 skill 明确要求先审计现有项目，再修复布局、间距、层级和样式。
- 比面向新建页面的默认 skill 更符合本项目。

可选辅助：

- `gpt-taste`

仅当首轮重设计结果仍显模板化时使用，不与主 skill 同时堆叠规则。

### 5.3 安装控制

1. 你批准 spec 后才执行安装。
2. 安装前确认仓库来源和目标 skill 名称。
3. 使用项目支持的 skill 安装流程，不手工复制未知脚本。
4. 安装后先读取 SKILL.md，再形成最终 Design Decisions。
5. 不允许 skill 改写业务流程、API 契约或页面功能。

## 6. 设计系统提案

### 6.1 定位四问

- Narrative role：AI 网关运行控制台，不是产品营销页。
- Viewing distance：主要为桌面 1 米阅读，同时支持手机近距离操作。
- Visual temperature：冷静、精密、可信，适度能量感。
- Capacity check：需要容纳聊天、参数、指标、图表和 trace 表格，采用中高密度布局。

### 6.2 Design Decisions

- Anchor：现代 Developer Tool / AI Infrastructure Console。
- 主色：`#2F7BFF`。
- 高亮蓝：`#57A0FF`。
- 深蓝背景：`#07111F`。
- 面板背景：`#0B1728`。
- 浮层背景：`#102039`。
- 边框：`#203451`。
- 主文字：`#EAF2FF`。
- 次文字：`#91A7C4`。
- 成功：`#32D583`。
- 警告：`#F5B942`。
- 危险：`#F05D68`。
- 标题字体：系统 sans，强调清晰和工程感。
- 正文字体：系统 sans。
- 数据和代码：JetBrains Mono / Consolas。
- 间距：4px 基础单位，主要使用 8/12/16/24/32。
- 圆角：输入与按钮 6px，面板 8px，不使用大药丸形状。
- 阴影：只在浮层、焦点和关键状态上使用轻量蓝色阴影。
- 动效：150-220ms，使用 opacity、border-color、translateY 2px。
- 图表：蓝色主序列，青色辅助序列，状态色只用于异常。

## 7. 分阶段执行方案

### Phase 0：基线与任务核验

动作：

- 运行 `npm run build`、`npm run lint`。
- 启动前端并用浏览器检查四个页面。
- 对照任务清单确认真实问题。
- 保存桌面端和移动端基线截图。

阶段汇报：

- 构建和 lint 结果。
- 每个任务的真实状态。
- 页面基线问题列表。
- 是否允许进入功能修复。

### Phase 1：功能与部署问题修复

动作：

- API base URL 环境变量化。
- 新增统一 HTTP 请求和错误解析。
- 修复 SSE 错误提示。
- 为 Dashboard、Breaker、Traces 增加错误状态。
- 验证现有 traces 接口，不重复新增后端路由。
- 优化路由懒加载和 chunk 拆分。

验收：

- 开发环境代理可用。
- 生产环境可以配置 API 地址。
- 后端错误 detail 能展示。
- 页面请求失败时有可见反馈。
- `npm run build` 和 `npm run lint` 通过。
- bundle warning 得到真实改善或有明确数据解释。

阶段汇报：

- 已修文件。
- 已解决问题。
- 构建体积变化。
- 剩余问题。

### Phase 2：安装并应用 Taste Skill

动作：

- 安装 `redesign-existing-projects`。
- 阅读 skill 规则。
- 对照当前项目调整 Design Decisions。
- 输出设计审计结论。

验收：

- skill 来源、版本和安装位置明确。
- 设计规则不与 dashboard 可用性冲突。
- 不改业务协议和功能。

阶段汇报：

- 安装结果。
- 采用的规则。
- 放弃的规则及原因。
- 最终设计系统。

### Phase 3：设计系统重构

动作：

- 重写 `index.css` token。
- 建立按钮、输入、面板、状态、空状态、错误提示等基础样式。
- 更新布局、Sidebar 和顶部栏。
- 取消 CRT 扫描线、noise 和强制零圆角。
- 建立统一 focus、hover、active、disabled 状态。

验收：

- 主色调为蓝色。
- 颜色语义统一。
- 文字可读性提升。
- 页面没有整体套卡片、嵌套卡片和无意义渐变。

阶段汇报：

- token 变化。
- 基础组件变化。
- 布局截图。
- 可访问性改进。

### Phase 4：逐页面美化

顺序：

1. Chat
2. Dashboard
3. Traces
4. Breaker

每个页面均处理：

- 信息层级。
- loading/error/empty 状态。
- 桌面与移动布局。
- 交互反馈。
- 科技蓝视觉一致性。

阶段汇报：

- 每完成一个页面，汇报修改点和截图。
- 明确功能是否保持。
- 明确下一页面计划。

### Phase 5：浏览器与生产构建验收

动作：

- `npm run lint`
- `npm run build`
- 启动本地应用。
- 用浏览器检查四个页面。
- 检查桌面和移动视口。
- 验证 API 错误、空状态和加载状态。
- 检查控制台错误、溢出、遮挡、布局跳动。

验收：

- 四个页面无明显布局问题。
- 主流程功能不回退。
- 无 TypeScript、lint、构建错误。
- 无不可解释的控制台错误。
- 关键页面提供前后对比截图。

阶段汇报：

- 最终验证清单。
- 截图与构建结果。
- 剩余风险。
- 总体成果。

## 8. 不在本轮范围

- 重写后端业务逻辑。
- 修改 SSE 协议。
- 删除现有 Chat、Dashboard、Breaker、Traces 功能。
- 完整 light theme。
- 营销落地页。
- 3D、粒子背景或大面积装饰动画。
- 为视觉效果引入不必要的大型依赖。

## 9. 需要你拍板

1. 是否同意按 Phase 0-5 顺序执行。
2. 是否同意采用深色科技蓝控制台方向。
3. 是否同意主色使用 `#2F7BFF`，状态色保持绿/黄/红。
4. 是否同意移除 CRT 扫描线、noise 和全局零圆角。
5. 是否同意从 Taste Skill 仓库安装 `redesign-existing-projects`。
6. 是否同意不执行任务清单中错误的 `chunkSizeWarningLimit: 600000`，改为真正拆包。
7. 是否同意每个页面完成后进行一次阶段汇报和截图验收。

