"""用户提供的直接 maafw snippet (跳过 Navigator) — 验证 group pipeline。"""
from maa.toolkit import Toolkit
from maa.controller import AdbController
from maa.resource import Resource
from maa.tasker import Tasker

Toolkit.init_option("./maafw_data", {"logging": True})
dev = Toolkit.find_adb_devices()[0]
controller = AdbController(adb_path=dev.adb_path, address=dev.address,
    screencap_methods=dev.screencap_methods,
    input_methods=dev.input_methods, config=dev.config)
controller.post_connection().wait()

resource = Resource()
resource.post_bundle(r"D:\自动日常源码带\MaaAutoNaruto-win-x86_64-v1.3.35\resource\base").wait()

tasker = Tasker()
tasker.bind(resource, controller)

import time
start = time.time()
detail = tasker.post_task("group").wait().get()
elapsed = time.time() - start

print(f"\n[RESULT] direct maafw group:")
print(f"  elapsed: {elapsed:.2f}s")
print(f"  status: {detail.status}")
print(f"  status.succeeded: {getattr(detail.status, 'succeeded', '?')}")
print(f"  status.done: {getattr(detail.status, 'done', '?')}")
print(f"  status.failed: {getattr(detail.status, 'failed', '?')}")