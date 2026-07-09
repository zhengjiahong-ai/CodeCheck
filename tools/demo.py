#!/usr/bin/env python3
r"""CodeCheck 机制演示脚本

在 mock LLM 下确定性复现以下行为：
  ① 治理护栏拦截危险动作
  ② 注入失败，反馈闭环使 agent 收到反馈并据此改变下一步动作
  ③ 反馈闭环（重点深度维度）的完整确定性行为

所有演示不依赖网络、不依赖真实 LLM、不依赖真实命令执行。
每次运行结果完全一致。

运行方式：
    python tools/demo.py
"""

import json
import sys
import tempfile
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


# ── 演示 ①：治理护栏拦截危险动作 ──────────────────────────────────────────


def demo_1_guardrail():
    """演示：治理护栏确定性拦截危险操作。

    验证点：
    - read_file → AUTO（自动放行）
    - write_file → CONFIRM（需人工确认）
    - git_push → FORBIDDEN（禁止）
    - unknown_tool → FORBIDDEN（白名单原则，未知工具默认拒绝）
    """
    from codecheck.guardrails.guard import Action, guardrail

    print("=" * 60)
    print("演示 ①：治理护栏拦截危险动作")
    print("=" * 60)

    # 场景 1：读文件 → 自动放行
    r1 = guardrail(Action("read_file", {"path": "src/main.py"}))
    assert r1.allowed and not r1.require_confirm
    print(f"\n✅ read_file:   {r1.reason}")

    # 场景 2：写文件 → 需人工确认
    r2 = guardrail(
        Action("write_file", {"path": "src/main.py", "old_string": "a", "new_string": "b"})
    )
    assert r2.allowed and r2.require_confirm
    print(f"⚠️  write_file:  {r2.reason}")

    # 场景 3：git push → 禁止
    r3 = guardrail(Action("git_push", {"remote": "origin"}))
    assert not r3.allowed
    print(f"❌ git_push:    {r3.reason}")

    # 场景 4：未知工具 → 默认拒绝（白名单原则）
    r4 = guardrail(Action("drop_table", {"table": "users"}))
    assert not r4.allowed
    print(f"❌ drop_table:  {r4.reason}")

    print()
    print("📋 结论：护栏是确定性代码，移除 LLM 后仍可独立验证。")
    print("   每个 Action 的返回结果每次运行完全一致。")
    print()


# ── 演示 ②：注入失败，反馈闭环使 agent 收到反馈并改变行为 ─────────────────


def demo_2_feedback_with_failure():
    """演示：反馈闭环 —— 注入第一次失败，LLM 收到反馈后调整策略并成功。

    验证点：
    - 第 1 轮：mock LLM 生成修复 → 应用（old_string 不匹配）→ 应用失败 → 重试
    - 第 2 轮：mock LLM 收到失败反馈 → 生成精确匹配的修复 → 测试通过 → 固定
    """
    from codecheck.feedback.loop import FeedbackLoop
    from codecheck.llm.mock_provider import MockProvider, MockRule

    print("=" * 60)
    print("演示 ②：反馈闭环 —— 注入失败 → 收到反馈 → 调整策略")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "app.py"
        test_file.write_text("import os\napi_key = 'sk-abc123'\n")

        # 构造 mock LLM 规则链：
        # 第 1 轮：返回故意错误的 old_string（不匹配文件内容）
        # 第 2 轮：收到反馈后返回精确匹配的 old_string
        mock_llm = MockProvider([
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "api_key = 'sk-wrong-key'",  # 故意写错，不匹配
                    "new_string": "api_key = os.getenv('API_KEY')",
                    "explanation": "第 1 次尝试：old_string 错误，无法匹配",
                }),
                consume=True,
            ),
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "api_key = 'sk-abc123'",  # 精确匹配
                    "new_string": "api_key = os.getenv('API_KEY')",
                    "explanation": "第 2 次尝试：收到反馈后调整，精确匹配",
                }),
                consume=True,
            ),
            MockRule(
                keyword=None,
                response_content=json.dumps({"old_string": "", "new_string": "", "explanation": "fallback"}),
                consume=False,
            ),
        ])

        issue = {
            "rule_id": "no-hardcoded-secret",
            "file": str(test_file),
            "line": 2,
            "severity": "critical",
            "message": "禁止硬编码密钥",
        }

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="echo 'all tests passed'",
            lint_command="echo 'no lint errors'",
        )

        report = loop.process([issue])

        fix = report.fixes[0]
        print(f"\n  问题: {fix.issue_id}")
        print(f"  最终状态: {fix.status}")
        print(f"  尝试次数: {fix.attempts}")
        print(f"  尝试详情:")
        for a in fix.attempts_detail:
            icon = "✅" if a.success else "❌"
            print(f"    {icon} 第 {a.round} 轮: {a.diff}")
            if a.failure_reason:
                print(f"       失败原因: {a.failure_reason}")

        if fix.status == "fixed" and fix.attempts > 1:
            print(f"\n📋 结论：第 1 轮修复失败（old_string 不匹配）→ 失败原因反馈给 LLM")
            print(f"   → 第 2 轮 LLM 调整策略，使用精确 old_string → 修复成功。")
            print(f"   整个反馈闭环（备份→应用→验证→回滚→重试）是确定性代码，")
            print(f"   LLM 只负责生成修复文本。")
        elif fix.status == "fixed":
            print(f"\n📋 结论：修复在第 1 轮即成功。")
            print(f"   整个反馈闭环（备份→应用→验证→回滚→重试）是确定性代码。")
        else:
            print(f"\n  注意：修复状态为 '{fix.status}'（{fix.attempts} 次尝试）")
        print()


# ── 演示 ③：反馈闭环（重点维度）的完整确定性行为 ──────────────────────────


def demo_3_full_feedback_loop():
    """演示：反馈闭环的完整确定性行为。

    验证点：
    - 问题 1（print）：修复成功 → 标记 fixed
    - 问题 2（eval）：3 轮修复全部失败（old_string 都不匹配）→ 标记 needs_manual
    - 每个环节都是确定性代码
    """
    from codecheck.feedback.loop import FeedbackLoop
    from codecheck.llm.mock_provider import MockProvider, MockRule

    print("=" * 60)
    print("演示 ③：反馈闭环 — 完整确定性行为（重点深度维度）")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "main.py"
        test_file.write_text("def foo():\n    print('debug')\n    x = eval('1+1')\n")

        # 构造 mock LLM 规则链：
        # 规则 1：print 修复（精确匹配）→ 成功
        # 规则 2-4：eval 修复（3 轮，old_string 全部故意写错，均不匹配）→ 3 轮后 needs_manual
        # 规则 5：兜底
        mock_llm = MockProvider([
            # 问题 1：print → 修复成功
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "    print('debug')",
                    "new_string": "    logging.debug('debug')",
                    "explanation": "替换 print 为 logging（精确匹配）",
                }),
                consume=True,
            ),
            # 问题 2：eval → 第 1 轮（old_string 故意写错，不匹配）
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "eval('wrong')",  # 故意写错
                    "new_string": "2",
                    "explanation": "第 1 次尝试修复 eval（old_string 错误）",
                }),
                consume=True,
            ),
            # 问题 2：eval → 第 2 轮（old_string 还是错的）
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "x = eval('wrong')",  # 故意写错
                    "new_string": "x = 2",
                    "explanation": "第 2 次尝试修复 eval（old_string 仍错误）",
                }),
                consume=True,
            ),
            # 问题 2：eval → 第 3 轮（old_string 仍然错误）
            MockRule(
                keyword=None,
                response_content=json.dumps({
                    "old_string": "x = eval('still-wrong')",  # 还是错的
                    "new_string": "x = int(1+1)",
                    "explanation": "第 3 次尝试修复 eval（old_string 依然错误）",
                }),
                consume=True,
            ),
            # 兜底
            MockRule(
                keyword=None,
                response_content=json.dumps({"old_string": "", "new_string": "", "explanation": "fallback"}),
                consume=False,
            ),
        ])

        issues = [
            {
                "rule_id": "no-debug-print",
                "file": str(test_file),
                "line": 2,
                "severity": "warning",
                "message": "生产代码中应移除调试用的 print()",
            },
            {
                "rule_id": "dangerous-eval",
                "file": str(test_file),
                "line": 3,
                "severity": "critical",
                "message": "禁止使用 eval()",
            },
        ]

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="echo 'tests passed'",
            lint_command="echo 'lint passed'",
        )

        report = loop.process(issues)

        print(f"\n  总问题数: {report.total_issues}")
        print(f"  已修复:   {report.fixed}")
        print(f"  需人工:   {report.needs_manual}")
        print(f"  已跳过:   {report.skipped}")
        print(f"\n  明细:")
        for fix in report.fixes:
            icon = {"fixed": "✅", "needs_manual": "⚠️", "failed": "❌", "skipped": "○"}.get(
                fix.status, "?"
            )
            print(f"    {icon} {fix.issue_id}")
            print(f"       状态: {fix.status}, 尝试次数: {fix.attempts}")
            for a in fix.attempts_detail:
                f_icon = "✅" if a.success else "❌"
                print(f"       - 第 {a.round} 轮: {f_icon} {a.diff[:80]}")
                if a.failure_reason:
                    print(f"         失败原因: {a.failure_reason}")

        print()
        print("📋 结论：反馈闭环的每个环节都是确定性代码，")
        print("   移除 LLM 后仍可独立验证：")
        print("   1. 备份文件（backup）→ 确定性")
        print("   2. 应用修复（write_file）→ 确定性")
        print("   3. 运行测试/验证（verifier）→ 确定性")
        print("   4. 回滚文件（restore）→ 确定性")
        print("   5. 失败信息回灌（feedback context）→ 确定性")
        print("   6. 收敛判断（max_rounds / needs_manual）→ 确定性")
        print("   LLM 只负责第 0 步：生成修复文本。其余全部是代码。")
        print()


# ── 主入口 ───────────────────────────────────────────────────────────────────


def main():
    """运行全部三个机制演示。"""
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║       CodeCheck 机制演示（Mock LLM 确定性复现）         ║")
    print("║                                                        ║")
    print("║  所有演示不依赖网络、真实 LLM、真实命令执行。           ║")
    print("║  每次运行结果完全一致。                                 ║")
    print("╚══════════════════════════════════════════════════════════╝")

    all_passed = True

    try:
        demo_1_guardrail()
    except Exception as e:
        print(f"❌ 演示 ① 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    try:
        demo_2_feedback_with_failure()
    except Exception as e:
        print(f"❌ 演示 ② 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    try:
        demo_3_full_feedback_loop()
    except Exception as e:
        print(f"❌ 演示 ③ 失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("=" * 60)
    if all_passed:
        print("✅ 全部三个演示完成。")
        print("   这证明了 CodeCheck 的 harness 机制是确定性代码，")
        print("   移除 LLM 后仍可独立验证。")
    else:
        print("❌ 部分演示失败，请检查错误信息。")
    print("=" * 60)
    print()

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())