# MiniMax × seekdb × PowerContext — 一次可复现的 SDD 实际代码修复

## 先看这里
**本目录是可运行的参赛源码，不是已经拿分的运行记录。**
必须有真实 MiniMax API Key；只有成功执行 `run.sh` 并生成
`evidence/ACCEPTANCE_SUMMARY.json` 的 `status=PASS`，才能声明完成验收。
六项验收全部通过才得 20 分，任何一项失败就是 0 分。

我们避免在 Windows 装 Docker：推荐在 GitHub Codespaces 的 Ubuntu 环境
（或任何 Python 3.11+ 的 Linux 云终端）运行。
运行目录必须是比赛私有答题仓库的
`2026-competition-ecosystem` 分支下的 `minimax/`，不要使用 `master`。

## 最短操作
1. 将整个 `minimax/` 文件夹上传到你的**正确的私有答题仓库**，分支为
   `2026-competition-ecosystem`。不要将 ZIP 文件本身当作提交产物。
   如果浏览器上传文件夹不方便，先打开同一分支的 GitHub Codespace，
   把 ZIP 拖进代码编辑区根目录，终端 `unzip -o minimax-sdd-package.zip`。
2. 在该分支创建 GitHub Codespace（浏览器里点击仓库 `Code → Codespaces`）。
   Codespaces 是否可用以及收费/免费额度，取决于 GitHub 账户。
3. 从 **MiniMax 官方开放平台**获得实际可调用的 API Key，并确认套餐
   对 `MiniMax-M2.5` 文本模型可用。请勿将密钥发给任何人或提交到 GitHub。
4. 在 Codespaces 的 Linux bash 终端，执行下面三行（密钥输入不可见）：

```bash
read -rs -p 'MiniMax API Key: ' MINIMAX_API_KEY; echo
export MINIMAX_API_KEY
bash minimax/run.sh
```

5. 真正看到 `PASS`，确认 `minimax/evidence/ACCEPTANCE_SUMMARY.json`
   内容为 `status=PASS`，把代码改动和真实 evidence 一并提交：

```bash
git add minimax && git commit -m "feat(minimax): live SDD acceptance with MiniMax seekdb PowerContext" && git push
```

6. 去比赛平台填实际分支 `2026-competition-ecosystem` 和提交后的 commit hash，
   根据平台指示提测。不要虚构测试记录。

## 输入与输出
主入口：`bash minimax/run.sh`，内部调用 `python -m sdd.run`。
输入：`TASK.md`、有效规格、`app/shipping.py`、测试与 MiniMax API Key。
输出：seekdb 检索上下文、MiniMax 模型响应、代码修改、真实测试日志、
PowerContext Memory 写入/重启后读取记录及代码差异，全部见 `evidence/`。

可执行测试：`python -m unittest tests.test_target tests.test_regression -v`
（在 `minimax/` 目录运行；运行前 target 应当失败，属于预期功能失败）。

## 可核验验收样例
- **初始状态**：`snapshots/before/shipping.py` 的条件为 `> 100`。
- **任务**：规格 SPEC-SHIP-001 要求金额等于 100 也享受免基础运费。
- **MiniMax 提供的开发上下文**：实时 seekdb SELECT 的当前规格、源码、
  目标测试、回归测试，以及 PowerContext 中的任务状态。
- **先运行**：`tests.test_target` 在 `100` 标准/快递测试上断言失败；
  `tests.test_regression` 全通过。
- **模型编辑**：MiniMax 返回补丁对象，由 `sdd.minimax_client` 验证
  并替换单一条件行；测试文件不变。
- **后运行**：目标及回归测试全部通过，`evidence/08_real_minimax_code_diff.patch`
  是由真实模型结果应用后计算出来的 diff。
- **规格更新**：向 seekdb 对相同有效规格 key 重新导入追加
  `SPEC-SHIP-006` 的版本，下一次查询读到新条目；随后恢复正式规格。
- **重启状态复用**：Server 写入 `BOUNDARY2026` Task Memory，
  停止并启动新 PowerContext 进程，同一个 Scope 再次搜索到该状态，
  该结果成为 `14_context_reused_after_restart.json` 的任务输入。

## 技术版本与依赖
- Python: >=3.11, Linux Ubuntu (推荐 GitHub Codespaces)；
- PowerContext: `powercontext[cli,server]==1.4.1`, SQLite basic memory；
- seekdb: 通过 `pylibseekdb` 本地嵌入式运行，PyMySQL SQL 驱动；
  SDK 安装时实际版本可用 `python -m pip show pylibseekdb` 记录；
- MiniMax: `MiniMax-M2.5`, 官方 HTTP Text ChatCompletion v2；
  默认 `https://api.minimax.io/v1/text/chatcompletion_v2`；
  如是中国区官方账号且区域不同，可设置经官方文档确认的
  `MINIMAX_API_URL`，不要误用第三方中转服务。
- 无前端、Embedding、Rerank、Docker、Dify 或预置私有数据依赖；
- 首次运行需要能访问 PyPI 和 MiniMax 官方模型 API；API Key 可能产生费用。

## 失败和重跑
如果未生成 PASS，请查看 `evidence/ERROR.json` 和报错，
不要直接提交声称六项已验收。
重新运行会**重置本目录 `app/shipping.py` 为已交付的 before 快照**，
再从头生成一次真实 MiniMax 补丁；请勿在其中放其他未备份改动。
本地持久数据在 `.local/`，不会提交；测试证据包含来源哈希和实际 Scope ID。
如希望完全重置初始状态，在停止服务后删除本目录 `.local/`，
这会清除测试记忆，不会删除仓库其他文件。不要执行 Docker 数据清理命令。

## 安全与已知限制
PowerContext 只绑定 `127.0.0.1:18761`，默认禁用鉴权，
不可对公网开放 Codespaces 端口。
MiniMax 密钥仅在环境变量中，不能通过截图、聊天、日志公开。
该演示的模型补丁仅允许固定范围内的单行修改：
实际使用 MiniMax 输出，同时限制任意代码注入风险。
没有模型权限、服务器下载失败、seekdb 不支持宿主平台，
都会导致真实验收停止；这些不能伪装为通过。

## 来源与自创范围
- seekdb: https://github.com/oceanbase/seekdb
- embedded seekdb: https://github.com/oceanbase/seekdb-bindings
- PowerContext: https://powercontext.oceanbase.io/zh/docs/develop/http-api/
- MiniMax: https://www.minimax.io/models/text
所有业务示例、测试和演示脚本是为本赛题新写的，没有直接改编示例仓库。
