import aiohttp
from datetime import datetime
from typing import Optional

async def sync_to_google_sheet(
    webhook_url: str,
    book_data: dict,
    recommender_name: str,
    message_jump_url: str = "",
    status: str = "推薦"
) -> bool:
    """
    透過 Google Apps Script Webhook 將小說資訊與評價同步至 Google 試算表。
    支援 Google Apps Script 的 302/307 重定向。
    """
    if not webhook_url:
        return False

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
        "url": book_data.get("url", ""),
        "jump_url": message_jump_url,
        "evaluation": status
    }

    try:
        # 重要：Google Apps Script Webhook 會發出 302 重定向，必須設定 allow_redirects=True
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                print(f"[Google Sheets] 同步狀態碼: {resp.status}")
                return resp.status in [200, 302, 307]
    except Exception as e:
        print(f"[Google Sheets Sync Error] {e}")
        return False
