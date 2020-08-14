FROM tiangolo/uvicorn-gunicorn-fastapi:python3.8-alpine3.10

ENV MODULE_NAME=es_stream_logs
ENV MAX_WORKERS=10
ENV PORT=3028

ADD requirements.txt /app/
RUN apk add --no-cache gcc make musl-dev && python -m pip install --upgrade pip && pip install -r /app/requirements.txt && apk del --no-cache gcc make musl-dev

ADD static /app/static

COPY config.json /app/
COPY render /app/render
COPY *.py /app/
