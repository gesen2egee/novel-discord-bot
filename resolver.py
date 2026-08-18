import os
import re
import aiohttp
import opencc
from typing import Optional, Dict, Any

# 簡繁轉換器
s2t_converter = opencc.OpenCC('s2t')
t2s_converter = opencc.OpenCC('t2s')

PLATFORM_NAMES = {
    "qidian": "起點中文網",
    "fanqie": "番茄小說",
    "fanqie_keyword": "番茄小說",
    "ciweimao": "刺蝟貓"
}

def clean_text(text: str) -> str:
    """清理多餘的連續空白、換行、章節目錄連結與雜訊"""
    if not text:
        return ""
    # 過濾 javascript: 虛擬連結與按鈕標籤
    text = re.sub(r'\[?(?:作品[簡简]介|作品[信資]息|立即[閱阅][讀读]|放入[書书]架|訂閱|订阅)\]?\(javascript:[^\)]*\)', '', text)
    text = re.sub(r'\[?(?:\[\s*\]|\(\s*\))', '', text)
    # 若包含目錄標題或章節列表，直接於起始處截斷
    text = re.split(r'\n+#+\s*(?:目录|目錄|最新章节|第一卷)|(?:\n+|^)\s*\[?第\s*\d+\s*章', text, maxsplit=1)[0]
    # 過濾開頭的項目符號留白
    text = re.sub(r'^\s*[\*•\-]\s*\n', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    cleaned = text.strip()
    if len(cleaned) > 500:
        cleaned = cleaned[:490] + "..."
    return cleaned

def clean_tags(raw_text: str) -> str:
    """
    純淨標籤清洗：
    1. 將 [標籤名](url) 提取為乾淨純文字「標籤名」
    2. 移除所有殘留網址、括號、引號等雜訊
    3. 全自動轉換為繁體中文，並以「・」美化排列
    """
    if not raw_text:
        return "作品標籤"
    # 提取 Markdown 連結文字
    text = re.sub(r'\[([^\]]+)\]\([^\)]*\)?', r'\1', raw_text)
    # 過濾所有殘留 URL
    text = re.sub(r'\(?https?://[^\s\)]*\)?', '', text)
    # 過濾多餘符號
    text = re.sub(r'[\[\]\(\)\{\}*#`"\'“”‘’]', ' ', text)
    raw_items = re.split(r'[·•|｜,，/、\s]+', text)

    valid_tags = []
    for item in raw_items:
        item = item.strip(" -·•|/，,")
        if not item or item.isdigit() or len(item) > 15:
            continue
        if any(bad in item.lower() for bad in ['http', 'www', 'qidian', 'fanqie', 'ciweimao', '.com', 'html', 'chapter', '正文卷', '免费试读', '加入书架', '作品信息', '在线阅读']):
            continue
        item_t = s2t_converter.convert(item)
        if item_t not in valid_tags:
            valid_tags.append(item_t)

    return "・".join(valid_tags) if valid_tags else "作品標籤"

def format_word_count(num_str: str) -> str:
    """將純數字或帶萬字數字格式化為漂亮的萬字字串"""
    num_str = num_str.replace(",", "").replace("_", "").strip()
    if "万" in num_str or "萬" in num_str:
        return f"{num_str}字" if "字" not in num_str else num_str
    if num_str.isdigit():
        val = int(num_str)
        if val >= 10000:
            return f"{val / 10000:.2f} 萬字"
        return f"{val} 字"
    return num_str

async def fetch_novel_info(platform: str, normalized_url: str, jina_api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    透過雲端 Reader API (r.jina.ai) 取得小說書籍結構化資料。
    免本地 HTML 爬蟲、高強健性正則提取作者、字數、標籤與 100% 純淨真實簡介。
    """
    jina_endpoint = f"https://r.jina.ai/{normalized_url}"
    headers = {
        "Accept": "application/json",
        "X-No-Cache": "false"
    }
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    try:
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(jina_endpoint) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                doc = data.get("data", {})
                
                raw_title = doc.get("title", "").strip()
                raw_desc = doc.get("description", "").strip()
                content = doc.get("content", "")

                # 1. 封面圖片提取
                cover_url = None
                img_matches = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
                for img in img_matches:
                    if any(k in img for k in ["bookcover", "qdbimg", "novel-pic", "byteimg", "kuangxiangit"]):
                        cover_url = img
                        break
                if not cover_url and img_matches:
                    cover_url = img_matches[0]

                title_clean = raw_title
                author = "未知作者"
                stats = "詳見官網"
                tags = "作品標籤"
                description = ""

                # =========================================================================
                # 1. 起點中文網
                # =========================================================================
                if platform == "qidian":
                    title_clean = re.sub(r'(_起[點点]中文[網网]|_閱文集團).*$', '', raw_title).strip(" _-|《》")
                    # 若標題被清空或為通用站名，從 content 或 raw_desc 提取真實書名
                    if not title_clean or title_clean in ["起点中文网", "起點中文網", "起点读书", "起点女生网", "全部分类"]:
                        t_match = re.search(r'(?:^|\n)#+\s*([^\n\r#\[\]]+?)(?:\s+在线阅读|\s+更新时间|\s*\n|\Z)', content)
                        if t_match and t_match.group(1).strip() not in ["起点中文网", "全部分类", "作品信息"]:
                            title_clean = t_match.group(1).strip()
                        elif raw_desc:
                            book_in_desc = re.search(r'《([^》]+)》', raw_desc)
                            if book_in_desc:
                                title_clean = book_in_desc.group(1).strip()
                    
                    author_match = re.search(r'(?:作者[：:\s]*|##\s*\[?)([^\s\n\r\]\(\)_]+)(?:\]|\s*更新時間|\s*更新时间|\s*著|\s*閱文|\s*阅文)', content)
                    if author_match and author_match.group(1) not in ["作品信息", "最新章节", "起点中文网"]:
                        author = author_match.group(1).strip()
                    else:
                        a_m = re.search(r'作者[：:]\s*([^\s\n\r]+)', content)
                        if a_m:
                            author = a_m.group(1).strip()
                        elif raw_desc:
                            author_in_desc = re.search(r'([^\s\n\r]+?)(?:创作的|著的|所著)', raw_desc)
                            if author_in_desc:
                                author = author_in_desc.group(1).strip()

                    word_match = re.search(r'(_?(\d+(?:\.\d+)?(?:萬|万)?)_?\s*字)', content)
                    if word_match:
                        stats = word_match.group(1).replace("_", "").strip()

                    tag_line = re.search(r'(?:^|\n)((?:连载中?|完本|已完结|连载|签约|VIP|免费)[·\s]+[^\n\r]+)', content)
                    if tag_line:
                        tags = clean_tags(tag_line.group(1))
                    else:
                        tags = "連載・作品推薦"

                    # 簡介提取 (優先抓取 ## 作品簡介；若無則抓取標籤下方精華簡介；最後從 raw_desc 提純)
                    desc_match = re.search(r'##\s*作品[簡简]介\s*\n+(.*?)(?:\n+####|\n+##|\n+\[月票\]|\n+目录|\n+目錄|\Z)', content, re.DOTALL)
                    if desc_match and desc_match.group(1).strip():
                        description = desc_match.group(1).strip()
                    else:
                        sub_desc = re.search(r'(?:连载|完本|签约|VIP|免费)[^\n]*\n+\s*(.*?)(?:\n+_\d+|\n+\[免费试读\]|\n+##|\n+####|\Z)', content, re.DOTALL)
                        if sub_desc and sub_desc.group(1).strip():
                            description = sub_desc.group(1).strip()
                        elif raw_desc:
                            # 從 raw_desc 提純（過濾開頭的 "xxx创作的小说...最新章节:xxx。"）
                            desc_clean_m = re.search(r'最新章节[：:][^\n\r。]+[。|\n]\s*(.*)', raw_desc, re.DOTALL)
                            description = desc_clean_m.group(1).strip() if desc_clean_m else raw_desc
                        else:
                            description = raw_desc

                # =========================================================================
                # 2. 番茄小說 (含 /keyword/ 與 /page/)
                # =========================================================================
                elif platform in ["fanqie", "fanqie_keyword"]:
                    img_title_m = re.search(r'!\[Image\s*\d*:\s*([^\]]+)\]', content)
                    if img_title_m and "番茄" not in img_title_m.group(1):
                        title_clean = img_title_m.group(1).strip()
                    else:
                        title_clean = re.sub(r'(-番茄小[說说]|-番茄免费小[說说]).*$', '', raw_title).strip(" -_|《》")
                        if "-" in title_clean:
                            parts = title_clean.split("-")
                            title_clean = parts[0].strip()
                            if len(parts) > 1:
                                author = parts[1].strip()

                    author_m = re.search(
                        r'!\[Image\s*\d*:[^\]]*?作者\s*([^\s\n\r\]]+)\]|'
                        r'([^\s\n\r/]+)\s*/\s*著|'
                        r'作者[：:\s]+([^\s\n\r]+)|'
                        r'!\[Image[^\]]*\]\([^\)]+\)\[([^\]\n\r]+)\]\(https?://(?:fanqienovel\.com|www\.changdunovel\.com)/page/',
                        content
                    )
                    if author_m:
                        author = (author_m.group(1) or author_m.group(2) or author_m.group(3) or author_m.group(4)).strip()

                    word_match = re.search(r'(\d+(?:\.\d+)?\s*(?:萬|万)?\s*字)', content)
                    read_match = re.search(r'(\d+(?:\.\d+)?\s*(?:萬|万)?\s*人在[讀读])', content)
                    stat_parts = []
                    if word_match:
                        stat_parts.append(word_match.group(1).replace(" ", ""))
                    if read_match:
                        stat_parts.append(read_match.group(1).replace(" ", ""))
                    if stat_parts:
                        stats = " ｜ ".join(stat_parts)

                    tag_m = re.search(r'(?:连载中|完结|已完结)\s+([^\n\r]+?)(?=\s*\[|\s*\n|\s*\d+章)', content)
                    if tag_m:
                        tags = clean_tags(tag_m.group(1))
                    else:
                        tags = "都市・穿越・連載中"

                    desc_m = re.search(
                        r'(?:##\s*作品[簡简]介\s*\n+|简介[：:\s]*\n+)(.*?)(?:\n+#+\s*|\n+男频|\n+女频|\n+目录|\n+目錄|\n+正序|\n+倒序|\n+第一卷|\Z)',
                        content,
                        re.DOTALL
                    )
                    if desc_m:
                        description = desc_m.group(1).strip()
                    else:
                        description = raw_desc

                # =========================================================================
                # 3. 刺蝟貓 (含 www, wap, mip)
                # =========================================================================
                elif platform == "ciweimao":
                    title_m = re.search(r'^(.*?)(?:最新[章節章节]|无弹窗|_刺[蝟猬][貓猫]|-欢乐书客|\(|$)', raw_title)
                    if title_m:
                        title_clean = title_m.group(1).strip(" _-|:：")
                    else:
                        title_clean = raw_title.split("_")[0].strip()

                    author_m = re.search(r'\(([^\)\(]+)\),|###\s*作者[信資]息\s*\n+.*?(?:###\s*([^\s\n\r\[\]]+)|\[([^\s\n\r\]]+)\]\(https://www.ciweimao.com/reader/)', content, re.DOTALL)
                    if author_m:
                        author = (author_m.group(1) or author_m.group(2) or author_m.group(3)).strip()
                    else:
                        t_author = re.search(r'\(([^)]+)\)', raw_title)
                        if t_author:
                            author = t_author.group(1).strip()

                    word_m = re.search(r'总字数[：:]\s*\**(\d+)\**|完成字数[：:]\s*_?(\d+)_?|(\d+(?:\.\d+)?(?:萬|万)?字)', content)
                    click_m = re.search(r'总点击[：:]\s*\**([^\s\*]+)\**', content)
                    stat_parts = []
                    if word_m:
                        w_val = word_m.group(1) or word_m.group(2) or word_m.group(3)
                        stat_parts.append(format_word_count(w_val))
                    if click_m:
                        stat_parts.append(f"{click_m.group(1)} 點擊")
                    if stat_parts:
                        stats = " ｜ ".join(stat_parts)

                    tag_m = re.findall(r'\[([^\]]+)\]\(https://www.ciweimao.com/(?:book_list|index/header_cate_list)[^\)]+\)', content)
                    tag_extra = re.search(r'(连载中|已完结|完结)', content)
                    tag_list = list(tag_m)
                    if tag_extra and tag_extra.group(1) not in tag_list:
                        tag_list.insert(0, tag_extra.group(1))
                    if tag_list:
                        tags = clean_tags("・".join(tag_list))
                    else:
                        tags = "宅文・歷史軍事・連載中"

                    # 簡介提取 (過濾 [作品信息] 與 [作品简介] 等 javascript 按鈕)
                    desc_m = re.search(r'(?:\[作品[簡简]介\][^\n]*\n+|简介[：:\s]*\n+)(.*?)(?:\n+（本站[鄭郑]重提醒|\n+小说性质|\n+###|\n+####|\n+目录|\Z)', content, re.DOTALL)
                    if desc_m:
                        raw_ciwei_desc = desc_m.group(1)
                    else:
                        raw_ciwei_desc = raw_desc

                    # 清理刺蝟貓特定按鈕與雜訊
                    raw_ciwei_desc = re.sub(r'[\*•\-]?\s*\[?作品[信資]息\]?\(javascript:[^\)]*\)', '', raw_ciwei_desc)
                    raw_ciwei_desc = re.sub(r'（?本站[鄭郑]重提醒.*?切勿模仿[。)]?', '', raw_ciwei_desc)
                    description = raw_ciwei_desc

                if not description:
                    description = raw_desc if raw_desc else "暫無簡介"

                # 繁簡雙向字元處理與最終清理
                title_traditional = s2t_converter.convert(title_clean)
                title_simplified = t2s_converter.convert(title_clean)
                author_t = s2t_converter.convert(author)
                desc_t = s2t_converter.convert(clean_text(description))
                stats_t = s2t_converter.convert(stats)

                return {
                    "platform": PLATFORM_NAMES.get(platform, "小說平台"),
                    "title_t": title_traditional,
                    "title_s": title_simplified,
                    "author": author_t,
                    "url": normalized_url,
                    "cover": cover_url,
                    "description": desc_t,
                    "tags": tags,
                    "stats": stats_t
                }
    except Exception as e:
        print(f"[Resolver Error] {e}")
        return None
