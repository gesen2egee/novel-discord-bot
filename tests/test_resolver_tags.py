import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resolver import clean_tags

class TestCleanTags(unittest.TestCase):
    def test_clean_markdown_links_and_urls(self):
        # 模擬截斷或未截斷的 Markdown 連結與 URL
        raw1 = "[连载](https://www.qidian.com/all/action1/) · [签约](https://www.qidian.com/all/vip0/) · [VIP](https://www.qidian.com/all/vip1/) · [轻小说](https://www.qidian.com/all/chanId12/) · [原生幻想](https://www.qidian.com/all/chanId12-subId66/)"
        self.assertEqual(clean_tags(raw1), "连载・签约・VIP・轻小说・原生幻想")

        # 模擬正則切斷導致帶有殘留網址 (https://www.qidian... 的情況
        raw2 = "连载 · 签约 · VIP · 轻小说 (https://www.qidian.com/all/chanId12/ · 原生幻想"
        self.assertEqual(clean_tags(raw2), "连载・签约・VIP・轻小说・原生幻想")

        # 模擬截斷一半的網址
        raw3 = "连载 · VIP · 轻小说 (https://www.qidian.com/all/ · 原生幻想"
        self.assertEqual(clean_tags(raw3), "连载・VIP・轻小说・原生幻想")

        # 模擬多餘括號與符號
        raw4 = "[连载中] 穿越 搞笑 [http://example.com]"
        self.assertEqual(clean_tags(raw4), "连载中・穿越・搞笑")

if __name__ == "__main__":
    unittest.main()
