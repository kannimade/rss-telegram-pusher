import asyncio
import html
import json
import logging
import os
import re
import time
from urllib.parse import urlparse

import feedparser
from telegram import Bot, InputMediaPhoto
from telegram.error import TelegramError

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
RSS_URL = os.getenv("RSS_URL")
RSS_URLS = os.getenv("RSS_URLS")
EXTRA_RSS_URLS = os.getenv("EXTRA_RSS_URLS")
POSTS_FILE = "sent_posts.json"
STATE_FILE = "rss_state.json"
SEND_IMAGES = os.getenv("SEND_IMAGES", "0").lower() in ("1", "true", "yes", "on")
MESSAGE_PREFIX = os.getenv("MESSAGE_PREFIX", "主人")
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

def env_int(name, default):
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logging.warning(f"环境变量 {name}={value!r} 不是整数，使用默认值 {default}")
        return default

MAX_PUSH_PER_RUN = env_int("MAX_PUSH_PER_RUN", 15)
MAX_STORED_IDS = env_int("MAX_STORED_IDS", 5000)
MAX_IMAGES_PER_POST = env_int("MAX_IMAGES_PER_POST", 4)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

URL_REGEX = re.compile(r"""https?://[^\s<>"']+""")
HREF_REGEX = re.compile(r"""href=["']([^"']+)""")
IMG_SRC_REGEX = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")

def _parse_feed_config_value(value, default_name_prefix="feed"):
    configs = []
    raw = (value or "").strip()
    if not raw:
        return configs

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            for index, item in enumerate(parsed, start=1):
                if isinstance(item, str):
                    configs.append({"name": f"{default_name_prefix}{index}", "url": item.strip()})
                elif isinstance(item, dict):
                    url = (item.get("url") or "").strip()
                    name = (item.get("name") or f"{default_name_prefix}{index}").strip()
                    if url:
                        config = {"name": name, "url": url}
                        if item.get("interval_minutes"):
                            config["interval_minutes"] = item.get("interval_minutes")
                        if item.get("prefix"):
                            config["prefix"] = item.get("prefix")
                        configs.append(config)
        elif isinstance(parsed, dict):
            for name, url in parsed.items():
                if url:
                    configs.append({"name": str(name).strip(), "url": str(url).strip()})
        return configs
    except json.JSONDecodeError:
        pass

    separators = "\n" if "\n" in raw else ","
    for index, item in enumerate(raw.split(separators), start=1):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, url = item.split("=", 1)
            configs.append({"name": name.strip(), "url": url.strip()})
        else:
            configs.append({"name": f"{default_name_prefix}{index}", "url": item})
    return configs

def parse_feed_configs():
    """Return feed configs from RSS_URLS, RSS_URL, and EXTRA_RSS_URLS.

    RSS_URLS and EXTRA_RSS_URLS accept either:
    - JSON array: [{"name": "bangumi", "url": "https://..."}, ...]
    - newline/comma separated values: "bangumi=https://...\nx=https://..."
    """
    configs = []

    if RSS_URLS:
        configs.extend(_parse_feed_config_value(RSS_URLS))
    elif RSS_URL:
        configs.append({"name": "default", "url": RSS_URL.strip()})

    configs.extend(_parse_feed_config_value(EXTRA_RSS_URLS, default_name_prefix="extra"))

    return [config for config in configs if config.get("url")]

def load_feed_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else {}
    except Exception as e:
        logging.error(f"读取RSS状态失败：{str(e)}")
    return {}

def save_feed_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
        logging.info("已保存RSS状态")
    except Exception as e:
        logging.error(f"保存RSS状态失败：{str(e)}")

def should_check_feed(feed_config, state, now=None):
    interval_minutes = feed_config.get("interval_minutes")
    if not interval_minutes:
        return True

    try:
        interval_seconds = int(interval_minutes) * 60
    except (TypeError, ValueError):
        logging.warning(f"RSS源[{feed_config['name']}] interval_minutes 无效，仍然检查")
        return True

    if interval_seconds <= 0:
        return True

    now = now or time.time()
    last_checked_at = state.get(feed_config["name"], {}).get("last_checked_at")
    if not last_checked_at:
        return True

    due = now - float(last_checked_at) >= interval_seconds
    if not due:
        remaining = int(interval_seconds - (now - float(last_checked_at)))
        logging.info(f"RSS源[{feed_config['name']}] 未到检查间隔，跳过，剩余约 {remaining} 秒")
    return due

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

def save_sent_posts(post_ids):
    try:
        if MAX_STORED_IDS > 0:
            post_ids = post_ids[-MAX_STORED_IDS:]
        with open(POSTS_FILE, "w", encoding="utf-8") as f:
            json.dump(post_ids, f, ensure_ascii=False, indent=2)
        logging.info(f"已保存ID列表（共{len(post_ids)}条）")
    except Exception as e:
        logging.error(f"保存已发送ID失败：{str(e)}")

def fetch_updates(feed_config):
    try:
        logging.info(f"获取RSS源[{feed_config['name']}]：{feed_config['url']}")
        feed = feedparser.parse(feed_config["url"])
        if feed.bozo:
            logging.error(f"RSS解析错误[{feed_config['name']}]：{feed.bozo_exception}")
            return None
        logging.info(f"成功获取[{feed_config['name']}]{len(feed.entries)}条RSS条目")
        return feed
    except Exception as e:
        logging.error(f"获取RSS失败[{feed_config['name']}]：{str(e)}")
        return None

def extract_post_id(entry):
    id_fields = ["id", "guid", "link"]
    for field in id_fields:
        value = getattr(entry, field, None)
        if value:
            candidate = value.strip()
            break
    else:
        return None

    match = re.search(r"(\d+)(?!.*\d)", candidate)
    if match:
        return match.group(1)
    return candidate

def build_sent_id(feed_name, post_id):
    if feed_name == "default":
        return str(post_id)
    return f"{feed_name}:{post_id}"

def is_already_sent(sent_post_ids, feed_name, post_id):
    post_id = str(post_id)
    return post_id in sent_post_ids or build_sent_id(feed_name, post_id) in sent_post_ids

def extract_description(entry):
    raw_description = getattr(entry, "description", None) or getattr(entry, "summary", None) or ""
    fallback = getattr(entry, "title", None) or getattr(entry, "link", None) or ""
    if raw_description:
        cleaned = raw_description.strip()
        if cleaned.startswith("<![CDATA[") and cleaned.endswith("]]>"):
            cleaned = cleaned[9:-3]
        cleaned = html.unescape(cleaned)
        cleaned = re.sub(r"<[^>]+>", "", cleaned)
        cleaned = cleaned.replace("\r", "").strip()
        if cleaned:
            return cleaned
    return fallback.strip()

def get_entry_timestamp(entry):
    time_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if time_struct:
        return time.mktime(time_struct)
    return 0

def _extract_urls_from_text(text):
    if not text:
        return []
    text = html.unescape(text)
    urls = []
    urls.extend(HREF_REGEX.findall(text))
    urls.extend(URL_REGEX.findall(text))
    return urls

def _normalize_url(url):
    if not url:
        return None
    url = html.unescape(url).strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url

def _looks_like_image_url(url):
    parsed = urlparse(url)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    return (
        path.endswith(IMAGE_EXTENSIONS)
        or "pbs.twimg.com" in host
        or "twimg.com" in host
        or "images.weserv.nl" in host
    )

def extract_image_urls(entry):
    candidates = []

    def add(url):
        url = _normalize_url(url)
        if not url or not url.startswith(("http://", "https://")):
            return
        if url not in candidates and _looks_like_image_url(url):
            candidates.append(url)

    for media in getattr(entry, "media_content", []) or []:
        if isinstance(media, dict):
            add(media.get("url"))

    for link_info in getattr(entry, "links", []) or []:
        if not isinstance(link_info, dict):
            continue
        link_type = (link_info.get("type") or "").lower()
        rel = (link_info.get("rel") or "").lower()
        href = link_info.get("href") or link_info.get("url")
        if "image" in link_type or rel == "enclosure":
            add(href)

    html_fragments = [
        getattr(entry, "summary", None),
        getattr(entry, "description", None),
        getattr(entry, "title", None),
    ]
    for content_info in getattr(entry, "content", []) or []:
        if isinstance(content_info, dict):
            html_fragments.append(content_info.get("value"))

    for fragment in html_fragments:
        if not fragment:
            continue
        for url in IMG_SRC_REGEX.findall(fragment):
            add(url)
        for url in _extract_urls_from_text(fragment):
            add(url)

    return candidates[:MAX_IMAGES_PER_POST]

def _score_entry_url(url):
    lower = url.lower()
    score = 0
    if any(domain in lower for domain in ("bangumi.tv", "bgm.tv", "chii.in")):
        score += 5
    if re.search(r"/(subject|ep|character|person|blog|group|rakuen|index|item)/\d+", lower):
        score += 60
    if re.search(r"/user/[^/]+/timeline", lower):
        score -= 100
    if re.search(r"/user/[^/]+/?$", lower):
        score -= 20
    return score

def extract_entry_link(entry):
    """Return the most specific URL for an RSS entry.

    Prefer URLs pointing to subject/episode/etc. instead of generic timeline pages.
    Tries entry.id/guid/link first, then scans entry content/summary for hrefs.
    """
    candidates = []

    def add_candidate(url):
        if not url:
            return
        url = url.strip()
        if not url:
            return
        if url.startswith("//"):
            url = f"https:{url}"
        if url not in candidates:
            candidates.append(url)

    for field in ("id", "guid", "link"):
        value = getattr(entry, field, None)
        if value:
            add_candidate(value)

    for link_info in getattr(entry, "links", []) or []:
        if isinstance(link_info, dict):
            add_candidate(link_info.get("href") or link_info.get("url"))

    for content_info in getattr(entry, "content", []) or []:
        if isinstance(content_info, dict):
            for url in _extract_urls_from_text(content_info.get("value") or ""):
                add_candidate(url)

    for text in (
        getattr(entry, "summary", None),
        getattr(entry, "description", None),
        getattr(entry, "title", None),
    ):
        for url in _extract_urls_from_text(text or ""):
            add_candidate(url)

    candidates = [url for url in candidates if url.startswith("http://") or url.startswith("https://")]
    if not candidates:
        return getattr(entry, "link", None)

    best = max(candidates, key=_score_entry_url)
    if _score_entry_url(best) < 0:
        return getattr(entry, "link", None)
    return best

def build_telegram_html(text, link=None, limit=TELEGRAM_MESSAGE_LIMIT, prefix=None):
    raw_text = str(text or "").strip()
    if not raw_text:
        raw_text = str(link or "").strip()
    prefix = MESSAGE_PREFIX if prefix is None else prefix

    suffix = ""
    while True:
        escaped_text = html.escape(raw_text + suffix)
        if link:
            escaped_link = html.escape(link, quote=True)
            message = f'{prefix}<a href="{escaped_link}">{escaped_text}</a>'
        else:
            message = f"{prefix}{escaped_text}"

        if len(message) <= limit:
            return message

        if not raw_text:
            return message[:limit]

        suffix = "…"
        overflow = len(message) - limit
        trim_by = max(1, overflow)
        raw_text = raw_text[:-trim_by]

async def send_message(bot, text, link=None, delay=3, prefix=None):
    try:
        await asyncio.sleep(delay)  # 发送间隔
        message = build_telegram_html(text, link=link, prefix=prefix)
        logging.info(f"发送消息：{message[:100]}")
        await bot.send_message(
            chat_id=CHAT_ID,
            text=message,
            parse_mode="HTML"
        )
        logging.info("消息发送成功")
        return True
    except TelegramError as e:
        logging.error(f"Telegram发送失败：{str(e)}")
        return False

async def send_post(bot, post, delay=3):
    text = post["text"]
    link = post.get("link")
    images = post.get("images") or []
    prefix = post.get("prefix")

    if not SEND_IMAGES or not images:
        return await send_message(bot, text, link=link, delay=delay, prefix=prefix)

    caption = build_telegram_html(text, link=link, limit=TELEGRAM_CAPTION_LIMIT, prefix=prefix)

    try:
        await asyncio.sleep(delay)
        if len(images) == 1:
            await bot.send_photo(
                chat_id=CHAT_ID,
                photo=images[0],
                caption=caption,
                parse_mode="HTML",
            )
        else:
            media = [InputMediaPhoto(media=images[0], caption=caption, parse_mode="HTML")]
            media.extend(InputMediaPhoto(media=url) for url in images[1:])
            await bot.send_media_group(chat_id=CHAT_ID, media=media)
        logging.info(f"图片消息发送成功，图片数：{len(images)}")
        return True
    except TelegramError as e:
        logging.error(f"Telegram图片发送失败，回退为文本：{str(e)}")
        return await send_message(bot, text, link=link, delay=0, prefix=prefix)

async def check_for_updates(sent_post_ids):
    feed_configs = parse_feed_configs()
    if not feed_configs:
        logging.error("未配置 RSS_URL 或 RSS_URLS")
        return

    state = load_feed_state()
    state_changed = False
    new_posts = []
    for feed_config in feed_configs:
        now = time.time()
        if not should_check_feed(feed_config, state, now=now):
            continue

        updates = fetch_updates(feed_config)
        state.setdefault(feed_config["name"], {})["last_checked_at"] = int(now)
        state_changed = True
        if not updates:
            continue

        for entry in updates.entries:
            try:
                post_id = extract_post_id(entry)
                if not post_id:
                    logging.warning(f"无效条目[{feed_config['name']}]，无法获取ID，跳过")
                    continue
                post_id = str(post_id)
                if is_already_sent(sent_post_ids, feed_config["name"], post_id):
                    continue

                description = extract_description(entry)
                link = extract_entry_link(entry)
                timestamp = get_entry_timestamp(entry)
                images = extract_image_urls(entry)
                sent_id = build_sent_id(feed_config["name"], post_id)
                logging.info(
                    f"解析到新条目[{feed_config['name']}] ID：{post_id}，"
                    f"内容长度：{len(description)}，图片数：{len(images)}"
                )
                new_posts.append({
                    "id": sent_id,
                    "text": description,
                    "link": link,
                    "timestamp": timestamp,
                    "images": images,
                    "feed": feed_config["name"],
                    "prefix": feed_config.get("prefix"),
                })
            except Exception as e:
                logging.error(f"解析条目失败[{feed_config['name']}]：{str(e)}")
                continue

    if new_posts:
        # 按发布时间排序（旧→新），避免连续运行时倒序刷屏。
        new_posts.sort(key=lambda x: (x["timestamp"], x["id"]))
        new_posts = new_posts[:MAX_PUSH_PER_RUN]
        logging.info(f"发现{len(new_posts)}条新信息（单次最多推{MAX_PUSH_PER_RUN}条），准备依次推送（间隔3秒）")

        async with Bot(token=TELEGRAM_TOKEN) as bot:
            for i, post in enumerate(new_posts):
                # 第一条立即发送，后续每条间隔3秒
                success = await send_post(bot, post, delay=3 if i > 0 else 0)
                if success:
                    sent_post_ids.append(post["id"])  # 仅记录成功发送的ID

        save_sent_posts(sent_post_ids)
    else:
        logging.info("无新帖子需要推送")

    if state_changed:
        save_feed_state(state)

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
