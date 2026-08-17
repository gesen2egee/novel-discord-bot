# 📖 Discord 小說網址自動解析與推書彙整機器人

專為繁體中文 Discord 小說社群打造的網址解析與自動書單彙整機器人。當頻道中有成員發送 **起點中文網**、**番茄小說**、**刺蝟貓** 的小說連結時，機器人會自動辨識並回覆包含 **推薦人、繁簡雙書名、作者、字數/數據、標籤分類、完整簡介與官方高解析封面** 的精美 Embed 卡片，並**自動同步轉發至專屬的「📚-推書彙整」頻道**！

---

## 🌟 核心特色

1. **完全免本機爬蟲**：採用雲端 Jina Reader 引擎，免安裝動態瀏覽器、免維護 DOM/HTML 規則，徹底解決 IP 封鎖與起點字型加密混淆問題。
2. **自動同步「📚-推書彙整」專屬頻道**：
   - 成員在任何閒聊頻道推薦小說，機器人除了在當前頻道回覆卡片外，還會**自動備份轉發至推書精華頻道**！
   - 轉發卡片附帶「💬 點擊前往原對話」跳轉按鈕，方便群友追溯當時的討論。
3. **網址自動正規化**：
   - 起點：無論手機版、電腦版、App 分享長網址，一律正規化為 `https://www.qidian.com/book/{id}/`
   - 番茄：暢讀分享、zlink 短鏈一律正規化為 `https://fanqienovel.com/page/{id}`；保留 keyword 落地頁
   - 刺蝟貓：WAP、MIP、目錄、歡樂書客舊鏈一律正規化為 `https://www.ciweimao.com/book/{id}`
4. **過濾單章干擾**：自動略過單章閱讀頁（`/reader/`、`/chapter/`），專注於書籍資訊推薦。
5. **推薦人與頭像顯示**：自動標記在頻道中分享小說的使用者暱稱與大頭貼。
6. **雙行書名展示**：
   - 標題顯示**繁體中文書名**（適合台灣與繁體讀者閱讀）。
   - 獨立欄位顯示**簡體原名**（方便複製去各大小說網站搜尋）。
7. **完整文案呈現**：不截斷簡介內容，完整呈現作品文案。
8. **快取防刷機制**：內建記憶體快取，短時間內重複貼出同本書直接秒回，不消耗外部額度。

---

## 📚 推書彙整頻道設定方法（超簡單）

機器人具備**全自動識別能力**：
- 只要在您的 Discord 伺服器中建立一個文字頻道，名稱包含 **`推書`**（例如：`📚-推書彙整`、`小說推薦`、`推書專區`）。
- 機器人上線後就會**自動鎖定該頻道作為推書表單記錄區**，零設定即可開箱即用！

*(若想特別指定某個頻道，也可在環境變數中設定 `RECOMMEND_CHANNEL_ID=頻道ID`)*

---

## ☁️ 雲端 24 小時免開機架設教學 (以 Zeabur 為例)

本專案已完全配置好 **Zeabur / Docker** 部署設定，只需以下 3 步即可 24 小時免費運行：

### 第一步：取得 Discord 機器人 Token
1. 前往 [Discord Developer Portal](https://discord.com/developers/applications)。
2. 建立新 Application 並新增 Bot。
3. **重要**：在 **Bot** 頁籤下，開啟 **`MESSAGE CONTENT INTENT`**（特權網關意圖）。
4. 點擊 **Reset Token** 取得 Token 並複製備用。
5. 前往 **OAuth2 -> URL Generator**，勾選 `bot` 及 `Send Messages`、`Embed Links`、`Read Message History` 權限，將機器人邀請至你的 Discord 伺服器。

### 第二步：上傳專案至 GitHub
在您的終端機執行：
```bash
git push -u origin main
```

### 第三步：在 Zeabur 部署並運行
1. 前往 [Zeabur 官方網站](https://zeabur.com/) 並使用 GitHub 帳號登入。
2. 點擊 **「建立新專案 (Create Project)」** $\rightarrow$ **「部署新服務 (Deploy New Service)」** $\rightarrow$ 選擇 **`gesen2egee/novel-discord-bot`**。
3. 進入該服務的 **「變數 (Variables)」** 頁籤：
   - 新增變數名稱：`DISCORD_TOKEN`
   - 變數值：貼上第一步取得的 Discord Bot Token
4. 點擊 **「重新部署 (Redeploy)」**，機器人即刻在線，24 小時不中斷運行！

---

## 📁 專案檔案結構

```
├── bot.py           # Discord 機器人主程式 (推薦人、卡片排版、自動轉發彙整)
├── normalizer.py    # 網址正規化模組 (正則辨識、短網址還原、排除單章)
├── resolver.py      # 雲端小說解析模組 (串接 Jina Reader API、繁簡轉換)
├── requirements.txt # Python 依賴清單
├── Dockerfile       # Zeabur / 雲端容器部署設定檔
├── Procfile         # 雲端背景服務定義檔
├── .dockerignore    # 容器構建過濾規則
├── .env.example     # 環境變數範本
├── .gitignore       # Git 提交過濾規則
└── README.md        # 完整繁體中文使用說明
```
