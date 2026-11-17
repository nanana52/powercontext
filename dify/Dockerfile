FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY third_party/powercontext-1.2.0-py3-none-any.whl /tmp/powercontext-1.2.0-py3-none-any.whl
RUN pip install --no-deps /tmp/powercontext-1.2.0-py3-none-any.whl
COPY backend/app.py /app/app.py
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --uid 10001 --create-home dream && mkdir /data && chown dream:dream /data
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY backend/fetch_runtime.py /tmp/fetch_runtime.py
COPY .model-cache/ /tmp/dream-model-cache/
RUN python /tmp/fetch_runtime.py && rm -rf /tmp/dream-model-cache
COPY backend/container_main.py /app/container_main.py
USER dream
EXPOSE 18090
ENTRYPOINT ["python","/app/container_main.py"]
