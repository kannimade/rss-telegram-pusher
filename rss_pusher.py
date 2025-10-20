import feedparser
import logging
import asyncio
import json
import os
import requests
from telegram import Bot
from telegram.error import TelegramError

# 从环境变量读取配置（请确保与仓库机密名称一致）
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RSS_URL = os.getenv("RSS_URL")
GIST_ID = os.getenv("GIST_ID")  # Gist ID
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")  # 已修正的GitHub令牌机密名称

# 配置日志（详细输出所有步骤，方便调试）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# 从Gist读取已发送的post_id
def load_sent_posts():
    try:
        # 新增：打印令牌前5字符，确认是否正确获取
        logging.info(f"当前使用的GitHub令牌前5字符：{GITHUB_TOKEN[:5] if GITHUB_TOKEN else '空'}")
        logging.info(f"开始读取Gist（ID：{GIST_ID}）")
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}  # 确保格式是"token 令牌"
        response = requests.get(
            f"https://api.github.com/gists/{GIST_ID}",
            headers=headers,
            timeout=10  # 超时设置
        )
        # 打印读取请求的状态码和响应内容
        logging.info(f"Gist读取状态码：{response.status_code}")
        logging.info(f"Gist读取响应内容：{response.text[:500]}")  # 只显示前500字符，避免过长
        
        response.raise_for_status()  # 触发HTTP错误（如404、401）
        gist_data = response.json()
        # 确认Gist中存在sent_posts.json文件
        if "sent_posts.json" not in gist_data["files"]:
            logging.warning("Gist中未找到sent_posts.json，返回空列表")
            return []
        # 解析文件内容
        content = gist_data["files"]["sent_posts.json"]["content"]
        sent_ids = json.loads(content)
        logging.info(f"成功读取已发送ID：{sent_ids}")
        return sent_ids
    except Exception as e:
        logging.error(f"读取Gist失败：{str(e)}", exc_info=True)  # 打印完整错误堆栈
        return []

# 保存已发送的post_id到Gist
def save_sent_posts(post_ids):
    try:
        # 新增：打印令牌前5字符，确认是否正确获取
        logging.info(f"当前使用的GitHub令牌前5字符：{GITHUB_TOKEN[:5] if GITHUB_TOKEN else '空'}")
        logging.info(f"准备保存ID到Gist：{post_ids}")
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}  # 确保格式是"token 令牌"
        data = {
            "files": {
                "sent_posts.json": {  # 严格匹配Gist中的文件名（区分大小写）
                    "content": json.dumps(post_ids, ensure_ascii=False, indent=2)  # 格式化JSON，便于查看
                }
            }
        }
        response = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            json=data,
            headers=headers,
            timeout=10
        )
        # 打印更新请求的状态码和响应内容
        logging.info(f"Gist更新状态码：{response.status_code}")
        logging.info(f"Gist更新响应内容：{response.text[:500]}")
        
        response.raise_for_status()
        logging.info(f"成功保存ID到Gist：{post_ids}")
    except Exception as e:
        logging.error(f"保存Gist失败：{str(e)}", exc_info=True)  # 打印完整错误堆栈

# 获取RSS更新
def fetch_updates():
    try:
        logging.info(f"开始获取RSS：{RSS_URL}")
        feed = feedparser.parse(RSS_URL)
        if feed.bozo:  # feedparser解析错误标识
            logging.error(f"RSS解析错误：{feed.bozo_exception}")
            return None
        logging.info(f"成功获取RSS，共{len(feed.entries)}条条目")
        return feed
    except Exception as e:
        logging.error(f"获取RSS失败：{str(e)}", exc_info=True)
        return None

# 转义Markdown特殊字符
def escape_markdown(text):
    special_chars = r"_*~`>#+-.!()"  # 补充常见特殊字符
    for char in special_chars:
        text = text.replace(char, f"\{char}")
    return text

# 发送消息到Telegram
async def send_message(bot, title, link):
    try:
        escaped_title = escape_markdown(title)
        escaped_link = escape_markdown(link)
        message = f"`{escaped_title}`\n{escaped_link}"
        logging.info(f"准备发送消息：{message[:100]}")  # 显示前100字符
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode='MarkdownV2'
        )
        logging.info("消息发送成功")
    except TelegramError as e:
        logging.error(f"Telegram发送失败：{str(e)}", exc_info=True)

# 检查更新并处理新帖子
async def check_for_updates(sent_post_ids):
    updates = fetch_updates()
    if not updates:
        return

    new_posts = []
    for entry in updates.entries:
        # 提取post_id（适配你的URL格式：https://www.dalao.net/thread-51588.htm）
        try:
            # 从URL中提取数字ID（如51588）
            guid_parts = entry.guid.split('-')
            if len(guid_parts) < 2:
                logging.warning(f"无法解析guid：{entry.guid}，跳过该条目")
                continue
            post_id = guid_parts[-1].split('.')[0]
            # 验证ID是否为数字（确保提取正确）
            if not post_id.isdigit():
                logging.warning(f"提取的ID不是数字：{post_id}，跳过该条目")
                continue
            logging.info(f"解析到有效条目：ID={post_id}，标题={entry.title[:20]}...")
            if post_id not in sent_post_ids:
                new_posts.append((post_id, entry.title, entry.link))
        except Exception as e:
            logging.error(f"解析条目失败（guid={entry.guid}）：{str(e)}")
            continue

    if new_posts:
        # 按ID升序排序（确保取最新的帖子）
        new_posts.sort(key=lambda x: int(x[0]))
        latest_post_id, title, link = new_posts[0]
        logging.info(f"发现新帖子，ID={latest_post_id}，准备发送")
        # 发送到Telegram
        async with Bot(token=TELEGRAM_TOKEN) as bot:
            await send_message(bot, title, link)
        # 更新已发送列表并保存
        sent_post_ids.append(latest_post_id)
        logging.info(f"已添加新ID到列表：{sent_post_ids}")
        save_sent_posts(sent_post_ids)
    else:
        logging.info("未发现新帖子")

# 主函数
async def main():
    logging.info("===== 脚本开始运行 =====")
    sent_post_ids = load_sent_posts()
    try:
        await check_for_updates(sent_post_ids)
    except Exception as e:
        logging.error(f"主逻辑执行失败：{str(e)}", exc_info=True)
    logging.info("===== 脚本运行结束 =====")

if __name__ == "__main__":
    asyncio.run(main())
