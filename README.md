# RSS 到 Telegram 推送工具配置指南

本仓库通过 GitHub Actions 实现 RSS 源内容自动推送到 Telegram 群组，以下是详细配置步骤。


## 一、准备工作

1. **创建 Telegram Bot**  
   联系 Telegram 官方机器人 @BotFather，发送指令 `/newbot`，按提示设置机器人名称和用户名（用户名需以 `bot` 或 `Bot` 结尾）。完成后会获得 Bot Token（格式：`123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`），请妥善保存备用。

2. **获取群组 ID**  
   将创建的 Bot 加入目标 Telegram 群组，在群组内发送任意消息，然后将该消息转发给 @getidsbot。@getidsbot 会返回群组 ID（格式：`-1001234567890`），保存备用。

3. **创建 GitHub 个人访问令牌**  
   访问 [个人访问令牌创建地址][2]，选择“生成经典令牌”：  
   - 自定义令牌名称（如 `rss-to-telegram`）；  
   - 有效期建议设置为 90 天；  
   - **必须勾选 `repo` 权限**（用于写入仓库）；  
   创建完成后，令牌（token）只会显示一次，请立即复制并保存。


## 二、设置仓库密钥

步骤：仓库主页 → Settings → Secrets and variables → Actions → 点击右上角「New repository secret」，依次添加以下 4 个密钥：

| 密钥名称         | 说明                          |
|------------------|-------------------------------|
| `TELEGRAM_TOKEN` | 第一步获取的 Telegram Bot Token |
| `CHAT_ID`        | 第二步获取的群组 ID           |
| `RSS_URL`        | 需推送的 RSS 源地址           |
| `MY_GITHUB_TOKEN`| 第三步创建的 GitHub 令牌      |

添加完成后示例：  
[![密钥设置示例](https://img.cdn.vin/dai/20251020/1760968222781.png)](https://img.cdn.vin/dai/20251020/1760968222781.png)


## 三、测试与验证

1. 进入仓库主页 → 点击顶部「Actions」；  
2. 左侧导航栏选择工作流「RSS to Telegram」；  
3. 点击「Run workflow」按钮，在弹出窗口中再次点击「Run workflow」手动触发运行；  
4. 运行后查看目标 Telegram 群组是否收到消息：  
   - 若收到消息，说明配置成功；  
   - 若未收到，可在 Actions 页面进入对应工作流的运行记录，查看报错信息排查问题。


## 注意事项
- 本脚本默认适配 [大佬论坛（www.dalao.net）][3] 的帖子 URL 结构（/thread-[tid].htm），相同结构的网站可以直接使用，其他网站可能需要调整代码中的 URL 解析逻辑才能正常运行。


[2]: https://github.com/settings/tokens
[3]: https://www.dalao.net/
