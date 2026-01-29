FROM python:3.12-slim

WORKDIR /app

# Копируем requirements первым для кеширования слоя
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY *.py ./

# Логи в stdout
ENV PYTHONUNBUFFERED=1

CMD ["python", "bot.py"]
