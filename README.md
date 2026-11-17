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


## Standard Docker Compose entrypoint

From either the repository root or `dify/`, run:

```bash
docker compose up --build
```

Open http://127.0.0.1:8080 after health becomes ready. The named data volume is initialized automatically and preserves Dify and PowerContext data. `DREAM_HTTP_PORT=18121 docker compose up --build` chooses a different loopback port. Resource limits are2CPU,2GiB and128PIDs. No account, external credential or manual DSL rebinding is needed. The root and application Compose files build their respective matching Dockerfile contexts. The complete source implementation remains inside `dify/`.

For repeatable fresh-player checks, use a new fictional nickname. To reset all state, stop only this Compose project and remove its named data volume; this removes that game's saved history. First build needs network access to the pinned official images, PyPI, Debian, ModelScope and llama.cpp release asset. The demonstration URL is optional; local deployment operates independently from it.


Build download recovery: model/runtime downloads now have30-second read timeouts, a600-second deadline per asset, up to5 attempts with verified Range resume, and SHA256 plus exact-size validation. Two independent assets download concurrently. Interrupted transfers, a server ignoring Range, wrong checksums, and verified caches were tested using an actual local HTTP server; evidence/download_recovery_test.json records results. The uncached standard Compose attempt stalled at435937280/491400032bytes and was stopped; evidence/previous_download_stall.json records this. Compose runtime acceptance used checksum-verified public asset caches from the preceding complete clean-root build. Caches contain no credentials and are not committed; normal builds download the same pinned assets. This is a real deployment reliability fix and does not establish the platformerror100cause.


Build runtime dependency reuse: the Dockerfile pins the same official Dify1.18.0 image digest and reuses its immutable Python site-packages through a .pth entry in a separate game venv. Dify's environment is not modified. Only aiosqlite0.22.1, sqlite-vec0.1.9, rfc8785=0.1.4, python-multipart0.0.32 and the unmodified checksum-locked PowerContext1.2.0 wheel are added to the game venv. Common dependency versions come from that pinned base image and are recorded by actual runtime inspection. The former full requirements list remains as provenance, not an additional installation step. This removes duplicate package downloads; actual cold workflow and memory integration passed; raw evidence is included, including a harmless English input refused by the small Qwen model.

The full application import is checked during image build, so a missing SDK dependency fails before deployment. Existing Dify model/runtime versions are fixed by the base-image digest. No scoring or evaluator code is changed. Earlier formal failures still have no disclosed backend cause; this deployment simplification does not establish their cause.
