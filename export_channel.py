import os
import sys
import csv
import json
import asyncio
import aiohttp
from datetime import timezone, timedelta
import discord
from dotenv import load_dotenv

# 載入 .env 設定
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

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

async def interactive_export():
    """互動式頻道選擇與匯出邏輯"""
    print("\n" + "=" * 50)
    print(" 📢 Discord 頻道歷史訊息與圖片匯出工具")
    print("=" * 50)
    
    # 列出所有可存取的文字頻道
    channels_map = {}
    print("\n可用的伺服器與頻道清單：")
    for guild in client.guilds:
        print(f"\n📁 伺服器：【{guild.name}】 (ID: {guild.id})")
        for channel in guild.text_channels:
            perms = channel.permissions_for(guild.me)
            if perms.read_messages and perms.read_message_history:
                channels_map[channel.id] = channel
                print(f"   💬 #{channel.name} (ID: {channel.id})")
            else:
                print(f"   🔒 #{channel.name} (無存取或讀取歷史權限)")

    print("\n" + "-" * 50)
    target_id_str = input("請輸入欲爬取的【頻道 ID】（直接按 Enter 結束）: ").strip()
    if not target_id_str:
        print("已取消操作。")
        await client.close()
        return

    try:
        target_id = int(target_id_str)
    except ValueError:
        print("[錯誤] 頻道 ID 格式不正確，請輸入純數字！")
        await client.close()
        return

    target_channel = client.get_channel(target_id)
    if not target_channel:
        try:
            target_channel = await client.fetch_channel(target_id)
        except Exception:
            target_channel = None

    if not target_channel or not isinstance(target_channel, discord.TextChannel):
        print(f"[錯誤] 找不到頻道 ID {target_id} 或該頻道不是文字頻道，請確認機器人是否在該伺服器且有權限！")
        await client.close()
        return

    # 建立輸出資料夾
    folder_name = sanitize_filename(f"{target_channel.name}_{target_channel.id}")
    export_dir = os.path.join(os.getcwd(), "exports", folder_name)
    images_dir = os.path.join(export_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    print(f"\n[開始爬取] 目標頻道: #{target_channel.name}")
    print(f"[儲存路徑] {export_dir}")
    print("正在抓取訊息與下載圖片，請稍候...\n")

    messages_list = []
    total_messages = 0
    total_attachments = 0

    async with aiohttp.ClientSession() as session:
        # oldest_first=True: 由舊到新爬取
        async for msg in target_channel.history(limit=None, oldest_first=True):
            total_messages += 1

            # 處理時間 (轉換成台灣時間 UTC+8)
            msg_time = msg.created_at.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")

            # 處理附件 (圖片/影片/檔案)
            att_records = []
            att_filenames = []
            for att in msg.attachments:
                total_attachments += 1
                safe_name = sanitize_filename(f"{msg.id}_{att.filename}")
                local_path = os.path.join(images_dir, safe_name)
                
                # 下載附件
                download_success = await download_attachment(session, att.url, local_path)
                att_filenames.append(safe_name if download_success else f"[下載失敗]_{safe_name}")

                att_records.append({
                    "filename": att.filename,
                    "saved_file": safe_name if download_success else None,
                    "url": att.url,
                    "size_bytes": att.size,
                    "content_type": att.content_type
                })

            msg_data = {
                "id": str(msg.id),
                "author_display_name": msg.author.display_name,
                "author_username": msg.author.name,
                "author_id": str(msg.author.id),
                "timestamp": msg_time,
                "content": msg.content,
                "attachments": att_records,
                "attachments_count": len(att_records),
                "jump_url": msg.jump_url
            }
            messages_list.append(msg_data)

            # 即時進度輸出
            if total_messages % 50 == 0:
                print(f" ⏳ 已爬取 {total_messages:5d} 則訊息 ｜ 已下載 {total_attachments:4d} 個附件/圖片...", end="\r", flush=True)

    print(f"\n\n✅ 爬取完成！共處理 {total_messages} 則訊息、下載 {total_attachments} 個附件。")

    # 1. 寫入 JSON 檔案
    json_path = os.path.join(export_dir, "messages.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(messages_list, f, ensure_ascii=False, indent=2)

    # 2. 寫入 CSV 檔案 (UTF-8 with BOM，方便 Excel 直接點開不亂碼)
    csv_path = os.path.join(export_dir, "messages.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["訊息ID", "發送時間 (UTC+8)", "發送者暱稱", "帳號名稱", "使用者ID", "文字內容", "附件圖片清單", "訊息連結"])
        for m in messages_list:
            att_str = " ; ".join([a["saved_file"] or a["url"] for a in m["attachments"]])
            writer.writerow([
                m["id"],
                m["timestamp"],
                m["author_display_name"],
                m["author_username"],
                m["author_id"],
                m["content"],
                att_str,
                m["jump_url"]
            ])

    print("=" * 50)
    print(f" 📄 JSON 資料檔 : {json_path}")
    print(f" 📊 CSV 試算表  : {csv_path}")
    print(f" 🖼️ 圖片資料夾  : {images_dir}")
    print("=" * 50)

    await client.close()

@client.event
async def on_ready():
    print(f"機器人已登入為: {client.user.name} ({client.user.id})")
    await interactive_export()

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在 .env 檔案中設定您的 DISCORD_TOKEN！")
        sys.exit(1)
    
    try:
        client.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n程式已被使用者中止。")
    except Exception as e:
        print(f"\n[錯誤] 執行失敗: {e}")
