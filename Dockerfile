FROM python:3-alpine

RUN pip install elasticsearch certifi flask

ADD static /app/static

COPY config.json /app/
COPY *.py /app/

CMD python /app/es-stream-logs.py /app/config.json 0.0.0.0 3028
