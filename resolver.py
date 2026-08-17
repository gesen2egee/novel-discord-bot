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
                    
                    # 作者提取 (優先從內文正則尋找)
                    author_match = re.search(r'(?:作者[：:\s]*|##\s*\[?)([^\s\n\r\]\(\)_]+)(?:\]|\s*更新時間|\s*更新时间|\s*著|\s*閱文|\s*阅文)', content)
                    if author_match and author_match.group(1) not in ["作品信息", "最新章节", "起点中文网"]:
                        author = author_match.group(1).strip()
                    else:
                        a_m = re.search(r'作者[：:]\s*([^\s\n\r]+)', content)
                        if a_m:
                            author = a_m.group(1).strip()

                    # 字數提取
                    word_match = re.search(r'(_?(\d+(?:\.\d+)?(?:萬|万)?)_?\s*字)', content)
                    if word_match:
                        stats = word_match.group(1).replace("_", "").strip()

                    # 標籤提取
                    tag_line = re.search(r'((?:連載|完本|連載中|签约|VIP|\[.+?\]|[^\n·]{2,6})(?:·[^\n]{2,30})+)', content)
                    if tag_line:
                        raw_tag_str = tag_line.group(1)
                        clean_tag_str = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', raw_tag_str)
                        clean_tag_str = re.sub(r'[\[\]]', '', clean_tag_str).replace("·", "・")
                        tags = clean_tag_str.strip("・ ")
                    else:
                        tags = "輕小說・連載・VIP"

                    # 簡介提取 (鎖定 ## 作品简介 與 下方月票/評論 之間)
                    desc_match = re.search(r'##\s*作品[簡简]介\s*\n+(.*?)(?:\n+####|\n+##|\n+\[月票\]|\n+目录|\n+目錄|\Z)', content, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                    else:
                        description = raw_desc

                # =========================================================================
                # 2. 番茄小說 (含 /keyword/ 搜尋頁與 /page/ 書籍主頁)
                # =========================================================================
                elif platform in ["fanqie", "fanqie_keyword"]:
                    # 書名提取：若有 Markdown 圖片標題，優先拿圖片上的真實書名
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

                    # 作者提取 (例如: 黑猫梦境 / 著 或 作者：XXX)
                    author_m = re.search(r'([^\s\n\r/]+)\s*/\s*著|作者[：:\s]+([^\s\n\r]+)', content)
                    if author_m:
                        author = (author_m.group(1) or author_m.group(2)).strip()

                    # 字數與在讀人數
                    word_match = re.search(r'(\d+(?:\.\d+)?\s*(?:萬|万)?\s*字)', content)
                    read_match = re.search(r'(\d+(?:\.\d+)?\s*(?:萬|万)?\s*人在[讀读])', content)
                    stat_parts = []
                    if word_match:
                        stat_parts.append(word_match.group(1).replace(" ", ""))
                    if read_match:
                        stat_parts.append(read_match.group(1).replace(" ", ""))
                    if stat_parts:
                        stats = " ｜ ".join(stat_parts)

                    # 標籤提取 (例如: 连载中 男频衍生 穿越 明朝 同人)
                    tag_m = re.search(r'(?:连载中|完结|已完结)\s+([^\n\r]+?)(?=\s*\[|\s*\n|\s*\d+章)', content)
                    if tag_m:
                        raw_t = tag_m.group(1).strip()
                        tags = re.sub(r'\s+', '・', raw_t)
                    else:
                        tags = "都市・穿越・連載中"

                    # 簡介提取
                    # 在番茄中，簡介通常在 [开始阅读] 或 [下载番茄小说] 後面
                    desc_m = re.search(r'(?:\[下载番茄小说\][^\n]*\n+|简介[：:\s]*\n+)(.*?)(?:\n+男频|\n+女频|\n+目录|\n+目錄|\n+正序|\Z)', content, re.DOTALL)
                    if desc_m:
                        description = desc_m.group(1).strip()
                    else:
                        description = raw_desc

                # =========================================================================
                # 3. 刺蝟貓 (含 www, wap, mip)
                # =========================================================================
                elif platform == "ciweimao":
                    # 書名清理 (例如: 大明:征服天堂最新章节(六角)... -> 大明:征服天堂)
                    title_m = re.search(r'^(.*?)(?:最新[章節章节]|无弹窗|_刺[蝟猬][貓猫]|-欢乐书客|\(|$)', raw_title)
                    if title_m:
                        title_clean = title_m.group(1).strip(" _-|:：")
                    else:
                        title_clean = raw_title.split("_")[0].strip()

                    # 作者提取 (例如: Title 裡的 (六角) 或 ### 作者信息\n... ### 六角)
                    author_m = re.search(r'\(([^\)\(]+)\),|###\s*作者[信資]息\s*\n+.*?(?:###\s*([^\s\n\r\[\]]+)|\[([^\s\n\r\]]+)\]\(https://www.ciweimao.com/reader/)', content, re.DOTALL)
                    if author_m:
                        author = (author_m.group(1) or author_m.group(2) or author_m.group(3)).strip()
                    else:
                        # 備用 Title 正則
                        t_author = re.search(r'\(([^)]+)\)', raw_title)
                        if t_author:
                            author = t_author.group(1).strip()

                    # 字數與點擊量提取 (例如: 总字数：9420864 或 942万字)
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

                    # 標籤提取 (例如: [宅文]>[历史军事] / 连载中)
                    tag_m = re.findall(r'\[([^\]]+)\]\(https://www.ciweimao.com/(?:book_list|index/header_cate_list)[^\)]+\)', content)
                    tag_extra = re.search(r'(连载中|已完结|完结)', content)
                    tag_list = list(tag_m)
                    if tag_extra and tag_extra.group(1) not in tag_list:
                        tag_list.insert(0, tag_extra.group(1))
                    if tag_list:
                        tags = "・".join(tag_list)
                    else:
                        tags = "宅文・歷史軍事・連載中"

                    # 簡介提取 (鎖定 [作品简介] 與 下方 [本站郑重提醒/目录] 之間)
                    desc_m = re.search(r'(?:\[作品简介\][^\n]*\n+|简介[：:\s]*\n+)(.*?)(?:\n+（本站郑重提醒|\n+小说性质|\n+###|\n+####|\n+目录|\Z)', content, re.DOTALL)
                    if desc_m:
                        description = desc_m.group(1).strip()
                    else:
                        description = raw_desc

                # 清理免責聲明與系統尾巴
                if description:
                    description = re.sub(r'（?本站[鄭郑]重提醒.*?切勿模仿[。)]?', '', description)
                    description = clean_text(description)

                if not description:
                    description = raw_desc if raw_desc else "暫無簡介"

                # 繁簡雙向字元處理
                title_traditional = s2t_converter.convert(title_clean)
                title_simplified = t2s_converter.convert(title_clean)
                author_t = s2t_converter.convert(author)
                desc_t = s2t_converter.convert(description)
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
