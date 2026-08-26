# DCSMizzer 开发测绘索引

这里保存项目测绘的证据、可重现程序和历史决策。它不是产品 API；
模型直接使用的只读入口位于仓库根目录的 `Tools/` 和 `Docs/`。

## 当前测绘（2026-07-27）

最终结论与边界见 [`REPORT-2026-07-27.md`](REPORT-2026-07-27.md)。

| 文件 | 证据范围 |
|---|---|
| [`baselines/2026-07-27-corpus.json`](baselines/2026-07-27-corpus.json) | MIZ/CMP 实例、内容去重、ZIP 安全、CRC 和来源重叠 |
| [`baselines/2026-07-27-semantic.json`](baselines/2026-07-27-semantic.json) | 安全 Lua 数据解析和匿名化 MIZ/CMP 语义统计 |
| [`baselines/2026-07-27-upstream.json`](baselines/2026-07-27-upstream.json) | 6 个上游 Git 仓库的远端、分支、提交、工作树和许可证 |
| [`../reference/provenance.json`](../reference/provenance.json) | 45 份旧参考数据的冻结提交与源文件映射 |
| [`baselines/2026-07-27-dcs-installation.json`](baselines/2026-07-27-dcs-installation.json) | 当前 DCS/Steam 版本、已安装模块、静态数据源和覆盖边界 |
| [`baselines/2026-07-27-runtime-boundary.json`](baselines/2026-07-27-runtime-boundary.json) | 静态验证与未执行运行时验证的明确分界 |

本轮实际覆盖 1,050 个 `.miz` 实例和 10 个 `.cmp` 实例；按内容去重后为
904 个 `.miz` 和 5 个 `.cmp`。6 个上游仓库和 45 份旧参考数据都已绑定
可追溯版本。默认报告不包含本机绝对路径、私有任务名、简报正文、
逐文件任务哈希或 Steam 账号标识。

### 重现与检查

从仓库根目录运行完整测绘测试：

```powershell
python -m unittest discover -s .develope\survey -t .develope\survey -p test_*.py
```

其中两项历史来源路径审计要求 `.develope/upstream` 下六个被忽略的只读
上游证据根均存在；干净 checkout 会明确跳过这两项环境审计，同时仍会执行
“来源根缺失必须失败关闭”的独立测试。要取得完整本地证据门禁结果，需先按
基线记录准备这些固定提交的克隆。

测绘 CLI：

```powershell
python .develope\survey\run_survey.py --help
python .develope\survey\run_survey.py corpus --help
python .develope\survey\run_survey.py semantic --help
python .develope\survey\run_survey.py upstream --help
python .develope\survey\run_survey.py legacy-reference --help
python .develope\survey\run_survey.py dcs --help
```

`corpus` 和 `semantic` 命令要求显式传入 `NAME:KIND=PATH` 根目录。
路径只存在于进程内存，报告只记录公开的 `NAME` 标签。

### 安全与结论边界

- ZIP 成员原位读取，不解包；检查 CRC、路径穿越、加密、重复成员、成员数、
  展开尺寸和压缩比。
- Lua 只由项目解析器当作数据解析，绝不执行；任务脚本、触发脚本和初始化脚本
  只计数，不运行。
- 上游克隆只作为只读证据。
- DCS 安装测绘只读取静态文件和可执行文件版本元数据，不启动 DCS。
- 按用户要求，不启动 DCS；运行时探针未执行，也不构成任何运行时有效性证据。

`archive-valid`、`parse-valid`、`static-valid` 和 `runtime-valid` 是相互独立的
状态。2026-07-27 基线只在最终报告记载的覆盖范围内建立前三类证据，
没有建立运行时有效性。

## 历史测绘与决策记录

以下文件保留方法、推理和决策演进。其数字、上游提交和当时的能力描述，
凡与 2026-07-27 基线冲突，均以当前基线为准：

- [`2026-07-26-evidence-ledger.md`](2026-07-26-evidence-ledger.md)
- [`2026-07-26-miz-cmp-corpus-map.md`](2026-07-26-miz-cmp-corpus-map.md)
- [`2026-07-26-mission-model-and-design-patterns.md`](2026-07-26-mission-model-and-design-patterns.md)
- [`2026-07-26-upstream-capability-map.md`](2026-07-26-upstream-capability-map.md)
- [`2026-07-26-docs-tools-source-map.md`](2026-07-26-docs-tools-source-map.md)
- [`2026-07-24-upstream-reference-extract.md`](2026-07-24-upstream-reference-extract.md)

历史文件不是当前 DCS 数据库，也不能单独证明功能已实现或验证。
