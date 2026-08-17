import os
import sys
import csv
import json
import asyncio
import aiohttp
from datetime import timezone, timedelta
import discord
from dotenv import load_dotenv

from normalizer import normalize_novel_url
from resolver import fetch_novel_info
from sheets_sync import sync_to_google_sheet

# 載入 .env 設定
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
JINA_API_KEY = os.getenv("JINA_API_KEY")
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL")

# 設定台北時間 (UTC+8)
TAIPEI_TZ = timezone(timedelta(hours=8))

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)

async def download_attachment(session: aiohttp.ClientSession, url: str, save_path: str) -> bool:
    """下載單一附件/圖片"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            if response.status == 200:
                with open(save_path, "wb") as f:
                    f.write(await response.read())
                return True
    except Exception as e:
        print(f"\n[警告] 下載圖片失敗 ({url}): {e}")
    return False

def sanitize_filename(filename: str) -> str:
    """過濾檔名中的特殊字元"""
    invalid_chars = '<>:"/\\|?*'
    for ch in invalid_chars:
        filename = filename.replace(ch, "_")
    return filename

async def process_channel_history(target_channel: discord.TextChannel):
    """
    抓取頻道全部歷史訊息：
    1. 下載所有文字、發文者、時間、討論跳轉連結與圖片。
    2. 自動分析所有起點/番茄/刺蝟貓小說網址，並同步寫入 Google 試算表 (自動去重)。
    """
    print(f"\n🚀 開始抓取頻道 【#{target_channel.name}】 的全部歷史訊息...")
    print("------------------------------------------------------")

    # 建立輸出資料夾
    folder_name = sanitize_filename(f"{target_channel.name}_{target_channel.id}")
    output_dir = os.path.join("exports", folder_name)
    images_dir = os.path.join(output_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    messages_data = []
    novel_records = []
    scanned_count = 0
    novel_count = 0

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 由舊到新遍歷全部訊息 (limit=None 代表全部)
        async for msg in target_channel.history(limit=None, oldest_first=True):
            if msg.author.bot:
                continue

            scanned_count += 1
            taipei_time = msg.created_at.astimezone(TAIPEI_TZ)
            time_str = taipei_time.strftime("%Y/%m/%d %H:%M:%S")
            date_only_str = taipei_time.strftime("%Y/%m/%d")

            # 處理附件/圖片下載
            attachments_info = []
            for att in msg.attachments:
                safe_name = sanitize_filename(att.filename)
                filename = f"{msg.id}_{safe_name}"
                filepath = os.path.join(images_dir, filename)
                
                # 下載圖片
                await download_attachment(session, att.url, filepath)
                attachments_info.append({
                    "filename": att.filename,
                    "local_path": filepath,
                    "url": att.url
                })

            # 記錄訊息資訊
            msg_info = {
                "id": str(msg.id),
                "jump_url": msg.jump_url,
                "time": time_str,
                "author_name": msg.author.display_name,
                "author_id": str(msg.author.id),
                "content": msg.content,
                "attachments_count": len(attachments_info),
                "attachments": attachments_info
            }
            messages_data.append(msg_info)

            # 檢查是否含有小說網址
            content = msg.content.strip()
            norm_result = await normalize_novel_url(content)
            if norm_result:
                platform, norm_url, book_id = norm_result
                print(f"\n📖 [發現小說] {platform} ({book_id}) | 推薦人: {msg.author.display_name} | 時間: {date_only_str}")
                
                # 解析書籍詳細資料
                book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
                if book_data:
                    novel_count += 1
                    novel_records.append({
                        "book_data": book_data,
                        "recommender": msg.author.display_name,
                        "jump_url": msg.jump_url,
                        "date": date_only_str
                    })
                    print(f"   -> 書名: 《{book_data['title_t']}》 | 作者: {book_data['author']} | 字數: {book_data['stats']}")

                    # 同步寫入 Google 試算表
                    if GOOGLE_SHEET_WEBHOOK_URL:
                        await sync_to_google_sheet(
                            GOOGLE_SHEET_WEBHOOK_URL,
                            book_data,
                            msg.author.display_name,
                            msg.jump_url,
                            status="乾糧"
                        )
                        print(f"   -> ✅ 已成功同步至 Google 試算表！")

            # 即時進度顯示
            if scanned_count % 20 == 0:
                print(f"⏳ 已掃描 {scanned_count} 則訊息... (已識別 {novel_count} 本小說)", end="\r")

    print(f"\n\n======================================================")
    print(f"🎉 抓取與分析完成！")
    print(f"📊 總掃描訊息數：{scanned_count} 則")
    print(f"📚 成功提取並同步小說數：{novel_count} 本")
    print(f"======================================================")

    # 1. 輸出 JSON 檔案
    json_path = os.path.join(output_dir, "messages.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(messages_data, f, ensure_ascii=False, indent=2)

    # 2. 輸出 CSV 檔案 (Excel 可直接開)
    csv_path = os.path.join(output_dir, "messages.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["訊息ID", "發送時間(台北)", "發送者暱稱", "發送者ID", "文字內容", "討論跳轉連結", "圖片數量"])
        for m in messages_data:
            writer.writerow([
                m["id"],
                m["time"],
                m["author_name"],
                m["author_id"],
                m["content"],
                m["jump_url"],
                m["attachments_count"]
            ])

    print(f"📁 歷史訊息 CSV 已儲存至：{csv_path}")
    print(f"📁 歷史訊息 JSON 已儲存至：{json_path}")
    print(f"🖼️ 歷史截圖圖片已下載至：{images_dir}")

async def interactive_export():
    """互動式頻道選擇"""
    print("\n" + "=" * 50)
    print(" 📢 Discord 頻道歷史推書全量抓取與表單同步工具")
    print("=" * 50)
    
    channels_map = {}
    print("\n可存取的伺服器與頻道清單：")
    for guild in client.guilds:
        print(f"\n📁 伺服器：【{guild.name}】")
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.read_messages and perms.read_message_history:
                channels_map[channel.id] = channel
                print(f"   💬 #{channel.name} (ID: {channel.id})")

    if not channels_map:
        print("\n[錯誤] 機器人目前沒有任何可讀取的文字頻道權限。")
        await client.close()
        return

    print("\n" + "-" * 50)
    user_input = input("👉 請輸入要抓取分析的「頻道 ID」（直接複製上方括號內的數字）: ").strip()

    if not user_input.isdigit() or int(user_input) not in channels_map:
        print("\n[錯誤] 輸入的頻道 ID 無效或機器人無權限存取。")
        await client.close()
        return

    target_channel = channels_map[int(user_input)]
    await process_channel_history(target_channel)
    await client.close()

@client.event
async def on_ready():
    print(f"機器人登入成功：{client.user.name}")
    await interactive_export()

def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在 .env 檔案中設定您的 DISCORD_TOKEN！")
        return
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    main()
