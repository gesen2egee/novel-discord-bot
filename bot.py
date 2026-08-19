import os
import re
import csv
import io
import urllib.parse
import asyncio
import aiohttp
from aiohttp import web
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from cachetools import TTLCache

from normalizer import normalize_novel_url
from resolver import fetch_novel_info
from sheets_sync import sync_to_google_sheet, delete_from_google_sheet

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

# 推薦歷史庫 (格式: { "qidian:1049370328": { "author_name": "小明", "jump_url": "https://...", "upvoters": ["小華"], "downvoters": [] } })
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
    確保賽博獵犬與社群覆議能 100% 依據 Google 試算表上的記錄判定。
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

                    # 欄位定義: 推薦時間(0) | 繁體書名(1) | 簡體原名(2) | 推薦人(3) | 平台(4) | 作者(5) | 小說網址(6) | DC討論原文(7) | 是否推薦(8) | 數據(9) | 標籤(10) | 覆議(11)
                    for row in rows[1:]:
                        if len(row) <= 6:
                            continue
                        novel_url = row[6].strip()
                        recommender = row[3].strip() if len(row) > 3 else "群友"
                        jump_url = row[7].strip() if len(row) > 7 else ""
                        eval_val = row[8].strip() if len(row) > 8 else "乾糧"
                        concurrence_val = row[11].strip() if len(row) > 11 else ""

                        # 解析現有覆議名單
                        upvoters = []
                        downvoters = []
                        if concurrence_val:
                            parts = [p.strip() for p in concurrence_val.split("｜") if p.strip()]
                            for part in parts:
                                if "同推" in part:
                                    names = part.replace("同推", "").strip().split(",")
                                    upvoters.extend([n.strip() for n in names if n.strip()])
                                elif "反推" in part or "不推" in part:
                                    names = part.replace("反推", "").replace("不推", "").strip().split(",")
                                    downvoters.extend([n.strip() for n in names if n.strip()])

                        if novel_url:
                            norm_res = await normalize_novel_url(novel_url)
                            if norm_res:
                                platform, _, book_id = norm_res
                                history_key = f"{platform}:{book_id}"
                                recommend_history[history_key] = {
                                    "author_name": recommender,
                                    "jump_url": jump_url,
                                    "evaluation": eval_val,
                                    "upvoters": upvoters,
                                    "downvoters": downvoters
                                }
                                count += 1
                    print(f"📊 [Google Sheets] 成功載入 {count} 本歷史小說與覆議資料至賽博獵犬庫！")
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

def build_book_embed(
    book_data: dict,
    author: discord.Member,
    evaluation: str = "乾糧",
    is_sync_channel: bool = True,
    upvoters: list = None,
    downvoters: list = None
) -> discord.Embed:
    """組裝 Discord 小說 Embed 卡片（支援覆議名單展示）"""
    if upvoters is None:
        upvoters = []
    if downvoters is None:
        downvoters = []

    # 平台簡稱對應
    platform_map = {
        "起點中文網": "起點",
        "起点中文网": "起點",
        "起點": "起點",
        "起点": "起點",
        "qidian": "起點",
        "番茄小說": "番茄",
        "番茄小说": "番茄",
        "番茄": "番茄",
        "fanqie": "番茄",
        "fanqie_keyword": "番茄",
        "刺蝟貓": "刺蝟貓",
        "刺猬猫": "刺蝟貓",
        "ciweimao": "刺蝟貓"
    }
    raw_platform = book_data.get("platform", "小說平台")
    short_platform = platform_map.get(raw_platform, raw_platform)
    display_title = f"{book_data['title_t']} ({short_platform})"

    info_lines = []
    # 繁體書名採用 H2 中間大小字級超連結 (介於特大與簡介之間)
    info_lines.append(f"## 📖 [{display_title}]({book_data['url']})")
    info_lines.append("")
    
    if book_data.get("title_s"):
        encoded_title = urllib.parse.quote_plus(book_data["title_s"])
        search_url = f"https://www.google.com/search?q={encoded_title}"
        info_lines.append(f"🔤 **簡體原名**：[{book_data['title_s']}]({search_url}) 🔍")
    
    if is_sync_channel:
        if evaluation == "糧草":
            eval_text = "🔥 強力推薦（糧草）"
            author_text = f"由 {author.display_name} 強力推薦"
            embed_color = discord.Color.from_rgb(230, 126, 34)  # 暖橙金
        elif evaluation in ["改不推薦", "不推薦"]:
            eval_text = "⚠️ 改不推薦"
            author_text = f"由 {author.display_name} 分享（⚠️ 改不推薦）"
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

    # 展示社群覆議 (同推 / 反推)
    if upvoters:
        info_lines.append(f"👥 **同推**：{', '.join(upvoters)}")
    if downvoters:
        info_lines.append(f"🚫 **反推**：{', '.join(downvoters)}")

    info_lines.append("")
    info_lines.append("### 📝 **作品簡介**")
    raw_desc = book_data.get("description", "暫無簡介").strip()
    if raw_desc:
        desc_paragraphs = raw_desc.split("\n")
        formatted_paragraphs = []
        for p in desc_paragraphs:
            p_str = p.strip()
            if not p_str:
                formatted_paragraphs.append("")
            elif p_str.startswith("### ") or p_str.startswith("## ") or p_str.startswith("# "):
                formatted_paragraphs.append(p_str)
            elif p_str in ["---", "——", "***", "···"]:
                formatted_paragraphs.append(p_str)
            else:
                formatted_paragraphs.append(f"### {p_str}")
        info_lines.append("\n".join(formatted_paragraphs))
    else:
        info_lines.append("### 暫無簡介")

    description_text = "\n".join(info_lines)

    if len(description_text) > 4000:
        description_text = description_text[:3990] + "\n...(簡介過長自動收合)"

    embed = discord.Embed(
        url=book_data["url"],
        description=description_text,
        color=embed_color
    )

    embed.set_author(
        name=author_text,
        icon_url=author.display_avatar.url if hasattr(author, "display_avatar") else None
    )

    if book_data.get("cover"):
        embed.set_thumbnail(url=book_data["cover"])

    embed.set_footer(text=footer_text)
    return embed

def extract_card_state_from_message(message: discord.Message):
    """
    從已發送的 Discord 訊息中精準還原卡片狀態。
    確保機器人即使重新部署或重啟，舊書卡上的所有按鈕仍然 100% 永久有效！
    """
    if not message or not message.embeds:
        return None
    embed = message.embeds[0]
    desc = embed.description or ""

    # 1. 提取原發文者 ID
    author_id_m = re.search(r'📢 \*\*分享人\*\*：<@!?(\d+)>', desc)
    author_id = int(author_id_m.group(1)) if author_id_m else None

    # 2. 原作者暱稱
    author_name = "推書群友"
    if embed.author and embed.author.name:
        author_name = re.sub(r'^由\s+|\s+(?:一般推薦|強力推薦|閒聊分享|分享.*)$', '', embed.author.name).strip()

    # 3. 提取當前評價
    if "🔥 強力推薦" in desc:
        evaluation = "糧草"
    elif "⚠️ 改不推薦" in desc or "⚠️ 不推薦" in desc:
        evaluation = "改不推薦"
    else:
        evaluation = "乾糧"

    # 4. 提取同推名單
    up_m = re.search(r'👥 \*\*同推\*\*：([^\n\r]+)', desc)
    upvoters = [n.strip() for n in up_m.group(1).split(",") if n.strip()] if up_m else []

    # 5. 提取反推名單 (支援「反推」與舊格式「不推」)
    down_m = re.search(r'🚫 \*\*(?:反推|不推)\*\*：([^\n\r]+)', desc)
    downvoters = [n.strip() for n in down_m.group(1).split(",") if n.strip()] if down_m else []

    # 6. 書籍基本資料還原 (支援: ## 📖 [書名 (平台)](url)、### 📖、# 📖 與 embed.title 歷史格式)
    h_title_m = re.search(r'^(?:###|##|#)\s*📖\s*\[(.+?)\s*\((起點|番茄|刺蝟貓|[^\)]+)\)\]', desc, re.MULTILINE)
    if h_title_m:
        title_clean = h_title_m.group(1).strip()
        platform = h_title_m.group(2).strip()
    else:
        raw_title = embed.title or "書籍分享"
        title_m = re.search(r'^📖\s*(.+?)\s*\((起點|番茄|刺蝟貓|[^\)]+)\)$', raw_title)
        if title_m:
            title_clean = title_m.group(1).strip()
            platform = title_m.group(2).strip()
        else:
            title_clean = re.sub(r'^📖\s*\[[^\]]+\]\s*', '', raw_title).strip()
            platform = "小說平台"
            p_m = re.search(r'^📖\s*\[([^\]]+)\]', raw_title)
            if p_m:
                platform = p_m.group(1)

    url = embed.url or ""
    cover = embed.thumbnail.url if embed.thumbnail else None

    title_s_m = re.search(r'🔤 \*\*簡體原名\*\*：\[([^\]]+)\]', desc)
    title_s = title_s_m.group(1) if title_s_m else title_clean

    author_m = re.search(r'👤 \*\*作者\*\*：([^\s\n\r|｜]+)', desc)
    author = author_m.group(1).strip() if author_m else "未知"

    stats_m = re.search(r'📊 \*\*數據\*\*：([^\n\r]+?)(?=\s*🏷️|\n|\Z)', desc)
    stats = stats_m.group(1).strip() if stats_m else "詳見官網"

    tags_m = re.search(r'🏷️ \*\*標籤分類\*\*：([^\n\r]+)', desc)
    tags = tags_m.group(1).strip() if tags_m else "作品標籤"

    desc_split = re.split(r'(?:###\s*)?📝 \*\*?(?:完整)?作品簡介\*\*?：?', desc)
    raw_extracted_desc = desc_split[1].strip() if len(desc_split) > 1 else ""
    clean_desc_lines = [re.sub(r'^###\s+', '', l) for l in raw_extracted_desc.split("\n")]
    book_desc = "\n".join(clean_desc_lines).strip()

    book_data = {
        "platform": platform,
        "title_t": title_clean,
        "title_s": title_s,
        "author": author,
        "stats": stats,
        "tags": tags,
        "url": url,
        "cover": cover,
        "description": book_desc
    }

    # 構建一個 Mock Author 物件以支援 Embed 重建
    class MockEmbedAuthor:
        def __init__(self, uid, dname, avatar_url):
            self.id = uid
            self.display_name = dname
            self.mention = f"<@{uid}>" if uid else f"@{dname}"
            self.display_avatar = MagicMockAvatar(avatar_url)

    class MagicMockAvatar:
        def __init__(self, url):
            self.url = url or ""

    author_obj = MockEmbedAuthor(author_id, author_name, embed.author.icon_url if embed.author else "")

    return {
        "author_id": author_id,
        "author_obj": author_obj,
        "author_name": author_name,
        "evaluation": evaluation,
        "upvoters": upvoters,
        "downvoters": downvoters,
        "book_data": book_data
    }

def format_concurrence_text(upvoters: list, downvoters: list) -> str:
    """組裝試算表覆議欄位文字 (以最後狀態覆蓋)"""
    parts = []
    if upvoters:
        parts.append(f"{', '.join(upvoters)} 同推")
    if downvoters:
        parts.append(f"{', '.join(downvoters)} 反推")
    return " ｜ ".join(parts)

class BookActionView(discord.ui.View):
    """
    持久化卡片互動按鈕 (Persistent View)
    支援上下箭頭三級狀態切換（發書者 3 級、其他群友 3 級）
    """
    def __init__(
        self,
        book_data: dict = None,
        original_author: discord.Member = None,
        jump_url: str = "",
        should_sync: bool = False,
        upvoters: list = None,
        downvoters: list = None
    ):
        super().__init__(timeout=None)
        self.book_data = book_data
        self.original_author = original_author
        self.jump_url = jump_url
        self.should_sync = should_sync
        self.evaluation = "乾糧"
        self.upvoters = upvoters if upvoters is not None else []
        self.downvoters = downvoters if downvoters is not None else []

        # 若在發送時已確定是非推書頻道，移除推薦切換按鈕，且不加入查看書單按鈕 (僅保留刪除按鈕)
        if book_data is not None and not self.should_sync:
            self.remove_item(self.vote_up)
            self.remove_item(self.vote_down)
        elif GOOGLE_SHEET_VIEW_URL:
            # 僅推書頻道附帶查看線上書單
            self.add_item(discord.ui.Button(
                label="📊 書單",
                url=GOOGLE_SHEET_VIEW_URL,
                row=0
            ))

    def get_concurrence_text(self) -> str:
        """組裝試算表覆議欄位文字"""
        return format_concurrence_text(self.upvoters, self.downvoters)

    def _restore_state_if_needed(self, interaction: discord.Interaction):
        """從互動訊息中動態還原狀態，確保跨重啟永久有效"""
        state = extract_card_state_from_message(interaction.message)
        if not state:
            return None
        
        should_sync = is_sync_channel(interaction.channel)
        return {
            "author_id": state["author_id"],
            "author_obj": self.original_author if self.original_author else state["author_obj"],
            "author_name": state["author_name"],
            "evaluation": state["evaluation"],
            "upvoters": list(state["upvoters"]),
            "downvoters": list(state["downvoters"]),
            "book_data": self.book_data if self.book_data else state["book_data"],
            "jump_url": self.jump_url if self.jump_url else interaction.message.jump_url,
            "should_sync": should_sync
        }

    @discord.ui.button(label="🔼 推薦", style=discord.ButtonStyle.secondary, custom_id="vote_up_btn", row=0)
    async def vote_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self._restore_state_if_needed(interaction)
        if not state:
            await interaction.response.defer()
            return

        author_id = state["author_id"]
        author_obj = state["author_obj"]
        book_data = state["book_data"]
        evaluation = state["evaluation"]
        upvoters = state["upvoters"]
        downvoters = state["downvoters"]
        should_sync = state["should_sync"]
        jump_url = state["jump_url"]
        user_name = interaction.user.display_name

        # 1. 發書者：三級切換（改不推薦 -> 乾糧 -> 糧草）
        if author_id is not None and interaction.user.id == author_id:
            if evaluation in ["改不推薦", "不推薦"]:
                evaluation = "乾糧"
            elif evaluation == "乾糧":
                evaluation = "糧草"
            else:
                await interaction.response.defer()
                return

            new_embed = build_book_embed(
                book_data,
                author_obj,
                evaluation,
                is_sync_channel=should_sync,
                upvoters=upvoters,
                downvoters=downvoters
            )
            await interaction.response.edit_message(embed=new_embed, view=self)

            if should_sync and GOOGLE_SHEET_WEBHOOK_URL:
                await sync_to_google_sheet(
                    GOOGLE_SHEET_WEBHOOK_URL,
                    book_data,
                    state["author_name"],
                    jump_url,
                    status=evaluation,
                    concurrence=format_concurrence_text(upvoters, downvoters)
                )
            return

        # 2. 其他群友：三級切換（反推 -> 無 -> 同推）
        if user_name in downvoters:
            downvoters.remove(user_name)
        elif user_name not in upvoters:
            upvoters.append(user_name)
        else:
            await interaction.response.defer()
            return

        new_embed = build_book_embed(
            book_data,
            author_obj,
            evaluation,
            is_sync_channel=should_sync,
            upvoters=upvoters,
            downvoters=downvoters
        )
        await interaction.response.edit_message(embed=new_embed, view=self)

        if should_sync and GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                book_data,
                state["author_name"],
                jump_url,
                status=evaluation,
                concurrence=format_concurrence_text(upvoters, downvoters)
            )

    @discord.ui.button(label="🔽 減推", style=discord.ButtonStyle.secondary, custom_id="vote_down_btn", row=0)
    async def vote_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self._restore_state_if_needed(interaction)
        if not state:
            await interaction.response.defer()
            return

        author_id = state["author_id"]
        author_obj = state["author_obj"]
        book_data = state["book_data"]
        evaluation = state["evaluation"]
        upvoters = state["upvoters"]
        downvoters = state["downvoters"]
        should_sync = state["should_sync"]
        jump_url = state["jump_url"]
        user_name = interaction.user.display_name

        # 1. 發書者：三級切換（糧草 -> 乾糧 -> 改不推薦）
        if author_id is not None and interaction.user.id == author_id:
            if evaluation == "糧草":
                evaluation = "乾糧"
            elif evaluation == "乾糧":
                evaluation = "改不推薦"
            else:
                await interaction.response.defer()
                return

            new_embed = build_book_embed(
                book_data,
                author_obj,
                evaluation,
                is_sync_channel=should_sync,
                upvoters=upvoters,
                downvoters=downvoters
            )
            await interaction.response.edit_message(embed=new_embed, view=self)

            if should_sync and GOOGLE_SHEET_WEBHOOK_URL:
                await sync_to_google_sheet(
                    GOOGLE_SHEET_WEBHOOK_URL,
                    book_data,
                    state["author_name"],
                    jump_url,
                    status=evaluation,
                    concurrence=format_concurrence_text(upvoters, downvoters)
                )
            return

        # 2. 其他群友：三級切換（同推 -> 無 -> 反推）
        if user_name in upvoters:
            upvoters.remove(user_name)
        elif user_name not in downvoters:
            downvoters.append(user_name)
        else:
            await interaction.response.defer()
            return

        new_embed = build_book_embed(
            book_data,
            author_obj,
            evaluation,
            is_sync_channel=should_sync,
            upvoters=upvoters,
            downvoters=downvoters
        )
        await interaction.response.edit_message(embed=new_embed, view=self)

        if should_sync and GOOGLE_SHEET_WEBHOOK_URL:
            await sync_to_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                book_data,
                state["author_name"],
                jump_url,
                status=evaluation,
                concurrence=format_concurrence_text(upvoters, downvoters)
            )

    @discord.ui.button(label="🗑️ 刪除", style=discord.ButtonStyle.secondary, custom_id="delete_card_btn", row=0)
    async def delete_card(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self._restore_state_if_needed(interaction)
        author_id = state["author_id"] if state else (self.original_author.id if self.original_author else None)
        book_data = state["book_data"] if state else self.book_data
        should_sync = state["should_sync"] if state else self.should_sync

        # 僅原發文者有權刪除書卡
        if author_id is not None and interaction.user.id != author_id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以刪除這張書卡喔！", ephemeral=True)
            return

        # 若在非推書頻道 (僅展開書卡，未寫入表單)，直接刪除訊息即可，無需彈出表單刪除選單
        if not should_sync:
            try:
                await interaction.message.delete()
            except Exception:
                pass
            return

        # 若在推書頻道，彈出發文者專屬私密確認選單
        confirm_view = DeleteConfirmView(
            target_message=interaction.message,
            book_data=book_data,
            author_id=author_id
        )
        await interaction.response.send_message(
            content="⚠️ **確定要刪除這張書卡嗎？**\n請選擇您希望的刪除方式：",
            view=confirm_view,
            ephemeral=True
        )

class DeleteConfirmView(discord.ui.View):
    """
    發書者刪除書卡時的私密確認面板 (Ephemeral)
    提供「僅刪除 Discord 書卡」與「同時從線上書單刪除」兩種選項
    """
    def __init__(self, target_message: discord.Message, book_data: dict, author_id: int):
        super().__init__(timeout=60)
        self.target_message = target_message
        self.book_data = book_data
        self.author_id = author_id

    @discord.ui.button(label="🗑️ 僅刪除 Discord 書卡", style=discord.ButtonStyle.secondary, custom_id="delete_msg_only")
    async def delete_msg_only(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以操作喔！", ephemeral=True)
            return

        try:
            await self.target_message.delete()
        except Exception:
            pass

        await interaction.response.edit_message(content="✅ 已成功刪除 Discord 上的書卡訊息！", view=None)

    @discord.ui.button(label="🧹 同時從線上書單刪除", style=discord.ButtonStyle.secondary, custom_id="delete_msg_and_sheet")
    async def delete_msg_and_sheet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ 只有發布此網址的原作者才可以操作喔！", ephemeral=True)
            return

        # 1. 刪除 Discord 訊息
        try:
            await self.target_message.delete()
        except Exception:
            pass

        # 2. 同步從 Google 試算表刪除
        if GOOGLE_SHEET_WEBHOOK_URL and self.book_data:
            await delete_from_google_sheet(
                GOOGLE_SHEET_WEBHOOK_URL,
                novel_url=self.book_data.get("url", ""),
                title_t=self.book_data.get("title_t", "")
            )

        # 3. 徹底從推薦歷史 (賽博獵犬庫) 與快取中移除
        if self.book_data:
            url = self.book_data.get("url", "")
            title_t = self.book_data.get("title_t", "")
            
            keys_to_remove = []
            norm_res = await normalize_novel_url(url) if url else None
            if norm_res:
                target_key = f"{norm_res[0]}:{norm_res[2]}"
                keys_to_remove.append(target_key)

            # 同步檢查 recommend_history 中是否有匹配的書名或 jump_url
            for k, val in list(recommend_history.items()):
                if k in keys_to_remove or (url and url in val.get("jump_url", "")):
                    keys_to_remove.append(k)

            for k in set(keys_to_remove):
                recommend_history.pop(k, None)
                cache.pop(k, None)

        await interaction.response.edit_message(content="✅ 已成功刪除 Discord 書卡，並同步從 Google 線上書單與賽博獵犬紀錄中移除！", view=None)

    @discord.ui.button(label="❌ 取消", style=discord.ButtonStyle.secondary, custom_id="cancel_delete")
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="已取消刪除操作。", view=None)

class CyberHoundView(discord.ui.View):
    """持久化賽博獵犬通知按鈕 (Persistent View)"""
    def __init__(self, original_author: discord.Member = None):
        super().__init__(timeout=None)
        self.original_author = original_author

    @discord.ui.button(label="🙇 我知錯了", style=discord.ButtonStyle.secondary, custom_id="hound_dismiss_btn", row=0)
    async def dismiss_hound(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.original_author and interaction.user.id != self.original_author.id:
            await interaction.response.send_message("❌ 只有觸發獵犬的原發文者才可以刪除這則通知喔！", ephemeral=True)
            return

        await interaction.message.delete()

@tasks.loop(minutes=30)
async def auto_sync_sheet_task():
    """背景每 30 分鐘自動同步一次 Google 試算表最新推書資料（防止短時間高頻重複請求導致連線阻塞）"""
    await load_history_from_google_sheet()

@auto_sync_sheet_task.before_loop
async def before_auto_sync():
    await bot.wait_until_ready()

async def setup_hook():
    """註冊 Persistent Views，確保機器人重啟後所有按鈕永久有效"""
    bot.add_view(BookActionView())
    bot.add_view(CyberHoundView())

bot.setup_hook = setup_hook

@bot.event
async def on_ready():
    print(f"==================================================")
    print(f" 小說解析機器人已成功上線！")
    print(f" 機器人名稱：{bot.user.name} ({bot.user.id})")
    print(f" 支援平台：起點中文網 ｜ 番茄小說 ｜ 刺蝟貓")
    print(f" 展開書卡：所有文字頻道均會展開")
    print(f" 試算表同步頻道：已設定為 [{SYNC_CHANNELS}]")
    print(f" 持久化按鈕：已全域掛載 (重啟後歷史按鈕永久有效)")
    print(f" 背景排程：每 30 分鐘定時同步試算表")
    print(f"==================================================")
    
    # 啟動時自動從 Google 試算表載入歷史資料至獵犬庫
    await load_history_from_google_sheet()

    # 啟動背景定期每 30 分鐘同步 Google 試算表任務
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
            if not is_valid_book_data(book_data):
                book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
                if is_valid_book_data(book_data):
                    cache[history_key] = book_data

            if is_valid_book_data(book_data):
                found_count += 1
                # 記錄到獵犬庫
                if history_key not in recommend_history:
                    recommend_history[history_key] = {
                        "author_name": msg.author.display_name,
                        "jump_url": msg.jump_url,
                        "evaluation": "乾糧",
                        "upvoters": [],
                        "downvoters": []
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

def is_valid_book_data(data: dict) -> bool:
    """檢查抓取的小說資料是否完整有效 (書名不可空白或通用站名)"""
    if not data or not isinstance(data, dict):
        return False
    title = data.get("title_t", "").strip()
    if not title or title in ["起点中文网", "起點中文網", "番茄小說", "番茄小说", "刺蝟貓", "刺猬猫", "小說平台", "全部分类"]:
        return False
    return True

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
        hound_user = message.author.display_name

        # 賽博獵犬算進同推 (以最後狀態覆蓋)
        upvoters = prev_record.setdefault("upvoters", [])
        downvoters = prev_record.setdefault("downvoters", [])
        if hound_user in downvoters:
            downvoters.remove(hound_user)
        if hound_user not in upvoters and hound_user != first_user:
            upvoters.append(hound_user)

        if first_url:
            hound_text = f"🐶 **你賽博獵犬囉！**\n這本前面 **{first_user}** 已經推薦過了～（已將您計入同推名單） 🔗 [點擊查看前人推薦訊息]({first_url})"
        else:
            hound_text = f"🐶 **你賽博獵犬囉！**\n這本前面 **{first_user}** 已經推薦過了～（已將您計入同推名單）"

        hound_view = CyberHoundView(original_author=message.author)
        await message.reply(
            content=hound_text,
            view=hound_view,
            mention_author=False
        )

        # 同步更新表單的同推覆議
        if GOOGLE_SHEET_WEBHOOK_URL:
            concurrence_str = format_concurrence_text(upvoters, downvoters)

            book_data = cache.get(history_key)
            if not is_valid_book_data(book_data):
                book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
                if is_valid_book_data(book_data):
                    cache[history_key] = book_data

            if is_valid_book_data(book_data):
                await sync_to_google_sheet(
                    GOOGLE_SHEET_WEBHOOK_URL,
                    book_data,
                    first_user,
                    first_url,
                    status=prev_record.get("evaluation", "乾糧"),
                    concurrence=concurrence_str
                )
        return

    # 3. 取得書籍資料 (自動淘汰無效髒快取並強制重新爬取)
    book_data = cache.get(history_key)
    if not is_valid_book_data(book_data):
        async with message.channel.typing():
            book_data = await fetch_novel_info(platform, norm_url, JINA_API_KEY)
            if is_valid_book_data(book_data):
                cache[history_key] = book_data

    # 4. 發送書卡 (所有頻道均會發送書卡；但僅指定推書頻道會同步進 Google 試算表與更新獵犬庫)
    if is_valid_book_data(book_data):
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
                "jump_url": sent_msg.jump_url,
                "evaluation": "乾糧",
                "upvoters": [],
                "downvoters": []
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
    
    while True:
        try:
            await bot.start(DISCORD_TOKEN)
        except (discord.ConnectionClosed, aiohttp.ClientError, asyncio.TimeoutError) as e:
            print(f"⚠️ [Discord 連線中斷] 5 秒後自動嘗試重新連線... (原因: {e})")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"⚠️ [Discord 發生例外] 10 秒後自動重試... (原因: {e})")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
