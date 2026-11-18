FROM python:3.11.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless ca-certificates && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
COPY requirements.txt /tmp/benchmark-requirements.txt
RUN pip install --no-cache-dir -r /tmp/benchmark-requirements.txt
WORKDIR /bench
