# Используем базовый образ Python 3.13
FROM python:3.13-rc-bookworm

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальные файлы
COPY . .

# Устанавливаем переменные окружения
ENV PYTHONUNBUFFERED=1
ENV HUGGINGFACE_HUB_CACHE=/app/.cache/huggingface/hub
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface/transformers

# Создаем директорию для кеша
RUN mkdir -p /app/.cache/huggingface/{hub,transformers}

# Команда для запуска приложения
CMD ["python", "main.py"]