一、准备工作

 1. 创建 Telegram Bot
联系 Telegram 官方机器人 @BotFather，发送`/newbot`，按提示设置名称和用户名，最终会获得一个Bot Token（格式：123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11），保存备用。
 2. 获取群组 ID
将你的 Bot 加入群组，然后在群组内发送任意消息，再向 @getidsbot 发送该消息的转发，会返回群组 ID（格式：-1001234567890），保存备用。##创建访问令牌
 3. 创建个人访问令牌（经典），[创建地址][2]，自定义令牌名称，有效期建议90天，令牌范围必须勾选`repo`（写入仓库），完成创建后只会显示一次令牌token，复制保存。

二、设置仓库密钥

步骤： Settings → Secrets and variables → Actions → Repository → New repository secret

添加以下密钥：
TELEGRAM_TOKEN：你的 Telegram Bot Token
CHAT_ID：目标群组 ID
RSS_URL：你的 RSS 源地址
MY_GITHUB_TOKEN：GitHub 令牌token

添加完成后如图：
[![1760968222781.png](https://img.cdn.vin/dai/20251020/1760968222781.png)](https://img.cdn.vin/dai/20251020/1760968222781.png)

三、测试与验证

进入仓库 → 点击顶部 “Actions” → 左侧选择 “RSS to Telegram” → 点击 “Run workflow” → “Run workflow”，手动触发一次运行，查看群内是否有信息，如果没有，在仓库页点击顶部导航栏的Actions标签，进入工作流运行记录页面，可查看报错原因。

----------
注：此脚本用于[本论坛][3]使用，适配本论坛帖子url，其它网站需稍作调整才可正常使用。



  [2]: https://github.com/settings/tokens
  [3]: https://www.dalao.net/
