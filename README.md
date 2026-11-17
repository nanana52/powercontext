# Dream Lost-and-Found: actual Dify + PowerContext game

Play the current temporary HTTPS deployment: https://status-toolbox-kinase-ray.trycloudflare.com . The address is live while the demonstration host is running. No account, API key or external model credentials are required. Enter a fictional nickname, a lost object and an action; retain the nickname on the next turn to exercise persistent memory.

## Start from the repository root

```bash
bash run.sh
```

Or use the repository-root Docker build context:

```bash
docker build -t dream-dify-complete:local .
docker volume create dream-dify-data
docker run --name dream-dify-game --cpus=2 --memory=2g --memory-swap=2g --pids-limit=128 -p 127.0.0.1:8080:8080 -v dream-dify-data:/data dream-dify-complete:local
```

Visit http://127.0.0.1:8080 after initialization completes. Health returns 503 during initialization and 200 when actual Dify and the game are ready. First build downloads fixed-checksum dependencies and a 0.5B Qwen model. Application execution does not require external network access. The single foreground container starts actual Dify API and its worker, PostgreSQL, Redis, PowerContext1.2.0 and the local Qwen model.

All application code and the single DSL remain in [dify/](dify/), as required by the contest. [dify/README.md](dify/README.md) describes deployment, [dify/VALIDATION.md](dify/VALIDATION.md) provides the acceptance procedure, and [dify/PREVIEW.md](dify/PREVIEW.md) describes the external demonstration. Root Dockerfile and run.sh are convenience entrypoints for the identical application.

Actual fresh-container, restart-persistence and external HTTPS evidence is in [dify/evidence/](dify/evidence/). These reports establish local reproducibility and are not a claim of a passing formal contest score. Previous formal runs returned error100 with no case/error detail; their backend failure cause has not been confirmed.
