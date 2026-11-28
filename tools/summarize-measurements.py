"""Summarize repeatable instrumented measurements without hiding ranges."""
import argparse
import json
from pathlib import Path
from statistics import median

parser = argparse.ArgumentParser()
parser.add_argument("baseline", type=Path)
parser.add_argument("current", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
before, after = (json.loads(path.read_text(encoding="utf-8-sig")) for path in (args.baseline, args.current))
for dataset in (before, after):
    if any(sample.get("shutdownClean") is not True for sample in dataset["samples"]):
        raise ValueError("Only samples followed by clean platform shutdown are eligible")
for key in ("cpu", "osVersion", "physicalMemoryBytes", "upstream"):
    if before["machine"][key] != after["machine"][key]:
        raise ValueError(f"Comparison environment differs: {key}")
rows = []
for scenario in ("empty-fresh", "repository-fresh", "repository-cached"):
    for key, label, divisor in (("frameReadyMs", "主窗口/EDT 就绪 (ms)", 1), ("gitLogReadyMs", "Git Log 首屏 (ms)", 1),
                                ("frameWorkingSetBytes", "主窗口工作集 (MiB)", 1024**2),
                                ("gitLogWorkingSetBytes", "Git Log 首屏工作集 (MiB)", 1024**2),
                                ("gitLogHeapUsedBytes", "Git Log 首屏 heap used (MiB)", 1024**2),
                                ("workingSetBytes", "任务结束后工作集 (MiB)", 1024**2), ("heapUsedBytes", "任务结束后 heap used (MiB)", 1024**2)):
        samples = []
        for dataset in (before, after):
            values = [sample[key] / divisor for sample in dataset["samples"] if sample["scenario"] == scenario and not sample["warmup"] and sample[key] is not None]
            if not (key.startswith("gitLog") and scenario == "empty-fresh"):
                if len(values) < 3:
                    raise ValueError(f"Need at least 3 measured samples: {scenario}/{key}")
            samples.append(values)
        if not samples[0]:
            continue
        rows.append({"scenario": scenario, "metric": label, "baseline": {"median": median(samples[0]), "min": min(samples[0]), "max": max(samples[0])},
                     "current": {"median": median(samples[1]), "min": min(samples[1]), "max": max(samples[1])}})
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.with_suffix(".json").write_text(json.dumps({"machine": before["machine"], "baseline": str(args.baseline.resolve()), "current": str(args.current.resolve()), "rows": rows}, indent=2) + "\n", encoding="utf-8")
lines = ["# Alhena 裁剪前后测量", "", "同机、同一固定源码和运行时，各场景至少 3 次。下表为中位数 [最小–最大]；cached 场景排除预热样本。", "",
         "数据为隐藏应用窗口的 Swing/EDT 探针观测，包含 Attach 与轮询开销；fresh 指应用配置/索引缓存，未清空操作系统文件缓存。每次通过平台退出流程保存设置并关闭 VFS；缓存启动不包含崩溃恢复样本。内存的末次采样在就绪后至少等待 5 秒、索引结束且公开进度任务连续两次为空后记录，不是峰值或强制 GC 后的存活集。", "",
         f"CPU：{before['machine']['cpu']}；Windows：{before['machine']['osVersion']}；物理内存：{before['machine']['physicalMemoryBytes']/1024**3:.1f} GiB。", "",
         "测试仓库：5 条提交、3 个文件，含分支合并。不能外推大型仓库性能。首次应用配置的仓库场景每次有新索引缓存，但测试仓库自身的 .idea 会在样本间保留。", "",
         "| 场景 | 指标 | 裁剪前 | 裁剪后 |", "| --- | --- | --- | --- |"]
for row in rows:
    def format_value(value):
        return f"{value['median']:.1f} [{value['min']:.1f}–{value['max']:.1f}]"
    lines.append(f"| {row['scenario']} | {row['metric']} | {format_value(row['baseline'])} | {format_value(row['current'])} |")
lines.extend(["", f"原始记录：`{args.baseline.resolve()}`、`{args.current.resolve()}`。", ""])
args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
print(args.output.with_suffix(".md"))
