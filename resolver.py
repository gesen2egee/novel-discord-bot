import os
import re
import aiohttp
import opencc
from typing import Optional, Dict, Any

# 簡繁轉換器 (opencc-python-reimplemented 傳入 's2t' 與 't2s')
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
    免本地 HTML 爬蟲、免維護 DOM 結構、免反爬阻擋。
    """
    jina_endpoint = f"https://r.jina.ai/{normalized_url}"
    headers = {
        "Accept": "application/json",
        "X-No-Cache": "false"
    }
    if jina_api_key:
        headers["Authorization"] = f"Bearer {jina_api_key}"

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(jina_endpoint) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                doc = data.get("data", {})
                
                raw_title = doc.get("title", "")
                raw_desc = doc.get("description", "")
                content = doc.get("content", "")
                
                # 從文章內容中嘗試提取封面圖片 (Markdown 格式 ![image](url))
                cover_url = None
                img_matches = re.findall(r'!\[.*?\]\((https?://[^\s\)]+)\)', content)
                for img in img_matches:
                    # 過濾一般圖示，鎖定包含封面特徵的圖片
                    if any(k in img for k in ["novel-pic", "bookcover", "kuangxiangit", "qdbimg", "byteimg"]):
                        cover_url = img
                        break
                if not cover_url and img_matches:
                    cover_url = img_matches[0]

                # 平台細節提取與清理
                title_clean = raw_title
                author = "未知作者"
                stats = "詳見官網"
                tags = "小說・作品"
                
                # 1. 起點中文網
                if platform == "qidian":
                    title_match = re.search(r'《?(.*?)》?_(.*?)(?:_起[點点]中文[網网]|$)', raw_title)
                    if title_match:
                        title_clean = title_match.group(1).strip()
                        author = title_match.group(2).strip()
                    else:
                        title_clean = raw_title.replace("起點中文網", "").replace("起点中文网", "").strip(" _-|")
                    
                    meta_tags = re.findall(r'(\d+(?:\.\d+)?(?:萬|万)?字|連載|完本|連載中|VIP|簽約|輕小說|玄幻|都市|仙俠|科幻|歷史|遊戲)', content)
                    if meta_tags:
                        unique_tags = list(dict.fromkeys(meta_tags))
                        word_items = [t for t in unique_tags if "字" in t]
                        if word_items:
                            stats = f"{word_items[0]}"
                        other_tags = [t for t in unique_tags if "字" not in t]
                        if other_tags:
                            tags = "・".join(other_tags[:5])

                # 2. 番茄小說 (包含 keyword)
                elif platform in ["fanqie", "fanqie_keyword"]:
                    title_match = re.search(r'(.*?)-(.*?)-(?:番茄小[說说]|$)', raw_title)
                    if title_match:
                        title_clean = title_match.group(1).strip()
                        author = title_match.group(2).strip()
                    else:
                        title_clean = raw_title.replace("番茄小說", "").replace("番茄小说", "").strip(" -_|")
                    
                    word_match = re.search(r'(\d+(?:\.\d+)?(?:萬|万)?字)', content)
                    read_match = re.search(r'(\d+(?:\.\d+)?(?:萬|万)?人在[讀读])', content)
                    stat_parts = []
                    if word_match:
                        stat_parts.append(word_match.group(1))
                    if read_match:
                        stat_parts.append(read_match.group(1))
                    if stat_parts:
                        stats = " ｜ ".join(stat_parts)
                    
                    tag_matches = re.findall(r'([^\s\n\|]{2,8}(?:・|·)[^\s\n\|]{2,8})', content)
                    if tag_matches:
                        tags = tag_matches[0].replace("·", "・")

                # 3. 刺蝟貓
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

                # 簡介提取 (完整呈現)
                description = raw_desc.strip()
                if len(description) < 30 and content:
                    desc_split = re.split(r'(?:作品簡介|內容簡介|簡介|简介)[：:\s]*\n', content)
                    if len(desc_split) > 1:
                        description = desc_split[1].split("\n\n目錄")[0].split("\n\n章节")[0].strip()
                    else:
                        description = content[:800].strip()

                if len(description) > 3500:
                    description = description[:3500] + "..."

                # 繁簡字元雙向處理
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
                    "description": desc_t if desc_t else "暫無簡介",
                    "tags": tags_t,
                    "stats": stats_t
                }
    except Exception as e:
        print(f"[Resolver Error] {e}")
        return None
