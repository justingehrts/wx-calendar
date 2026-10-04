FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 CALENDAR_DATA_DIR=/data CALENDAR_DB=/data/calendar.db
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
ARG TARGETARCH=amd64
ARG LITESTREAM_VERSION=0.3.13
RUN curl -fsSL "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-${TARGETARCH}.tar.gz" | tar -xz -C /usr/local/bin litestream
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x run.sh
EXPOSE 8501
CMD ["./run.sh"]
