# 本地语言模型对照测试

`benchmark-model.py` 用本机已有的 Rime DLL、词典和 `.gram` 模型，在新建的隔离目录中比较有／无语法模型时的整句候选与按键耗时。适用于已部署、启用 `grammar/language` 的全拼方案，例如万象全拼。

这不是神经网络推理服务，也不会安装或下载模型。实际输入法不需要为了运行测试而重装。脚本不复制用户词典、输入历史或 Lua 扩展，不修改正在使用的方案。

## 准备与运行

需要 Visual Studio C++ 工具链、与 DLL 架构匹配的编译环境、Python 和 PyYAML。使用独立 Python 环境；如需安装 PyYAML，请安装到该环境中。

在匹配 DLL 架构的 Visual Studio Developer PowerShell 中，从仓库根目录运行：

```powershell
New-Item -ItemType Directory -Force msbuild/model-benchmark | Out-Null
cl /nologo /std:c++17 /EHsc /MT /I include tools/model-benchmark.cpp /Fo:msbuild/model-benchmark/runner.obj /Fe:msbuild/model-benchmark/runner.exe
if ($LASTEXITCODE -ne 0) { throw 'Model benchmark build failed' }

python tools/benchmark-model.py `
  --dll output/rime.dll `
  --runner msbuild/model-benchmark/runner.exe `
  --user-data "$env:APPDATA/Rime" `
  --schema wanxiang `
  --work-dir msbuild/model-trial-01
```

`--user-data` 应指向实际 Rime 用户目录；自定义过目录时需要替换。`--work-dir` 必须尚不存在，避免覆盖已有数据。每次测试会复制词典和模型，请预留相应磁盘空间。资源名称目前仅支持英文字母、数字、下划线和连字符。

输出包括 `summary.json`、两组逐句 TSV、隔离配置以及 Rime 日志。脚本遇到无模型、缺资源、空候选、子进程错误或超时会返回失败，不应把这类结果当成准确率。

## 如何理解结果

- 默认语料是 `test/data/model-pinyin.tsv` 的 24 条合成句子，仅用于冒烟测试，不代表真实用户总体准确率。可用 `--corpus` 指定 UTF-8 无 BOM 的 TSV，每行是 ASCII 全拼按键序列、一个制表符、期望整句。以 `#` 开头的行会忽略。
- 两组使用相同词典、拼写规则和搜索参数；仅模型组加入已部署的 `grammar` 设置。用户词典和上下文联想关闭，Lua、预测等扩展不参加测试。
- 先预热一次，再记录三轮。`top1_exact` / `top5_exact` 是第一轮整句精确匹配条数，允许语义相同但文字不同的结果仍会计为不匹配。
- 计时覆盖每次 `process_key` 和前五候选读取，不含 Weasel IPC、界面绘制及真实应用延迟。汇总值是各句各轮按键 P50／P95 的中位数，**不是所有按键合并后的总体 P95**。
- DLL、模型、词典、CPU 及缓存状态会影响结果；选方案的初始化时间不应当作冷启动比较。模型 SHA-256 随报告保存，便于识别版本。
- 语料不会上屏提交或用于学习。测试成功不表示完整 UI、双拼、联想或跨应用体验已验证。

## 本机配置与构建的关系

已有 DLL 支持 `grammar` 时，安装模型和配置输入方案通常只需重新部署 Rime。修改 C++ 源码则需要重新构建，并在升级运行中的程序后才会生效；Git 提交本身不会替换当前程序。

皮肤应通过用户目录的 `weasel.custom.yaml` 的 `patch` 保存，例如 `style` 和 `preset_color_schemes/<配色名>`，避免直接修改基础 `weasel.yaml` 后被更新覆盖。`preserve-weasel-style.py` 从已部署配置生成这份补丁，并把颜色写成带引号的八位十六进制字符串。这个格式很重要：`0x00000000` 表示透明，普通 YAML 工具若把它改写成十进制 `0`，Weasel 会按不透明黑色解释，候选窗就会出现黑块。

```powershell
# Preview first. Both paths must be replaced when the Rime directory is customized.
python tools/preserve-weasel-style.py --user-data "$env:APPDATA/Rime" --output msbuild/weasel-style-preview.yaml

# Write a backup beside the new output, replace the custom file, then redeploy.
python tools/preserve-weasel-style.py --user-data "$env:APPDATA/Rime" --output msbuild/weasel-style-apply.yaml --apply
```

迁移后应核对部署结果。背景图的本机绝对路径仅留在用户配置中，不应写入仓库；若换机，还需复制图片并调整路径。

## 万象全拼简拼修复与扩展词库

`configure-wanxiang.py` 为带声调字表的万象全拼追加一条拼写规则，排除 `bun / ceok / ceon / dim / din / tii` 作为完整拼音。这样 `bun` 可以按 `bu + n` 匹配“不能”，而不会被字表里标作 `būn` 的“兺”抢占。不会删除字表中的字；正常普通话读音 `nun` 保留。双拼、其他声调编码方案应另行验证。

```powershell
# Preview only; the output directory must be new.
python tools/configure-wanxiang.py --user-data "$env:APPDATA/Rime" --output-dir msbuild/typing-preview

# Back up existing files, save the patch, then redeploy from the tray menu.
python tools/configure-wanxiang.py --user-data "$env:APPDATA/Rime" --output-dir msbuild/typing-backup --apply
```

可额外传入 `--dictionary domain.dict.yaml` 导入独立词库，或 `--dictionary-url "https://<host>/<dictionary>.dict.yaml"` 按需联网下载。两种参数只能选一个；仅在执行命令时访问网络，不上传输入内容，不启动后台更新。建议使用可信来源的固定版本 URL，先预览，再用新的备份目录加 `--apply` 应用，最后重新部署。

导入文件必须为 UTF-8 Rime 字典，YAML 头以 `...` 结束；数据列为“词语、空格分隔的小写全拼、可选整数词频”，以制表符分隔。暂不接受无拼音词库、依赖其他表的词库或改变列顺序的文件。联网文件上限 20 MiB，失败不会写入用户配置。工具保留头部注释、记录来源及 SHA-256，并把导入词频限制在 1～1000。大词库不一定改善排序，应按领域少量增补并测试。

搜狗 `.scel` 可先用开源 [深蓝词库转换](https://github.com/studyzy/imewlconverter) 转为 Rime 格式，再使用 `--dictionary` 导入。当前工具不直接解析 `.scel`，也没有接入搜狗云候选服务。转换器 3.x 的命令示例：

```powershell
dotnet ImeWlConverterCmd.dll -i scel -o rime -O domain.dict.yaml domain.scel
```

导入后采用 `wanxiang_extended.dict.yaml` 和 `user_extension.dict.yaml`，保留原有字表及用户词典路径，不改原始 `wanxiang.dict.yaml`。再次导入会替换这份扩展词库，应先合并需要保留的词条。万象主词库的 `import_tables` 结构升级后，需要重新运行工具以更新扩展配置。

回退时，按 `output-dir/backup/manifest.json` 恢复 `replaced_files` 对应的备份文件，移除本次新增且未被后续修改的 `new_files`，然后重新部署。请保留备份目录。应用过程若中断，也可用这份清单恢复；脚本不自动修改已部署的二进制词典。

验证工具：`python -B -m unittest discover -s test -p test_typing_tools.py`。输入方案回归语料见 `test/data/abbreviated-pinyin.tsv`。
