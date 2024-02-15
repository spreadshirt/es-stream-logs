FROM python:3.12

WORKDIR /app

CMD ["uvicorn", "es_stream_logs:app", "--host", "0.0.0.0", "--port", "3028", "--workers", "10"]

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

ADD static /app/static

COPY config.json /app/
COPY render /app/render
COPY *.py /app/
