FROM python:3.11-slim

RUN mkdir app/ && useradd -m python && \
    mkdir -p app/chroma && chown python: app/chroma && \
    apt-get update && \
    apt-get install -y \
        build-essential &&\
    rm -rf /var/lib/apt/lists/*

USER python

COPY documents_parser_llm/ app/

WORKDIR app

RUN pip install -r requirements.txt

ENTRYPOINT [ "python" ]

CMD [ "main.py" ]