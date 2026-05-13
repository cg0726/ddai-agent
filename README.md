# 尽责报告助手

尽责报告助手是一款面向银行授信审批场景的智能文档处理工具，帮助用户高效撰写尽责调查报告。

## 功能特性

- 📄 **文档管理**：支持上传上期报告、本期模板、本期资料、参考报告等多种类型文件
- 🔍 **智能检索**：基于智谱AI知识库实现精准的文档内容检索
- 💬 **智能问答**：支持基于文档内容的问答模式，快速获取信息
- 📝 **报告生成**：自动提取章节结构，辅助撰写尽责调查报告
- 🌐 **联网搜索**：集成知乎开放平台，支持联网搜索补充信息

## 使用指引

### 1. 登录系统

打开浏览器访问应用，使用配置的密码登录系统。

### 2. 创建项目

在首页点击"新建项目"，输入项目名称后创建新的报告项目。

### 3. 上传文件

在项目页面的文件管理区域，点击"上传文件"，选择对应类别的文件：
- **上期报告**：上一期的尽责调查报告
- **本期模板**：本期报告的模板文件
- **本期资料**：本期项目的相关资料
- **参考报告**：其他参考文档

### 4. 智能问答

切换到"问答"模式，输入问题即可基于上传的文档内容获得答案。

### 5. 生成报告

切换到"报告"模式，系统会自动提取章节结构，点击各章节可查看或编辑内容，支持重新生成和导出为 Word 文档。

## Docker 部署指南

## 环境要求

- Docker Engine >= 20.10
- Docker Compose >= 2.0

## 快速部署

### 1. 下载项目

```bash
git clone <项目仓库地址>
cd ddai-agent
```

### 2. 配置环境变量

```bash
# 从模板创建环境变量文件
cp .env.example .env
```

编辑 `.env` 文件，**务必修改以下配置**：

| 变量 | 说明 | 是否必填 |
|------|------|----------|
| `APP_PASSWORD` | **登录密码（务必修改默认值！）** | 是 |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥（智能对话核心） | 是 |
| `ZHIPUAI_API_KEY` | 智谱AI API 密钥（文件管理） | 是 |
| `KNOWLEDGE_BASE_ID` | 智谱AI 知识库 ID | 是 |
| `ZHIHU_ACCESS_SECRET` | 知乎开放平台密钥（联网搜索） | 否 |
| `EXTRACT_API_KEY` | 网页内容提取模型密钥（可选） | 否 |

### 3. 启动服务

```bash
# 构建并启动（后台运行）
docker compose up -d

# 查看启动日志
docker compose logs -f
```

### 4. 访问应用

打开浏览器访问：**http://localhost:8501**

使用 `.env` 中设置的 `APP_PASSWORD` 登录。

## 目录结构说明

部署后容器内关键路径：

```
/app
├── app.py                  # 主入口
├── modules/                # 业务模块
├── .streamlit/             # Streamlit 配置
└── data/                   # 持久化数据（挂载自宿主机）
    ├── projects.db         # SQLite 数据库
    ├── uploads/            # 上传文件
    └── exports/            # 导出的 Word 报告
```

宿主机 `./data/` 目录挂载到容器 `/app/data/`，数据不会因容器重启而丢失。

## 常用命令

```bash
# 启动服务
docker compose up -d

# 停止服务
docker compose down

# 查看日志
docker compose logs -f

# 重启服务
docker compose restart

# 重新构建镜像（依赖变更后需要）
docker compose build --no-cache

# 更新并重启（代码变更后）
docker compose down
docker compose up -d
```

## 安全提醒

1. **必须修改 `APP_PASSWORD` 默认值**，生产环境请使用强密码（建议 16 位以上，包含大小写字母、数字和特殊字符）
2. 配置文件 `.env` 包含敏感 API 密钥，**切勿泄露**
3. 建议定期备份 `./data/` 目录下的数据库文件
4. 如需对外暴露服务，建议在 Docker 前增加反向代理（如 Nginx）并配置 HTTPS

## 常见问题

**Q: 端口冲突怎么办？**

修改 `docker-compose.yml` 中的端口映射，例如将宿主机端口改为 8080：

```yaml
ports:
  - "8080:8501"
```

**Q: 如何更新应用代码？**

```bash
git pull                     # 拉取最新代码
docker compose down          # 停止容器
docker compose up -d         # 重新构建并启动
```

**Q: 如何查看容器资源使用？**

```bash
docker stats ddai-agent
```
