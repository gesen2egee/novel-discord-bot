# 📖 Discord 小說網址自動解析機器人

專為繁體中文 Discord 小說社群打造的網址解析機器人。當頻道中有成員發送 **起點中文網**、**番茄小說**、**刺蝟貓** 的小說連結時，機器人會自動辨識並在當前頻道回覆包含 **推薦人、評價狀態、繁簡雙書名、作者、字數/數據、標籤分類、100% 完整簡介與官方高解析封面** 的精美 Embed 卡片，並提供**🐶 賽博獵犬重複推薦提醒**、**一鍵切換評價（推薦 / ⚠️ 不推薦）**、**原發文者專屬刪除** 與 **自動同步 Google 試算表 (Google Sheets)**！

---

## 🌟 核心特色

1. **🐶 賽博獵犬重複推薦提醒**：
   - 當同一本書被重複貼出時，機器人會幽默調侃並提供前人討論位置跳轉連結（不重複發送書卡與寫入試算表）：
     `🐶 你賽博獵犬囉！這本前面由 XXX 已經推薦過了～ 🔗 [點擊查看前人推薦訊息]`
   - 附帶 **`🙇 我知錯了`** 按鈕，只有觸發獵犬的原發文者可點擊立即撤回/刪除該則獵犬提醒通知！
2. **完全免本機爬蟲**：採用雲端 Jina Reader 引擎，免安裝動態瀏覽器、免維護 DOM/HTML 規則，徹底解決 IP 封鎖與起點字型加密混淆問題。
3. **🔄 🔼 / 🔽 上下箭頭三級狀態切換（發書者 3 級 / 群友 3 級）**：
   - **發書者操作**：
     - 按 **`🔼 增加推薦`**：`⚠️ 不推薦` $\rightarrow$ `🌾 一般推薦（乾糧）` $\rightarrow$ `🔥 強力推薦（糧草）`
     - 按 **`🔽 減少推薦`**：`🔥 強力推薦（糧草）` $\rightarrow$ `🌾 一般推薦（乾糧）` $\rightarrow$ `⚠️ 不推薦`
   - **其他群友操作（社群覆議）**：
4. **🗑️ 原發文者專屬刪除 ＆ 雙重刪除選項**：
   - 只有分享該小說連結的原作者點擊 **`🗑️ 刪除書卡`** 時，會彈出專屬私密確認面板（Ephemeral）：
     - **`🗑️ 僅刪除 Discord 書卡`**：只撤回 Discord 訊息，保留線上書單紀錄。
     - **`🧹 同時從線上書單刪除`**：撤回 Discord 訊息並發送 Webhook 刪除指令，將該小說由 Google 試算表中整行移除！
     - **`❌ 取消`**：取消刪除操作。
   - 其他人點擊會收到隱私提示無權刪除，防止他人惡意亂刪！
5. **📊 Google 試算表自動同步與去重**：
   - 每次推書自動同步 Google 表格，支援智慧去重與推薦人累加。
   - 支援台北時間純日期（`YYYY/MM/DD`）。
   - 卡片下方附帶 **`📊 查看線上書單`** 按鈕直接跳轉 Google Sheets。
6. **🌐 全文字頻道智慧解析 ＆ 指定頻道進表單**：
   - 伺服器內**所有文字頻道與討論串**皆會自動解析網址並展開書卡與按鈕。
   - 預設**僅限「懶人推書」與「推薦書單」頻道**的分享與評價變更會同步寫入 Google 試算表，避免閒聊區雜訊污染書庫！可在 `.env` 的 `SYNC_CHANNELS` 自訂。
7. **網址自動正規化**：
   - 起點：一律正規化為 `https://www.qidian.com/book/{id}/`
   - 番茄：一律正規化為 `https://fanqienovel.com/page/{id}`；保留 keyword 落地頁
   - 刺蝟貓：一律正規化為 `https://www.ciweimao.com/book/{id}`
8. **過濾單章干擾**：自動略過單章閱讀頁（`/reader/`、`/chapter/`），專注於書籍資訊。
9. **雙行書名展示**：標題顯示繁體中文，獨立欄位提供簡體原名方便複製搜尋。
10. **100% 完整文案呈現**：採用 Embed Description 模式，突破字數限制完整保留全文案。

---

## 📊 Google 試算表自動同步設定教學

### 步驟 1：建立 Google 試算表
在第 1 列依序填入 12 個欄位標題：
`推薦時間` ｜ `繁體書名` ｜ `簡體原名` ｜ `推薦人` ｜ `平台` ｜ `作者` ｜ `小說網址` ｜ `DC討論原文` ｜ `是否推薦` ｜ `字數/數據` ｜ `標籤` ｜ `覆議`

### 步驟 2：貼上 Google Apps Script 腳本 (支援覆議、同推與整列刪除)
1. 點擊頂部選單的 **「擴充功能」 $\rightarrow$ 「Apps Script」**。
2. 清空裡面的程式碼，完整貼上以下腳本：

```javascript
function doGet(e) {
  return ContentService.createTextOutput("✅ Google Sheets Webhook 正常運作中！")
    .setMimeType(ContentService.MimeType.TEXT);
}

function doPost(e) {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheets()[0];
    var data = JSON.parse(e.postData.contents);
    var values = sheet.getDataRange().getValues();

    // 0. 處理刪除請求 (Action: delete)
    if (data.action === "delete") {
      var targetUrl = data.url ? data.url.trim().toLowerCase() : "";
      var targetTitle = data.title_t ? data.title_t.trim() : "";
      var deleted = false;

      for (var i = values.length - 1; i >= 1; i--) {
        var rowUrl = values[i][6] ? values[i][6].toString().trim().toLowerCase() : "";
        var rowTitle = values[i][1] ? values[i][1].toString().trim() : "";
        if ((targetUrl && rowUrl === targetUrl) || (targetTitle && rowTitle === targetTitle)) {
          sheet.deleteRow(i + 1);
          deleted = true;
        }
      }
      return ContentService.createTextOutput(JSON.stringify({"status": "deleted", "deleted": deleted}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    var existingRowIndex = -1;
    
    // 1. 去重比對：檢查第 7 欄 (小說網址) 或第 2 欄 (繁體書名)
    for (var i = 1; i < values.length; i++) {
      var rowUrl = values[i][6];   // 第 7 欄: 小說網址
      var rowTitle = values[i][1]; // 第 2 欄: 繁體書名
      if (rowUrl === data.url || (data.title_t && rowTitle === data.title_t)) {
        existingRowIndex = i + 1;
        break;
      }
    }
    
    // 2. 若書籍已存在，更新現有資料 (去重)
    if (existingRowIndex !== -1) {
      var currentRecommenders = sheet.getRange(existingRowIndex, 4).getValue().toString(); // 第 4 欄: 推薦人
      if (data.recommender && currentRecommenders.indexOf(data.recommender) === -1) {
        currentRecommenders = currentRecommenders ? (currentRecommenders + ", " + data.recommender) : data.recommender;
      }
      sheet.getRange(existingRowIndex, 1).setValue(data.time); // 更新為最新時間
      sheet.getRange(existingRowIndex, 4).setValue(currentRecommenders);
      sheet.getRange(existingRowIndex, 8).setValue(data.jump_url); // 第 8 欄: DC討論原文
      if (data.evaluation) {
        sheet.getRange(existingRowIndex, 9).setValue(data.evaluation); // 第 9 欄: 是否推薦
      }
      sheet.getRange(existingRowIndex, 10).setValue(data.stats); // 第 10 欄: 字數/數據
      sheet.getRange(existingRowIndex, 11).setValue(data.tags);  // 第 11 欄: 標籤
      if (data.concurrence !== undefined) {
        sheet.getRange(existingRowIndex, 12).setValue(data.concurrence); // 第 12 欄: 覆議
      }
      
      return ContentService.createTextOutput(JSON.stringify({"status": "updated", "row": existingRowIndex}))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // 3. 全新書籍寫入新列 (精準填入空白行)
    var targetRow = values.length + 1;
    if (values.length >= 2 && !values[1][1] && !values[1][6]) {
      targetRow = 2;
    }
    
    var newRowData = [
      data.time || "",
      data.title_t || "",
      data.title_s || "",
      data.recommender || "",
      data.platform || "",
      data.author || "",
      data.url || "",
      data.jump_url || "",
      data.evaluation || "乾糧",
      data.stats || "",
      data.tags || "",
      data.concurrence || ""
    ];
    
    sheet.getRange(targetRow, 1, 1, newRowData.length).setValues([newRowData]);
    
    return ContentService.createTextOutput(JSON.stringify({"status": "inserted", "row": targetRow}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"status": "error", "message": error.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
```

### 步驟 3：部署並取得 Webhook 網址
1. 點擊 **「部署」 $\rightarrow$ 「管理部署作業」 $\rightarrow$ 點擊鉛筆圖示編輯**。
2. 版本選擇 **「新版本 (New version)」** $\rightarrow$ 點擊 **「部署」**。

---

## ☁️ 雲端 24 小時免費架設 (以 Render 免費平台為例)

1. **取得 Discord Bot Token**：至 [Discord Developer Portal](https://discord.com/developers/applications) 取得 Token，並開啟 `MESSAGE CONTENT INTENT`。
2. **推送代碼至 GitHub**：
   ```bash
   git push -u origin main
   ```
3. **在 Render 建立免費 Web 服務**：
   - 登入 [Render (render.com)](https://render.com/)，點擊 **New +** $\rightarrow$ **Web Service**。
   - 連接你的 GitHub 倉庫 `gesen2egee/novel-discord-bot`。
   - 選擇 **Free** 免費方案。
   - 在「Environment Variables」新增 `DISCORD_TOKEN`（以及選填的 `GOOGLE_SHEET_WEBHOOK_URL`）。
   - 點擊 **Create**，機器人即刻 24 小時在線！

---

## 📁 專案檔案結構

```
├── bot.py           # Discord 機器人主程式 (賽博獵犬提醒、評價切換、安全刪除按鈕)
├── normalizer.py    # 網址正規化模組 (正則辨識、短網址還原、排除單章)
├── resolver.py      # 雲端小說解析模組 (串接 Jina Reader API、繁簡轉換)
├── sheets_sync.py   # Google 試算表自動同步模組 (含去重與討論連結)
├── requirements.txt # Python 依賴清單
├── Dockerfile       # 容器部署設定檔
├── Procfile         # 雲端背景服務定義檔
├── .dockerignore    # 容器構建過濾規則
├── .env.example     # 環境變數範本
├── .gitignore       # Git 提交過濾規則
└── README.md        # 完整繁體中文使用說明
```
