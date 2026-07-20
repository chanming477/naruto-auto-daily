# CI/CD 自动发布:naruto-auto-daily "下载即用"

**2026-07-20** · 关联: brainstorming plan（v2,含本次实现偏差修正）

## 目标

用户从 GitHub Releases 下载 zip → 解压 → 双击 `start.bat` → GUI 启动，零安装。

## 最终方案（v2）

### git 追踪策略

`.gitignore` 从"整个 `frontend/MFAAvalonia/` 忽略"改为"只忽略二进制"。

**追踪（3 个文件）**：
- `frontend/MFAAvalonia/interface.json` — 任务编排（task 块 + option 块）
- `frontend/MFAAvalonia/appsettings.json` — 应用设置
- `frontend/MFAAvalonia/config/instances/default.json` — 默认任务列表

**忽略**：
- 所有二进制（`MFAAvalonia.exe` / `*.dll` / `*.deps.json` / `*.runtimeconfig.json` / `libloader.dll` / `*.bat`）
- 运行时目录（`runtimes/` / `python/` / `libs/` / `plugins/` / `agent/` / `resource/` / `resources/` / `ThirdParty/` / `backup/` / `debug/` / `logs/` / `temp/`）
- 上游默认配置（`config/config.json` / `maa_option.json` / `maa_pi_config.json`）
- 备份文件（`*.bak` / `interface.json.bak` / `config/instances/*.bak`）
- 平台相关库（`*.so` / `*.dylib`）

### 与 v1 的差异

| 项 | v1 (2026-07-19 前) | v2 (本设计) |
|---|---|---|
| 配置文件管理 | `packaging/mfaavalonia-overlay/` 镜像 | **git 追踪 `frontend/MFAAvalonia/config/` + `interface.json`** |
| 版本号同步 | 3 处手写 | workflow 用 `actions/github-script` 从 `pyproject.toml` 解析 |
| Python 缓存 | 无 | `actions/cache@v4` 缓存 tarball |
| 测试关卡 | 可选 | **强制** `pytest -q` 不过则 build 失败 |
| 并发锁 | 无 | `concurrency: group: release-${{ github.ref }}` |
| Defender 误报 | 无 | README 加"已知问题"段落 |
| 前置检查 | 假设工具齐全 | step 0 pre-flight 验证必需文件 |

### 本次实现 vs 原 plan 的关键修正

| 项 | 原 plan | 本次实现 | 原因 |
|---|---|---|---|
| MFAAvalonia 下载源 | MaaXYZ/MaaFramework releases | **MaaXYZ/MFAAvalonia releases**（独立 repo） | plan 假设错;MFAAvalonia 是独立 repo |
| MFAAvalonia asset 名 | `MFAAvalonia-win-x64.zip` | `MFAAvalonia-v{ver}-win-x64.zip` | 实际命名 |
| MFAAvalonia 版本号 | 从 `maafw` 解析 | **从 `pyproject.toml` 新增的 `[tool.naruto-auto-daily] mfaavalonia-version` 字段解析** | 跟 maafw 独立,不能复用 |
| spec doc 路径 | `docs/superpowers/specs/` | `docs/`（tracked） | `.gitignore` 已 exclude `docs/superpowers/`,放进去不入库没意义 |
| agent/custom/*.py 追踪 | plan 列了 4 个文件要 commit | **跳过** | 2026-07-19 OPT-3 清理后,MFAvalonia/agent/custom/ 只剩 `__init__.py`;源在项目根 `agent/`,`bundle_python.py` 会自动复制 |

## 实施清单

| # | 文件 | 操作 |
|---|---|---|
| 1 | `.gitignore` | **改**: 拆分为二进制 ignore + 配置追踪 |
| 2 | `frontend/MFAAvalonia/interface.json` | **git add**（从本地） |
| 3 | `frontend/MFAAvalonia/appsettings.json` | **git add**（从本地） |
| 4 | `frontend/MFAAvalonia/config/instances/default.json` | **git add**（从本地） |
| 5 | `.github/workflows/release.yml` | **新增**（11 步） |
| 6 | `README.md` | **改**: 加 Defender 误报段落 |
| 7 | `docs/2026-07-20-cicd-release-design.md` | **新增**（本文档） |

> **计划偏差（2026-07-19 OPT-3 后的调整）**：
> 原计划要 commit 的 `frontend/MFAAvalonia/agent/custom/{sink,reco,action}.py` + `agent/main.py`
> 在 2026-07-19 OPT-3 清理中已经从 `MFAAvalonia/agent/custom/` 删除（只留 `__init__.py` 占位）。
> 这些文件的源在项目根 `agent/`，`tools/bundle_python.py` 已自动复制到 `MFAAvalonia/agent/`。
> 因此只追踪配置文件即可，无需追踪 agent 代码副本。

## 工作流结构

`.github/workflows/release.yml` 11 步：

```
0  Pre-flight       验证必需文件存在
1  Checkout         actions/checkout@v4 (depth=0)
2  Version parse    actions/github-script 读 pyproject.toml → project + maafw + mfaavalonia
3  Setup Python 3.11 build-time Python
4  Test gate        pytest tests -q  (v2 强制)
5  Download MFA     从 MaaXYZ/MFAAvalonia releases 下 MFAAvalonia-v{ver}-win-x64.zip
5.5 Restore configs git checkout 还原我们的 3 个配置
6  Cache + Download .cache/python-build-standalone/  tarball
7  bundle_python    python tools/bundle_python.py --local-tarball
8  Init config      python main.py --init-config (best-effort)
9  Pack zip         choco install 7zip + 7z a ... (排除 .git/.github/tests/...)
10 Upload release   softprops/action-gh-release@v2
11 Summary          echo size + version
```

**触发**：
- push tag `v*`（自动）
- `workflow_dispatch`（手动测试，可指定 version）

**并发锁**：`concurrency: group: release-${{ github.ref }}`

**权限**：`contents: write`（用于创建/上传 release）

## 验证方式

1. **本地 dry-run**（不 push tag）：
   ```powershell
   python tools/bundle_python.py
   python main.py --init-config
   choco install 7zip -y
   7z a test.zip . -xr!.git -xr!.github -xr!tests
   ```
2. **CI dry-run**：推 `v0.7.1-test` tag，看 workflow 跑通
3. **端到端测试**：在干净 Windows 虚拟机：
   - 解压 zip
   - 双击 `start.bat`
   - MFAAvalonia GUI 正常起来
   - 跑一个 task，确认 Agent 模式 Python 子进程 spawn 成功
4. **回归测试**：`pytest -q` 全过

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| `tools/bundle_python.py` CI 假设不成立 | step 0 pre-flight + 已知 `--local-tarball` 支持 |
| Windows Defender 误杀 | README 段落（"已知问题 → Defender 误报"） |
| MFAAvalonia 版本号漂移 | 从 `pyproject.toml` 自动提取，只改一处 |
| 350-500 MB 上传慢 | 接受；可改 PyOxidizer / AOT 后期优化 |
| 第一次 CI 跑挂 | 用 `v0.7.1-test` tag 试，别直接打正式版 |
| workflow 配置写错 | 推 test tag 验证 |
| 并发 tag 触发竞态 | `concurrency` group 锁 |
| 测试关卡导致频繁 release 失败 | 接受 —— 比"代码错版本打出去"好 |

## 关联文档

- 原始 brainstorming plan: `D:\claude-data\claude-config\plans\generic-bubbling-sprout.md`（v2，含 5 个被本次实现修正的偏差）
- MFAAvalonia interface.json 修复历史: `docs/MAF_CONFIG_FIX.md`
- 项目 README: `README.md`

## 后续维护

升级 MFAAvalonia 时,只改一行:
```toml
# pyproject.toml
[tool.naruto-auto-daily]
mfaavalonia-version = "X.Y.Z"   # 改这里
```

然后推 tag（如 `v0.7.1`）即可,workflow 自动:
1. 从 MaaXYZ/MFAAvalonia releases 下对应版本
2. 套我们的 3 个 config
3. 跑测试 + bundle + 打包 + 上传 release
