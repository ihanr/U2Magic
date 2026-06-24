FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

WORKDIR /app

RUN python -m venv /app/.venv

COPY requirements.txt /tmp/requirements.txt
RUN /app/.venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

COPY *.py /app/
COPY defaults/ /opt/u2-scripts-defaults/
COPY entrypoint.sh /usr/local/bin/u2-scripts-entrypoint.sh
RUN chmod +x /usr/local/bin/u2-scripts-entrypoint.sh

EXPOSE 18765

ENTRYPOINT ["/usr/local/bin/u2-scripts-entrypoint.sh"]

