import os
import asyncio
from aiohttp import web
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
PORT = int(os.getenv("PORT", 8080))

# Google 試算表設定 (若無設定環境變數則使用預設試算表)
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL")
GOOGLE_SHEET_VIEW_URL = os.getenv(
    "GOOGLE_SHEET_VIEW_URL",
    "https://docs.google.com/spreadsheets/d/13COcdiJUUFApMDVBbBTf0wY2utr9gGjW12gio43Awqc/edit?gid=0#gid=0"
)

# 初始化快取 (最多快取 200 本書，有效期 10 分鐘)
cache = TTLCache(maxsize=200, ttl=600)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ----------------- 輕量 Web 健康檢查伺服器 -----------------
async def health_check(request):
    return web.Response(text="Discord Novel Bot is Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f" Web 健康檢查端口已在 Port {PORT} 啟動 (支援 Render 免費 Web Service)")
# -----------------------------------------------------------

def build_book_embed(book_data: dict, author: discord.Member, is_recommended: bool = True) -> discord.Embed:
    """組裝 Discord 小說 Embed 卡片"""
    info_lines = []
    
    if book_data.get("title_s"):
        info_lines.append(f"🔤 **簡體原名**：`{book_data['title_s']}`")
    
    eval_text = "👍 推薦" if is_recommended else "⚠️ 不推薦"
    info_lines.append(f"📢 **分享人**：{author.mention} ｜ **評價**：**{eval_text}**")
    info_lines.append(f"👤 **作者**：{book_data.get('author', '未知')} ｜ 📊 **數據**：{book_data.get('stats', '詳見官網')}")
    info_lines.append(f"🏷️ **標籤分類**：{book_data.get('tags', '作品標籤')}")
    info_lines.append("")
    info_lines.append("📝 **完整作品簡介**：")
    info_lines.append(book_data.get("description", "暫無簡介"))

    description_text = "\n".join(info_lines)

    if len(description_text) > 4000:
        description_text = description_text[:3990] + "\n...(簡介過長自動收合)"

    if is_recommended:
        author_text = f"由 {author.display_name} 推薦"
    else:
        author_text = f"由 {author.display_name} 分享（⚠️ 不推薦）"

    embed = discord.Embed(
        title=f"📖 [{book_data['platform']}] {book_data['title_t']}",
        url=book_data["url"],
        description=description_text,
        color=discord.Color.from_rgb(52, 152, 219)
    )

    embed.set_author(
        name=author_text,
        icon_url=author.display_avatar.url
    )

    if book_data.get("cover"):
        embed.set_thumbnail(url=book_data["cover"])

    embed.set_footer(text="小說資訊自動解析 ｜ 點擊標題直接前往書籍頁面")
    return embed

class BookActionView(discord.ui.View):
    """卡片互動按鈕"""
    def __init__(self, book_data: dict, original_author: discord.Member, jump_url: str = ""):
        super().__init__(timeout=None)
        self.book_data = book_data
        self.original_author = original_author
        self.jump_url = jump_url
        self.is_recommended = True

        # 線上書單按鈕 (必顯示)
        if GOOGLE_SHEET_VIEW_URL:
            self.add_item(discord.ui.Button(
                label="📊 查看線上書單",
                url=GOOGLE_SHEET_VIEW_URL,
                row=0
            ))

    @discord.ui.button(label="👎 改為不推薦", style=discord.ButtonStyle.secondary, custom_id="toggle_eval_btn", row=0)
    async def toggle_evaluation(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以修改評價狀態喔！", ephemeral=True)
            return

        self.is_recommended = not self.is_recommended
        if self.is_recommended:
            button.label = "👎 改為不推薦"
            eval_status = "推薦"
        else:
            button.label = "👍 改為推薦"
            eval_status = "不推薦"

        new_embed = build_book_embed(self.book_data, self.original_author, self.is_recommended)
        await interaction.response.edit_message(embed=new_embed, view=self)

        if GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                self.book_data,
                self.original_author.display_name,
                self.jump_url,
                status=eval_status
            )

    @discord.ui.button(label="🗑️ 刪除書卡", style=discord.ButtonStyle.danger, custom_id="delete_card_btn", row=0)
    async def delete_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以刪除這張書卡喔！", ephemeral=True)
            return

        await interaction.message.delete()

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f" 簡介模式：100% 完整簡介顯示 (Embed Description 模式)")
    print(f" 線上書單：{GOOGLE_SHEET_VIEW_URL}")
    if GOOGLE_SHEET_WEBHOOK_URL:
        print(f" Google 試算表 Webhook：已配置")
    print(f"==================================================")
    await bot.change_presence(activity=discord.Game(name="監聽小說網址 (起點/番茄/刺蝟貓)"))

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    norm_result = await normalize_novel_url(content)
    if not norm_result:
        await bot.process_commands(message)
        return

    platform, norm_url, book_id = norm_result

    cache_key = f"{platform}:{book_id}"
    book_data = cache.get(cache_key)

    if not book_data:
        async with message.channel.typing():
            book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
            if book_data:
                cache[cache_key] = book_data

    if book_data:
        embed_reply = build_book_embed(book_data, message.author, is_recommended=True)
        view = BookActionView(book_data, message.author, jump_url=message.jump_url)
        sent_msg = await message.reply(embed=embed_reply, view=view, mention_author=False)
        view.jump_url = sent_msg.jump_url

        if GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                book_data,
                message.author.display_name,
                sent_msg.jump_url,
                status="推薦"
            )

    await bot.process_commands(message)

async def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在環境變數中設定您的 DISCORD_TOKEN！")
        return
    await start_web_server()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
