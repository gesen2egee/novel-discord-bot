import aiohttp
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

# 台北時區 (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

async def sync_to_google_sheet(
    webhook_url: str,
    book_data: dict,
    recommender_name: str,
    message_jump_url: str = "",
    status: str = "推薦",
    concurrence: str = ""
) -> bool:
    """
    透過 Google Apps Script Webhook 將小說資訊與評價同步至 Google 試算表。
    時間統一採用「台北時間 (UTC+8)」並僅顯示日期 (YYYY/MM/DD)。
    """
    if not webhook_url or not webhook_url.startswith("http"):
        print("[Google Sheets] 警告: 未設定有效的 GOOGLE_SHEET_WEBHOOK_URL，略過試算表同步。")
        return False

    # 取得當前台北時間，並格式化為純日期 (例如: 2026/08/17)
    now_date_str = datetime.now(TAIPEI_TZ).strftime("%Y/%m/%d")

    payload = {
        "time": now_date_str,
        "title_t": book_data.get("title_t", ""),
        "title_s": book_data.get("title_s", ""),
        "recommender": recommender_name,
        "platform": book_data.get("platform", ""),
        "author": book_data.get("author", ""),
        "stats": book_data.get("stats", ""),
        "tags": book_data.get("tags", ""),
        "url": book_data.get("url", ""),
        "jump_url": message_jump_url,
        "evaluation": status,
        "concurrence": concurrence
    }

    try:
        headers = {"Content-Type": "text/plain;charset=utf-8"}
        body_data = json.dumps(payload, ensure_ascii=False)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                data=body_data,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp_text = await resp.text()
                print(f"[Google Sheets] 同步回應狀態碼: {resp.status} ｜ 回應內容: {resp_text[:100]}")
                return resp.status in [200, 302, 307]
    except Exception as e:
        print(f"[Google Sheets Sync Error] 同步失敗: {e}")
        return False

async def delete_from_google_sheet(
    webhook_url: str,
    novel_url: str,
    title_t: str = ""
) -> bool:
    """
    透過 Google Apps Script Webhook 從 Google 試算表中刪除指定小說那一列。
    """
    if not webhook_url or not webhook_url.startswith("http"):
        return False

    payload = {
        "action": "delete",
        "url": novel_url,
        "title_t": title_t
    }

    try:
        headers = {"Content-Type": "text/plain;charset=utf-8"}
        body_data = json.dumps(payload, ensure_ascii=False)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                data=body_data,
                headers=headers,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                resp_text = await resp.text()
                print(f"[Google Sheets] 刪除回應狀態碼: {resp.status} ｜ 回應內容: {resp_text[:100]}")
                return resp.status in [200, 302, 307]
    except Exception as e:
        print(f"[Google Sheets Delete Error] 刪除失敗: {e}")
        return False
