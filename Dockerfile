FROM python:3-alpine

ADD requirements.txt /app/
RUN pip install -r /app/requirements.txt

ADD static /app/static

COPY config.json /app/
COPY render /app/render
COPY *.py /app/

CMD python /app/es-stream-logs.py /app/config.json 0.0.0.0 3028
