# Design

## Source of truth
- Status: Draft
- Last refreshed: 2026-07-08
- Primary product surfaces: Web 管理工作台、Python 后端 API、TOML 配置、Docker 运行镜像
- Evidence reviewed: 用户需求、空仓库状态、固定挂载目录 `/config` 与 `/media`、ChineseSubFinder 的 `pkg/settings/common_settings.go`、`pkg/settings/supplier_settings.go`、`pkg/ifaces/iSupplier.go`、`pkg/sub_formatter/emby/emby.go`、`docker/readme.md`

## Brand
- Personality: 安静、可靠、偏运维工具感，适合长期运行和批量整理。
- Trust signals: 明确显示扫描范围、来源启用状态、任务结果和失败原因。
- Avoid: 影视门户式推荐页、营销式首页、不可解释的自动改名。

## Product goals
- Goals: 整理电影和电视剧目录；从多个来源刮削元数据；从多个来源下载字幕；通过 TOML 管理配置；容器化运行；兼容 Emby/Jellyfin 常见字幕命名。
- Non-goals: 首版不做在线播放、用户账号体系、复杂分布式任务调度。
- Success signals: 能识别电影/电视剧目录差异；能配置多个来源；能预览扫描结果；Docker 挂载路径固定且清晰。

## Personas and jobs
- Primary personas: 自托管媒体库用户、Emby/Jellyfin 用户、NAS 或家庭服务器维护者。
- User jobs: 扫描媒体库、识别影片和剧集、补全元数据、下载字幕、按规则整理文件名。
- Key contexts of use: Docker 容器内后台运行，偶尔打开 Web 页面检查状态和处理失败项。

## Information architecture
- Primary navigation: 工作台、媒体库、来源、任务、设置。
- Core routes/screens: 首版只实现单页工作台，后续再拆分路由。
- Content hierarchy: 系统状态优先，其次是媒体库扫描结果，再是来源和配置摘要。

## Design principles
- Principle 1: 所有会改动文件的操作先支持 dry-run/预览。
- Principle 2: 来源是可替换适配器，核心流程不绑定某个站点；沿用 ChineseSubFinder 的供应商思想，但不复制旧队列、浏览器自动化和时间轴修复复杂度。
- Tradeoffs: 首版保留同步扫描和简单内存结果，等真实长任务需求出现后再加队列和数据库。

## Visual language
- Color: 白/墨色底，少量绿色表示可用，琥珀色表示待处理，红色表示失败。
- Typography: 系统 sans-serif，表格和路径使用等宽字体。
- Spacing/layout rhythm: 管理台式紧凑布局，信息密度优先。
- Shape/radius/elevation: 小圆角、细边框、轻阴影，避免装饰性卡片堆叠。
- Motion: 只在加载和任务状态变化时使用轻量反馈。
- Imagery/iconography: 首版不依赖图片资产。

## Components
- Existing components to reuse: 空仓库，无现成组件。
- New/changed components: 状态条、媒体库表、来源列表、扫描结果表。
- Variants and states: Loading、Empty、Error、Success、Disabled。
- Token/component ownership: 前端 CSS 变量先放在 `frontend/src/style.css`。

## Accessibility
- Target standard: 基础 WCAG 2.1 AA。
- Keyboard/focus behavior: 所有按钮、链接、表格控件可键盘访问。
- Contrast/readability: 正文和状态色满足可读对比。
- Screen-reader semantics: 使用语义化 `main`、`section`、`table`。
- Reduced motion and sensory considerations: 首版无强动画。

## Responsive behavior
- Supported breakpoints/devices: 桌面优先，兼容平板和手机查看。
- Layout adaptations: 窄屏下表格横向滚动，顶部摘要纵向堆叠。
- Touch/hover differences: 交互控件保持足够点击区域。

## Interaction states
- Loading: 显示正在读取后端和扫描状态。
- Empty: 显示未发现媒体项或未配置媒体库。
- Error: 展示后端返回的错误文本。
- Success: 展示扫描数量和路径。
- Disabled: 未启用来源在列表中标记。
- Offline/slow network, if applicable: 前端显示 API 连接失败。

## Content voice
- Tone: 简洁、直接、可操作。
- Terminology: 媒体库、电影、电视剧、季、集、元数据源、字幕源、整理规则。
- Microcopy rules: 文件操作必须说明是预览还是执行。

## Implementation constraints
- Framework/styling system: 后端 Python 标准库 HTTP 服务；前端 React + TypeScript + Vite；配置 TOML；首版不依赖数据库。
- Design-token constraints: 不引入 UI 框架，CSS 变量足够。
- Performance constraints: 首版扫描为递归文件遍历，适合中小型库；超大库后续再加增量索引。
- Compatibility constraints: 容器固定 `/config` 和 `/media`，目录规则兼容 Emby/Jellyfin/TinyMediaManager 常见结构。
- Test/screenshot expectations: 后端扫描逻辑用 unittest 覆盖；前端至少通过 TypeScript 构建。

## Open questions
- [ ] 是否需要首版就执行真实重命名，还是只提供 dry-run 预览 / owner: user / impact: 文件安全
- [ ] 首批要支持哪些元数据源和字幕源 / owner: user / impact: 适配器优先级
- [ ] 是否需要数据库保存任务历史，还是 TOML + 文件缓存足够 / owner: user / impact: 运行复杂度
