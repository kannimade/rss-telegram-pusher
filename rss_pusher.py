import feedparser
import logging
import asyncio
import json
import os
from telegram import Bot
from telegram.error import TelegramError

# 从环境变量读取配置
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RSS_URL = os.getenv("RSS_URL")

# 存储已发送ID的文件（仓库中的本地文件）
POSTS_FILE = "sent_posts.json"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 读取已发送的post_id（从仓库文件）
def load_sent_posts():
    try:
        if os.path.exists(POSTS_FILE):
            with open(POSTS_FILE, "r", encoding="utf-8") as f:
                data = f.read().strip()
                return json.loads(data) if data else []
        logging.info("首次运行，无已发送ID文件，返回空列表")
        return []
    except Exception as e:
        logging.error(f"读取已发送ID失败：{e}")
        return []

# 保存已发送的post_id（到仓库文件）
def save_sent_posts(post_ids):
    try:
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(post_ids, f, ensure_ascii=False, indent=2)
        logging.info(f"已保存最新ID列表：{post_ids}")
    except Exception as e:
        logging.error(f"保存已发送ID失败：{e}")

# 获取RSS更新
def fetch_updates():
    try:
        logging.info(f"获取RSS：{RSS_URL}")
        feed = feedparser.parse(RSS_URL)
        if feed.bozo:
            logging.error(f"RSS解析错误：{feed.bozo_exception}")
            return None
        logging.info(f"成功获取{len(feed.entries)}条RSS条目")
        return feed
    except Exception as e:
        logging.error(f"获取RSS失败：{e}")
        return None

# 转义Markdown特殊字符
def escape_markdown(text):
    special_chars = r"_*~`>#+-.!()"
    for char in special_chars:
        text = text.replace(char, f"\{char}")
    return text

# 发送消息到Telegram
async def send_message(bot, title, link):
    try:
        escaped_title = escape_markdown(title)
        escaped_link = escape_markdown(link)
        message = f"`{escaped_title}`\n{escaped_link}"
        logging.info(f"发送消息：{message[:100]}")
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="MarkdownV2")
        logging.info("消息发送成功")
    except TelegramError as e:
        logging.error(f"Telegram发送失败：{e}")

# 检查更新并处理
async def check_for_updates(sent_post_ids):
    updates = fetch_updates()
    if not updates:
        return

    new_posts = []
    for entry in updates.entries:
        try:
            # 提取ID（适配你的URL格式）
            post_id = entry.guid.split("-")[-1].split(".")[0]
            if not post_id.isdigit():
                logging.warning(f"无效ID：{post_id}，跳过")
                continue
            logging.info(f"解析到ID：{post_id}，标题：{entry.title[:20]}...")
            if post_id not in sent_post_ids:
                new_posts.append((post_id, entry.title, entry.link))
        except Exception as e:
            logging.error(f"解析条目失败：{e}")
            continue

    if new_posts:
        new_posts.sort(key=lambda x: int(x[0]))  # 按ID升序
        latest_post_id, title, link = new_posts[0]
        logging.info(f"发现新帖子ID：{latest_post_id}")
        async with Bot(token=TELEGRAM_TOKEN) as bot:
            await send_message(bot, title, link)
        # 更新ID列表并保存
        sent_post_ids.append(latest_post_id)
        save_sent_posts(sent_post_ids)
    else:
        logging.info("无新帖子")

# 主函数
async def main():
    logging.info("===== 脚本开始 =====")
    sent_post_ids = load_sent_posts()
    try:
        await check_for_updates(sent_post_ids)
    except Exception as e:
        logging.error(f"执行失败：{e}")
    logging.info("===== 脚本结束 =====")

if __name__ == "__main__":
    asyncio.run(main())
