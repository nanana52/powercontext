# 先看这个：只有 3 组操作（推荐 GitHub Codespaces）

**重要：这道题必须真实运行后才能声称完成，不是单独上传代码就能拿 20 分。**
本包还没有真实 MiniMax / seekdb / PowerContext 成功日志，绝不提供伪造证据。

## ① 把项目放进比赛专用仓库
打开**你导入后的私有 PowerContext 答题仓库**，分支选
`2026-competition-ecosystem`。进入 `Code → Codespaces`，
在该分支创建 Codespace。把整个 ZIP 拖入 Codespaces 文件区根目录。
在 Codespaces **Linux 终端**执行：

```bash
unzip -o minimax-sdd-package.zip
```

解压后仓库根目录应当出现 `minimax/`，而不是 `minimax/minimax/`。

## ② 运行真实验收
从官方 MiniMax 开放平台获取你自己的文本 API Key，并确认
`MiniMax-M2.5` 有使用权限。Key 不要发给聊天、截图或提交到仓库。

在 **Linux Bash 终端**一次执行：

```bash
read -rs -p 'MiniMax API Key: ' MINIMAX_API_KEY; echo
export MINIMAX_API_KEY
bash minimax/run.sh
```

它会自动下载 Python 依赖、启动 PowerContext、用 seekdb 真实查询资料，
调用 MiniMax 产生源码修改、比较修改前后相同的测试并生成证据。
第一次安装依赖需要联网；不需要使用 Windows 本地 Docker。

## ③ 只有 PASS 才提交
确认看到 `PASS` 且 `minimax/evidence/ACCEPTANCE_SUMMARY.json` 的
`status` 是 `PASS`。然后在 Codespaces 终端运行：

```bash
git add minimax && git commit -m "feat(minimax): verified SDD context and code change" && git push
```

最后去比赛平台填写 `2026-competition-ecosystem` 和本次真实 commit hash。

若 **没有 PASS**，不要先提交宣称通过；把最后 15 行错误发给我
（隐藏密钥），我只修复那个具体问题。

### 费用与限制
Codespaces 可用性/额度视 GitHub 账户而定，MiniMax API 调用也可能计费。
这道题 6 项缺一不可；它并不比魔搭 Skill 和高德题简单。
