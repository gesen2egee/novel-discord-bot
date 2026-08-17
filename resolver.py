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
    """清理多餘的連續空白、換行與無效的 Markdown 連結"""
    if not text:
        return ""
    # 過濾 javascript: 虛擬連結與按鈕標籤
    text = re.sub(r'\[?(?:作品[簡简]介|作品[信資]息|立即[閱阅][讀读]|放入[書书]架|訂閱|订阅)\]?\(javascript:[^\)]*\)', '', text)
    text = re.sub(r'\[?(?:\[\s*\]|\(\s*\))', '', text)
    # 過濾開頭的項目符號留白
    text = re.sub(r'^\s*[\*•\-]\s*\n', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def clean_and_format_tags(raw_text: str) -> str:
    """
    清理並格式化標籤：
    1. 支援保留合法的 Markdown 連結 [分類名](https://...)，並將標籤文字轉為繁體，同時保持網址純淨。
    2. 支援純文字標籤（如 連載、簽約、VIP 等）。
    3. 徹底濾除截斷或未閉合的破損網址（如 (https://www.qidian... 等雜訊）。
    4. 統一以「・」美化分隔。
    """
    if not raw_text:
        return "作品標籤"

    # 使用 placeholder 暫存合法的 Markdown 連結
    link_map = {}
    def replace_link(match):
        label = match.group(1).strip()
        url = match.group(2).strip()
        label_t = s2t_converter.convert(label)
        placeholder = f"__MDLINK{len(link_map)}__"
        link_map[placeholder] = f"[{label_t}]({url})"
        return f" {placeholder} "

    # 1. 替換完整合法的 Markdown 連結
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s\)]+)\)', replace_link, raw_text)

    # 2. 徹底過濾所有不完整或殘留的 http/https 網址 (如未閉合的 (https://www.qidian...)
    text = re.sub(r'\(?https?://[^\s\)]*\)?', '', text)

    # 3. 移除多餘符號（但保留字母與底線 placeholder）
    text = re.sub(r'[\[\]\(\)\{\}*#`]', ' ', text)

    # 4. 依照分隔符分割
    raw_items = re.split(r'[·•|｜,，/、\s]+', text)

    valid_tags = []
    for item in raw_items:
        item = item.strip(" -·•|/，,")
        if not item:
            continue
        if item in link_map:
            valid_tags.append(link_map[item])
        else:
            if len(item) > 15:
                continue
            if item.isdigit():
                continue
            if any(bad in item.lower() for bad in ["http", "www", "qidian", "fanqie", "ciweimao", ".com", "html"]):
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
                    
                    author_match = re.search(r'(?:作者[：:\s]*|##\s*\[?)([^\s\n\r\]\(\)_]+)(?:\]|\s*更新時間|\s*更新时间|\s*著|\s*閱文|\s*阅文)', content)
                    if author_match and author_match.group(1) not in ["作品信息", "最新章节", "起点中文网"]:
                        author = author_match.group(1).strip()
                    else:
                        a_m = re.search(r'作者[：:]\s*([^\s\n\r]+)', content)
                        if a_m:
                            author = a_m.group(1).strip()

                    word_match = re.search(r'(_?(\d+(?:\.\d+)?(?:萬|万)?)_?\s*字)', content)
                    if word_match:
                        stats = word_match.group(1).replace("_", "").strip()

                    tag_line = re.search(r'(?:^|\n)((?:连载中?|完本|已完结|连载|签约|VIP|免费)[·\s]+[^\n\r]+)', content)
                    if tag_line:
                        tags = clean_and_format_tags(tag_line.group(1))
                    else:
                        # 備援：若無連載狀態標記，抓取頂部分類導航
                        nav_match = re.search(r'\[首页\]\(https://www\.qidian\.com/\)[^\n]*', content)
                        if nav_match:
                            tags = clean_and_format_tags(nav_match.group(0))
                        else:
                            tags = "連載・作品推薦"

                    desc_match = re.search(r'##\s*作品[簡简]介\s*\n+(.*?)(?:\n+####|\n+##|\n+\[月票\]|\n+目录|\n+目錄|\Z)', content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
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

                    author_m = re.search(r'([^\s\n\r/]+)\s*/\s*著|作者[：:\s]+([^\s\n\r]+)', content)
                    if author_m:
                        author = (author_m.group(1) or author_m.group(2)).strip()

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
                        tags = clean_and_format_tags(tag_m.group(1))
                    else:
                        tags = "都市・穿越・連載中"

                    desc_m = re.search(r'(?:\[下载番茄小说\][^\n]*\n+|简介[：:\s]*\n+)(.*?)(?:\n+男频|\n+女频|\n+目录|\n+目錄|\n+正序|\Z)', content, re.DOTALL)
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
                        tags = clean_and_format_tags("・".join(tag_list))
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
