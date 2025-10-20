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

# 存储已发送ID的本地文件
POSTS_FILE = "sent_posts.json"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 读取已发送的post_id
def load_sent_posts():
    try:
        if os.path.exists(POSTS_FILE):
            with open(POSTS_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else []
        logging.info("首次运行，创建空ID列表")
        return []
    except Exception as e:
        logging.error(f"读取已发送ID失败：{str(e)}")
        return []

# 保存已发送的post_id
def save_sent_posts(post_ids):
    try:
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(post_ids, f, ensure_ascii=False, indent=2)
        logging.info(f"已保存ID列表（共{len(post_ids)}条）：{post_ids}")
    except Exception as e:
        logging.error(f"保存已发送ID失败：{str(e)}")

# 获取RSS更新
def fetch_updates():
    try:
        logging.info(f"获取RSS源：{RSS_URL}")
        feed = feedparser.parse(RSS_URL)
        if feed.bozo:
            logging.error(f"RSS解析错误：{feed.bozo_exception}")
            return None
        logging.info(f"成功获取{len(feed.entries)}条RSS条目")
        return feed
    except Exception as e:
        logging.error(f"获取RSS失败：{str(e)}")
        return None

# 转义Markdown特殊字符
def escape_markdown(text):
    special_chars = r"_*~`>#+-.!()"
    for char in special_chars:
        text = text.replace(char, f"\{char}")
    return text

# 发送单条消息到Telegram（带间隔）
async def send_message(bot, title, link, delay=3):
    try:
        # 发送前等待指定秒数（避免频率限制）
        await asyncio.sleep(delay)
        escaped_title = escape_markdown(title)
        escaped_link = escape_markdown(link)
        message = f"`{escaped_title}`\n{escaped_link}"
        logging.info(f"发送消息：{message[:100]}")
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="MarkdownV2"
        )
        logging.info("消息发送成功")
        return True
    except TelegramError as e:
        logging.error(f"Telegram发送失败：{str(e)}")
        return False

# 检查更新并推送所有新帖子
async def check_for_updates(sent_post_ids):
    updates = fetch_updates()
    if not updates:
        return

    new_posts = []
    for entry in updates.entries:
        try:
            # 提取帖子ID（适配URL格式）
            guid_parts = entry.guid.split("-")
            if len(guid_parts) < 2:
                logging.warning(f"无效GUID格式：{entry.guid}，跳过")
                continue
            post_id = guid_parts[-1].split(".")[0]
            if not post_id.isdigit():
                logging.warning(f"提取的ID非数字：{post_id}，跳过")
                continue
            logging.info(f"解析到有效ID：{post_id}，标题：{entry.title[:20]}...")
            if post_id not in sent_post_ids:
                new_posts.append((post_id, entry.title, entry.link))
        except Exception as e:
            logging.error(f"解析条目失败（GUID：{entry.guid}）：{str(e)}")
            continue

    if new_posts:
        # 按ID升序排序（从旧到新推送），若想从新到旧则用reverse=True
        new_posts.sort(key=lambda x: int(x[0]))  # 从小到大：旧→新
        # new_posts.sort(key=lambda x: int(x[0]), reverse=True)  # 从大到小：新→旧

        logging.info(f"发现{len(new_posts)}条新帖子，准备依次推送（间隔3秒）")
        async with Bot(token=TELEGRAM_TOKEN) as bot:
            # 逐条推送，每条间隔3秒
            for i, (post_id, title, link) in enumerate(new_posts):
                # 第一条消息延迟0秒，后续每条延迟3秒
                success = await send_message(bot, title, link, delay=3 if i > 0 else 0)
                if success:
                    sent_post_ids.append(post_id)  # 仅成功推送的ID才记录

        # 保存所有成功推送的ID
        save_sent_posts(sent_post_ids)
    else:
        logging.info("无新帖子需要推送")

# 主函数
async def main():
    logging.info("===== 脚本开始运行 =====")
    sent_post_ids = load_sent_posts()
    try:
        await check_for_updates(sent_post_ids)
    except Exception as e:
        logging.error(f"主逻辑执行失败：{str(e)}")
    logging.info("===== 脚本运行结束 =====")

if __name__ == "__main__":
    asyncio.run(main())
