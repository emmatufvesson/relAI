FROM debian:bullseye-slim

RUN set -eux; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      ca-certificates curl gnupg libusb-1.0-0 \
      python3 python3-pip; \
    rm -rf /var/lib/apt/lists/*

# Coral repo (utan apt-key)
RUN set -eux; \
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | gpg --dearmor -o /usr/share/keyrings/coral-archive-keyring.gpg; \
    echo "deb [signed-by=/usr/share/keyrings/coral-archive-keyring.gpg] https://packages.cloud.google.com/apt coral-edgetpu-stable main" \
      > /etc/apt/sources.list.d/coral-edgetpu.list

# EdgeTPU runtime + PyCoral (matchar Python 3.9 i bullseye)
RUN set -eux; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      libedgetpu1-std python3-pycoral; \
    rm -rf /var/lib/apt/lists/*

# Webserver libs
RUN set -eux; \
    python3 -m pip install --no-cache-dir --upgrade pip; \
    python3 -m pip install --no-cache-dir fastapi uvicorn python-multipart pillow

WORKDIR /app
COPY server.py /app/server.py

EXPOSE 5052
CMD ["python3","-m","uvicorn","server:app","--host","0.0.0.0","--port","5052"]
