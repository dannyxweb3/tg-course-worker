FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# lxml / pymupdf 的运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2 libxslt1.1 tzdata ca-certificates sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY scripts ./scripts
COPY report ./report

RUN mkdir -p data/media logs

CMD ["python", "-m", "app.main"]
