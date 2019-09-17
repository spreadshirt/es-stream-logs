FROM python:3-alpine

RUN pip install elasticsearch certifi flask

ADD static /app/static

COPY es-stream-logs.py /app/es-stream-logs.py

CMD python /app/es-stream-logs.py 0.0.0.0 10006
