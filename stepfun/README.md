# Fieldnotes — StepFun × seekdb

2026 OceanBase 数据库大赛 · 阶跃星辰生态伙伴赛题：端侧 AI 推理性能优化与 seekdb 混合检索。

**参赛目录**：`stepfun/`。**分支**：`2026-competition-ecosystem`。

## 一、快速复现（Linux / VS Code Codespaces）

环境要求：Node.js >=20.19、npm、Docker Engine、curl、OpenSSL；推荐 >=4 GiB 可用内存和充足磁盘空间。数据库 Docker 镜像用于本地开发、测试及本题复现，而非生产环境。

在仓库的 `stepfun/` 目录下，逐条运行：

```bash
npm ci --legacy-peer-deps
bash scripts/01_seekdb_docker.sh
bash scripts/02_download_models.sh
bash scripts/03_start_site.sh
```

最后一个命令会持续运行网站服务，保留该终端。打开 VS Code **PORTS** 面板中的 **5173** 端口转发地址（保持 **Private**）；建议 Chrome/Edge 浏览器。

- `01_seekdb_docker.sh`：启动 Docker seekdb Server，创建 `test` 数据库，执行真实 `SELECT 1` 验证。容器端口仅绑定 `127.0.0.1:2881`，数据库数据持久化在 Docker volume `stepfun-seekdb-data`。首次启动会生成本地 root 密码，仅保存在 `$HOME/.config/stepfun/seekdb.env`（不在 Git 仓库中）。
- `02_download_models.sh`：从 Hugging Face 公开模型仓库下载配置、分词文件及 FP32、Q8、FP16 ONNX 模型，保存到 **Git 忽略**的 `public/models/Xenova/all-MiniLM-L6-v2/`。首次下载需要 Codespaces 可访问 `huggingface.co`；**浏览器不直接访问 Hugging Face**，而是从站点自己的 `/models/` 路径加载模型文件。
- `03_start_site.sh`：从上述本地密码文件读取数据库凭据，设置 `SEEKDB_PASSWORD`，清除曾用于 Embedded 排错的 `LD_PRELOAD`、`GLIBC_TUNABLES` 后执行 `npm run dev`。

**已有环境**：脚本会复用名为 `stepfun-seekdb` 的容器及已经完整下载的模型，不会清空原数据库。请不要把密码文件的内容粘贴到聊天或上传 Git。

### 启动验证

另外打开一个终端：

```bash
curl -fsS http://127.0.0.1:5173/api/health
npm run check
npm run acceptance
npm run build
```

`/api/health` 必须返回 `"ready":true`（仅 HTTP 200 网页 HTML 不算数据库就绪）。本机验收记录是一次实际浏览器端到端运行的证据，不等于新环境已自动通过；重新部署仍需手工验证。

## 二、操作与功能验收

1. 网页顶部应显示 **seekdb · 在线**，无 WebGPU 时显示 **WebGPU · 不可用**。
2. 点击 **导入演示语料**：浏览器中的 Transformers.js + ONNX Runtime Web 执行 embedding，默认自动优先 FP16/WebGPU；不支持或加载失败则退到 Q8/WASM。默认演示语料有 16 条文本。
3. 输入 `How does a vector database combine semantic and keyword search?`，执行混合检索，核对数据库返回的文档 ID、原文与排序。
4. 点击 **运行完整实验**：固定 16 文档、8 查询，分别记录 FP32/WASM 基线与 Q8/WASM 优化结果；支持 WebGPU 时可增加 FP16/WebGPU。数据保存在 `evidence/`，报告生成于 `TECH_ONE_PAGE_RESULTS.md`。
5. 用下拉菜单显式选择 Q8 / WASM 进行导入与检索，检查无 WebGPU 时回退路径。没有实际 GPU 运行证据时不得声称已实测 WebGPU。

若浏览器无法加载模型，先检查 `public/models/` 目录和浏览器 Network 面板中 `/models/` 请求；不要将云端推理 API 替换进流程。

## 三、技术架构

```text
浏览器：.txt/.md 文档 -> 分段 -> Transformers.js/ONNX Runtime Web
       -> 模型本地推理 -> 384维归一化 embedding -> POST /api/import
Node.js：接收原文、元数据及客户端向量（不负责模型推理）
       -> seekdb-js Server 模式（host 127.0.0.1、port 2881、db test）
       -> collection.add -> 向量 HNSW + 全文索引 -> 可见性验证
浏览器：查询文本本地向量化 -> POST /api/search
Node.js：seekdb-js collection.hybridSearch({query, knn, rank:{rrf:{}}})
       -> seekdb 内部融合排序 -> 返回 ID、原文和元数据
```

- 数据库连接由 `server/db.mjs` 使用 `SeekdbClient({host,port,user,password,database})`；密码由环境变量 `SEEKDB_PASSWORD` 提供。
- 不使用 Embedded 的 `.data/seekdb` 作为当前运行数据库。数据库与站点分进程，避免 Node 加载 `libseekdb.so` 时的 TLS 兼容问题。
- 文档 ID、原文、元数据与 384 维向量保存在 seekdb；集合隔离知识库和模型精度；增量写入后通过真实混合检索验证索引可见性。
- 查询的向量化在浏览器执行。检索融合在 seekdb 执行，不是客户端分别查询两路再拼接。
- 模型标识：`Xenova/all-MiniLM-L6-v2`，Apache-2.0。FP32：`onnx/model.onnx`；INT8(Q8)：`onnx/model_quantized.onnx`；FP16：`onnx/model_fp16.onnx`。模型文件由 `02_download_models.sh` 下载，不放进 Git。
- 运行时：`@huggingface/transformers@3.8.1`；模型路径 `/models/`，已关闭运行时远程模型加载（`web/model.js`）。
- 本地模型下载到 Codespaces 不等于云端推理：向量生成仍在最终用户浏览器中执行。

## 四、已完成的实测与限制

2026-10-31 的浏览器端实测（报告：`evidence/browser-benchmark-2026-10-31T08-37-51-740Z.json`）：

| 配置 | ONNX 文件大小 | 向量化吞吐 | seekdb 热查询 | 端到端热查询 | Recall@3 | nDCG@3 |
|---|---:|---:|---:|---:|---:|---:|
| FP32 / WASM | 90.39 MB | 22.28 doc/s | 3.9 ms | 293 ms | 62.5% | 0.615 |
| Q8 / WASM | 22.97 MB | 35.87 doc/s | 4.8 ms | 364 ms | 68.8% | 0.6633 |

- 仅按 **ONNX 文件**计，FP32/Q8 大小比约 **3.93 倍**；此口径不包括 tokenizer、WASM 运行时和缓存。
- 测试中 FP32 baseline batch=1、Q8 优化 batch=8，因此吞吐差异同时包含精度与批处理配置影响，**不能全部归因于量化**。
- Q8 的本轮吞吐与质量数值更高，但端到端查询延迟更大；不宣称每个指标均优化。
- 此环境 WebGPU 不可用，**未提供 FP16/WebGPU 实测**。若评测设备可用，应依照相同测试集另行验证。
- 两个模型的对比结果取自已记录的测试；设备型号、浏览器版本及更详细实验配置以该次真实报告为准，没有的数据不凭空填写。

## 五、提交范围与安全

提交 `stepfun/` 下的源码、`package-lock.json`、演示语料、脚本、README、技术说明和真实实测 JSON；**不要提交** `public/models/`、`node_modules/`、`dist/`、`vendor/`、本地密码、`.data/` 或任何私人文档。提交前检查 `git diff --cached --name-only` 与 `git diff --cached --stat`，确认未包含其他比赛目录。

`evidence/server-events.jsonl` 可能包含实际查询文本：如曾导入私人资料，应在提交前人工审核与脱敏，而不是直接上传。

## 参考资料

- Docker seekdb 官方说明：https://github.com/oceanbase/docker-images/blob/main/seekdb/README.md
- seekdb-js 官方项目：https://github.com/oceanbase/seekdb-js
- 开源模型文件：https://huggingface.co/Xenova/all-MiniLM-L6-v2/tree/main/onnx
- Transformers.js 本地模型配置：https://huggingface.co/docs/transformers.js/custom_usage

更多测试方法见 `TECH_ONE_PAGE.md`、`TECH_ONE_PAGE_RESULTS.md` 和 `evidence/`。
