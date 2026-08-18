import asyncio
import aiohttp
import re
import opencc

s2t = opencc.OpenCC('s2t')

def clean_and_format_tags(raw_text: str) -> str:
    if not raw_text:
        return '作品標籤'

    link_map = {}
    def replace_link(match):
        label = match.group(1).strip()
        url = match.group(2).strip()
        label_t = s2t.convert(label)
        placeholder = f'__MDLINK{len(link_map)}__'
        link_map[placeholder] = f'[{label_t}]({url})'
        return f' {placeholder} '

    # 1. 替換完整合法的 Markdown 連結 (支援帶有 "title" 的情況，將 title 丟棄)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s\)\"\']+)(?:\s+[^)]*)?\)', replace_link, raw_text)
    # 2. 徹底過濾任何殘留或截斷的 http/https 網址
    text = re.sub(r'\(?https?://[^\s\)]*\)?', '', text)
    # 3. 移除多餘符號（包含引號）
    text = re.sub(r'[\[\]\(\)\{\}*#`"\'“”‘’]', ' ', text)
    raw_items = re.split(r'[·•|｜,，/、\s]+', text)

    valid_tags = []
    for item in raw_items:
        item = item.strip(' -·•|/，,')
        if not item or item.isdigit() or len(item) > 15:
            continue
        if item in link_map:
            valid_tags.append(link_map[item])
        else:
            if any(bad in item.lower() for bad in ['http', 'www', 'qidian', 'fanqie', 'ciweimao', '.com', 'html', 'chapter', '正文卷', '免费试读', '加入书架']):
                continue
            item_t = s2t.convert(item)
            if item_t not in valid_tags:
                valid_tags.append(item_t)

    return '・'.join(valid_tags) if valid_tags else '作品標籤'

async def test():
    urls = [
        "https://www.qidian.com/book/1049126057/",
        "https://www.qidian.com/book/1049836819/",
        "https://www.qidian.com/book/1031798363/"
    ]
    for url in urls:
        jina_url = f"https://r.jina.ai/{url}"
        async with aiohttp.ClientSession() as s:
            async with s.get(jina_url, headers={'Accept':'application/json'}) as r:
                d = await r.json()
                c = d.get('data', {}).get('content', '')
                raw_t = d.get('data', {}).get('title', '')
                
                # 測試書名提取與備援
                t_clean = re.sub(r'(_起[點点]中文[網网]|_閱文集團).*$', '', raw_t).strip(" _-|《》")
                if not t_clean or t_clean in ["起点中文网", "起點中文網", "起点读书"]:
                    t_match = re.search(r'(?:^|\n)#+\s*([^\n\r#\[\]]+?)(?:\s+在线阅读|\s+更新时间|\s*\n|\Z)', c)
                    if t_match:
                        t_clean = t_match.group(1).strip()

                # 測試標籤提取
                tag_m = re.search(r'(?:^|\n)((?:连载中?|完本|已完结|连载|签约|VIP|免费)[·\s]+[^\n\r]+)', c)
                tags = clean_and_format_tags(tag_m.group(1)) if tag_m else "連載・作品推薦"

                # 測試簡介提取與備援
                desc_match = re.search(r'##\s*作品[簡简]介\s*\n+(.*?)(?:\n+####|\n+##|\n+\[月票\]|\n+目录|\n+目錄|\Z)', c, re.DOTALL)
                if desc_match and desc_match.group(1).strip():
                    desc = desc_match.group(1).strip()
                else:
                    sub_desc = re.search(r'(?:连载|完本|签约|VIP|免费)[^\n]*\n+\s*(.*?)(?:\n+_\d+|\n+\[免费试读\]|\n+##|\n+####|\Z)', c, re.DOTALL)
                    desc = sub_desc.group(1).strip() if sub_desc else "暫無簡介"

                print(f"=== {url} ===")
                print("Title:", s2t.convert(t_clean))
                print("Tags:", tags)
                print("Desc preview:", s2t.convert(desc)[:100])

if __name__ == "__main__":
    asyncio.run(test())
