import os
import re
import csv
import io
import asyncio
import aiohttp
from aiohttp import web
import discord
from discord.ext import commands, tasks
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

# 試算表同步頻道設定 (支援名稱或頻道ID，以逗號分隔；預設為「懶人推書,推薦書單」)
SYNC_CHANNELS = os.getenv("SYNC_CHANNELS", "懶人推書,推薦書單").strip()

# Google 試算表設定
GOOGLE_SHEET_WEBHOOK_URL = os.getenv("GOOGLE_SHEET_WEBHOOK_URL")
GOOGLE_SHEET_VIEW_URL = os.getenv(
    "GOOGLE_SHEET_VIEW_URL",
    "https://docs.google.com/spreadsheets/d/13COcdiJUUFApMDVBbBTf0wY2utr9gGjW12gio43Awqc/edit?gid=0#gid=0"
)

# 快取 (最多快取 300 本書，有效期 1 小時)
cache = TTLCache(maxsize=300, ttl=3600)

# 推薦歷史庫 (格式: { "qidian:1049370328": { "author_name": "小明", "jump_url": "https://..." } })
recommend_history = {}

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
    print(f" Web 健康檢查端口已在 Port {PORT} 啟動")
# -----------------------------------------------------------

async def load_history_from_google_sheet() -> int:
    """
    從 Google 試算表公開檢視連結下載並載入歷史推薦資料至 recommend_history。
    確保賽博獵犬能 100% 依據 Google 試算表上的記錄判定。
    """
    if not GOOGLE_SHEET_VIEW_URL or "docs.google.com/spreadsheets" not in GOOGLE_SHEET_VIEW_URL:
        return 0

    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", GOOGLE_SHEET_VIEW_URL)
    if not match:
        return 0

    sheet_id = match.group(1)
    gid_match = re.search(r"[#&]gid=([0-9]+)", GOOGLE_SHEET_VIEW_URL)
    gid = gid_match.group(1) if gid_match else "0"

    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

    count = 0
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(csv_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    text = await resp.text(encoding="utf-8")
                    reader = csv.reader(io.StringIO(text))
                    rows = list(reader)
                    if not rows:
                        return 0

                    # 欄位定義: 推薦時間(0) | 繁體書名(1) | 簡體原名(2) | 推薦人(3) | 平台(4) | 作者(5) | 小說網址(6) | DC討論原文(7) | 是否推薦(8)
                    for row in rows[1:]:
                        if len(row) <= 6:
                            continue
                        novel_url = row[6].strip()
                        recommender = row[3].strip() if len(row) > 3 else "群友"
                        jump_url = row[7].strip() if len(row) > 7 else ""

                        if novel_url:
                            norm_res = await normalize_novel_url(novel_url)
                            if norm_res:
                                platform, _, book_id = norm_res
                                history_key = f"{platform}:{book_id}"
                                recommend_history[history_key] = {
                                    "author_name": recommender,
                                    "jump_url": jump_url
                                }
                                count += 1
                    print(f"📊 [Google Sheets] 成功載入 {count} 本歷史小說至賽博獵犬庫！")
                else:
                    print(f"⚠️ [Google Sheets] 無法直接讀取試算表 CSV (HTTP {resp.status})，請確認試算表共用權限設為「任何知道連結的使用者均可檢視」。")
    except Exception as e:
        print(f"⚠️ [Google Sheets] 載入歷史資料發生例外: {e}")
    return count

def is_sync_channel(channel) -> bool:
    """
    判斷指定頻道（或討論串母頻道）是否屬於允許同步至 Google 試算表的頻道。
    預設支援「懶人推書」與「推薦書單」。
    """
    if not SYNC_CHANNELS:
        return True  # 若未設定則預設全部同步

    target_names = []
    target_ids = []

    if hasattr(channel, "name"):
        target_names.append(channel.name.lower().replace("#", "").strip())
    if hasattr(channel, "id"):
        target_ids.append(channel.id)

    # 若為討論串 (Thread)，同時檢查母頻道名稱與 ID
    if hasattr(channel, "parent") and channel.parent:
        if hasattr(channel.parent, "name"):
            target_names.append(channel.parent.name.lower().replace("#", "").strip())
        if hasattr(channel.parent, "id"):
            target_ids.append(channel.parent.id)

    sync_list = [c.strip().strip('"').strip("'").replace("#", "").lower() for c in SYNC_CHANNELS.split(",") if c.strip()]

    for allowed in sync_list:
        if allowed.isdigit():
            if int(allowed) in target_ids:
                return True
        else:
            for name in target_names:
                if allowed in name:
                    return True
    return False

def build_book_embed(book_data: dict, author: discord.Member, evaluation: str = "乾糧", is_sync_channel: bool = True) -> discord.Embed:
    """組裝 Discord 小說 Embed 卡片"""
    info_lines = []
    
    if book_data.get("title_s"):
        info_lines.append(f"🔤 **簡體原名**：`{book_data['title_s']}`")
    
    if is_sync_channel:
        if evaluation == "糧草":
            eval_text = "🔥 強力推薦（糧草）"
            author_text = f"由 {author.display_name} 強力推薦"
            embed_color = discord.Color.from_rgb(230, 126, 34)  # 暖橙金
        elif evaluation == "不推薦":
            eval_text = "⚠️ 不推薦"
            author_text = f"由 {author.display_name} 分享（⚠️ 不推薦）"
            embed_color = discord.Color.from_rgb(149, 165, 166)  # 灰色
        else:  # 乾糧（預設）
            eval_text = "🌾 一般推薦（乾糧）"
            author_text = f"由 {author.display_name} 一般推薦"
            embed_color = discord.Color.from_rgb(52, 152, 219)  # 經典藍

        info_lines.append(f"📢 **分享人**：{author.mention} ｜ **評價**：**{eval_text}** ｜ ✅ **已寫入表單**")
        footer_text = "✅ 已自動同步至線上書單 ｜ 點擊標題直接前往書籍頁面"
    else:
        author_text = f"由 {author.display_name} 閒聊分享"
        embed_color = discord.Color.from_rgb(52, 152, 219)
        info_lines.append(f"📢 **分享人**：{author.mention} ｜ 💬 *(僅展開書卡，不進入表單)*")
        footer_text = "💡 本頻道僅展開書卡（不進入表單） ｜ 點擊標題前往書籍頁面"

    info_lines.append(f"👤 **作者**：{book_data.get('author', '未知')} ｜ 📊 **數據**：{book_data.get('stats', '詳見官網')}")
    info_lines.append(f"🏷️ **標籤分類**：{book_data.get('tags', '作品標籤')}")
    info_lines.append("")
    info_lines.append("📝 **完整作品簡介**：")
    info_lines.append(book_data.get("description", "暫無簡介"))

    description_text = "\n".join(info_lines)

    if len(description_text) > 4000:
        description_text = description_text[:3990] + "\n...(簡介過長自動收合)"

    embed = discord.Embed(
        title=f"📖 [{book_data['platform']}] {book_data['title_t']}",
        url=book_data["url"],
        description=description_text,
        color=embed_color
    )

    embed.set_author(
        name=author_text,
        icon_url=author.display_avatar.url
    )

    if book_data.get("cover"):
        embed.set_thumbnail(url=book_data["cover"])

    embed.set_footer(text=footer_text)
    return embed

class BookActionView(discord.ui.View):
    """卡片互動按鈕"""
    def __init__(self, book_data: dict, original_author: discord.Member, jump_url: str = "", should_sync: bool = False):
        super().__init__(timeout=None)
        self.book_data = book_data
        self.original_author = original_author
        self.jump_url = jump_url
        self.should_sync = should_sync
        self.evaluation = "乾糧"  # 預設為一般推薦 (乾糧)

        if not self.should_sync:
            # 在其他頻道 (非推書頻道)，僅保留「線上書單」與「刪除書卡」兩個按鈕
            self.remove_item(self.toggle_tier)
            self.remove_item(self.toggle_evaluation)

        if GOOGLE_SHEET_VIEW_URL:
            self.add_item(discord.ui.Button(
                label="📊 查看線上書單",
                url=GOOGLE_SHEET_VIEW_URL,
                row=0
            ))

    @discord.ui.button(label="🔥 強力推薦", style=discord.ButtonStyle.primary, custom_id="toggle_tier_btn", row=0)
    async def toggle_tier(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以修改評價狀態喔！", ephemeral=True)
            return

        if self.evaluation == "糧草":
            self.evaluation = "乾糧"
            button.label = "🔥 強力推薦"
            button.style = discord.ButtonStyle.primary
        else:
            self.evaluation = "糧草"
            button.label = "🌾 一般推薦"
            button.style = discord.ButtonStyle.secondary

        # 若原先是不推薦狀態，重設「不推薦」按鈕標籤為「改為不推薦」
        for child in self.children:
            if getattr(child, "custom_id", None) == "toggle_eval_btn":
                child.label = "👎 改為不推薦"
                child.style = discord.ButtonStyle.secondary

        new_embed = build_book_embed(self.book_data, self.original_author, self.evaluation, is_sync_channel=self.should_sync)
        await interaction.response.edit_message(embed=new_embed, view=self)

        if self.should_sync and GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                self.book_data,
                self.original_author.display_name,
                self.jump_url,
                status=self.evaluation
            )

    @discord.ui.button(label="👎 改為不推薦", style=discord.ButtonStyle.secondary, custom_id="toggle_eval_btn", row=0)
    async def toggle_evaluation(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以修改評價狀態喔！", ephemeral=True)
            return

        if self.evaluation != "不推薦":
            self.evaluation = "不推薦"
            button.label = "👍 恢復推薦"
            button.style = discord.ButtonStyle.success
        else:
            tier_btn = next((c for c in self.children if getattr(c, "custom_id", None) == "toggle_tier_btn"), None)
            if tier_btn and tier_btn.label == "🌾 一般推薦":
                self.evaluation = "糧草"
            else:
                self.evaluation = "乾糧"
            button.label = "👎 改為不推薦"
            button.style = discord.ButtonStyle.secondary

        new_embed = build_book_embed(self.book_data, self.original_author, self.evaluation, is_sync_channel=self.should_sync)
        await interaction.response.edit_message(embed=new_embed, view=self)

        if self.should_sync and GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                self.book_data,
                self.original_author.display_name,
                self.jump_url,
                status=self.evaluation
            )

    @discord.ui.button(label="🗑️ 刪除書卡", style=discord.ButtonStyle.danger, custom_id="delete_card_btn", row=0)
    async def delete_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以刪除這張書卡喔！", ephemeral=True)
            return

        # 僅刪除 Discord 書卡訊息，保持不影響 Google 試算表紀錄
        await interaction.message.delete()

class CyberHoundView(discord.ui.View):
    """賽博獵犬通知互動按鈕"""
    def __init__(self, original_author: discord.Member):
        super().__init__(timeout=None)
        self.original_author = original_author

    @discord.ui.button(label="🙇 我知錯了", style=discord.ButtonStyle.secondary, custom_id="hound_dismiss_btn", row=0)
    async def dismiss_hound(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有觸發獵犬的原發文者才可以刪除這則通知喔！", ephemeral=True)
            return

        await interaction.message.delete()

@tasks.loop(seconds=60)
async def auto_sync_sheet_task():
    """背景每 60 秒自動同步一次 Google 試算表最新推書資料"""
    await load_history_from_google_sheet()

@auto_sync_sheet_task.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f" 展開書卡：所有文字頻道均會展開")
    print(f" 試算表同步頻道：已設定為 [{SYNC_CHANNELS}]")
    print(f"==================================================")
    
    # 啟動時自動從 Google 試算表載入歷史資料至獵犬庫
    await load_history_from_google_sheet()

    # 啟動背景定期每分鐘同步 Google 試算表任務
    if not auto_sync_sheet_task.is_running():
        auto_sync_sheet_task.start()
    
    await bot.change_presence(activity=discord.Game(name="監聽小說網址 (起點/番茄/刺蝟貓)"))

# ----------------- 手動重新載入 Google 試算表歷史指令 -----------------
@bot.command(name="同步表單", aliases=["reload_sheet", "sync_sheet"])
@commands.has_permissions(administrator=True)
async def reload_sheet_command(ctx: commands.Context):
    """管理員指令：立即從 Google 試算表重新載入推書資料至賽博獵犬庫"""
    msg = await ctx.reply("⏳ 正在從 Google 試算表載入最新推書資料...")
    count = await load_history_from_google_sheet()
    await msg.edit(content=f"✅ **同步完成！**\n已從 Google 試算表成功載入 **{count}** 本小說至賽博獵犬庫！")

# ----------------- 管理員回溯歷史舊文章指令 -----------------
@bot.command(name="掃描歷史", aliases=["scan", "backfill"])
@commands.has_permissions(administrator=True)
async def scan_history_command(ctx: commands.Context, limit: int = 100):
    """
    管理員指令：掃描當前頻道過去的歷史訊息，自動將舊的小說網址錄入 Google 試算表與書庫。
    使用方式：!掃描歷史 100
    """
    if limit > 500:
        await ctx.reply("⚠️ 為避免 Discord 速率限制，單次歷史掃描上限為 500 則訊息。")
        limit = 500

    status_msg = await ctx.reply(f"🔍 開始掃描 **#{ctx.channel.name}** 過去 **{limit}** 則歷史訊息中的小說分享...")
    
    found_count = 0
    scanned_total = 0

    # 由舊到新讀取歷史訊息
    async for msg in ctx.channel.history(limit=limit, oldest_first=True):
        if msg.id == status_msg.id or msg.author.bot:
            continue

        scanned_total += 1
        content = msg.content.strip()
        if not content:
            continue

        norm_result = await normalize_novel_url(content)
        if norm_result:
            platform, norm_url, book_id = norm_result
            history_key = f"{platform}:{book_id}"

            # 抓取小說資料
            book_data = cache.get(history_key)
            if not book_data:
                book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
                if book_data:
                    cache[history_key] = book_data

            if book_data:
                found_count += 1
                # 記錄到獵犬庫
                if history_key not in recommend_history:
                    recommend_history[history_key] = {
                        "author_name": msg.author.display_name,
                        "jump_url": msg.jump_url
                    }
                # 同步寫入 Google 試算表 (自動去重)
                if GOOGLE_SHEET_WEBHOOK_URL:
                    await sync_to_google_sheet(
                        GOOGLE_SHEET_WEBHOOK_URL,
                        book_data,
                        msg.author.display_name,
                        msg.jump_url,
                        status="乾糧"
                    )
                # 微量延遲避免觸發 API 頻率限制
                await asyncio.sleep(1)

    await status_msg.edit(content=f"🎉 **歷史掃描完成！**\n共掃描 **{scanned_total}** 則訊息，成功錄入 **{found_count}** 本小說至 Google 試算表與書庫！")

@scan_history_command.error
async def scan_history_error(ctx: commands.Context, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply("❌ 此歷史回溯指令只有**伺服器管理員**可以使用喔！")
# -----------------------------------------------------------

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 先處理指令 (如 !掃描歷史, !同步表單)
    await bot.process_commands(message)

    content = message.content.strip()
    if not content or content.startswith("!"):
        return

    # 1. 網址正規化與平台識別
    norm_result = await normalize_novel_url(content)
    if not norm_result:
        return

    platform, norm_url, book_id = norm_result
    history_key = f"{platform}:{book_id}"

    # 判斷當前是否為推書指定同步頻道 (如 懶人推書、推薦書單)
    should_sync = is_sync_channel(message.channel)

    # 2. 檢查是否已被推薦過 (只有在指定推書頻道才會觸發賽博獵犬；其他聊天頻道一律正常展開書卡)
    prev_record = recommend_history.get(history_key)
    if should_sync and prev_record:
        first_user = prev_record.get("author_name", "群友")
        first_url = prev_record.get("jump_url", "")
        if first_url:
            hound_text = f"🐶 **你賽博獵犬囉！**\n這本前面 **{first_user}** 已經推薦過了～ 🔗 [點擊查看前人推薦訊息]({first_url})"
        else:
            hound_text = f"🐶 **你賽博獵犬囉！**\n這本前面 **{first_user}** 已經推薦過了～"

        hound_view = CyberHoundView(original_author=message.author)
        await message.reply(
            content=hound_text,
            view=hound_view,
            mention_author=False
        )
        return

    # 3. 取得書籍資料
    book_data = cache.get(history_key)
    if not book_data:
        async with message.channel.typing():
            book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
            if book_data:
                cache[history_key] = book_data

    # 4. 發送書卡 (所有頻道均會發送書卡；但僅指定推書頻道會同步進 Google 試算表與更新獵犬庫)
    if book_data:
        embed_reply = build_book_embed(book_data, message.author, evaluation="乾糧", is_sync_channel=should_sync)
        view = BookActionView(book_data, message.author, jump_url=message.jump_url, should_sync=should_sync)

        sent_msg = await message.reply(
            embed=embed_reply,
            view=view,
            mention_author=False
        )
        view.jump_url = sent_msg.jump_url

        # 若在指定推書頻道，記錄至獵犬歷史庫並同步 Google 試算表
        if should_sync:
            recommend_history[history_key] = {
                "author_name": message.author.display_name,
                "jump_url": sent_msg.jump_url
            }

            if GOOGLE_SHEET_WEBHOOK_URL:
                await sync_to_google_sheet(
                    GOOGLE_SHEET_WEBHOOK_URL,
                    book_data,
                    message.author.display_name,
                    sent_msg.jump_url,
                    status="乾糧"
                )

async def main():
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("[錯誤] 請先在環境變數中設定您的 DISCORD_TOKEN！")
        return
    await start_web_server()
    await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
