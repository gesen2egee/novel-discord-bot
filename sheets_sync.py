import aiohttp
from datetime import datetime
from typing import Optional

async def sync_to_google_sheet(webhook_url: str, book_data: dict, recommender_name: str) -> bool:
    """
    透過 Google Apps Script Webhook 將推書資訊自動新增至 Google 試算表。
    免 GCP 複雜設定、零門檻快速寫入。
    """
    if not webhook_url:
        return False

    # 取得當前時間 (台北時間 / UTC+8)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "time": now_str,
        "title_t": book_data.get("title_t", ""),
        "title_s": book_data.get("title_s", ""),
        "recommender": recommender_name,
        "platform": book_data.get("platform", ""),
        "author": book_data.get("author", ""),
        "stats": book_data.get("stats", ""),
        "tags": book_data.get("tags", ""),
        "url": book_data.get("url", "")
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"[Google Sheets Sync Error] {e}")
        return False
