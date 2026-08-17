import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from cachetools import TTLCache

from normalizer import normalize_novel_url
from resolver import fetch_novel_info
from sheets_sync import sync_to_google_sheet

# 載入環境變數
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
JINA_API_KEY = os.getenv("JINA_API_KEY")

# Google 試算表 Webhook 網址 (選填)
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL")

# 初始化快取 (最多快取 200 本書，有效期 10 分鐘)
cache = TTLCache(maxsize=200, ttl=600)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def build_book_embed(book_data: dict, author: discord.Member) -> discord.Embed:
    """
    組裝精美的 Discord 小說 Embed 卡片。
    使用 Embed.description 承載完整簡介 (支援高達 4096 字元，確保 100% 完整呈現不被截斷)。
    """
    info_lines = []
    
    # 雙行書名：簡體原名
    if book_data.get("title_s"):
        info_lines.append(f"🔤 **簡體原名**：`{book_data['title_s']}`")
    
    # 推薦人、作者、數據與標籤
    info_lines.append(f"📢 **推薦人**：{author.mention}")
    info_lines.append(f"👤 **作者**：{book_data.get('author', '未知')} ｜ 📊 **數據**：{book_data.get('stats', '詳見官網')}")
    info_lines.append(f"🏷️ **標籤分類**：{book_data.get('tags', '作品標籤')}")
    info_lines.append("")
    info_lines.append("📝 **完整作品簡介**：")
    info_lines.append(book_data.get("description", "暫無簡介"))

    description_text = "\n".join(info_lines)

    # 安全邊界保護
    if len(description_text) > 4000:
        description_text = description_text[:3990] + "\n...(簡介過長自動收合)"

    embed = discord.Embed(
        title=f"📖 [{book_data['platform']}] {book_data['title_t']}",
        url=book_data["url"],
        description=description_text,
        color=discord.Color.from_rgb(52, 152, 219)
    )

    # 頂部 Author 顯示推薦人與頭像
    embed.set_author(
        name=f"由 {author.display_name} 推薦",
        icon_url=author.display_avatar.url
    )

    # 高解析官方封面縮圖
    if book_data.get("cover"):
        embed.set_thumbnail(url=book_data["cover"])

    embed.set_footer(text="小說資訊自動解析 ｜ 點擊標題直接前往書籍頁面")
    return embed

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f" 簡介模式：100% 完整簡介顯示 (Embed Description 模式)")
    if GOOGLE_SHEET_WEBHOOK_URL:
        print(f" Google 試算表同步：已啟用 (含 Discord 討論跳轉連結)")
    print(f"==================================================")
    await bot.change_presence(activity=discord.Game(name="監聽小說網址 (起點/番茄/刺蝟貓)"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    # 1. 網址正規化與平台識別 (自動排除單章閱讀頁)
    norm_result = await normalize_novel_url(content)
    if not norm_result:
        await bot.process_commands(message)
        return

    platform, norm_url, book_id = norm_result

    # 2. 檢查快取
    cache_key = f"{platform}:{book_id}"
    book_data = cache.get(cache_key)

    if not book_data:
        async with message.channel.typing():
            book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
            if book_data:
                cache[cache_key] = book_data

    # 3. 原頻道回覆 Embed 與同步 Google 試算表
    if book_data:
        # A. 原頻道回覆 Embed 書卡
        embed_reply = build_book_embed(book_data, message.author)
        sent_msg = await message.reply(embed=embed_reply, mention_author=False)

        # B. 自動同步寫入 Google 試算表 (帶上 Discord 討論訊息跳轉連結)
        if GOOGLE_SHEET_WEBHOOK_URL:
            jump_url = sent_msg.jump_url if sent_msg else message.jump_url
            await sync_to_google_sheet(GOOGLE_SHEET_WEBHOOK_URL, book_data, message.author.display_name, jump_url)

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在 .env 檔案中設定您的 DISCORD_TOKEN！")
    else:
        bot.run(DISCORD_TOKEN)
