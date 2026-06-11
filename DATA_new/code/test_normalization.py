"""
测试脚本：验证无向边规范化和覆盖真实性增强
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "official_pipeline"))

from gap_pipeline.coverage_tracker import (
    CoverageTracker,
    _l1_key_normalized,
    _l2_key_normalized,
)


def test_normalization_functions():
    print("=" * 60)
    print("Test 1: Normalization Functions")
    print("=" * 60)

    assert _l1_key_normalized("a", "b") == "a->b"
    assert _l1_key_normalized("b", "a") == "a->b"
    print("[PASS] L1 normalization test passed")

    assert _l2_key_normalized("a", "b", "c") == "a->b->c"
    assert _l2_key_normalized("c", "b", "a") == "a->b->c"
    print("[PASS] L2 normalization test passed")
    print()


def main():
    print("\nStarting test: Undirected edge normalization\n")

    try:
        test_normalization_functions()
        print("[SUCCESS] All tests passed!")
    except Exception as e:
        print(f"[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
