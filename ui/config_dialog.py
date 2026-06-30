"""ui.config_dialog — 配置编辑对话框(Phase 5)。

职责(单一):
    允许用户修改 ``retry.*`` / ``recovery.*`` / ``template_matching.threshold`` 字段,
    保存到 ``config/app_config.yaml``,自动 reload。

设计要点:
    - 数据来源: ConfigManager(Phase 1 资产)
    - **不**修改任务 / 状态机 / ADB / Recovery / Retry 相关配置
    - 字段加载 → 用户编辑 → Pydantic 校验 → 写 yaml → reload
    - 校验失败:显示错误,不让关 dialog(直到用户改对或点取消)

公开 API:
    ConfigDialog(config_manager: ConfigManager, parent=None)
        .result() -> bool   # QDialog 惯例,True = accepted
"""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    from PySide6 import QtCore, QtWidgets
except ImportError as _exc:  # pragma: no cover
    raise ImportError(
        "ui.config_dialog requires PySide6",
    ) from _exc

if TYPE_CHECKING:
    from core.config_manager import ConfigManager


class ConfigDialog(QtWidgets.QDialog):
    """配置编辑对话框。"""

    def __init__(
        self,
        config_manager: "ConfigManager",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cfg = config_manager
        self.setWindowTitle("编辑配置")
        self.setMinimumWidth(400)
        self._build_ui()
        self._load_values()

    # ----- public ----------------------------------------------------

    def result(self) -> bool:
        """QDialog.result() 兼容 — 返 True 表示用户点 OK 且保存成功。"""
        return super().result() == QtWidgets.QDialog.Accepted

    # ----- internals -------------------------------------------------

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        # form layout
        form = QtWidgets.QFormLayout()
        # retry.max_attempts
        self._spin_retry_max = QtWidgets.QSpinBox(self)
        self._spin_retry_max.setRange(1, 20)
        form.addRow("retry.max_attempts:", self._spin_retry_max)
        # retry.delay_seconds
        self._spin_retry_delay = QtWidgets.QDoubleSpinBox(self)
        self._spin_retry_delay.setRange(0.0, 60.0)
        self._spin_retry_delay.setSingleStep(0.1)
        self._spin_retry_delay.setDecimals(2)
        form.addRow("retry.delay_seconds:", self._spin_retry_delay)
        # recovery.max_unknown_retries
        self._spin_recovery_unknown = QtWidgets.QSpinBox(self)
        self._spin_recovery_unknown.setRange(1, 20)
        form.addRow("recovery.max_unknown_retries:", self._spin_recovery_unknown)
        # recovery.max_popup_retries
        self._spin_recovery_popup = QtWidgets.QSpinBox(self)
        self._spin_recovery_popup.setRange(1, 20)
        form.addRow("recovery.max_popup_retries:", self._spin_recovery_popup)
        # template_matching.threshold
        self._spin_tmpl_threshold = QtWidgets.QDoubleSpinBox(self)
        self._spin_tmpl_threshold.setRange(0.0, 1.0)
        self._spin_tmpl_threshold.setSingleStep(0.01)
        self._spin_tmpl_threshold.setDecimals(3)
        form.addRow("template_matching.threshold:", self._spin_tmpl_threshold)
        layout.addLayout(form)
        # 错误信息
        self._lbl_error = QtWidgets.QLabel("", self)
        self._lbl_error.setStyleSheet("color: #c0392b;")
        self._lbl_error.setWordWrap(True)
        layout.addWidget(self._lbl_error)
        # 按钮
        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_values(self) -> None:
        """从 ConfigManager 加载当前值。"""
        r = self._cfg.app.retry
        self._spin_retry_max.setValue(int(r.max_attempts))
        self._spin_retry_delay.setValue(float(r.delay_seconds))
        rec = self._cfg.app.recovery
        self._spin_recovery_unknown.setValue(int(rec.max_unknown_retries))
        self._spin_recovery_popup.setValue(int(rec.max_popup_retries))
        tm = self._cfg.app.template_matching
        self._spin_tmpl_threshold.setValue(float(tm.default_threshold))

    def _on_accept(self) -> None:
        """点 OK:校验 + 写 yaml + reload。"""
        new_retry_max = int(self._spin_retry_max.value())
        new_retry_delay = float(self._spin_retry_delay.value())
        new_recovery_unknown = int(self._spin_recovery_unknown.value())
        new_recovery_popup = int(self._spin_recovery_popup.value())
        new_tmpl_threshold = float(self._spin_tmpl_threshold.value())
        # P1-QUAL-01: 用 self._cfg.app(公开 property)而非 self._cfg._app(私有)
        # Pydantic v2 允许 mutate;ConfigManager.app 是 property 代理 self._app
        try:
            app = self._cfg.app
            app.retry.max_attempts = new_retry_max
            app.retry.delay_seconds = new_retry_delay
            app.recovery.max_unknown_retries = new_recovery_unknown
            app.recovery.max_popup_retries = new_recovery_popup
            app.template_matching.default_threshold = new_tmpl_threshold
        except Exception as exc:
            self._lbl_error.setText(f"配置值非法: {exc}")
            return
        # 写回 yaml(用 ConfigManager 自带 save_default_configs 行为)
        try:
            self._save_yaml()
        except Exception as exc:
            self._lbl_error.setText(f"保存失败: {exc}")
            return
        # reload
        try:
            self._cfg.reload()
        except Exception as exc:
            self._lbl_error.setText(f"reload 失败: {exc}")
            return
        self.accept()

    def _save_yaml(self) -> None:
        """把 cfg 写回 app_config.yaml。

        P0-STABLE-02 修复: 旧版 ``self._cfg._app is None → return`` 是静默失败,
        用户的修改会丢失但不报错。改为 ``ConfigError`` 明确抛出。
        P1-QUAL-01: 用 ``self._cfg.app`` 公开 property。
        """
        import yaml

        from core.config_manager import ConfigurationError

        # Pydantic model validation:重新走一次校验,失败直接抛
        try:
            app = self._cfg.app  # 触发 _load (如果未加载)
        except ConfigurationError as exc:
            raise ConfigurationError(
                f"config validation failed before save: {exc}",
            ) from exc
        if app is None:
            # 不应该发生(ConfigManager.app property 不返 None),但保险起见显式抛
            raise ConfigurationError(
                "ConfigManager.app returned None unexpectedly; "
                "config not loaded?",
            )
        path = self._cfg.config_dir / "app_config.yaml"
        payload = app.model_dump(mode="json")
        try:
            path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ConfigurationError(
                f"failed to write {path}: {exc}",
            ) from exc
