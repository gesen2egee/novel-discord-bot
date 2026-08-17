FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 設定 Python 不寫入 pyc 與無緩衝輸出
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 安裝依賴套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案原始碼
COPY . .

# 執行 Discord 機器人
CMD ["python", "bot.py"]
