FROM python:3.11-slim

WORKDIR /app

# Cài đặt các gói phụ thuộc
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sao chép mã nguồn
COPY . .

# Chạy bot Telegram
CMD ["python", "bot.py"]
