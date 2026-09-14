#!/usr/bin/env python3
"""
youtube_digest.py

Раз в день собирает ВСЕ видео (включая Shorts), загруженные на YouTube-канал
с прошлой сводки, и присылает про них одно сообщение-список в Telegram —
вместо мгновенного оповещения на каждое видео по отдельности.

Рассчитан на запуск по расписанию (например, раз в день через GitHub
Actions) — хранит время последней сводки в digest_state.json, чтобы не
пропустить и не задублировать видео между запусками.

Требуемые переменные окружения:
  TELEGRAM_BOT_TOKEN   - токен бота от @BotFather
  TELEGRAM_CHAT_ID     - id канала/чата, куда слать сводку
  YOUTUBE_CHANNEL_ID   - ID канала YouTube (UCxxxxxxxx...)
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest_state.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")

YOUTUBE_ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

DEFAULT_STATE = {
    # ISO-время последней отправленной сводки. None = ни разу не
    # запускались — при первом запуске просто запоминаем текущий момент
    # как точку отсчёта и НЕ шлём сводку по всем видео, что уже есть в
    # фиде (иначе первый же запуск вывалит сразу все 15 последних видео).
    "last_digest_at": None,
}


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_STATE)
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_STATE)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def http_get(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def http_post_form(url, data, timeout=15):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[error] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }
    try:
        resp = http_post_form(url, data)
        result = json.loads(resp)
        if not result.get("ok"):
            print(f"[error] Telegram API вернул ошибку: {result}", file=sys.stderr)
            return False
        return True
    except urllib.error.URLError as e:
        print(f"[error] Не удалось отправить сообщение в Telegram: {e}", file=sys.stderr)
        return False


def fetch_recent_uploads():
    """
    Возвращает список видео из RSS-фида канала, отсортированный от
    старых к новым: [{"video_id", "title", "published"}], где published —
    объект datetime с таймзоной. В фиде обычно 15 последних видео.
    """
    url = "https://www.youtube.com/feeds/videos.xml?" + urllib.parse.urlencode(
        {"channel_id": YOUTUBE_CHANNEL_ID}
    )
    xml_text = http_get(url)
    root = ET.fromstring(xml_text)
    videos = []
    for entry in root.findall("atom:entry", YOUTUBE_ATOM_NS):
        video_id_el = entry.find("yt:videoId", YOUTUBE_ATOM_NS)
        title_el = entry.find("atom:title", YOUTUBE_ATOM_NS)
        published_el = entry.find("atom:published", YOUTUBE_ATOM_NS)
        if video_id_el is None or published_el is None:
            continue
        try:
            published = datetime.fromisoformat(published_el.text.strip())
        except ValueError:
            continue
        videos.append({
            "video_id": video_id_el.text.strip(),
            "title": title_el.text.strip() if title_el is not None and title_el.text else "",
            "published": published,
        })
    videos.sort(key=lambda v: v["published"])
    return videos


def build_digest_message(videos):
    lines = [f"🎬 <b>Новые видео за день ({len(videos)}):</b>", ""]
    for i, v in enumerate(videos, start=1):
        title = v["title"] or "(без названия)"
        lines.append(f"{i}. {title}")
        lines.append(f"👉 https://youtube.com/watch?v={v['video_id']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def main():
    if not YOUTUBE_CHANNEL_ID:
        print("[error] YOUTUBE_CHANNEL_ID не задан", file=sys.stderr)
        return

    state = load_state()
    now = datetime.now(timezone.utc)

    try:
        videos = fetch_recent_uploads()
    except (urllib.error.URLError, ET.ParseError) as e:
        print(f"[warn] Не удалось получить список видео: {e}", file=sys.stderr)
        return

    last_digest_at_raw = state.get("last_digest_at")

    if last_digest_at_raw is None:
        # Первый запуск — не шлём сводку по всей истории, что уже есть в
        # фиде, просто запоминаем текущий момент как точку отсчёта.
        state["last_digest_at"] = now.isoformat()
        save_state(state)
        return

    last_digest_at = datetime.fromisoformat(last_digest_at_raw)
    new_videos = [v for v in videos if v["published"] > last_digest_at]

    if new_videos:
        text = build_digest_message(new_videos)
        send_telegram_message(text)

    state["last_digest_at"] = now.isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
