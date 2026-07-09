#!/usr/bin/env python3
"""
Test suite for kanban_chains — the unified parallel-chains + optional synthesis
topology creator.

These tests run WITHOUT a live kanban DB: they mock the subprocess calls the
handler makes to `hermes kanban ...` and assert the EXACT sequence of CLI
invocations. This proves the handler mechanically builds:

  root card (completed)  →  N parallel chains (each sequential)
                           →  optional `after` fan-in tail
                           →  caller linked + blocked (dependency)

Coverage (19 areas):
  1.  Schema definition (KANBAN_CHAINS, name, required fields, step shapes)
  2.  Handler importable
  3.  Simple topology (1 chain, 1 step, no after)
  4.  Multi-chain (2 chains, 1 step each)
  5.  Chain with multiple steps (parenting within a chain)
  6.  After fan-in sequence
  7.  After with multiple steps (parenting within after)
  8.  Container block (image_tag → container setup in body)
  9.  Port allocation (base_port + chain_index)
  10. Idempotency key on root
  11. Block verification (status=todo → blocked)
  12. Block failure (non-todo status → error)
  13. Validation errors
  14. Skill flag (--skill singular)
  15. Workspace flag (--workspace dir:<path>)
  16. Plugin registration (__init__ + plugin.yaml)
  17. Compile check (all .py)
  18. Root card completed after create
  19. Blackboard comment on root with [swarm:blackboard] prefix
"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ── Path setup ────────────────────────────────────────────────────────────────
PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_DIR))

import tools as kc_tools
import schemas as kc_schemas


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

class FakeSubprocess:
    """Records every `hermes kanban ...` call and returns canned responses.

    Handles subcommands: create, complete, comment, link, block, show.
      - create → successive dicts from `create_responses` (JSON, via _run_kanban_json)
      - show   → {"task": {"status": show_status}} (JSON, via _run_kanban_json)
      - others → OK (returncode 0)
    """

    def __init__(self, create_responses=None, show_status="todo"):
        self.create_responses = create_responses or []
        self.show_status = show_status
        self._call_idx = 0
        self.calls = []  # list of full argv lists

    def run(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        # cmd looks like ['hermes', 'kanban', '--board', board, <verb>, ...]
        args = cmd[4:] if len(cmd) > 4 else []

        if args and args[0] == "create":
            if self._call_idx < len(self.create_responses):
                resp = self.create_responses[self._call_idx]
                self._call_idx += 1
                return self._ok(json.dumps(resp))
            return self._fail("no more canned create responses")

        if args and args[0] == "show":
            return self._ok(json.dumps({"task": {"status": self.show_status}}))

        # complete / comment / link / block — always succeed
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


def _extract_create_calls(fake):
    """Return only the create calls, each as a list of argv after the verb."""
    return [cmd[5:] for cmd in fake.calls if len(cmd) > 4 and cmd[4] == "create"]


def _calls_with_verb(fake, verb):
    """Return full cmd lists whose kanban verb is `verb`."""
    return [cmd for cmd in fake.calls if len(cmd) > 4 and cmd[4] == verb]


def _arg_value(args, flag):
    """Return the value following `flag` in an argv list, or None."""
    if flag in args:
        return args[args.index(flag) + 1]
    return None


def _run_handler(args, create_responses, show_status="todo", task_id="t_caller"):
    """Convenience: run kanban_chains against a fresh FakeSubprocess, return (parsed, fake)."""
    fake = FakeSubprocess(create_responses=create_responses, show_status=show_status)
    with patch.object(kc_tools.subprocess, "run", side_effect=fake.run):
        result = kc_tools.kanban_chains(args=args, task_id=task_id)
    return json.loads(result), fake


def _chain_step(assignee="developer", title="do thing", body="build it",
                skill=None, workspace_path=None, priority=None):
    step = {"assignee": assignee, "title": title, "body": body}
    if skill is not None:
        step["skill"] = skill
    if workspace_path is not None:
        step["workspace_path"] = workspace_path
    if priority is not None:
        step["priority"] = priority
    return step


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Schema tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchema(unittest.TestCase):

    def test_schema_exists(self):
        self.assertTrue(hasattr(kc_schemas, "KANBAN_CHAINS"))

    def test_schema_name(self):
        self.assertEqual(kc_schemas.KANBAN_CHAINS["name"], "kanban_chains")

    def test_required_goal_and_chains(self):
        required = kc_schemas.KANBAN_CHAINS["parameters"]["required"]
        self.assertIn("goal", required)
        self.assertIn("chains", required)

    def test_optional_params_present(self):
        props = kc_schemas.KANBAN_CHAINS["parameters"]["properties"]
        for opt in ("after", "blackboard", "idempotency_key"):
            self.assertIn(opt, props)

    def test_chain_step_required_fields(self):
        chain_item = kc_schemas.KANBAN_CHAINS["parameters"]["properties"]["chains"]["items"]
        step = chain_item["items"]
        self.assertEqual(set(step["required"]), {"assignee", "title", "body"})

    def test_chain_step_optional_fields(self):
        step = kc_schemas.KANBAN_CHAINS["parameters"]["properties"]["chains"]["items"]["items"]
        props = step["properties"]
        for opt in ("skill", "workspace_path", "priority"):
            self.assertIn(opt, props)

    def test_after_step_required_fields(self):
        after_item = kc_schemas.KANBAN_CHAINS["parameters"]["properties"]["after"]["items"]
        self.assertEqual(set(after_item["required"]), {"assignee", "title"})

    def test_blackboard_sub_properties(self):
        bb = kc_schemas.KANBAN_CHAINS["parameters"]["properties"]["blackboard"]["properties"]
        for sub in ("image_tag", "container_port", "base_port", "env_facts", "spec_path", "extra"):
            self.assertIn(sub, bb)
        self.assertEqual(bb["container_port"]["default"], 3000)
        self.assertEqual(bb["base_port"]["default"], 18081)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Handler importable
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandlerExists(unittest.TestCase):

    def test_handler_callable(self):
        self.assertTrue(hasattr(kc_tools, "kanban_chains"))
        self.assertTrue(callable(kc_tools.kanban_chains))

    def test_helpers_present(self):
        for name in ("_get_board", "_run_kanban", "_run_kanban_json",
                     "_get_my_card_id", "_validate", "_container_block"):
            self.assertTrue(hasattr(kc_tools, name), f"missing helper {name}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Simple topology (1 chain, 1 step, no after)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimpleTopology(unittest.TestCase):

    def test_single_chain_single_step(self):
        parsed, fake = _run_handler(
            args={"goal": "ship feature", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["root_id"], "t_root")
        self.assertEqual(parsed["chains"], [["t_c0"]])
        self.assertEqual(parsed["after"], [])
        self.assertEqual(parsed["terminal_ids"], ["t_c0"])
        self.assertTrue(parsed["block_verified"])

        creates = _extract_create_calls(fake)
        self.assertEqual(len(creates), 2)  # root + 1 step

        # step parented on root
        self.assertEqual(_arg_value(creates[1], "--parent"), "t_root")

        # caller linked as child of the chain terminal
        links = _calls_with_verb(fake, "link")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][5], "t_c0")      # parent
        self.assertEqual(links[0][6], "t_caller")  # child

        # caller blocked with dependency
        blocks = _calls_with_verb(fake, "block")
        self.assertEqual(len(blocks), 1)
        # block <my_card_id> <reason...> --kind dependency
        block_argv = blocks[0][5:]
        self.assertEqual(block_argv[0], "t_caller")
        self.assertIn("--kind", block_argv)
        self.assertEqual(_arg_value(block_argv, "--kind"), "dependency")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Multi-chain (2 chains, 1 step each)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiChain(unittest.TestCase):

    def test_two_chains_each_one_step(self):
        parsed, fake = _run_handler(
            args={"goal": "parallel work", "chains": [
                [_chain_step(title="A")],
                [_chain_step(title="B")],
            ]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}, {"id": "t_c1"}],
        )
        self.assertEqual(parsed["chains"], [["t_c0"], ["t_c1"]])
        self.assertEqual(parsed["terminal_ids"], ["t_c0", "t_c1"])

        # caller linked to BOTH chain terminals (no after → per-chain link)
        links = _calls_with_verb(fake, "link")
        link_parents = sorted(l[5] for l in links)
        self.assertEqual(link_parents, ["t_c0", "t_c1"])
        for l in links:
            self.assertEqual(l[6], "t_caller")

        # both chain steps parented on root
        creates = _extract_create_calls(fake)
        self.assertEqual(_arg_value(creates[1], "--parent"), "t_root")
        self.assertEqual(_arg_value(creates[2], "--parent"), "t_root")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Chain with multiple steps (intra-chain parenting)
# ═══════════════════════════════════════════════════════════════════════════════

class TestChainMultipleSteps(unittest.TestCase):

    def test_step1_parented_on_step0(self):
        parsed, fake = _run_handler(
            args={"goal": "sequential", "chains": [
                [_chain_step(title="first"), _chain_step(title="second")],
            ]},
            create_responses=[{"id": "t_root"}, {"id": "t_s0"}, {"id": "t_s1"}],
        )
        self.assertEqual(parsed["chains"], [["t_s0", "t_s1"]])
        self.assertEqual(parsed["terminal_ids"], ["t_s1"])

        creates = _extract_create_calls(fake)
        # step[0] → root, step[1] → step[0]
        self.assertEqual(_arg_value(creates[1], "--parent"), "t_root")
        self.assertEqual(_arg_value(creates[2], "--parent"), "t_s0")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. After fan-in sequence
# ═══════════════════════════════════════════════════════════════════════════════

class TestAfterFanIn(unittest.TestCase):

    def test_after_zero_fans_in_from_chain_terminals(self):
        parsed, fake = _run_handler(
            args={
                "goal": "synth after",
                "chains": [
                    [_chain_step(title="A")],
                    [_chain_step(title="B")],
                ],
                "after": [{"assignee": "synth", "title": "merge"}],
            },
            create_responses=[
                {"id": "t_root"}, {"id": "t_c0"}, {"id": "t_c1"}, {"id": "t_a0"},
            ],
        )
        self.assertEqual(parsed["after"], ["t_a0"])
        self.assertEqual(parsed["terminal_ids"], ["t_a0"])

        links = _calls_with_verb(fake, "link")
        # 2 fan-in links (t_c0→t_a0, t_c1→t_a0) + 1 caller link (t_a0→caller)
        self.assertEqual(len(links), 3)
        fan_in = sorted((l[5], l[6]) for l in links if l[6] == "t_a0")
        self.assertEqual(fan_in, [("t_c0", "t_a0"), ("t_c1", "t_a0")])
        caller_links = [l for l in links if l[6] == "t_caller"]
        self.assertEqual(len(caller_links), 1)
        self.assertEqual(caller_links[0][5], "t_a0")

        # after[0] created with NO --parent
        creates = _extract_create_calls(fake)
        after_create = creates[-1]
        self.assertNotIn("--parent", after_create)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. After with multiple steps (intra-after parenting)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAfterMultipleSteps(unittest.TestCase):

    def test_after_step1_parented_on_after_step0(self):
        parsed, fake = _run_handler(
            args={
                "goal": "two-step after",
                "chains": [[_chain_step(title="build")]],
                "after": [
                    {"assignee": "verifier", "title": "verify"},
                    {"assignee": "synth", "title": "report"},
                ],
            },
            create_responses=[
                {"id": "t_root"}, {"id": "t_c0"}, {"id": "t_a0"}, {"id": "t_a1"},
            ],
        )
        self.assertEqual(parsed["after"], ["t_a0", "t_a1"])
        self.assertEqual(parsed["terminal_ids"], ["t_a1"])

        creates = _extract_create_calls(fake)
        # after[0] (creates[2]) no parent; after[1] (creates[3]) parented on after[0]
        self.assertNotIn("--parent", creates[2])
        self.assertEqual(_arg_value(creates[3], "--parent"), "t_a0")

        # caller linked to last after step only
        links = _calls_with_verb(fake, "link")
        caller_links = [l for l in links if l[6] == "t_caller"]
        self.assertEqual(len(caller_links), 1)
        self.assertEqual(caller_links[0][5], "t_a1")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Container block (image_tag → container setup in body)
# ═══════════════════════════════════════════════════════════════════════════════

class TestContainerBlock(unittest.TestCase):

    def test_first_step_gets_container_setup(self):
        parsed, fake = _run_handler(
            args={
                "goal": "containerized chains",
                "chains": [[_chain_step(title="worker")]],
                "blackboard": {"image_tag": "qa-test:latest", "container_port": 3000},
            },
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        creates = _extract_create_calls(fake)
        chain_body = _arg_value(creates[1], "--body")
        self.assertIn("## Container", chain_body)
        self.assertIn("qa-test:latest", chain_body)
        self.assertIn("podman run -d", chain_body)


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Port allocation (base_port + chain_index)
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortAllocation(unittest.TestCase):

    def test_three_chains_get_distinct_ports(self):
        parsed, fake = _run_handler(
            args={
                "goal": "port fan-out",
                "chains": [
                    [_chain_step(title="c0")],
                    [_chain_step(title="c1")],
                    [_chain_step(title="c2")],
                ],
                "blackboard": {"image_tag": "img:1"},
            },
            create_responses=[
                {"id": "t_root"}, {"id": "t_c0"}, {"id": "t_c1"}, {"id": "t_c2"},
            ],
        )
        creates = _extract_create_calls(fake)
        ports = []
        for c in creates[1:]:  # skip root
            body = _arg_value(c, "--body")
            self.assertIn("Port: ", body)
            ports.append(_after(body, "Port: "))
        # base_port default 18081 → 18081, 18082, 18083
        self.assertEqual(ports, ["18081", "18082", "18083"])

        # worker names should be qa-worker-1, qa-worker-2, qa-worker-3
        workers = []
        for c in creates[1:]:
            body = _arg_value(c, "--body")
            workers.append(_after(body, "qa-worker-"))
        self.assertEqual(workers, ["1", "2", "3"])

    def test_custom_base_port(self):
        parsed, fake = _run_handler(
            args={
                "goal": "custom port",
                "chains": [[_chain_step(title="c0")], [_chain_step(title="c1")]],
                "blackboard": {"image_tag": "img:1", "base_port": 20000},
            },
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}, {"id": "t_c1"}],
        )
        creates = _extract_create_calls(fake)
        body0 = _arg_value(creates[1], "--body")
        body1 = _arg_value(creates[2], "--body")
        self.assertIn("Port: 20000", body0)
        self.assertIn("Port: 20001", body1)


def _after(text, marker):
    """Return the trailing token in `text` that immediately follows `marker`."""
    idx = text.index(marker) + len(marker)
    rest = text[idx:]
    return rest.split()[0] if rest.split() else ""


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Idempotency key on root
# ═══════════════════════════════════════════════════════════════════════════════

class TestIdempotencyKey(unittest.TestCase):

    def test_key_passed_to_root_create(self):
        parsed, fake = _run_handler(
            args={
                "goal": "dedup me",
                "chains": [[_chain_step()]],
                "idempotency_key": "run-42",
            },
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        creates = _extract_create_calls(fake)
        root_create = creates[0]
        self.assertIn("--idempotency-key", root_create)
        self.assertEqual(_arg_value(root_create, "--idempotency-key"), "run-42")

    def test_no_key_means_no_flag(self):
        parsed, fake = _run_handler(
            args={"goal": "no key", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        creates = _extract_create_calls(fake)
        self.assertNotIn("--idempotency-key", creates[0])


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Block verification (status=todo → blocked)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockVerification(unittest.TestCase):

    def test_block_verified_returns_blocked(self):
        parsed, fake = _run_handler(
            args={"goal": "block ok", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
            show_status="todo",
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertTrue(parsed["block_verified"])

        # a show call was made on the caller
        shows = _calls_with_verb(fake, "show")
        self.assertEqual(len(shows), 1)
        self.assertEqual(shows[0][5], "t_caller")


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Block failure (non-todo status → error)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockFailure(unittest.TestCase):

    def test_non_todo_status_returns_error(self):
        parsed, fake = _run_handler(
            args={"goal": "block fail", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
            show_status="running",
        )
        self.assertIn("error", parsed)
        self.assertFalse(parsed.get("block_verified", False))
        self.assertIn("running", parsed["error"])


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Validation errors
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidationErrors(unittest.TestCase):

    def _expect_error(self, args):
        # validation happens before any subprocess call
        fake = FakeSubprocess(create_responses=[])
        with patch.object(kc_tools.subprocess, "run", side_effect=fake.run):
            result = kc_tools.kanban_chains(args=args, task_id="t_caller")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertEqual(fake.calls, [], "validation must not call kanban")

    def test_missing_goal(self):
        self._expect_error({"chains": [[_chain_step()]]})

    def test_empty_goal(self):
        self._expect_error({"goal": "   ", "chains": [[_chain_step()]]})

    def test_missing_chains(self):
        self._expect_error({"goal": "x"})

    def test_empty_chains_list(self):
        self._expect_error({"goal": "x", "chains": []})

    def test_empty_inner_chain(self):
        self._expect_error({"goal": "x", "chains": [[]]})

    def test_step_missing_assignee(self):
        step = {"title": "t", "body": "b"}
        self._expect_error({"goal": "x", "chains": [[step]]})

    def test_step_missing_title(self):
        step = {"assignee": "dev", "body": "b"}
        self._expect_error({"goal": "x", "chains": [[step]]})

    def test_step_missing_body(self):
        step = {"assignee": "dev", "title": "t"}
        self._expect_error({"goal": "x", "chains": [[step]]})

    def test_after_step_missing_assignee(self):
        # chains valid, but after step invalid → still an error (caught in _validate)
        self._expect_error({
            "goal": "x",
            "chains": [[_chain_step()]],
            "after": [{"title": "no assignee"}],
        })


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Skill flag (--skill singular)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSkillFlag(unittest.TestCase):

    def test_skill_is_singular_flag(self):
        parsed, fake = _run_handler(
            args={"goal": "skilled", "chains": [[_chain_step(skill="tdd")]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        creates = _extract_create_calls(fake)
        chain_create = creates[1]
        self.assertIn("--skill", chain_create)
        self.assertEqual(_arg_value(chain_create, "--skill"), "tdd")
        # MUST be singular, not --skills
        self.assertNotIn("--skills", chain_create)


# ═══════════════════════════════════════════════════════════════════════════════
# 15. Workspace flag (--workspace dir:<path>)
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkspaceFlag(unittest.TestCase):

    def test_workspace_dir_form(self):
        parsed, fake = _run_handler(
            args={"goal": "ws", "chains": [[_chain_step(workspace_path="/repo/app")]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        creates = _extract_create_calls(fake)
        chain_create = creates[1]
        self.assertIn("--workspace", chain_create)
        self.assertEqual(_arg_value(chain_create, "--workspace"), "dir:/repo/app")


# ═══════════════════════════════════════════════════════════════════════════════
# 16. Plugin registration
# ═══════════════════════════════════════════════════════════════════════════════

class TestPluginRegistration(unittest.TestCase):

    def test_init_registers_kanban_chains(self):
        src = (PLUGIN_DIR / "__init__.py").read_text()
        self.assertIn("kanban_chains", src)
        self.assertIn("KANBAN_CHAINS", src)

    def test_plugin_yaml_lists_kanban_chains(self):
        src = (PLUGIN_DIR / "plugin.yaml").read_text()
        self.assertRegex(src, r"name:\s*kanban_chains")
        self.assertIn("- kanban_chains", src)


# ═══════════════════════════════════════════════════════════════════════════════
# 17. Compile check
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompileCheck(unittest.TestCase):

    def test_tools_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "tools.py"), doraise=True)

    def test_schemas_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "schemas.py"), doraise=True)

    def test_init_py_compiles(self):
        import py_compile
        py_compile.compile(str(PLUGIN_DIR / "__init__.py"), doraise=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 18. Root card completed after create
# ═══════════════════════════════════════════════════════════════════════════════

class TestRootCompleted(unittest.TestCase):

    def test_complete_called_on_root(self):
        parsed, fake = _run_handler(
            args={"goal": "complete root", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        completes = _calls_with_verb(fake, "complete")
        self.assertEqual(len(completes), 1)
        # complete <root_id> --result ...
        self.assertEqual(completes[0][5], "t_root")
        self.assertIn("--result", completes[0][5:])


# ═══════════════════════════════════════════════════════════════════════════════
# 19. Blackboard comment on root with [swarm:blackboard] prefix
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlackboardComment(unittest.TestCase):

    def test_comment_made_when_blackboard_provided(self):
        parsed, fake = _run_handler(
            args={
                "goal": "shared ctx",
                "chains": [[_chain_step()]],
                "blackboard": {"image_tag": "img:1", "env_facts": "node 20"},
            },
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        comments = _calls_with_verb(fake, "comment")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0][5], "t_root")
        payload_text = comments[0][6]
        self.assertTrue(payload_text.startswith("[swarm:blackboard]"))

    def test_no_comment_when_no_blackboard(self):
        parsed, fake = _run_handler(
            args={"goal": "no bb", "chains": [[_chain_step()]]},
            create_responses=[{"id": "t_root"}, {"id": "t_c0"}],
        )
        comments = _calls_with_verb(fake, "comment")
        self.assertEqual(comments, [])


# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestSchema,                   # 1
        TestHandlerExists,            # 2
        TestSimpleTopology,           # 3
        TestMultiChain,               # 4
        TestChainMultipleSteps,       # 5
        TestAfterFanIn,               # 6
        TestAfterMultipleSteps,       # 7
        TestContainerBlock,           # 8
        TestPortAllocation,           # 9
        TestIdempotencyKey,           # 10
        TestBlockVerification,        # 11
        TestBlockFailure,             # 12
        TestValidationErrors,         # 13
        TestSkillFlag,                # 14
        TestWorkspaceFlag,            # 15
        TestPluginRegistration,       # 16
        TestCompileCheck,             # 17
        TestRootCompleted,            # 18
        TestBlackboardComment,        # 19
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    passed = result.testsRun - len(result.failures) - len(result.errors)
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {len(result.failures)} failed, "
          f"{len(result.errors)} errors, {result.testsRun} total")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)
