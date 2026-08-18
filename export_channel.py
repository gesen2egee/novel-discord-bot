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
    scanned_count = 0
    downloaded_images = 0

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 由舊到新遍歷全部訊息 (limit=None 代表全部)
        async for msg in target_channel.history(limit=None, oldest_first=True):
            if msg.author.bot:
                continue

            scanned_count += 1
            taipei_time = msg.created_at.astimezone(TAIPEI_TZ)
            time_str = taipei_time.strftime("%Y/%m/%d %H:%M:%S")
            time_file_prefix = taipei_time.strftime("%Y%m%d_%H%M%S")
            safe_author = sanitize_filename(msg.author.display_name)

            # 處理附件/圖片下載
            attachments_info = []
            for att in msg.attachments:
                safe_name = sanitize_filename(att.filename)
                filename = f"{time_file_prefix}_{safe_author}_{msg.id}_{safe_name}"
                filepath = os.path.join(images_dir, filename)
                
                # 下載圖片
                success = await download_attachment(session, att.url, filepath)
                if success:
                    downloaded_images += 1
                attachments_info.append({
                    "filename": filename,
                    "original_filename": att.filename,
                    "local_path": filepath,
                    "url": att.url
                })

            category_name = target_channel.category.name if target_channel.category else "無分類"
            guild_name = target_channel.guild.name if target_channel.guild else "未知伺服器"
            channel_name = target_channel.name

            # 記錄訊息資訊
            msg_info = {
                "id": str(msg.id),
                "guild_name": guild_name,
                "category_name": category_name,
                "channel_name": channel_name,
                "jump_url": msg.jump_url,
                "time": time_str,
                "author_name": msg.author.display_name,
                "author_id": str(msg.author.id),
                "content": msg.content,
                "attachments_count": len(attachments_info),
                "attachments": attachments_info
            }
            messages_data.append(msg_info)

            # 即時進度顯示
            if scanned_count % 20 == 0:
                print(f"⏳ 已掃描 {scanned_count} 則訊息... (已下載 {downloaded_images} 張圖片)", end="\r")

    print(f"\n\n======================================================")
    print(f"🎉 頻道 【#{target_channel.name}】 抓取完成！")
    print(f"📊 總掃描訊息數：{scanned_count} 則")
    print(f"🖼️ 總下載圖片附件數：{downloaded_images} 個")
    print(f"======================================================")

    # 1. 輸出 JSON 檔案
    json_path = os.path.join(output_dir, "messages.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(messages_data, f, ensure_ascii=False, indent=2)

    # 2. 輸出 CSV 檔案 (Excel 可直接開)
    csv_path = os.path.join(output_dir, "messages.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["訊息ID", "伺服器", "分類版位", "頻道名稱", "發送時間(台北)", "發送者暱稱", "發送者ID", "文字內容", "討論跳轉連結", "圖片數量", "圖片檔名"])
        for m in messages_data:
            att_files = "; ".join([att["filename"] for att in m["attachments"]])
            writer.writerow([
                m["id"],
                m["guild_name"],
                m["category_name"],
                m["channel_name"],
                m["time"],
                m["author_name"],
                m["author_id"],
                m["content"],
                m["jump_url"],
                m["attachments_count"],
                att_files
            ])

    print(f"📁 歷史訊息 CSV 已儲存至：{csv_path}")
    print(f"📁 歷史訊息 JSON 已儲存至：{json_path}")
    print(f"🖼️ 歷史截圖圖片已下載至：{images_dir}")

def extract_channel_ids_from_input(text: str) -> list[int]:
    """從輸入字串（支援純 ID、多個 ID 或 Discord 網址）解析出頻道 ID 列表"""
    import re
    ids = []
    # 支援 Discord 網址格式 https://discord.com/channels/<guild_id>/<channel_id>
    url_pattern = re.findall(r"discord\.com/channels/\d+/(\d+)", text)
    if url_pattern:
        for cid in url_pattern:
            ids.append(int(cid))
    
    # 支援一般數字或逗號/空格分隔數字
    raw_tokens = re.findall(r"\b\d{17,20}\b", text)
    for token in raw_tokens:
        cid = int(token)
        if cid not in ids:
            ids.append(cid)
    return ids

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
    print("💡 支援直接貼上頻道網址（例如：https://discord.com/channels/.../1411976730347962509）")
    print("💡 或輸入多個頻道 ID（以空格或逗號分隔）")
    print("💡 若直接按 Enter，預設抓取指定的 2 個頻道 (1411976730347962509 與 898072480109965313)")
    user_input = input("\n👉 請輸入頻道網址或 ID [直接按 Enter 抓取預設 2 個頻道]: ").strip()

    target_ids = []
    if not user_input:
        target_ids = [1411976730347962509, 898072480109965313]
    else:
        target_ids = extract_channel_ids_from_input(user_input)

    valid_channels = [channels_map[cid] for cid in target_ids if cid in channels_map]
    missing_ids = [cid for cid in target_ids if cid not in channels_map]

    if missing_ids:
        print(f"\n⚠️ 以下頻道 ID 無法存取（機器人未加入該伺服器或無權限）：{missing_ids}")

    if not valid_channels:
        print("\n[錯誤] 沒有找到任何有效且具備權限的頻道。")
        await client.close()
        return

    print(f"\n🚀 即將開始抓取 {len(valid_channels)} 個頻道...")
    for ch in valid_channels:
        await process_channel_history(ch)

    print("\n🎉 所有指定頻道的歷史資料與圖片皆已下載完成！")
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
