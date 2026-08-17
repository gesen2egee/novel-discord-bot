import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from resolver import clean_tags

class TestCleanTags(unittest.TestCase):
    def test_clean_tags_pure_traditional(self):
        raw1 = "连载·免费·[武侠](https://www.qidian.com/wuxia/ \"武侠小说\")·[武侠同人](https://www.qidian.com/all/chanId2-subCateId20100/ \"武侠同人小说\")"
        expected1 = "連載・免費・武俠・武俠同人"
        self.assertEqual(clean_tags(raw1), expected1)

    def test_clean_tags_light_novel(self):
        raw2 = "连载·签约·VIP·[轻小说](https://www.qidian.com/2cy/)·[原生幻想](https://www.qidian.com/all/chanId12-subCateId60/)"
        expected2 = "連載・簽約・VIP・輕小說・原生幻想"
        self.assertEqual(clean_tags(raw2), expected2)

    def test_plain_tags(self):
        raw3 = "连载中 穿越 搞笑 异世大陆"
        expected3 = "連載中・穿越・搞笑・異世大陸"
        self.assertEqual(clean_tags(raw3), expected3)

if __name__ == "__main__":
    unittest.main()
