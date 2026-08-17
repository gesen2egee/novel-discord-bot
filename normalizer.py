import re
import aiohttp
from typing import Optional, Tuple

# 1. 起點：匹配 /book/{id}、/info/{id} 或 App 分享 bookId={id}（排除 /chapter/）
RE_QIDIAN = re.compile(
    r'(?:(?:www\.|m\.|book\.)?qidian\.com/(?:book|info)/(\d+)|(?:magev6|h5)\.if\.qidian\.com/.*?[?&]bookId=(\d+))',
    re.IGNORECASE
)

# 2. 番茄：匹配 /page/{id} 或 changdunovel book_id={id} 或 /keyword/{id} 或 zlink 短網址（排除 /reader/）
RE_FANQIE_PAGE = re.compile(
    r'(?:fanqienovel\.com/page/(\d+)|changdunovel\.com/.*?[?&]book_id=(\d+))',
    re.IGNORECASE
)
RE_FANQIE_KEYWORD = re.compile(
    r'fanqienovel\.com/keyword/(\d+)',
    re.IGNORECASE
)
RE_FANQIE_ZLINK = re.compile(
    r'https?://zlink\.fqnovel\.com/[a-zA-Z0-9]+',
    re.IGNORECASE
)

# 3. 刺蝟貓：匹配 /book/{id}、/chapter-list/{id}（排除 /chapter/{id}）
RE_CIWEIMAO = re.compile(
    r'(?:(?:www\.|wap\.|mip\.|m\.)?(?:ciweimao|hbooker)\.com/(?:book|chapter-list)/(\d+))',
    re.IGNORECASE
)

# 排除單章的快速黑名單正則
RE_CHAPTER_BLACKLIST = re.compile(
    r'(?:/reader/\d+|/chapter/\d+|read\.qidian\.com/chapter|\.qidian\.com/chapter/)',
    re.IGNORECASE
)

async def resolve_short_url(url: str) -> str:
    """自動還原短網址 (如 zlink.fqnovel.com)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return str(resp.url)
    except Exception:
        return url

async def normalize_novel_url(message_content: str) -> Optional[Tuple[str, str, str]]:
    """
    從訊息文字中辨識小說平台並正規化為標準電腦版書籍首頁。
    
    回傳值: (平台代碼, 標準正規化網址, 原始/正規ID)
    若非支援的書籍網址或屬於單章閱讀頁，則回傳 None。
    """
    # 檢查是否為單章閱讀頁（若是則略過不解析）
    # 注意：需排除刺蝟貓的 /chapter-list/ 目錄頁
    if "/chapter-list/" not in message_content and RE_CHAPTER_BLACKLIST.search(message_content):
        return None

    # 1. 檢查起點
    qidian_match = RE_QIDIAN.search(message_content)
    if qidian_match:
        book_id = qidian_match.group(1) or qidian_match.group(2)
        norm_url = f"https://www.qidian.com/book/{book_id}/"
        return "qidian", norm_url, book_id

    # 2. 檢查番茄短鏈 zlink
    zlink_match = RE_FANQIE_ZLINK.search(message_content)
    if zlink_match:
        real_url = await resolve_short_url(zlink_match.group(0))
        # 轉址後再次比對番茄 page
        fq_m = RE_FANQIE_PAGE.search(real_url)
        if fq_m:
            book_id = fq_m.group(1) or fq_m.group(2)
            norm_url = f"https://fanqienovel.com/page/{book_id}"
            return "fanqie", norm_url, book_id

    # 3. 檢查番茄書籍頁 (Page / Changdu)
    fanqie_page_match = RE_FANQIE_PAGE.search(message_content)
    if fanqie_page_match:
        book_id = fanqie_page_match.group(1) or fanqie_page_match.group(2)
        norm_url = f"https://fanqienovel.com/page/{book_id}"
        return "fanqie", norm_url, book_id

    # 4. 檢查番茄 Keyword 頁
    fanqie_kw_match = RE_FANQIE_KEYWORD.search(message_content)
    if fanqie_kw_match:
        kw_id = fanqie_kw_match.group(1)
        norm_url = f"https://fanqienovel.com/keyword/{kw_id}"
        return "fanqie_keyword", norm_url, kw_id

    # 5. 檢查刺蝟貓
    ciwei_match = RE_CIWEIMAO.search(message_content)
    if ciwei_match:
        book_id = ciwei_match.group(1)
        norm_url = f"https://www.ciweimao.com/book/{book_id}"
        return "ciweimao", norm_url, book_id

    return None
