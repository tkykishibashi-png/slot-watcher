import os
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup

TARGET_URL = os.environ["TARGET_URL"]
DISCORD_WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
STATE_FILE = "state.json"

HEADERS = {"User-Agent": "slot-watcher/1.0 (+github actions)"}

# 判定に使う文言（ユーザー指定）
CLOSED_PHRASE = "誠に申し訳ございませんが、ただいま予約を受け付けておりません。"

# 1時間クールダウン
COOLDOWN_SECONDS = 60 * 60


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def fetch_html() -> str:
    r = requests.get(TARGET_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def normalize(s: str) -> str:
    # 改行/半角全角スペースを除去して比較しやすくする
    return s.replace("\n", "").replace(" ", "").replace("　", "")


def notify_discord(message: str) -> None:
    resp = requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=20)
    resp.raise_for_status()


def main():
    state = load_state()

    html = fetch_html()
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)

    normalized = normalize(text)
    closed_norm = normalize(CLOSED_PHRASE)

    # 変化検知（テキストハッシュ）
    current_hash = sha256(normalized)
    last_hash = state.get("last_hash")

    if last_hash == current_hash:
        print("No change.")
        return

    state["last_hash"] = current_hash
    state["last_change_at"] = int(time.time())

    now = int(time.time())
    last_notified_at = int(state.get("last_notified_at", 0))
    in_cooldown = (now - last_notified_at) < COOLDOWN_SECONDS

    is_closed = (closed_norm in normalized)

    # 「閉じてます文言が無い」なら通知候補（ただし1時間抑制）
    if (not is_closed) and (not in_cooldown):
        msg = (
            "✅ 予約受付ページの表示が変わりました（要確認）\n"
            f"{TARGET_URL}\n"
            "※通知後1時間は抑制します"
        )
        notify_discord(msg)
        state["last_notified_at"] = now
        state["last_notify_reason"] = "closed_phrase_missing"
        print("Notified.")
    elif (not is_closed) and in_cooldown:
        print("Change detected but in cooldown (skip notify).")
    else:
        print("Closed phrase present (no notify).")

    save_state(state)


if __name__ == "__main__":
    main()
