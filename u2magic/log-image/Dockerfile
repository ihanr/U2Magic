FROM python:3.13-alpine

WORKDIR /app
COPY deploy/log_server.py /app/log_server.py

EXPOSE 18081
CMD ["python", "/app/log_server.py"]

