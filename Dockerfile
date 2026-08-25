FROM python:3.11-slim

WORKDIR /app

# Отключаем буферизацию вывода Python для мгновенного вывода логов в консоль
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]
