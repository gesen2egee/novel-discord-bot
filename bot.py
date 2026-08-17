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

# 初始化快取 (最多快取 200 本書，有效期 10 分鐘)
cache = TTLCache(maxsize=200, ttl=600)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f"==================================================")
    await bot.change_presence(activity=discord.Game(name="監聽小說網址 (起點/番茄/刺蝟貓)"))

@bot.event
async def on_message(message: discord.Message):
    # 忽略機器人自身的訊息
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

    # 3. 組裝 Discord 內嵌卡片 (Embed)
    if book_data:
        embed = discord.Embed(
            title=f"📖 [{book_data['platform']}] {book_data['title_t']}",
            url=book_data["url"],
            color=discord.Color.from_rgb(52, 152, 219)
        )

        # 頂部顯示推薦人姓名與頭像
        embed.set_author(
            name=f"由 {message.author.display_name} 推薦",
            icon_url=message.author.display_avatar.url
        )

        # 雙行書名：第二行顯示簡體原名（方便複製搜尋）
        if book_data.get("title_s"):
            embed.add_field(name="🔤 簡體原名", value=f"`{book_data['title_s']}`", inline=False)

        # 推薦人、作者與統計數據
        embed.add_field(name="📢 推薦人", value=message.author.mention, inline=True)
        embed.add_field(name="👤 作者", value=book_data.get("author", "未知"), inline=True)
        embed.add_field(name="📊 字數 / 數據", value=book_data.get("stats", "詳見官網"), inline=True)

        embed.add_field(name="🏷️ 標籤分類", value=book_data.get("tags", "作品標籤"), inline=False)

        # 完整簡介 (不截斷)
        embed.add_field(name="📝 完整簡介", value=book_data.get("description", "暫無簡介"), inline=False)

        # 高解析封面縮圖
        if book_data.get("cover"):
            embed.set_thumbnail(url=book_data["cover"])

        embed.set_footer(text="小說資訊自動解析 ｜ 點擊標題直接前往書籍頁面")

        await message.reply(embed=embed, mention_author=False)

    await bot.process_commands(message)

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在 .env 檔案中設定您的 DISCORD_TOKEN！")
    else:
        bot.run(DISCORD_TOKEN)
