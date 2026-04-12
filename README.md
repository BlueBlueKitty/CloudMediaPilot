# CloudMediaPilot

CloudMediaPilot 是一个影视推荐、资源搜索和网盘转存助手。后端基于 FastAPI，WebUI 内置在后端服务中，打开浏览器即可使用。

主要能力：

- TMDB / 豆瓣推荐与影视搜索
- PanSou + Prowlarr 聚合资源搜索
- 115 / 夸克分享资源逐级选择与转存
- 115 磁力离线任务创建
- WebUI 配置、连接测试、日志查看

默认访问地址：`http://localhost:1315/`

默认登录账号：`admin`

默认登录密码：`admin`

## 界面预览

### 推荐页

![推荐页](images/recommend.png)

### 搜索页

![搜索页](images/search.png)

### 设置页

![设置页](images/settings.png)

## Docker 部署

CloudMediaPilot 会在 `/app/config/.env` 不存在时自动生成配置文件，因此 Docker 部署时不需要提前复制 `.env`。

### 方式一：docker run

```bash
docker run -d \
  --name cloudmediapilot \
  -p 1315:1315 \
  -e CONFIG_ENV_PATH=/app/config/.env \
  -e SYSTEM_PASSWORD=admin \
  -v "$PWD/cloudmediapilot/config:/app/config" \
  -v "$PWD/cloudmediapilot/data:/app/data" \
  bluebluekitty/cloudmediapilot:latest
```

访问：`http://localhost:1315/`

### 方式二：docker compose

不需要复制本项目文件。新建一个目录，例如 `cloudmediapilot`，在里面创建 `docker-compose.yml`：

```yaml
services:
  backend:
    image: bluebluekitty/cloudmediapilot:latest
    container_name: cloudmediapilot-backend
    environment:
      CONFIG_ENV_PATH: /app/config/.env
      SYSTEM_PASSWORD: admin
    ports:
      - "1315:1315"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:1315/health')"]
      interval: 20s
      timeout: 5s
      retries: 3
      start_period: 10s
```

启动：

```bash
docker compose up -d
```

### 部署变量说明

Docker 部署常用只需要关注这几项：

| 项 | 含义 |
| --- | --- |
| `./config:/app/config` | 配置目录。首次启动会自动生成 `/app/config/.env`，WebUI 保存设置也会写入这里。请备份这个目录。 |
| `./data:/app/data` | 数据目录。用于持久化运行期数据和后续扩展数据。 |
| `SYSTEM_PASSWORD` | 首次自动生成配置时使用的 WebUI 初始登录密码。默认账号是 `admin`。 |

## Docker 构建

本地构建镜像：

```bash
docker build -f backend/Dockerfile -t cloudmediapilot:local .
```

运行本地镜像：

```bash
docker run -d \
  --name cloudmediapilot \
  -p 1315:1315 \
  -e CONFIG_ENV_PATH=/app/config/.env \
  -e SYSTEM_PASSWORD=admin \
  -v "$PWD/config:/app/config" \
  -v "$PWD/data:/app/data" \
  cloudmediapilot:local
```

发布到 Docker Hub 可使用脚本：

```bash
export DOCKERHUB_TOKEN=你的DockerHubToken
./scripts/dockerhub_publish.sh 0.1.0
```

脚本会构建并推送：

- `bluebluekitty/cloudmediapilot:0.1.0`
- `bluebluekitty/cloudmediapilot:latest`

## 本地运行

### 环境要求

- Python 3.11+
- 推荐使用虚拟环境

### 安装依赖

```bash
make install
```

### 启动服务

```bash
make run
```

等价命令：

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 1315
```

打开：`http://localhost:1315/`

本地运行时如果 `config/.env` 不存在，程序也会自动生成。

## 常用开发命令

```bash
make test
make smoke-mock
make verify-secrets
```

含义：

- `make test`：运行后端测试
- `make smoke-mock`：mock 模式冒烟测试
- `make verify-secrets`：检查潜在敏感信息
