# CloudMediaPilot

CloudMediaPilot 是一个影视检索与离线任务分发 Web 应用，包含：

- TMDB 影视搜索（海报卡片展示）
- PanSou + Prowlarr 资源聚合搜索
- 115 离线任务创建与状态追踪
- WebUI 设置中心（TMDB / Prowlarr / PanSou / 115）
- 配置持久化到 SQLite（不再使用 `.env` 存业务配置）

---

## 1. 技术栈

- Backend: FastAPI
- 配置存储: SQLite (`data/cloudmediapilot.db`)
- 前端: 原生 HTML/CSS/JS（内置于后端）
- 容器化: Docker Compose

---

## 2. 功能页面

启动后访问 `http://localhost:8000/`：

1. **搜索页**：TMDB 卡片式影视搜索
2. **结果页**：资源表格展示 + 来源/类型/关键词筛选
3. **任务页**：查看离线任务状态
4. **设置页**：维护 TMDB / Prowlarr / PanSou / 115 配置并测试连接

> 密钥类字段（API Key、Cookie）只会脱敏显示，不会明文回显。

---

## 3. 本地运行

### 3.1 环境准备

- Python >= 3.11
- 建议先复制环境文件：

```bash
cp .env.example .env
```

`.env` 仅用于运行参数（如 `CMP_USE_MOCK`、`CMP_CONFIG_DB_PATH`），业务配置在 WebUI 设置页保存。

### 3.2 安装依赖

```bash
make install
```

### 3.3 启动服务

```bash
make run
```

打开：`http://localhost:8000/`

---

## 4. Docker 构建与运行

### 4.1 构建并启动

```bash
docker compose up --build
```

### 4.2 持久化说明

`docker-compose.yml` 已挂载：

- `./data:/app/data`

因此 WebUI 中保存的 SQLite 配置会持久化到宿主机 `data/` 目录。

---

## 5. 验证命令

```bash
make lint
make typecheck
make test
make smoke-mock
make verify-secrets
```

说明：

- `smoke-mock`：用 mock 模式验证主流程可用
- `verify-secrets`：检查仓库内潜在密钥泄露模式

---

## 6. 配置使用说明（重点）

### 6.1 在 WebUI 设置页配置以下项

- TMDB: Base URL / API Key
- Prowlarr: Base URL / API Key
- PanSou: Base URL
- 115: Base URL / Cookie / 默认目录 / 允许动作 / API 路径

保存后点击“测试连接”可快速验证连通性。

### 6.2 `.env` 与业务配置边界

- `.env`：运行参数（环境、mock 开关、SQLite 路径、超时）
- SQLite：业务提供方配置（TMDB / Prowlarr / PanSou / 115）

---

## 7. 常见问题

### Q1: `make install` 失败（Multiple top-level packages discovered: ['app', 'data']）

原因：setuptools 自动发现把 `data/` 误识别为包。  
已在 `backend/pyproject.toml` 限制仅打包 `app*`，拉取最新代码后重新执行：

```bash
make install
```

### Q2: 明明保存了设置，重启容器后丢失

请确认使用 `docker compose up`（而非临时容器），并确认 `./data:/app/data` 挂载存在。

---

## 8. 安全说明

- WebUI 返回的是脱敏密钥，不回显明文。
- `.env` / `key.txt` 已在忽略规则中，避免进入镜像或版本库。
- 请不要在 issue / 日志中粘贴真实 API Key 或 Cookie。
