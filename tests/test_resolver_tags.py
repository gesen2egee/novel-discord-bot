import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resolver import clean_and_format_tags

class TestCleanAndFormatTags(unittest.TestCase):
    def test_markdown_links_preserved_and_converted(self):
        # 測試合法的 Markdown 連結保留與繁體化
        raw1 = "连载·签约·VIP·[都市](https://www.qidian.com/dushi/)·[商战职场](https://www.qidian.com/all/chanId4-subCateId153/)"
        expected1 = "連載・簽約・VIP・[都市](https://www.qidian.com/dushi/)・[商戰職場](https://www.qidian.com/all/chanId4-subCateId153/)"
        self.assertEqual(clean_and_format_tags(raw1), expected1)

    def test_truncated_broken_urls_filtered(self):
        # 測試截斷損壞的網址被安全去除
        raw2 = "连载 · 签约 · VIP · [都市](https://www.qidian.com/dushi/) (https://www.qidian.com/all/chan · [商战职场](https://www.qidian.com/all/chanId4-subCateId153/)"
        expected2 = "連載・簽約・VIP・[都市](https://www.qidian.com/dushi/)・[商戰職場](https://www.qidian.com/all/chanId4-subCateId153/)"
        self.assertEqual(clean_and_format_tags(raw2), expected2)

    def test_plain_tags(self):
        raw3 = "连载中 穿越 搞笑 异世大陆"
        self.assertEqual(clean_and_format_tags(raw3), "連載中・穿越・搞笑・異世大陸")

if __name__ == "__main__":
    unittest.main()
