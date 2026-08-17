import asyncio
import aiohttp
import json

async def test():
    urls = [
        "https://www.qidian.com/book/1049370328/",
        "https://m.qidian.com/book/1049370328/",
    ]
    headers = {"Accept": "application/json"}
    for u in urls:
        jina_url = f"https://r.jina.ai/{u}"
        async with aiohttp.ClientSession() as session:
            async with session.get(jina_url, headers=headers) as resp:
                data = await resp.json()
                doc = data.get("data", {})
                print(f"=== URL: {u} ===")
                print("Title:", doc.get("title"))
                print("Description:", doc.get("description"))
                print("Content sample:\n", doc.get("content", "")[:1200])
                print("="*40)

if __name__ == "__main__":
    asyncio.run(test())
