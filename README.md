# 📖 Discord 小說網址自動解析與推書彙整機器人

專為繁體中文 Discord 小說社群打造的網址解析與自動書單彙整機器人。當頻道中有成員發送 **起點中文網**、**番茄小說**、**刺蝟貓** 的小說連結時，機器人會自動辨識並回覆包含 **推薦人、繁簡雙書名、作者、字數/數據、標籤分類、完整簡介與官方高解析封面** 的精美 Embed 卡片，並**自動同步轉發至「📚-推書彙整」頻道**與**自動寫入 Google 試算表 (Google Sheets)**！

---

## 🌟 核心特色

1. **完全免本機爬蟲**：採用雲端 Jina Reader 引擎，免安裝動態瀏覽器、免維護 DOM/HTML 規則，徹底解決 IP 封鎖與起點字型加密混淆問題。
2. **自動同步 Google 試算表 (Google Sheets)**：
   - 每次推書自動在 Google 表格新增一行（時間、繁體書名、簡體原名、推薦人、作者、字數、標籤、網址）。
   - 所有人隨時用手機點開表格就能檢索、篩選、排序全群推薦書單！
3. **自動同步「📚-推書彙整」專屬頻道**：
   - 成員在任何閒聊頻道推薦小說，機器人自動備份轉發至推書精華頻道。
   - 轉發卡片附帶「💬 點擊前往原對話」跳轉按鈕，方便群友追溯當時的討論。
4. **網址自動正規化**：
   - 起點：無論手機版、電腦版、App 分享長網址，一律正規化為 `https://www.qidian.com/book/{id}/`
   - 番茄：暢讀分享、zlink 短鏈一律正規化為 `https://fanqienovel.com/page/{id}`；保留 keyword 落地頁
   - 刺蝟貓：WAP、MIP、目錄、歡樂書客舊鏈一律正規化為 `https://www.ciweimao.com/book/{id}`
5. **過濾單章干擾**：自動略過單章閱讀頁（`/reader/`、`/chapter/`），專注於書籍資訊推薦。
6. **推薦人與頭像顯示**：自動標記在頻道中分享小說的使用者暱稱與大頭貼。
7. **雙行書名展示**：
   - 標題顯示**繁體中文書名**（適合台灣與繁體讀者閱讀）。
   - 獨立欄位顯示**簡體原名**（方便複製去各大小說網站搜尋）。
8. **100% 完整文案呈現**：採用 Embed Description 模式，突破欄位字數限制，完整保留全篇文案。
9. **快取防刷機制**：內建記憶體快取，短時間內重複貼出同本書直接秒回，不消耗外部額度。

---

## 📊 Google 試算表自動同步設定教學（3 步完成）

只要建立一個 Google 試算表並貼上專屬腳本，機器人就能自動將推書寫入試算表！

### 步驟 1：建立 Google 試算表
1. 打開 [Google 試算表 (sheets.new)](https://sheets.new/) 建立新表格（例如命名為：`DC 小說推薦清單`）。
2. 在第 1 列依序填入欄位標題：
   `推薦時間` ｜ `繁體書名` ｜ `簡體原名` ｜ `推薦人` ｜ `平台` ｜ `作者` ｜ `字數/數據` ｜ `標籤` ｜ `小說網址`

### 步驟 2：貼上 Google Apps Script 腳本
1. 點擊頂部選單的 **「擴充功能」 $\rightarrow$ 「Apps Script」**。
2. 清空裡面的程式碼，完整貼上以下腳本：

```javascript
function doPost(e) {
  try {
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var data = JSON.parse(e.postData.contents);
    
    // 將推書資料寫入新的一列
    sheet.appendRow([
      data.time,
      data.title_t,
      data.title_s,
      data.recommender,
      data.platform,
      data.author,
      data.stats,
      data.tags,
      data.url
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
1. 點擊右上角的 **「部署 (Deploy)」 $\rightarrow$ 「新增部署作業 (New deployment)」**。
2. 點選左側齒輪圖示 $\rightarrow$ 選擇 **「網頁應用程式 (Web app)」**。
3. 設定：
   - 說明：`DC Bot Webhook`
   - 執行身分：**`我 (Me)`**
   - 誰可以存取：**`所有人 (Anyone)`** *(重要！這樣機器人才能寫入)*
4. 點擊 **「部署」**（首次會要求授權 Google 帳號，點擊允許）。
5. 複製產生的 **網頁應用程式網址 (Web app URL)**（格式如 `https://script.google.com/macros/s/.../exec`）。
6. 在 Zeabur 的環境變數中新增：
   - 變數名稱：`GOOGLE_SHEET_WEBHOOK_URL`
   - 變數值：貼上剛複製的 Web app URL

🎉 設定完成！之後每當有人在頻道推薦小說，試算表就會**即時自動新增一筆紀錄**！

---

## ☁️ 雲端 24 小時免開機架設教學 (以 Zeabur 為例)

1. **取得 Discord Bot Token**：至 [Discord Developer Portal](https://discord.com/developers/applications) 取得 Token，並開啟 `MESSAGE CONTENT INTENT`。
2. **推送代碼至 GitHub**：
   ```bash
   git push -u origin main
   ```
3. **在 Zeabur 一鍵部署**：
   - 登入 [Zeabur (zeabur.com)](https://zeabur.com/)，選擇部署你的 `gesen2egee/novel-discord-bot` 倉庫。
   - 在服務的「變數 (Variables)」填入 `DISCORD_TOKEN`（以及選填的 `GOOGLE_SHEET_WEBHOOK_URL`）。
   - 機器人即刻 24 小時自動在線！

---

## 📁 專案檔案結構

```
├── bot.py           # Discord 機器人主程式 (推薦人、卡片排版、自動轉發彙整)
├── normalizer.py    # 網址正規化模組 (正則辨識、短網址還原、排除單章)
├── resolver.py      # 雲端小說解析模組 (串接 Jina Reader API、繁簡轉換)
├── sheets_sync.py   # Google 試算表自動同步模組 (Webhook 寫入)
├── requirements.txt # Python 依賴清單
├── Dockerfile       # Zeabur / 雲端容器部署設定檔
├── Procfile         # 雲端背景服務定義檔
├── .dockerignore    # 容器構建過濾規則
├── .env.example     # 環境變數範本
├── .gitignore       # Git 提交過濾規則
└── README.md        # 完整繁體中文使用說明
```
