FROM langgenius/dify-api:1.18.0@sha256:0120970fb4ea59aa328d63b7dda635cccc071efb8aae470cd07115a026dbffd3
USER root
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-15=15.20-0+deb12u1 redis-server=5:7.0.15-1~deb12u10 libgomp1 libstdc++6 && (pg_dropcluster --stop 15 main || true) && rm -rf /var/lib/apt/lists/*
RUN /usr/local/bin/python -m venv /opt/dream-venv
COPY backend/requirements.txt /tmp/dream-requirements.txt
RUN /opt/dream-venv/bin/pip install --no-cache-dir -r /tmp/dream-requirements.txt
COPY scripts/fetch_dependencies.py /tmp/dream-fetch.py
RUN /opt/dream-venv/bin/python /tmp/dream-fetch.py --wheel /tmp/powercontext-1.2.0-py3-none-any.whl && /opt/dream-venv/bin/pip install --no-deps /tmp/powercontext-1.2.0-py3-none-any.whl && rm /tmp/powercontext-1.2.0-py3-none-any.whl
COPY backend/fetch_runtime.py /tmp/dream-model-fetch.py
COPY .model-cache/ /tmp/dream-model-cache/
RUN /opt/dream-venv/bin/python /tmp/dream-model-fetch.py && rm -rf /tmp/dream-model-cache
WORKDIR /opt/dream
COPY backend/ /opt/dream/backend/
COPY demo/index.html /opt/dream/demo/index.html
COPY app.yml /opt/dream/app.yml
ENV PORT=8080 PYTHONDONTWRITEBYTECODE=1 LANG=C.UTF-8 LC_ALL=C.UTF-8
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=180s --retries=6 CMD /opt/dream-venv/bin/python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health',timeout=2)"
ENTRYPOINT ["/opt/dream-venv/bin/python","/opt/dream/backend/supervise.py"]
