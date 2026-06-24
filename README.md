# RSS 到 Telegram 推送工具

这个仓库通过 GitHub Actions 定时读取一个或多个 RSS 源，并把新条目推送到 Telegram 频道或群组。

## 功能

- 支持单 RSS 源 `RSS_URL`，兼容旧配置
- 支持多 RSS 源 `RSS_URLS`
- 使用 `sent_posts.json` 去重，避免重复推送
- 可选提取 RSS 条目中的图片并发送到 Telegram
- 可配合自建 RSSHub 推送 X/Twitter、Bangumi 等来源

## GitHub Secrets

在仓库 `Settings -> Secrets and variables -> Actions -> Secrets` 中配置：

| 名称 | 必填 | 说明 |
| --- | --- | --- |
| `TELEGRAM_TOKEN` | 是 | Telegram Bot Token |
| `CHAT_ID` | 是 | Telegram 频道或群组 ID |
| `MY_GITHUB_TOKEN` | 是 | 用于把 `sent_posts.json` 提交回仓库的 GitHub token |
| `RSS_URL` | 否 | 单个 RSS 源，旧配置可继续使用 |
| `RSS_URLS` | 否 | 多 RSS 源配置；设置后优先于 `RSS_URL` |
| `EXTRA_RSS_URLS` | 否 | 在保留旧 `RSS_URL` 的同时追加 RSS 源 |

`RSS_URLS` 支持 JSON：

```json
[
  {
    "name": "bangumi",
    "url": "https://example.com/bangumi.xml",
    "prefix": "主人"
  },
  {
    "name": "x",
    "url": "https://rsshub.asashiki.com/twitter/user/asashiki_/includeReplies=0&includeRts=1&readable=1&addLinkForPics=1&showTimestampInDescription=1&heightOfPics=180?key=YOUR_ACCESS_KEY",
    "interval_minutes": 30,
    "prefix": "主人发推了："
  }
]
```

也支持换行文本：

```text
bangumi=https://example.com/bangumi.xml
x=https://rsshub.asashiki.com/twitter/user/asashiki_/includeReplies=0&includeRts=1&readable=1&addLinkForPics=1&showTimestampInDescription=1&heightOfPics=180?key=YOUR_ACCESS_KEY
```

如果需要为不同 RSS 源设置不同检查间隔或提示字，请使用 JSON 格式。`interval_minutes` 表示该 RSS 源至少间隔多少分钟才会被请求一次；GitHub Actions 本身仍可保持较高频率运行。

如果现有 Bangumi 地址已经配置在 `RSS_URL`，只需要新增 `EXTRA_RSS_URLS`：

```json
[
  {
    "name": "x",
    "url": "https://rsshub.asashiki.com/twitter/user/asashiki_/includeReplies=0&includeRts=1&readable=1&addLinkForPics=1&showTimestampInDescription=1&heightOfPics=180?key=YOUR_ACCESS_KEY",
    "interval_minutes": 30,
    "prefix": "主人发推了："
  }
]
```

## GitHub Variables

在 `Settings -> Secrets and variables -> Actions -> Variables` 中可以按需配置：

| 名称 | 默认值 | 说明 |
| --- | --- | --- |
| `SEND_IMAGES` | `0` | 设为 `1` 时发送 RSS 条目中的图片 |
| `MAX_IMAGES_PER_POST` | `4` | 每条最多发送几张图 |
| `MAX_PUSH_PER_RUN` | `15` | 单次 workflow 最多推送几条 |
| `MESSAGE_PREFIX` | `主人` | 默认消息提示字；也可以在 `RSS_URLS` 的单个源里用 `prefix` 覆盖 |

## 自建 RSSHub 推送 X/Twitter

RSSHub 的 Twitter 路由需要自建实例并配置 X 登录态。建议使用非重要小号。

1. 在 VPS 上准备目录：

```bash
mkdir -p ~/rsshub
cd ~/rsshub
```

2. 复制本仓库的 `deploy/rsshub.compose.yml` 和 `deploy/rsshub.env.example` 到 VPS，并把示例环境文件改名：

```bash
cp rsshub.env.example .env
```

3. 编辑 `.env`：

```env
ACCESS_KEY=一串长随机字符串
TWITTER_AUTH_TOKEN=浏览器Cookie里的auth_token
# 可选。当前 Twitter 路由不能只靠用户名/密码工作。
# TWITTER_USERNAME=你的X小号登录名
# TWITTER_PASSWORD=你的X小号密码
# TWITTER_AUTHENTICATION_SECRET=如果开了2FA则填TOTP secret
```

4. 启动 RSSHub：

```bash
docker compose -f rsshub.compose.yml up -d
```

5. 本机测试：

```bash
curl "http://127.0.0.1:1200/twitter/user/asashiki_/includeReplies=0&includeRts=1&readable=1&addLinkForPics=1&showTimestampInDescription=1&heightOfPics=180?key=ACCESS_KEY"
```

如果 GitHub Actions 要访问这个 RSSHub，需要用 Caddy 或 Nginx 反代到 HTTPS 域名，再把完整 RSS 地址填入 `RSS_URLS`。
