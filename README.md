# d-news：热点抓取 + DeepSeek 摘要 + 飞书推送（n8n 定时）

这个项目包含一套脚本链路：
`news_spider.py`（抓取热点）→ `ai_news_filter.py`（DeepSeek 摘要/分类/过滤）→ `send_to_feishu.py`（飞书机器人推送）
并提供一个宿主机常驻 HTTP 服务 `host_trigger.py`，让 n8n 通过 HTTP 定时触发执行 `run_all.py` 全流程。

## 1. 你需要准备的东西

### 必要条件
- 安装 Python（本机执行脚本用）
- 安装 Python 依赖：`requests`
- 可访问外网（抓取站点与调用 DeepSeek、飞书 Webhook）

### 可选（但强烈建议）
- 能持续运行：Docker 里的 n8n + 宿主机的 `host_trigger.py`
  - 如果关机/重启，这个定时服务不会执行“错过的次数”，下次开机后才会到下一个触发时间点再跑。

## 2. 配置环境变量（.env）

复制示例文件：
- `.env.example` → `.env`

在项目根目录编辑 `.env`，至少需要：

- `DEEPSEEK_API_KEY=...`：DeepSeek API Key
- `FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/...`：飞书机器人自定义 Webhook

可选项：
- `FEISHU_USE_TEXT=true`：飞书用纯文本推送（不走交互卡片）
- `WEIBO_COOKIE=...`：如果微博接口 403，可从浏览器登录后复制 Cookie（勿泄露）
- `N8N_TRIGGER_KEY=...`：为 n8n HTTP 请求加鉴权（需要同时在 n8n HTTP Request 头里配置 `X-API-Key`）
- `HOST_TRIGGER_PORT=8765`：宿主机监听端口，改了要同步修改 n8n 的 URL

> 注意：本项目脚本会在需要时读取 `.env`，因此 `.env` 必须放在 `d:\桌面\news\`（脚本所在目录同级）。

## 3. 手动跑通全流程（先确认没问题）

### 3.1 先安装依赖（仅一次）
在项目目录执行（PowerShell）：
```bash
pip install requests
```

### 3.2 运行全流程
```bash
python d:\桌面\news\run_all.py
```

如果成功，依次会跑：
1. `news_spider.py`：生成 `hot_news.json`
2. `ai_news_filter.py`：生成 `ai_news_result.txt`
3. `send_to_feishu.py`：调用飞书 Webhook

如果失败，请看报错信息（通常是 DeepSeek Key/网络/飞书 Webhook 等问题）。

## 4. 启动宿主机 HTTP 触发服务（给 n8n 用）

n8n 不直接跑 Python 脚本，而是 POST 请求宿主机：
`http://host.docker.internal:8765/run`

因此你必须先在宿主机启动 `host_trigger.py`：
```bash
cd d:\桌面\news
python host_trigger.py
```

启动后它会监听：
`http://127.0.0.1:8765/run`

当 n8n 调用 `...:8765/run` 时，宿主机会执行：
`python run_all.py`。

## 5. 在 n8n 上创建定时工作流

### 5.1 新建工作流
在 n8n 里进入 Workflows（工作流），创建一个新的工作流（从零开始）。

### 5.2 添加第一个节点：Schedule Trigger（定时触发）
选择：
- `Cron` 或 `Every day`

如果用 Cron：例如每天 8:00（按你 n8n 的时区）：
- `0 8 * * *`

### 5.3 添加第二个节点：HTTP Request（HTTP 请求）
用 `Schedule Trigger` 输出连到 `HTTP Request`。

HTTP Request 配置建议：
- Method：`POST`
- URL：`http://host.docker.internal:8765/run`
- Authentication：`None`
- Send Body：通常可以关掉；若必须填写，就传空 JSON：`{}`
- Headers：
  - 如果你在 `.env` 设置了 `N8N_TRIGGER_KEY`，则需要加一行：
    - `X-API-Key` = 你的密钥
  - 如果你没设置 `N8N_TRIGGER_KEY`，就不要加这行 Header。

### 5.4 手动测试一次
点 `Execute workflow`（执行工作流）。

你需要看到：
- `HTTP Request` 节点返回成功（HTTP 状态 200）
- 返回体里通常包含 `ok: true`

失败时返回体里会有 `returncode`、`stderr`，用于定位是 AI 或飞书步骤出错。

### 5.5 开启自动运行
把工作流设置为启用（Active/启用）。
之后到 Cron 时间点会自动执行。

## 6. 开机/关机注意事项（是否需要一直开着）

- 需要一直“跑着”的是两部分：
  1. Docker 里的 n8n 服务（否则 n8n 没法触发工作流）
  2. 宿主机上的 `host_trigger.py`（否则 n8n 调不到 `...:8765/run`）
- 电脑关机：服务会停止，触发不会自动补跑；开机后到下次时间点才继续。

## 7. 常见问题快速定位

### 7.1 n8n 里 HTTP Request 报连接失败/502/超时
- 宿主机没启动 `host_trigger.py`
- `HOST_TRIGGER_PORT` 端口不一致（改了要改 URL）
- Docker 网络问题：确认 `host.docker.internal` 在你的 Docker 环境可用

### 7.2 n8n 返回 401 unauthorized
- 你设置了 `N8N_TRIGGER_KEY`
- 但 n8n HTTP Request 没带 `X-API-Key` 或带错了值

### 7.3 返回 ok:false 且 stderr 显示飞书/DeepSeek 请求失败
- 检查 `.env`：
  - `DEEPSEEK_API_KEY` 是否有效
  - `FEISHU_WEBHOOK` 是否正确且机器人未被禁用/删除
- 也可能是网络问题（超时/被限流）

---
如果你愿意，把 n8n 返回的 HTTP Request 节点输出（打码密钥后）贴出来，我可以帮你精确定位是第 2 步（AI）还是第 3 步（飞书）失败。

