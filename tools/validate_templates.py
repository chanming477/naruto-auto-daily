"""tools.validate_templates — 校验所有 .py 代码中的模板引用完整性。

职责:
    扫描 ``D:\\火影自动日常`` 下所有 .py 文件,提取形如
    ``"<subdir>/<filename>.png"`` 的字符串字面量,作为模板引用,
    然后校验它们能否在 ``resources/templates/actions/`` 下找到对应文件。

    同时检测:
        - 引用了空目录 ``resources/templates/shared/`` 的代码(应改用 ``actions/shared/``)
        - 引用了 ``SharedNode/`` 等老 narutomobile 路径(已归档,不应再用)
        - 模板文件存在但代码里完全没引用(可能是孤儿)

输出:
    三段报告:
        1. MISSING:  引用了但文件不存在(高优先级修复)
        2. ORPHAN:   文件存在但代码里没人引用(可选清理)
        3. SUSPECT:  引用了但路径可疑(老路径/空目录/已归档目录)

用法:
    # 默认扫描整个项目
    python tools/validate_templates.py

    # 指定项目根目录
    python tools/validate_templates.py --project-root D:\\火影自动日常

    # 输出 JSON(给 CI/其他工具用)
    python tools/validate_templates.py --json

退出码:
    0 = 无 MISSING(可继续)
    1 = 有 MISSING(必须修复)
    2 = 参数错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# 模板路径字面量模式: "<dir>/<filename>.png" / '<dir>/<filename>.png'
# 允许字符: 字母/数字/下划线/连字符
TEMPLATE_RE = re.compile(r"""['"](?P<path>[a-zA-Z_][a-zA-Z0-9_/.\-]*\.png)['"]""")

# 可疑路径模式:命中这些的引用视为"应改/应清"
# 注意:模板根目录是 resources/templates/actions/,所以 "shared/" 是合法的子目录,
# 不算 SUSPECT。真正可疑的是:
#   - SharedNode (narutomobile 老目录,模板已归档到 narutomobile_ref/)
#   - 任何引用了 narutomobile_ref/ 下文件的代码(只读参考,不该在生产 pipeline)
DEPRECATED_DIRS = {
    "SharedNode",  # narutomobile 老目录,已归档到 resources/templates/narutomobile_ref/
    "narutomobile_ref",  # 仅供 v1.2 节日参考,生产 pipeline 不应引用
}

# 排除目录:这些目录里的 .py 不扫描
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "_archive",
    "_scratch",
    "_debug",
}


@dataclass
class TemplateRef:
    """单条模板引用。"""

    path: str  # 原始路径字面量,例 "shared/x.png"
    source_file: Path  # 引用所在的 .py
    line_no: int  # 行号(1-indexed)

    def __str__(self) -> str:
        rel = self.source_file.name
        return f"{rel}:{self.line_no}: {self.path!r}"


@dataclass
class ValidationReport:
    """校验结果汇总。"""

    project_root: Path
    templates_root: Path
    missing: list[tuple[TemplateRef, Path]] = field(default_factory=list)
    orphan: list[Path] = field(default_factory=list)
    suspect: list[tuple[TemplateRef, str]] = field(default_factory=list)
    total_refs: int = 0
    total_templates: int = 0

    @property
    def is_ok(self) -> bool:
        return len(self.missing) == 0

    def summary(self) -> str:
        return (
            f"refs={self.total_refs} templates={self.total_templates} "
            f"missing={len(self.missing)} orphan={len(self.orphan)} "
            f"suspect={len(self.suspect)}"
        )


def iter_python_files(project_root: Path) -> Iterable[Path]:
    """遍历项目下所有 .py,排除缓存/虚拟环境。"""
    for path in project_root.rglob("*.py"):
        rel = path.relative_to(project_root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        yield path


def extract_template_refs(py_file: Path) -> list[TemplateRef]:
    """从一个 .py 文件里提取所有模板路径字面量。"""
    refs: list[TemplateRef] = []
    try:
        text = py_file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # GBK 文件(如 docs/项目准备.md)跳过
        return refs
    for line_no, line in enumerate(text.splitlines(), 1):
        for match in TEMPLATE_RE.finditer(line):
            path = match.group("path")
            # 过滤明显的非模板字符串:
            #   - 路径不能以数字开头
            #   - 必须至少有一个 '/' 分隔(subdir/name)
            #   - 子目录不能以 '.' 开头(避免匹配 ./foo.png)
            #   - 不能包含反斜杠(避免匹配 Windows 路径)
            if "\\" in path:
                continue
            if "/" not in path:
                continue
            subdir = path.split("/", 1)[0]
            if subdir.startswith("."):
                continue
            # 排除明显非模板的子目录
            if subdir in {
                "config",
                "docs",
                "tests",
                "tools",
                "tasks",
                "core",
                "device",
                "ui",
                "screenshots",
                "resources",
                "logs",
            }:
                continue
            refs.append(TemplateRef(path=path, source_file=py_file, line_no=line_no))
    return refs


def resolve_template(templates_root: Path, ref_path: str) -> Path:
    """把 "shared/x.png" 解析为绝对路径。"""
    return (templates_root / ref_path).resolve()


def first_segment_is_suspect(ref_path: str) -> str | None:
    """检查 ref_path 的第一段是否在 DEPRECATED_DIRS 里。返回原因或 None。

    注意:模板根目录是 ``resources/templates/actions/``,所以 "shared/" 等子目录是合法的,
    本函数只标记真正过期的目录(如 SharedNode / narutomobile_ref)。
    """
    first = ref_path.split("/", 1)[0]
    if first == "SharedNode":
        return (
            "deprecated directory 'SharedNode' "
            "(narutomobile 老目录,已归档到 resources/templates/narutomobile_ref/)"
        )
    if first == "narutomobile_ref":
        return "deprecated directory 'narutomobile_ref' " "(仅作 v1.2 节日参考,生产 pipeline 不应直接引用)"
    return None


def collect_template_files(templates_root: Path) -> set[Path]:
    """收集 templates_root 下所有 .png 模板文件的相对路径集合。"""
    return {p.relative_to(templates_root) for p in templates_root.rglob("*.png")}


def validate(project_root: Path) -> ValidationReport:
    """执行完整校验。"""
    templates_root = project_root / "resources" / "templates" / "actions"
    report = ValidationReport(
        project_root=project_root,
        templates_root=templates_root,
    )

    # 1. 扫描所有模板引用
    all_refs: list[TemplateRef] = []
    for py_file in iter_python_files(project_root):
        all_refs.extend(extract_template_refs(py_file))
    report.total_refs = len(all_refs)

    # 2. 分类:missing / suspect
    seen_refs: set[str] = set()
    for ref in all_refs:
        seen_refs.add(ref.path)
        suspect_reason = first_segment_is_suspect(ref.path)
        if suspect_reason:
            report.suspect.append((ref, suspect_reason))
        abs_path = resolve_template(templates_root, ref.path)
        if not abs_path.exists():
            report.missing.append((ref, abs_path))

    # 3. orphan:文件存在但没人引用
    # 注意:seen_refs 是路径字符串(str),all_files 是相对路径集合(Path),
    # 必须把 seen_refs 也转成相对路径才能做集合减法,否则 abs vs rel 不等
    all_files = collect_template_files(templates_root)
    report.total_templates = len(all_files)
    seen_paths: set[Path] = {
        Path(ref_path) for ref_path in seen_refs  # 保持与 collect_template_files 一致的相对路径形式
    }
    report.orphan = sorted(all_files - seen_paths)

    return report


# ----- 输出 ----------------------------------------------------------------


def print_human_report(report: ValidationReport) -> None:
    """人类可读的报告输出。"""
    print("=" * 70)
    print(f"Project root : {report.project_root}")
    print(f"Templates    : {report.templates_root}")
    print(f"Summary      : {report.summary()}")
    print("=" * 70)

    if report.missing:
        print(f"\n[MISSING] {len(report.missing)} references point to non-existent files:")
        # 按文件路径分组
        by_path: dict[str, list[TemplateRef]] = defaultdict(list)
        for ref, _ in report.missing:
            by_path[ref.path].append(ref)
        for path in sorted(by_path):
            refs = by_path[path]
            print(f"  - {path!r}  ({len(refs)} 引用)")
            for ref in refs[:3]:
                print(f"      {ref}")
            if len(refs) > 3:
                print(f"      ... +{len(refs) - 3} more")
    else:
        print("\n[MISSING] none — 所有引用的模板文件都存在 ✓")

    if report.suspect:
        print(f"\n[SUSPECT] {len(report.suspect)} references to deprecated/suspect paths:")
        for ref, reason in report.suspect:
            print(f"  - {ref}")
            print(f"      reason: {reason}")

    if report.orphan:
        print(f"\n[ORPHAN] {len(report.orphan)} template files not referenced by any code:")
        # 只显示前 30 个,避免刷屏
        for p in report.orphan[:30]:
            print(f"  - {p.as_posix()}")
        if len(report.orphan) > 30:
            print(f"  ... +{len(report.orphan) - 30} more (use --json 看完整清单)")
    else:
        print("\n[ORPHAN] none — 所有模板文件都被代码引用 ✓")

    print("\n" + "=" * 70)
    if report.is_ok:
        print("✓ PASS — 无 MISSING")
    else:
        print(f"✗ FAIL — {len(report.missing)} MISSING 引用需要修复")
    print("=" * 70)


def print_json_report(report: ValidationReport) -> None:
    """JSON 输出。"""
    data = {
        "summary": report.summary(),
        "is_ok": report.is_ok,
        "missing": [
            {
                "ref": ref.path,
                "expected_file": str(expected),
                "source_file": str(ref.source_file),
                "line": ref.line_no,
            }
            for ref, expected in report.missing
        ],
        "orphan": [p.as_posix() for p in report.orphan],
        "suspect": [
            {
                "ref": ref.path,
                "reason": reason,
                "source_file": str(ref.source_file),
                "line": ref.line_no,
            }
            for ref, reason in report.suspect
        ],
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="校验所有 .py 代码中的模板引用完整性",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path("D:/火影自动日常"),
        help="项目根目录(默认 D:/火影自动日常)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出",
    )
    args = parser.parse_args(argv)

    project_root: Path = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"ERROR: project root not a directory: {project_root}", file=sys.stderr)
        return 2

    report = validate(project_root)
    if args.json:
        print_json_report(report)
    else:
        print_human_report(report)

    return 0 if report.is_ok else 1


if __name__ == "__main__":
    sys.exit(main())
