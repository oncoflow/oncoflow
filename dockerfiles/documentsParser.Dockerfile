FROM python:3.11-slim 

LABEL LABEL org.opencontainers.image.source https://github.com/oncoflow/oncoflow

RUN mkdir app/ && useradd -m python && \
    mkdir -p app/chroma && chown python: app/chroma && \
    apt-get update && \
    apt-get install -y \
        build-essential \
        libmagic-dev poppler-utils tesseract-ocr qpdf \
        ffmpeg libsm6 libxext6 && \
    rm -rf /var/lib/apt/lists/*

USER python


COPY documents_parser_llm/ app/

WORKDIR app

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python" ]

CMD [ "app.py" ]