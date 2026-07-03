"""测试 _parse_custom_action_param 修复。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maafw_bridge.custom_actions import _parse_custom_action_param


class FakeArgv:
    pass


# Case 1: dict
a1 = FakeArgv()
a1.custom_action_param = {"start_x": 100, "start_y": 200}
r1 = _parse_custom_action_param(a1)
assert r1 == {"start_x": 100, "start_y": 200}, f"case1 fail: {r1}"
print("[OK] case1: dict input")

# Case 2: JSON string
a2 = FakeArgv()
a2.custom_action_param = '{"start_x": 100, "start_y": 200}'
r2 = _parse_custom_action_param(a2)
assert r2 == {"start_x": 100, "start_y": 200}, f"case2 fail: {r2}"
print("[OK] case2: JSON string input")

# Case 3: None
a3 = FakeArgv()
a3.custom_action_param = None
r3 = _parse_custom_action_param(a3)
assert r3 == {}, f"case3 fail: {r3}"
print("[OK] case3: None input")

# Case 4: invalid JSON
a4 = FakeArgv()
a4.custom_action_param = "not json"
r4 = _parse_custom_action_param(a4)
assert r4 == {}, f"case4 fail: {r4}"
print("[OK] case4: invalid JSON input")

# Case 5: nested dict
a5 = FakeArgv()
a5.custom_action_param = {"entry_name": ["秘境探险", "秋境探险"]}
r5 = _parse_custom_action_param(a5)
assert r5 == {"entry_name": ["秘境探险", "秋境探险"]}, f"case5 fail: {r5}"
print("[OK] case5: nested dict")

print("[OK] all 5 _parse_custom_action_param cases pass")
