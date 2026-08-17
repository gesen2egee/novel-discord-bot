import os
import sys
import io
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from resolver import fetch_novel_info

async def main():
    res = await fetch_novel_info("qidian", "https://www.qidian.com/book/1049370328/")
    print("=== 解析結果 ===")
    print("書名(繁):", res["title_t"])
    print("書名(簡):", res["title_s"])
    print("作者:", res["author"])
    print("數據:", res["stats"])
    print("標籤:", res["tags"])
    print("封面:", res["cover"])
    print("簡介:\n" + res["description"])
    print("================")

if __name__ == "__main__":
    asyncio.run(main())
