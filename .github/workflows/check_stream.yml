#!/usr/bin/env python3
"""
stream_notifier.py

Проверяет, не начался ли стрим на Twitch и/или YouTube, и если да —
присылает оповещение в Telegram-канал. Скрипт рассчитан на запуск
по расписанию (например, каждые 5 минут через GitHub Actions), а не
как постоянно висящий процесс — он сам хранит состояние в state.json,
чтобы не слать повторные оповещения на каждый прогон.

Требуемые переменные окружения:
  TELEGRAM_BOT_TOKEN   - токен бота от @BotFather
  TELEGRAM_CHAT_ID     - id канала/чата, куда слать оповещения
  TWITCH_CLIENT_ID     - Client ID приложения на dev.twitch.tv
  TWITCH_CLIENT_SECRET - Client Secret того же приложения
  TWITCH_CHANNEL       - логин канала на Twitch (как в URL twitch.tv/<login>)

Необязательные:
  YOUTUBE_CHANNEL_ID   - ID канала YouTube (UCxxxxxxxx...), для отдельного
                         оповещения о старте на YouTube. Если не задан,
                         проверка YouTube пропускается.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TWITCH_CLIENT_ID = os.environ.get("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.environ.get("TWITCH_CLIENT_SECRET", "")
TWITCH_CHANNEL = os.environ.get("TWITCH_CHANNEL", "")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID", "")

DEFAULT_STATE = {
    "twitch_live": False,
    "twitch_last_stream_id": None,
    "youtube_live": False,
    "youtube_last_video_id": None,
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


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

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


def send_telegram_photo(photo_url, caption):
    """
    Отправляет фото по URL с подписью. Telegram сам скачивает картинку по
    ссылке — файл через нас не проходит. Если по какой-то причине отправить
    фото не получилось (ссылка на превью ещё не сгенерировалась, таймаут и
    т.п.) — подстраховываемся и шлём обычное текстовое сообщение, чтобы
    оповещение в любом случае дошло.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[error] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы", file=sys.stderr)
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML",
    }
    try:
        resp = http_post_form(url, data)
        result = json.loads(resp)
        if not result.get("ok"):
            print(f"[warn] Не удалось отправить фото ({result}), шлю текстом", file=sys.stderr)
            return send_telegram_message(caption)
        return True
    except urllib.error.URLError as e:
        print(f"[warn] Не удалось отправить фото ({e}), шлю текстом", file=sys.stderr)
        return send_telegram_message(caption)


# ---------------------------------------------------------------------------
# Twitch (официальный Helix API)
# ---------------------------------------------------------------------------

def get_twitch_app_token():
    url = "https://id.twitch.tv/oauth2/token"
    data = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials",
    }
    resp = http_post_form(url, data)
    return json.loads(resp)["access_token"]


def check_twitch_live():
    """Возвращает dict с данными стрима, если канал сейчас live, иначе None."""
    if not (TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET and TWITCH_CHANNEL):
        return None
    try:
        token = get_twitch_app_token()
        url = "https://api.twitch.tv/helix/streams?" + urllib.parse.urlencode(
            {"user_login": TWITCH_CHANNEL}
        )
        headers = {
            "Client-Id": TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        resp = http_get(url, headers=headers)
        payload = json.loads(resp)
        streams = payload.get("data", [])
        if streams:
            return streams[0]
        return None
    except (urllib.error.URLError, KeyError, json.JSONDecodeError) as e:
        print(f"[warn] Не удалось проверить Twitch: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# YouTube (лёгкая проверка страницы /live, без API-ключа и без квоты)
# ---------------------------------------------------------------------------

def check_youtube_live():
    """
    Возвращает video_id, если канал сейчас ведёт прямую трансляцию, иначе None.

    Использует публичную страницу https://www.youtube.com/channel/<ID>/live —
    если канал не в эфире, YouTube отдаёт обычную страницу канала; если в
    эфире, в HTML присутствует "isLiveBroadcast" и canonical-ссылка указывает
    на конкретное видео. Это не официальный API (не требует ключа и не тратит
    квоту), но при желании его можно заменить на YouTube Data API v3
    (search.list с eventType=live) — см. README.
    """
    if not YOUTUBE_CHANNEL_ID:
        return None
    try:
        url = f"https://www.youtube.com/channel/{YOUTUBE_CHANNEL_ID}/live"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; StreamNotifierBot/1.0)"}
        html = http_get(url, headers=headers)

        if '"isLiveBroadcast"' not in html and '"isLive":true' not in html:
            return None

        m = re.search(r'<link rel="canonical" href="https://www\.youtube\.com/watch\?v=([\w-]{11})"', html)
        if m:
            return m.group(1)
        return None
    except urllib.error.URLError as e:
        print(f"[warn] Не удалось проверить YouTube: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Основная логика
# ---------------------------------------------------------------------------

def main():
    state = load_state()
    changed = False

    # --- Twitch ---
    twitch_stream = check_twitch_live()
    twitch_is_live = twitch_stream is not None
    twitch_stream_id = twitch_stream.get("id") if twitch_stream else None

    if twitch_is_live and not state["twitch_live"]:
        title = twitch_stream.get("title", "").strip()
        game = twitch_stream.get("game_name", "").strip()
        text = f"🔴 <b>Стрим начался на Twitch!</b>\n"
        if title:
            text += f"{title}\n"
        if game:
            text += f"Категория: {game}\n"
        text += f"\n👉 https://twitch.tv/{TWITCH_CHANNEL}"

        # thumbnail_url приходит вида ".../live_user_<канал>-{width}x{height}.jpg"
        # и обновляется Twitch каждые несколько минут — это и есть "скриншот" эфира
        raw_thumb = twitch_stream.get("thumbnail_url", "")
        if raw_thumb:
            # добавляем случайный параметр, чтобы Telegram не взял картинку из своего кэша
            thumb_url = raw_thumb.replace("{width}", "1280").replace("{height}", "720")
            thumb_url += f"?t={twitch_stream_id or ''}"
            send_telegram_photo(thumb_url, text)
        else:
            send_telegram_message(text)

    state["twitch_live"] = twitch_is_live
    state["twitch_last_stream_id"] = twitch_stream_id
    changed = True

    # --- YouTube ---
    if YOUTUBE_CHANNEL_ID:
        youtube_video_id = check_youtube_live()
        youtube_is_live = youtube_video_id is not None

        if youtube_is_live and not state["youtube_live"]:
            text = (
                "🔴 <b>Стрим начался на YouTube!</b>\n\n"
                f"👉 https://youtube.com/watch?v={youtube_video_id}"
            )
            # hqdefault.jpg YouTube обновляет по ходу трансляции — тоже
            # получается что-то вроде живого кадра с эфира
            thumb_url = f"https://i.ytimg.com/vi/{youtube_video_id}/hqdefault.jpg"
            send_telegram_photo(thumb_url, text)

        state["youtube_live"] = youtube_is_live
        state["youtube_last_video_id"] = youtube_video_id

    save_state(state)


if __name__ == "__main__":
    main()
