FROM nvidia/cuda:13.0.2-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        ffmpeg \
        libsndfile1 \
        libasound2-dev \
        portaudio19-dev \
        git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /backend

COPY privnurse_gemma3n/backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --default-timeout=120 --retries=10 -r /tmp/requirements.txt

COPY privnurse_gemma3n/backend/ ./

EXPOSE 8000

CMD ["python3", "main.py"]
