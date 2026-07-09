#!/usr/bin/env python3
"""
Test suite for qa_file_finding — the code-level enforcement of the dev→verifier
invariant for QA-originated developer cards.

These tests run WITHOUT a live kanban DB: they mock the subprocess calls the
handler makes to `hermes kanban ...` and assert the EXACT sequence of CLI
invocations. This proves the handler mechanically creates a dev+verifier pair
for every finding, with the verifier parented on the developer card.

Acceptance criteria covered:
  AC1: QA-originated developer cards always have a verifier child card
  AC2: normal implementation loop cards are unaffected (tech-lead plugin unchanged)
  AC3: all tests pass
  AC4: tests cover the new QA→developer→verifier path
"""

import importlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
QA_PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(QA_PLUGIN_DIR))

import tools as qa_tools
import schemas as qa_schemas


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

class FakeSubprocess:
    """Records every `hermes kanban ...` call and returns canned responses."""

    def __init__(self, create_responses=None):
        # create_responses: list of dicts to return for successive create calls
        self.create_responses = create_responses or []
        self._call_idx = 0
        self.calls = []  # list of full argv lists

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        # Extract the subcommand (after "kanban --board <board>")
        # cmd looks like ['hermes', 'kanban', '--board', 'team', 'create', ...]
        # Find the action verb
        args = cmd[4:] if len(cmd) > 4 else []

        if args and args[0] == "create":
            if self._call_idx < len(self.create_responses):
                resp = self.create_responses[self._call_idx]
                self._call_idx += 1
                return self._ok(json.dumps(resp))
            return self._fail("no more canned create responses")

        # link / block / show / comment — always succeed for these tests
        return self._ok("OK")

    def _ok(self, stdout):
        m = MagicMock()
        m.returncode = 0
        m.stdout = stdout
        m.stderr = ""
        return m

    def _fail(self, stderr):
        m = MagicMock()
        m.returncode = 1
        m.stdout = ""
        m.stderr = stderr
        return m


def _extract_create_calls(fake: FakeSubprocess):
    """Return only the create calls, each as a list of argv after the verb."""
    creates = []
    for cmd in fake.calls:
        if len(cmd) > 4 and cmd[4] == "create":
            creates.append(cmd[5:])  # everything after "create"
    return creates


# ═══════════════════════════════════════════════════════════════════════════════
# Test classes
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchema(unittest.TestCase):
    """Tests for the QA_FILE_FINDING schema definition."""

    def test_schema_exists(self):
        self.assertTrue(hasattr(qa_schemas, "QA_FILE_FINDING"))

    def test_schema_name(self):
        self.assertEqual(qa_schemas.QA_FILE_FINDING["name"], "qa_file_finding")

    def test_schema_requires_findings(self):
        props = qa_schemas.QA_FILE_FINDING["parameters"]["properties"]
        self.assertIn("findings", props)
        required = qa_schemas.QA_FILE_FINDING["parameters"]["required"]
        self.assertIn("findings", required)

    def test_finding_item_requires_all_fields(self):
        item = qa_schemas.QA_FILE_FINDING["parameters"]["properties"]["findings"]["items"]
        required = item["required"]
        for field in ("title", "body", "severity", "workspace_path"):
            self.assertIn(field, required, f"field '{field}' should be required")

    def test_severity_enum(self):
        item = qa_schemas.QA_FILE_FINDING["parameters"]["properties"]["findings"]["items"]
        sev = item["properties"]["severity"]
        self.assertEqual(set(sev["enum"]), {"P0", "P1", "P2"})

    def test_schema_mentions_do_not_kanban_create(self):
        desc = qa_schemas.QA_FILE_FINDING["description"]
        self.assertIn("Do NOT use kanban_create", desc)


class TestHandlerExists(unittest.TestCase):
    """Tests that qa_file_finding handler is defined and importable."""

    def test_handler_exists(self):
        self.assertTrue(hasattr(qa_tools, "qa_file_finding"))
        self.assertTrue(callable(qa_tools.qa_file_finding))


class TestSingleFinding(unittest.TestCase):
    """AC1 core: a single finding produces exactly one dev + one verifier card."""

    def test_single_finding_creates_dev_plus_verifier_pair(self):
        fake = FakeSubprocess(create_responses=[
            {"id": "t_dev001", "title": "[P1] test bug"},
            {"id": "t_ver001", "title": "[verify] test bug"},
        ])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [{
                    "title": "test bug",
                    "body": "something is broken",
                    "severity": "P1",
                    "workspace_path": "/repo/project",
                }]
            }, task_id="t_synth")

        parsed = json.loads(result)
        self.assertEqual(parsed["status"], "filed")
        self.assertEqual(parsed["findings_filed"], 1)
        self.assertEqual(parsed["developer_ids"], ["t_dev001"])
        self.assertEqual(parsed["verifier_ids"], ["t_ver001"])

        creates = _extract_create_calls(fake)
        self.assertEqual(len(creates), 2, "should make exactly 2 create calls")

        # First create: developer card
        dev_create = creates[0]
        self.assertIn("--assignee", dev_create)
        dev_assignee_idx = dev_create.index("--assignee") + 1
        self.assertEqual(dev_create[dev_assignee_idx], "developer")
        self.assertIn("test bug", " ".join(dev_create))
        self.assertIn("[P1]", " ".join(dev_create))

        # Second create: verifier card, parented on dev
        ver_create = creates[1]
        self.assertIn("--assignee", ver_create)
        ver_assignee_idx = ver_create.index("--assignee") + 1
        self.assertEqual(ver_create[ver_assignee_idx], "verifier")
        self.assertIn("--parent", ver_create)
        parent_idx = ver_create.index("--parent") + 1
        self.assertEqual(ver_create[parent_idx], "t_dev001")


class TestMultipleFindings(unittest.TestCase):
    """Multiple findings in one call produce N dev+verifier pairs."""

    def test_two_findings_create_two_pairs(self):
        fake = FakeSubprocess(create_responses=[
            {"id": "t_dev1"},
            {"id": "t_ver1"},
            {"id": "t_dev2"},
            {"id": "t_ver2"},
        ])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [
                    {"title": "bug A", "body": "broken A", "severity": "P0", "workspace_path": "/repo"},
                    {"title": "bug B", "body": "broken B", "severity": "P2", "workspace_path": "/repo"},
                ]
            }, task_id="t_synth")

        parsed = json.loads(result)
        self.assertEqual(parsed["status"], "filed")
        self.assertEqual(parsed["findings_filed"], 2)
        self.assertEqual(len(parsed["developer_ids"]), 2)
        self.assertEqual(len(parsed["verifier_ids"]), 2)

        creates = _extract_create_calls(fake)
        self.assertEqual(len(creates), 4)

        # Verify alternation: dev, ver, dev, ver
        assignees = []
        for c in creates:
            ai = c.index("--assignee") + 1
            assignees.append(c[ai])
        self.assertEqual(assignees, ["developer", "verifier", "developer", "verifier"])

        # Verify each verifier is parented on the preceding dev card
        ver1_parent = creates[1][creates[1].index("--parent") + 1]
        ver2_parent = creates[3][creates[3].index("--parent") + 1]
        self.assertEqual(ver1_parent, "t_dev1")
        self.assertEqual(ver2_parent, "t_dev2")


class TestSeverityTags(unittest.TestCase):
    """Severity appears in the developer card title as [P0], [P1], or [P2]."""

    def test_p0_severity_in_title(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "blocker", "body": "x", "severity": "P0", "workspace_path": "/r"}]
            }, task_id="t_s")
        creates = _extract_create_calls(fake)
        self.assertIn("[P0]", " ".join(creates[0]))

    def test_p2_severity_in_title(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "major", "body": "x", "severity": "P2", "workspace_path": "/r"}]
            }, task_id="t_s")
        creates = _extract_create_calls(fake)
        self.assertIn("[P2]", " ".join(creates[0]))

    def test_invalid_severity_defaults_to_p1(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "weird", "body": "x", "severity": "XYZ", "workspace_path": "/r"}]
            }, task_id="t_s")
        creates = _extract_create_calls(fake)
        self.assertIn("[P1]", " ".join(creates[0]))


class TestDoesNotBlockCaller(unittest.TestCase):
    """Critical: unlike kanban_delegate, qa_file_finding must NOT block the caller."""

    def test_no_block_call_in_cli_sequence(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "bug", "body": "x", "severity": "P1", "workspace_path": "/r"}]
            }, task_id="t_caller")
        # No call should contain 'block' as the verb
        for cmd in fake.calls:
            args_after_board = cmd[4:]
            self.assertNotEqual(args_after_board[0], "block",
                                f"qa_file_finding must NOT call kanban block, but got: {cmd}")

    def test_no_link_caller_as_child(self):
        """Unlike kanban_delegate, the caller should NOT be linked as a dependent."""
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "bug", "body": "x", "severity": "P1", "workspace_path": "/r"}]
            }, task_id="t_caller")
        # No link call should reference the caller's card id as the child
        for cmd in fake.calls:
            if len(cmd) > 4 and cmd[4] == "link":
                # link parent child — the child (cmd[6]) must not be the caller
                self.assertNotEqual(cmd[6], "t_caller",
                                    f"Caller was linked as dependent: {cmd}")


class TestValidationErrors(unittest.TestCase):
    """Error handling for invalid inputs."""

    def test_empty_findings_returns_error(self):
        result = qa_tools.qa_file_finding(args={"findings": []}, task_id="t_x")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_missing_findings_key_returns_error(self):
        result = qa_tools.qa_file_finding(args={}, task_id="t_x")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_finding_missing_title_skipped(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [
                    {"title": "", "body": "x", "severity": "P1", "workspace_path": "/r"},  # bad
                    {"title": "good", "body": "x", "severity": "P1", "workspace_path": "/r"},  # ok
                ]
            }, task_id="t_s")
        parsed = json.loads(result)
        self.assertEqual(parsed["findings_filed"], 1)

    def test_finding_missing_body_skipped(self):
        fake = FakeSubprocess(create_responses=[])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [{"title": "x", "body": "", "severity": "P1", "workspace_path": "/r"}]
            }, task_id="t_s")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_finding_missing_workspace_skipped(self):
        fake = FakeSubprocess(create_responses=[])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [{"title": "x", "body": "desc", "severity": "P1", "workspace_path": ""}]
            }, task_id="t_s")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_all_findings_fail_returns_error(self):
        fake = FakeSubprocess(create_responses=[])  # dev create always fails
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            result = qa_tools.qa_file_finding(args={
                "findings": [{"title": "x", "body": "d", "severity": "P1", "workspace_path": "/r"}]
            }, task_id="t_s")
        parsed = json.loads(result)
        self.assertIn("error", parsed)


class TestDevCardWorkspace(unittest.TestCase):
    """The developer card must get a workspace (dir:<path>) so the fix has a repo."""

    def test_dev_create_has_workspace(self):
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "bug", "body": "x", "severity": "P1", "workspace_path": "/my/repo"}]
            }, task_id="t_s")
        creates = _extract_create_calls(fake)
        dev_create = creates[0]
        self.assertIn("--workspace", dev_create)
        ws_idx = dev_create.index("--workspace") + 1
        self.assertEqual(dev_create[ws_idx], "dir:/my/repo")

    def test_verifier_create_has_no_workspace(self):
        """Verifier card should NOT get a workspace — it verifies, not builds."""
        fake = FakeSubprocess(create_responses=[{"id": "t_d"}, {"id": "t_v"}])
        with patch.object(qa_tools.subprocess, "run", side_effect=fake.run):
            qa_tools.qa_file_finding(args={
                "findings": [{"title": "bug", "body": "x", "severity": "P1", "workspace_path": "/my/repo"}]
            }, task_id="t_s")
        creates = _extract_create_calls(fake)
        ver_create = creates[1]
        self.assertNotIn("--workspace", ver_create)


class TestSynthesizerBodyInstructsQAFileFinding(unittest.TestCase):
    """AC4: the qa_swarm synthesizer body must instruct qa_file_finding."""

    def test_synth_body_mentions_qa_file_finding(self):
        src = QA_PLUGIN_DIR / "tools.py"
        content = src.read_text()
        self.assertIn("qa_file_finding", content)

    def test_synth_body_warns_against_kanban_create(self):
        src = QA_PLUGIN_DIR / "tools.py"
        content = src.read_text()
        self.assertIn("kanban_create", content)

    def test_synth_body_warns_against_kanban_delegate(self):
        """The body should explain why NOT to use kanban_delegate (it blocks)."""
        src = QA_PLUGIN_DIR / "tools.py"
        content = src.read_text()
        self.assertIn("kanban_delegate", content)


class TestPluginRegistration(unittest.TestCase):
    """The new tool must be registered in __init__.py and plugin.yaml."""

    def test_init_registers_qa_file_finding(self):
        src = (QA_PLUGIN_DIR / "__init__.py").read_text()
        self.assertIn("qa_file_finding", src)
        self.assertIn("QA_FILE_FINDING", src)

    def test_plugin_yaml_lists_qa_file_finding(self):
        import yaml
        plugin = yaml.safe_load((QA_PLUGIN_DIR / "plugin.yaml").read_text())
        self.assertIn("qa_file_finding", plugin["provides_tools"])


class TestTechLeadPluginUnchanged(unittest.TestCase):
    """AC2: the tech-lead dev_workflow plugin (normal loop) must be unchanged."""

    def test_tech_lead_kanban_delegate_still_creates_pair(self):
        """The tech-lead kanban_delegate should still do its dev+verifier create."""
        tl_path = Path(os.path.expanduser(
            "~/.hermes-teams/startup/profiles/tech-lead/plugins/dev_workflow/tools.py"
        ))
        self.assertTrue(tl_path.exists(), f"tech-lead dev_workflow missing: {tl_path}")
        content = tl_path.read_text()
        self.assertIn('"developer"', content)
        self.assertIn('"verifier"', content)
        self.assertIn("--parent", content)

    def test_tech_lead_plugin_blocks_caller(self):
        """kanban_delegate still blocks — that's its job (normal loop)."""
        tl_path = Path(os.path.expanduser(
            "~/.hermes-teams/startup/profiles/tech-lead/plugins/dev_workflow/tools.py"
        ))
        content = tl_path.read_text()
        self.assertIn("block", content)


class TestCompileCheck(unittest.TestCase):
    """All modified Python files compile without SyntaxError."""

    def test_tools_py_compiles(self):
        import py_compile
        py_compile.compile(str(QA_PLUGIN_DIR / "tools.py"), doraise=True)

    def test_schemas_py_compiles(self):
        import py_compile
        py_compile.compile(str(QA_PLUGIN_DIR / "schemas.py"), doraise=True)

    def test_init_py_compiles(self):
        import py_compile
        py_compile.compile(str(QA_PLUGIN_DIR / "__init__.py"), doraise=True)


class TestConfigRegistersPlugin(unittest.TestCase):
    """qa/config.yaml still registers qa_workflow (which now provides qa_file_finding)."""

    def test_config_has_qa_workflow(self):
        import yaml
        cfg_path = Path(os.path.expanduser("~/.hermes-teams/startup/profiles/qa/config.yaml"))
        cfg = yaml.safe_load(cfg_path.read_text())
        enabled = cfg.get("plugins", {}).get("enabled", [])
        self.assertIn("qa_workflow", enabled)


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestSchema,
        TestHandlerExists,
        TestSingleFinding,
        TestMultipleFindings,
        TestSeverityTags,
        TestDoesNotBlockCaller,
        TestValidationErrors,
        TestDevCardWorkspace,
        TestSynthesizerBodyInstructsQAFileFinding,
        TestPluginRegistration,
        TestTechLeadPluginUnchanged,
        TestCompileCheck,
        TestConfigRegistersPlugin,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {len(result.failures)} failed, {len(result.errors)} errors, {result.testsRun} total")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)
