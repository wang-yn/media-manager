# GitHub OAuth 登录与用户白名单设计

## 目标

为 Media Manager 增加 GitHub 单点登录。所有页面和 API 默认需要登录，只有环境变量白名单中的 GitHub 用户名可以建立并继续使用会话。

正式访问地址为：

```text
https://media.example.com
```

GitHub OAuth App 回调地址固定为：

```text
https://media.example.com/auth/github/callback
```

## 配置

应用从以下环境变量读取认证配置：

```env
MEDIA_MANAGER_PUBLIC_URL=https://media.example.com
MEDIA_MANAGER_SESSION_SECRET=<至少32字节随机值>
GITHUB_OAUTH_CLIENT_ID=<OAuth App Client ID>
GITHUB_OAUTH_CLIENT_SECRET=<OAuth App Client Secret>
GITHUB_ALLOWED_USERS=wang-yn,other-user
```

约束：

- `MEDIA_MANAGER_PUBLIC_URL` 必须是无末尾斜杠的 HTTPS 地址。
- `MEDIA_MANAGER_SESSION_SECRET` 至少 32 字节，只用于 HMAC 签名。
- `GITHUB_ALLOWED_USERS` 使用英文逗号分隔，去除首尾空白后按 `casefold()` 比较，至少包含一个用户名。
- 任一配置缺失或不合法时，生产应用拒绝启动，不提供未认证降级模式。
- `create_app(auth_enabled=False)` 仅用于现有自动化测试显式关闭认证，不对应任何部署环境变量。

## 组件边界

新增 `backend/src/media_manager/auth.py`，负责：

- 认证环境变量解析与校验。
- GitHub authorize URL 和 PKCE 参数生成。
- 使用授权码换取 access token，并调用 GitHub `/user` 获取身份。
- OAuth 临时 Cookie 与登录会话 Cookie 的编码、签名、验证和过期处理。
- 登录、无权限和认证错误 HTML 页面。

`backend/src/media_manager/server.py` 只负责：

- 注册认证路由。
- 通过全局中间件保护现有页面和 API。
- 把认证配置和 GitHub HTTP 客户端注入认证函数。

`frontend/src/App.tsx` 只增加退出按钮，不保存 OAuth token 或会话数据。

## 路由与访问控制

公开路由只有：

- `GET /login`：显示登录页面。
- `GET /auth/github/login`：启动 GitHub OAuth 流程。
- `GET /auth/github/callback`：处理 GitHub OAuth 回调。

认证路由：

- `POST /auth/logout`：清除会话 Cookie，并返回登录页地址。

全局访问规则：

- 未登录访问 `/api/*` 返回结构化 `401` JSON。
- 未登录访问其他路径返回 `303` 并跳转到 `/login`。
- 已登录但用户名已不在当前白名单中的会话视为无效。
- `/api/health` 也需要认证，避免暴露本地配置路径和集成状态。
- 登录页使用内联样式，不需要额外公开静态资源。

## OAuth 流程

1. 用户打开 `/login` 并点击“使用 GitHub 登录”。
2. `/auth/github/login` 生成随机 `state` 和 PKCE `code_verifier`，计算 `S256` `code_challenge`。
3. `state`、`code_verifier` 和 10 分钟过期时间写入 HMAC 签名的临时 Cookie。
4. 浏览器跳转到 `https://github.com/login/oauth/authorize`，携带 `client_id`、固定 `redirect_uri`、`state`、`code_challenge` 和 `code_challenge_method=S256`。不申请额外 scope。
5. GitHub 回调后，应用逐字比较查询参数 `state` 与临时 Cookie 中的值；缺失、不一致、篡改或过期都终止流程。
6. 后端向 `https://github.com/login/oauth/access_token` 提交 `client_id`、`client_secret`、`code`、固定 `redirect_uri` 和 `code_verifier`。
7. 后端使用返回的 Bearer token 请求 `https://api.github.com/user`。
8. GitHub 用户名不在白名单时返回 `403` 页面，不创建会话。
9. GitHub 用户名在白名单时创建登录会话 Cookie，删除 OAuth 临时 Cookie，并跳转到 `/`。
10. access token 在身份查询完成后丢弃，不写入 Cookie、日志、配置或文件。

## 会话

会话 Cookie 包含：

- GitHub 数字用户 ID。
- GitHub `login`。
- 签发时间和过期时间。

会话规则：

- 使用 HMAC-SHA256 签名，编码采用 URL-safe Base64。
- 有效期固定为 7 天。
- Cookie 属性为 `Secure`、`HttpOnly`、`SameSite=Lax`、`Path=/`。
- 每次请求验证签名、过期时间和当前用户名白名单。
- 无效或过期会话按未登录处理。
- 退出操作清除会话 Cookie；服务端不保存会话表。

## 页面交互

登录页展示：

- 产品名 `Media Manager`。
- “使用 GitHub 登录”主按钮。
- OAuth 或配置错误的简短提示，不显示 secret、token 或 GitHub 原始响应。

无权限页面展示当前 GitHub 用户名以及“该账号未获授权”，提供重新登录入口。

登录后的现有顶部工具栏增加“退出”按钮。点击后调用 `POST /auth/logout`，成功后跳转 `/login`。

## 错误处理

- 缺少 `code`、OAuth 临时 Cookie或 `state` 不匹配：返回 `400` 登录错误页。
- GitHub token 或用户 API 超时、非成功状态、响应格式错误：返回 `502` 登录错误页。
- GitHub 用户不在白名单：返回 `403` 无权限页。
- 会话 Cookie 篡改、格式错误或过期：不暴露原因，按未登录处理。
- 日志和错误响应不得包含 client secret、access token、code verifier 或完整会话 Cookie。

## 测试

后端测试覆盖：

- 配置缺失、HTTPS 地址校验、secret 长度和用户名列表解析。
- OAuth authorize URL、PKCE、临时 Cookie 签名、篡改和过期。
- state 缺失或不匹配。
- GitHub token 和 `/user` 成功、失败及非法响应。
- 白名单允许、拒绝和大小写不敏感匹配。
- 会话签名、篡改、过期及用户从白名单移除。
- 页面未登录重定向、API `401`、公开认证路由和退出清除 Cookie。
- 现有服务端测试通过 `auth_enabled=False` 保持原行为测试范围。

前端与部署验证覆盖：

- TypeScript 和 Vite 生产构建。
- 登录页、GitHub 跳转、无权限页、登录后首页及退出流程。
- Docker Compose 环境变量传递。
- 反向代理后的回调地址、Secure Cookie 和完整真实 OAuth 流程。

## 文档和部署

- `docker-compose.yml` 增加五个认证环境变量。
- README 增加 GitHub OAuth App 创建步骤、Homepage URL、Authorization callback URL、secret 生成命令和允许用户名示例。
- OAuth client secret 和 session secret 不写入仓库配置文件或镜像。

## 不包含

- GitHub 组织、团队或仓库权限判断。
- 多角色权限和管理员页面。
- 服务端数据库会话、refresh token 或 GitHub token 持久化。
- 多个 OAuth provider。
- 多个公开访问地址或多个回调地址。

## 官方参考

- [Authorizing OAuth apps](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps)
- [Creating an OAuth app](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/creating-an-oauth-app)
- [Authenticating to the REST API with an OAuth app](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authenticating-to-the-rest-api-with-an-oauth-app)
- [Best practices for creating an OAuth app](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/best-practices-for-creating-an-oauth-app)
