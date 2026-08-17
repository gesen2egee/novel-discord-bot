import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from cachetools import TTLCache

from normalizer import normalize_novel_url
from resolver import fetch_novel_info

# 載入環境變數
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
JINA_API_KEY = os.getenv("JINA_API_KEY")

# 推書彙整頻道設定 (可填頻道 ID 或頻道名稱關鍵字)
RECOMMEND_CHANNEL_ID = os.getenv("RECOMMEND_CHANNEL_ID")
RECOMMEND_CHANNEL_NAME = os.getenv("RECOMMEND_CHANNEL_NAME", "推書彙整")

# 初始化快取 (最多快取 200 本書，有效期 10 分鐘)
cache = TTLCache(maxsize=200, ttl=600)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def build_book_embed(book_data: dict, author: discord.Member, original_msg_url: str = None) -> discord.Embed:
    """組裝精美的 Discord 小說 Embed 卡片"""
    embed = discord.Embed(
        title=f"📖 [{book_data['platform']}] {book_data['title_t']}",
        url=book_data["url"],
        color=discord.Color.from_rgb(52, 152, 219)
    )

    # 頂部 Author 顯示推薦人與頭像
    embed.set_author(
        name=f"由 {author.display_name} 推薦",
        icon_url=author.display_avatar.url
    )

    # 雙行書名：顯示簡體原名（方便複製搜尋）
    if book_data.get("title_s"):
        embed.add_field(name="🔤 簡體原名", value=f"`{book_data['title_s']}`", inline=False)

    # 推薦人、作者與統計數據
    embed.add_field(name="📢 推薦人", value=author.mention, inline=True)
    embed.add_field(name="👤 作者", value=book_data.get("author", "未知"), inline=True)
    embed.add_field(name="📊 字數 / 數據", value=book_data.get("stats", "詳見官網"), inline=True)

    # 標籤分類
    embed.add_field(name="🏷️ 標籤分類", value=book_data.get("tags", "作品標籤"), inline=False)

    # 完整簡介 (不截斷)
    embed.add_field(name="📝 完整簡介", value=book_data.get("description", "暫無簡介"), inline=False)

    # 若為轉發至彙整頻道，附上原討論訊息連結
    if original_msg_url:
        embed.add_field(name="💬 來源討論", value=f"[點擊前往原對話]({original_msg_url})", inline=False)

    # 高解析封面縮圖
    if book_data.get("cover"):
        embed.set_thumbnail(url=book_data["cover"])

    embed.set_footer(text="小說資訊自動解析 ｜ 點擊標題直接前往書籍頁面")
    return embed

async def find_recommend_channel(guild: discord.Guild) -> discord.TextChannel:
    """尋找伺服器中的專屬推書彙整頻道"""
    if not guild:
        return None

    # 1. 優先使用指定的 RECOMMEND_CHANNEL_ID
    if RECOMMEND_CHANNEL_ID and RECOMMEND_CHANNEL_ID.isdigit():
        target = guild.get_channel(int(RECOMMEND_CHANNEL_ID))
        if target:
            return target

    # 2. 自動按名稱關鍵字尋找 (如「推書彙整」、「推書」或「book-recommend」)
    for channel in guild.text_channels:
        if RECOMMEND_CHANNEL_NAME in channel.name or "推書" in channel.name or "book-recommend" in channel.name:
            return channel

    return None

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f" 自動轉發功能：已啟用 (目標頻道名稱關鍵字: {RECOMMEND_CHANNEL_NAME})")
    print(f"==================================================")
    await bot.change_presence(activity=discord.Game(name="監聽小說網址 ＆ 自動彙整書單"))

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

    # 3. 回覆原頻道與轉發至「推書彙整」頻道
    if book_data:
        # A. 原頻道回覆 Embed
        embed_reply = build_book_embed(book_data, message.author)
        sent_msg = await message.reply(embed=embed_reply, mention_author=False)

        # B. 自動轉發至專屬「📚-推書彙整」頻道 (若伺服器有此頻道且不在該頻道內)
        if message.guild:
            rec_channel = await find_recommend_channel(message.guild)
            if rec_channel and rec_channel.id != message.channel.id:
                try:
                    embed_archive = build_book_embed(book_data, message.author, original_msg_url=sent_msg.jump_url)
                    await rec_channel.send(
                        content=f"📌 **來自 {message.channel.mention} 的新推書分享：**",
                        embed=embed_archive
                    )
                except Exception as e:
                    print(f"[轉發失敗] 無法轉發至 #{rec_channel.name}: {e}")

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在 .env 檔案中設定您的 DISCORD_TOKEN！")
    else:
        bot.run(DISCORD_TOKEN)
