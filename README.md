# 📖 Discord 小說網址自動解析機器人

專為繁體中文 Discord 小說社群打造的網址解析機器人。當頻道中有成員發送 **起點中文網**、**番茄小說**、**刺蝟貓** 的小說連結時，機器人會自動辨識並回覆包含 **繁簡雙書名、作者、字數/數據、標籤分類、完整簡介與官方高解析封面** 的精美 Embed 卡片。

---

## 🌟 核心特色

1. **完全免本機爬蟲**：採用雲端 Jina Reader 引擎，免安裝動態瀏覽器、免維護 DOM/HTML 規則，徹底解決 IP 封鎖與起點字型加密混淆問題。
2. **網址自動正規化**：
   - 起點：無論手機版、電腦版、App 分享長網址，一律正規化為 `https://www.qidian.com/book/{id}/`
   - 番茄：暢讀分享、zlink 短鏈一律正規化為 `https://fanqienovel.com/page/{id}`；保留 keyword 落地頁
   - 刺蝟貓：WAP、MIP、目錄、歡樂書客舊鏈一律正規化為 `https://www.ciweimao.com/book/{id}`
3. **過濾單章干擾**：自動略過單章閱讀頁（`/reader/`、`/chapter/`），專注於書籍資訊推薦。
4. **雙行書名展示**：
   - 標題顯示**繁體中文書名**（適合台灣與繁體讀者閱讀）。
   - 獨立欄位顯示**簡體原名**（方便複製去各大小說網站搜尋）。
5. **完整文案呈現**：不截斷簡介內容，完整呈現作品文案。
6. **快取防刷機制**：內建記憶體快取，短時間內重複貼出同本書直接秒回，不消耗外部額度。

---

## 🛠️ 安裝與使用教學

### 1. 取得 Discord Bot Token
1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)。
2. 建立新 Application 並新增 Bot。
3. **重要設定**：在 **Bot** 頁籤下，將 **Privileged Gateway Intents** 中的 **`MESSAGE CONTENT INTENT`** 開啟。
4. 點擊 **Reset Token** 取得 Token 並複製。
5. 前往 **OAuth2 -> URL Generator**，勾選 `bot` 權限以及發送訊息、嵌入連結（Embed Links）權限，將機器人邀請至你的 Discord 伺服器。

### 2. 環境安裝與啟動
```bash
# 1. 建立並啟動 Python 虛擬環境 (建議)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux / macOS

# 2. 安裝必要套件
pip install -r requirements.txt

# 3. 複製設定檔並填入 Token
cp .env.example .env
# 編輯 .env 檔案，填入你的 DISCORD_TOKEN

# 4. 啟動機器人
python bot.py
```

---

## 📁 檔案結構

```
├── bot.py           # Discord 機器人主程式 (監聽訊息、組裝卡片、快取)
├── normalizer.py    # 網址正規化模組 (正則辨識、短網址還原、排除單章)
├── resolver.py      # 雲端小說解析模組 (串接 Reader API、繁簡雙向轉換)
├── requirements.txt # 專案 Python 依賴套件
├── .env.example     # 環境變數範本
└── README.md        # 說明文件
```
