import aiohttp
import json
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
    高相容性 Payload 傳輸，並在日誌輸出同步狀態。
    """
    if not webhook_url or not webhook_url.startswith("http"):
        print("[Google Sheets] 警告: 未設定有效的 GOOGLE_SHEET_WEBHOOK_URL，略過試算表同步。")
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
        # 使用 text/plain 傳送 JSON 字串，完全避開 Google Apps Script 的 CORS 預檢阻擋
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
