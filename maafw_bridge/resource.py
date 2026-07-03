"""maafw_bridge.resource — 加载 narutomobile resource。

只提供 v2.0 方案 §5.3 要求的最小 API:
    - ``load_narutomobile_resource(resource_path: str) -> maa.resource.Resource``
    - ``verify_resource_path(path) -> (ok, msg)``  — 给 init 时做校验

设计原则:
    - 路径解析交给调用方(tasker.init(cfg) 拿 cfg.app.maafw.narutomobile_resource_path + cfg.project_root 拼)
    - 本模块不做 set/get 路径状态 — 那是 CLI 调试工具的事,不属于核心 API
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

try:
    from maa.resource import Resource  # type: ignore
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("maafw 未安装,先跑: pip install maafw==5.10.4") from exc


def verify_resource_path(path: str | Path) -> tuple[bool, str]:
    """校验 resource 路径合法(必须含 pipeline/merged.json + image/)。

    Args:
        path: 资源路径,绝对或相对都行(调用方负责 resolve)。

    Returns:
        (ok, message) 元组。
    """
    p = Path(path)
    if not p.exists():
        return False, f"resource 目录不存在: {p}"
    if not p.is_dir():
        return False, f"resource 不是目录: {p}"
    merged = p / "pipeline" / "merged.json"
    if not merged.exists():
        return False, f"缺少 pipeline/merged.json: {merged}"
    image_dir = p / "image"
    if not image_dir.exists():
        return False, f"缺少 image/ 目录: {image_dir}"
    return True, str(p)


def load_narutomobile_resource(resource_path: str) -> Resource:
    """加载 narutomobile resource 目录,返回 ``maa.resource.Resource`` 实例。

    Args:
        resource_path: resource/base 路径字符串(绝对或相对都行,本函数内部 resolve)。

    Returns:
        ``maa.resource.Resource`` 实例(已 post_bundle().wait() 完成)。

    Raises:
        FileNotFoundError: 路径不存在 / 缺 merged.json / 缺 image/。
    """
    path = Path(resource_path).resolve()
    ok, msg = verify_resource_path(path)
    if not ok:
        raise FileNotFoundError(msg)

    n_templates = sum(1 for _ in (path / "image").rglob("*.png"))
    logger.info(
        "loading narutomobile resource: {} ({} templates)",
        path,
        n_templates,
    )

    resource = Resource()
    job = resource.post_bundle(str(path))
    job.wait()
    # maafw 5.10.4 Resource 没有 inited 属性
    logger.success(
        "narutomobile resource loaded: {} ({} templates)",
        path,
        n_templates,
    )
    return resource
