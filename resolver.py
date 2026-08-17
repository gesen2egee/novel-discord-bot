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
    """清理多餘的連續空白與換行"""
    if not text:
        return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

async def fetch_novel_info(platform: str, normalized_url: str, jina_api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    透過雲端 Reader API (r.jina.ai) 取得小說書籍結構化資料。
    免本地 HTML 爬蟲、精準正則提取作者、字數、標籤與真實簡介。
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
                tags = "小說作品"
                description = ""

                # ------------------- 1. 起點中文網 -------------------
                if platform == "qidian":
                    # 書名清理
                    title_clean = re.sub(r'(_起[點点]中文[網网]|_閱文集團).*$', '', raw_title).strip(" _-|《》")
                    
                    # 作者提取 (優先從內文正則尋找)
                    # 例如: 作者:洛上公子 或 ## [洛上公子](...)
                    author_match = re.search(r'(?:作者[：:\s]*|##\s*\[?)([^\s\n\r\]\(\)_]+)(?:\]|\s*更新時間|\s*更新时间|\s*著|\s*閱文|\s*阅文)', content)
                    if author_match and author_match.group(1) not in ["作品信息", "最新章节", "起点中文网"]:
                        author = author_match.group(1).strip()
                    else:
                        # 備用作者匹配
                        a_m = re.search(r'作者[：:]\s*([^\s\n\r]+)', content)
                        if a_m:
                            author = a_m.group(1).strip()

                    # 字數提取 (例如: _45.35万_ 字 或 45.35萬字)
                    word_match = re.search(r'(_?(\d+(?:\.\d+)?(?:萬|万)?)_?\s*字)', content)
                    if word_match:
                        stats = word_match.group(1).replace("_", "").strip()

                    # 標籤提取 (例如: 连载·签约·VIP·[武侠]·[武侠幻想])
                    tag_line = re.search(r'((?:連載|完本|連載中|签约|VIP|\[.+?\]|[^\n·]{2,6})(?:·[^\n]{2,30})+)', content)
                    if tag_line:
                        raw_tag_str = tag_line.group(1)
                        # 清理 markdown 連結如 [武侠](url)
                        clean_tag_str = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw_tag_str)
                        clean_tag_str = re.sub(r'[\[\]]', '', clean_tag_str).replace("·", "・")
                        tags = clean_tag_str.strip("・ ")
                    else:
                        tags = "武俠・連載・VIP"

                    # 簡介提取 (鎖定 ## 作品简介 與 下方月票/評論 之間)
                    desc_match = re.search(r'##\s*作品[簡简]介\s*\n+(.*?)(?:\n+####|\n+##|\n+\[月票\]|\n+目录|\n+目錄|\Z)', content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                    else:
                        description = raw_desc

                # ------------------- 2. 番茄小說 -------------------
                elif platform in ["fanqie", "fanqie_keyword"]:
                    title_match = re.search(r'(.*?)-(.*?)-(?:番茄小[說说]|$)', raw_title)
                    if title_match:
                        title_clean = title_match.group(1).strip()
                        author = title_match.group(2).strip()
                    else:
                        title_clean = raw_title.replace("番茄小說", "").replace("番茄小说", "").strip(" -_|")

                    # 字數與在讀
                    word_match = re.search(r'(\d+(?:\.\d+)?(?:萬|万)?字)', content)
                    read_match = re.search(r'(\d+(?:\.\d+)?(?:萬|万)?人在[讀读])', content)
                    stat_parts = []
                    if word_match:
                        stat_parts.append(word_match.group(1))
                    if read_match:
                        stat_parts.append(read_match.group(1))
                    if stat_parts:
                        stats = " ｜ ".join(stat_parts)

                    # 標籤
                    tag_matches = re.findall(r'([^\s\n\|]{2,8}(?:・|·)[^\s\n\|]{2,8})', content)
                    if tag_matches:
                        tags = tag_matches[0].replace("·", "・")

                    # 簡介
                    desc_match = re.search(r'(?:简介|簡介|内容简介)[：:\s]*\n+(.*?)(?:\n+目录|\n+目錄|\n+章节|\n+最新章节|\Z)', content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                    else:
                        description = raw_desc

                # ------------------- 3. 刺蝟貓 -------------------
                elif platform == "ciweimao":
                    title_match = re.search(r'(.*?)_(.*?)(?:_刺[蝟猬][貓猫]|$)', raw_title)
                    if title_match:
                        title_clean = title_match.group(1).strip()
                        author = title_match.group(2).strip()
                    else:
                        title_clean = raw_title.replace("刺蝟貓", "").replace("刺猬猫", "").strip(" _-|")

                    word_match = re.search(r'(\d+(?:\.\d+)?(?:萬|万)?字|\d+字)', content)
                    if word_match:
                        stats = word_match.group(1)

                    tag_matches = re.findall(r'(?:分類|標籤|标签)[：:]\s*([^\n\r]+)', content)
                    if tag_matches:
                        tags = tag_matches[0].strip().replace(" ", "・").replace(",", "・")

                    desc_match = re.search(r'(?:简介|簡介|简介：|簡介：)\s*\n+(.*?)(?:\n+目录|\n+目錄|\n+章节|\Z)', content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                    else:
                        description = raw_desc

                # 簡介後處理 (過濾多餘 Markdown 空白與符號)
                if not description:
                    description = raw_desc if raw_desc else "暫無簡介"

                # 繁簡雙向字元處理
                title_traditional = s2t_converter.convert(title_clean)
                title_simplified = t2s_converter.convert(title_clean)
                author_t = s2t_converter.convert(author)
                desc_t = s2t_converter.convert(clean_text(description))
                tags_t = s2t_converter.convert(tags)
                stats_t = s2t_converter.convert(stats)

                return {
                    "platform": PLATFORM_NAMES.get(platform, "小說平台"),
                    "title_t": title_traditional,
                    "title_s": title_simplified,
                    "author": author_t,
                    "url": normalized_url,
                    "cover": cover_url,
                    "description": desc_t,
                    "tags": tags_t,
                    "stats": stats_t
                }
    except Exception as e:
        print(f"[Resolver Error] {e}")
        return None
