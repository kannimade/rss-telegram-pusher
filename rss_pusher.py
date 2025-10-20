import feedparser
import logging
import asyncio
import json
import os
import requests  # 用于操作GitHub Gist
from telegram import Bot
from telegram.error import TelegramError

# 从环境变量读取配置（避免硬编码敏感信息）
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RSS_URL = os.getenv("RSS_URL")
GIST_ID = os.getenv("GIST_ID")  # 存储已发送帖子ID的Gist ID
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")  # 操作Gist的GitHub令牌

# 从GitHub Gist读取已发送的帖子ID
def load_sent_posts():
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        # 调用Gist API获取文件内容
        response = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers
        )
        response.raise_for_status()  # 若请求失败，抛出异常
        # 解析Gist中的sent_posts.json文件内容
        gist_data = response.json()
        content = gist_data["files"]["sent_posts.json"]["content"]
        return json.loads(content)
    except Exception as e:
        logging.warning(f"读取Gist失败（首次运行可能为空，忽略即可）：{e}")
        return []  # 初始状态为空列表

# 保存已发送的帖子ID到GitHub Gist
def save_sent_posts(post_ids):
    try:
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        # 构造更新Gist的请求数据
        data = {
            "files": {
                "sent_posts.json": {
                    "content": json.dumps(post_ids, ensure_ascii=False)  # 保存为JSON格式
                }
            }
        }
        # 调用Gist API更新内容
        response = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            json=data,
            headers=headers
        )
        response.raise_for_status()
        logging.info("已发送的帖子ID已成功更新到Gist")
    except Exception as e:
        logging.error(f"保存到Gist失败：{e}")

# 从RSS源获取更新
def fetch_updates():
    try:
        return feedparser.parse(RSS_URL)
    except Exception as e:
        logging.error(f"获取RSS更新失败：{e}")
        return None

# 转义Markdown特殊字符（避免Telegram解析错误）
def escape_markdown(text):
    special_chars = r"_*~`>#+-.!"
    for char in special_chars:
        text = text.replace(char, f"\{char}")
    return text

# 发送消息到Telegram群
async def send_message(bot, title, link):
    escaped_title = escape_markdown(title)
    escaped_link = escape_markdown(link)
    # 构造MarkdownV2格式消息（标题用反引号包裹，链接单独一行）
    message = f"`{escaped_title}`\n{escaped_link}"
    try:
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='MarkdownV2'
        )
        logging.info(f"消息发送成功：{escaped_title}")
    except TelegramError as e:
        logging.error(f"发送消息到Telegram失败：{e}")

# 检查RSS更新并处理新内容
async def check_for_updates(sent_post_ids):
    updates = fetch_updates()
    if updates is None:
        return  # 若RSS获取失败，直接返回

    new_posts = []
    for entry in updates.entries:
        # 提取帖子ID（根据你的RSS源格式调整，这里沿用你原脚本的逻辑）
        post_id = entry.guid.split('-')[-1].split('.')[0]
        if post_id not in sent_post_ids:
            new_posts.append((post_id, entry.title, entry.link))  # 存储ID、标题、链接

    if new_posts:
        # 按ID升序排序，取最新的帖子（若需发送所有新帖，可循环遍历new_posts）
        new_posts.sort(key=lambda x: int(x[0]))
        latest_post_id, title, link = new_posts[0]
        # 发送消息到Telegram
        async with Bot(token=TELEGRAM_TOKEN) as bot:
            await send_message(bot, title, link)
        # 更新已发送ID列表并保存到Gist
        sent_post_ids.append(latest_post_id)
        save_sent_posts(sent_post_ids)

# 主函数（单次运行，由GitHub Actions定时触发）
async def main():
    logging.basicConfig(level=logging.INFO)  # 开启日志，方便调试
    sent_post_ids = load_sent_posts()  # 加载已发送的帖子ID
    try:
        await check_for_updates(sent_post_ids)
    except Exception as e:
        logging.error(f"执行过程出错：{e}")

if __name__ == "__main__":
    asyncio.run(main())
