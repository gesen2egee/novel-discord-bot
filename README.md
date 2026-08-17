# 📖 Discord 小說網址自動解析機器人

專為繁體中文 Discord 小說社群打造的網址解析機器人。當頻道中有成員發送 **起點中文網**、**番茄小說**、**刺蝟貓** 的小說連結時，機器人會自動辨識並在當前頻道回覆包含 **推薦人、評價狀態、繁簡雙書名、作者、字數/數據、標籤分類、100% 完整簡介與官方高解析封面** 的精美 Embed 卡片，並提供**一鍵切換評價（推薦/不推薦避雷）**、**原發文者專屬刪除** 與 **自動同步 Google 試算表 (Google Sheets)**！

---

## 🌟 核心特色

1. **完全免本機爬蟲**：採用雲端 Jina Reader 引擎，免安裝動態瀏覽器、免維護 DOM/HTML 規則，徹底解決 IP 封鎖與起點字型加密混淆問題。
2. **🔄 一鍵切換評價（推薦 / 避雷不推薦）**：
   - 卡片下方附帶按鈕，原發文者如果想避雷或吐槽，點擊 **`👎 改為不推薦/避雷`**，書卡會**即時切換為警戒紅色邊框**、標題標記 `⚠️ [不推薦/避雷]`，並同步更新 Google 試算表！
3. **🗑️ 原發文者專屬刪除**：
   - 只有分享該小說連結的原作者點擊 **`🗑️ 刪除書卡`** 才能撤回訊息，其他人點擊會收到隱私提示無權刪除，防止他人惡意亂刪！
4. **📊 Google 試算表自動同步**：
   - 每次推書自動在 Google 表格新增一行（時間、繁體書名、簡體原名、推薦人、評價狀態、作者、字數、標籤、小說網址、Discord 討論連結）。
   - 卡片下方可附帶 **`📊 查看線上書單`** 按鈕直接跳轉 Google Sheets。
5. **網址自動正規化**：
   - 起點：一律正規化為 `https://www.qidian.com/book/{id}/`
   - 番茄：一律正規化為 `https://fanqienovel.com/page/{id}`；保留 keyword 落地頁
   - 刺蝟貓：一律正規化為 `https://www.ciweimao.com/book/{id}`
6. **過濾單章干擾**：自動略過單章閱讀頁（`/reader/`、`/chapter/`），專注於書籍資訊。
7. **雙行書名展示**：標題顯示繁體中文，獨立欄位提供簡體原名方便複製搜尋。
8. **100% 完整文案呈現**：採用 Embed Description 模式，突破字數限制完整保留全文案。

---

## 📊 Google 試算表自動同步設定教學（選填）

### 步驟 1：建立 Google 試算表
1. 打開 [Google 試算表 (sheets.new)](https://sheets.new/) 建立新表格。
2. 在第 1 列依序填入 11 個欄位標題：
   `推薦時間` ｜ `繁體書名` ｜ `簡體原名` ｜ `分享者` ｜ `平台` ｜ `作者` ｜ `字數/數據` ｜ `標籤` ｜ `小說網址` ｜ `Discord 討論連結` ｜ `評價`

### 步驟 2：貼上 Google Apps Script 腳本
1. 點擊頂部選單的 **「擴充功能」 $\rightarrow$ 「Apps Script」**。
2. 清空裡面的程式碼，完整貼上以下腳本：

```javascript
function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = JSON.parse(e.postData.contents);
    
    // 將推書資料寫入新的一列 (包含評價與 Discord 討論連結)
    sheet.appendRow([
      data.time,
      data.title_t,
      data.title_s,
      data.recommender,
      data.platform,
      data.author,
      data.stats,
      data.tags,
      data.url,
      data.jump_url,
      data.evaluation
    ]);
    
    return ContentService.createTextOutput(JSON.stringify({"status": "success"}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
```

### 步驟 3：部署並取得 Webhook 網址
1. 點擊 **「部署」 $\rightarrow$ 「新增部署作業」** $\rightarrow$ 選擇 **「網頁應用程式」**。
2. 設定：執行身分：`我` ｜ 誰可以存取：`所有人`。
3. 部署後複製 **網頁應用程式網址 (Web app URL)**。
4. 在雲端環境變數填入：
   - `GOOGLE_SHEET_WEBHOOK_URL` = 你的 Web app URL
   - `GOOGLE_SHEET_VIEW_URL` = 你的試算表分享網址（選填）

---

## ☁️ 雲端 24 小時免費架設 (以 Render 免費平台為例)

1. **取得 Discord Bot Token**：至 [Discord Developer Portal](https://discord.com/developers/applications) 取得 Token，並開啟 `MESSAGE CONTENT INTENT`。
2. **推送代碼至 GitHub**：
   ```bash
   git push -u origin main
   ```
3. **在 Render 建立免費服務**：
   - 登入 [Render (render.com)](https://render.com/)，點擊 **New +** $\rightarrow$ **Background Worker** (或 Web Service)。
   - 連接你的 GitHub 倉庫 `gesen2egee/novel-discord-bot`。
   - 選擇 **Free** 免費方案。
   - 在「Environment Variables」新增 `DISCORD_TOKEN`（以及選填的 `GOOGLE_SHEET_WEBHOOK_URL`、`GOOGLE_SHEET_VIEW_URL`）。
   - 點擊 **Create**，機器人即刻 24 小時在線！

---

## 📁 專案檔案結構

```
├── bot.py           # Discord 機器人主程式 (監聽、評價切換、安全刪除按鈕)
├── normalizer.py    # 網址正規化模組 (正則辨識、短網址還原、排除單章)
├── resolver.py      # 雲端小說解析模組 (串接 Jina Reader API、繁簡轉換)
├── sheets_sync.py   # Google 試算表自動同步模組 (含評價與討論連結)
├── requirements.txt # Python 依賴清單
├── Dockerfile       # 容器部署設定檔
├── Procfile         # 雲端背景服務定義檔
├── .dockerignore    # 容器構建過濾規則
├── .env.example     # 環境變數範本
├── .gitignore       # Git 提交過濾規則
└── README.md        # 完整繁體中文使用說明
```
