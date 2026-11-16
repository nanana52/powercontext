FROM python:3.12.12-slim-bookworm
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY vendor/powercontext/src /vendor/powercontext/src
COPY backend/app.py /app/app.py
ENV PYTHONPATH=/vendor/powercontext/src PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home dream && mkdir /data && chown dream:dream /data
USER dream
EXPOSE 18090
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","18090"]
