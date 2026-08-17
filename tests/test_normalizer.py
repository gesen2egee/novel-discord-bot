import os
import sys
import asyncio

# 加入根目錄至 sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from normalizer import normalize_novel_url

async def main():
    test_cases = [
        # 起點
        ("https://www.qidian.com/book/1049836819/", ("qidian", "https://www.qidian.com/book/1049836819/")),
        ("https://book.qidian.com/info/1049836819", ("qidian", "https://www.qidian.com/book/1049836819/")),
        ("https://m.qidian.com/book/1048845422/", ("qidian", "https://www.qidian.com/book/1048845422/")),
        ("https://magev6.if.qidian.com/h5/share/book?channel=qidianapp&bookId=1049543990", ("qidian", "https://www.qidian.com/book/1049543990/")),
        
        # 番茄
        ("https://fanqienovel.com/page/7284341720949460030", ("fanqie", "https://fanqienovel.com/page/7284341720949460030")),
        ("https://changdunovel.com/wap/share-v2.html?aid=1967&book_id=7628071472921054233", ("fanqie", "https://fanqienovel.com/page/7628071472921054233")),
        ("https://fanqienovel.com/keyword/7369001635726788617", ("fanqie_keyword", "https://fanqienovel.com/keyword/7369001635726788617")),
        
        # 刺蝟貓
        ("https://www.ciweimao.com/book/100456881", ("ciweimao", "https://www.ciweimao.com/book/100456881")),
        ("https://wap.ciweimao.com/book/100364708", ("ciweimao", "https://www.ciweimao.com/book/100364708")),
        ("https://mip.ciweimao.com/book/100471009", ("ciweimao", "https://www.ciweimao.com/book/100471009")),
        ("https://www.ciweimao.com/chapter-list/100456881/", ("ciweimao", "https://www.ciweimao.com/book/100456881")),
        
        # 應該被排除的單章閱讀頁
        ("https://fanqienovel.com/reader/7634371127728423449", None),
        ("https://www.ciweimao.com/chapter/110171886", None),
        ("https://read.qidian.com/chapter/1049836819/123456", None),
    ]

    all_passed = True
    for text, expected in test_cases:
        res = await normalize_novel_url(text)
        if expected is None:
            passed = (res is None)
            print(f"[{'PASS' if passed else 'FAIL'}] 排除單章: {text[:50]} -> {res}")
            if not passed:
                all_passed = False
        else:
            exp_platform, exp_url = expected
            if res and res[0] == exp_platform and res[1] == exp_url:
                passed = True
                print(f"[{'PASS' if passed else 'FAIL'}] 正規化: {text[:50]} -> {res[1]}")
            else:
                passed = False
                print(f"[FAIL] 預期 {expected} 但得到 {res}")
                all_passed = False

    print("\n==========================================")
    print("測試結果：全部通過！" if all_passed else "測試結果：有失敗項")
    print("==========================================")

if __name__ == "__main__":
    asyncio.run(main())
