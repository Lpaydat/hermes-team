#!/usr/bin/env python3
"""
Test suite for kanban_chains — the unified parallel-chains + optional synthesis
topology creator.

These tests run WITHOUT a live kanban DB: they mock the kanban_db module that
the handler imports via _kb(), and assert the EXACT sequence of API calls.
This proves the handler mechanically builds:

  root card (completed)  ->  N parallel chains (each sequential)
                           ->  optional `after` fan-in tail
                           ->  caller linked + blocked (dependency)

Coverage (19 areas):
  1.  Schema definition (KANBAN_CHAINS, name, required fields, step shapes)
  2.  Handler importable + helpers present
  3.  Simple topology (1 chain, 1 step, no after)
  4.  Multi-chain (2 chains, 1 step each)
  5.  Chain with multiple steps (parenting within a chain)
  6.  After fan-in sequence
  7.  After with multiple steps (parenting within after)
  8.  Container block (image_tag -> container setup in body)
  9.  Port allocation (base_port + chain_index)
  10. Block success (block_task returns True -> status=blocked)
  11. Block failure (block_task returns False -> error)
  12. Validation errors
  13. Skill flag (skills= in create_task)
  14. Workspace flag (workspace_path= in create_task)
  15. Plugin registration (__init__ + plugin.yaml)
  16. Compile check (all .py)
  17. Root card completed after create
  18. Blackboard comment on root with [swarm:blackboard] prefix
  19. Regression: port string coercion (int() fix)
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# -- Path setup -----------------------------------------------------------------
PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_DIR))

import tools as kc_tools
import schemas as kc_schemas


# =============================================================================
# Mock kanban_db
# =============================================================================

class FakeKanbanDB:
    """Records every kanban_db API call and returns canned responses.

    Methods mocked: connect_closing (ctx mgr), create_task, add_comment,
    complete_task, link_tasks, block_task.

    create_task returns successive IDs from `create_ids`.
    block_task returns `block_result` (True/False).
    """

    def __init__(self, create_ids=None, block_result=True):
        self.create_ids = create_ids or []
        self.block_result = block_result
        self._create_idx = 0
        self.calls = []  # list of (method_name, args_tuple, kwargs_dict)

    # -- context manager for connect_closing --

    def connect_closing(self, board=None):
        self.calls.append(("connect_closing", (), {"board": board}))
        return self

    def __enter__(self):
        return "fake_conn"

    def __exit__(self, *args):
        return False

    # -- kanban_db API methods --

    def create_task(self, conn, title=None, body=None, assignee=None,
                    created_by=None, parents=None, skills=None,
                    workspace_path=None, priority=0):
        kwargs = {
            "title": title,
            "body": body,
            "assignee": assignee,
            "created_by": created_by,
            "parents": parents,
            "skills": skills,
            "workspace_path": workspace_path,
            "priority": priority,
        }
        self.calls.append(("create_task", (conn,), kwargs))
        if self._create_idx < len(self.create_ids):
            tid = self.create_ids[self._create_idx]
            self._create_idx += 1
            return tid
        return f"t_fallback_{self._create_idx}"

    def add_comment(self, conn, task_id, author, text):
        self.calls.append(("add_comment", (conn, task_id, author, text), {}))

    def complete_task(self, conn, task_id, summary=None, metadata=None):
        self.calls.append(("complete_task", (conn, task_id),
                           {"summary": summary, "metadata": metadata}))

    def link_tasks(self, conn, parent_id, child_id):
        self.calls.append(("link_tasks", (conn, parent_id, child_id), {}))

    def block_task(self, conn, task_id, reason=None, kind=None,
                   expected_run_id=None):
        self.calls.append(("block_task", (conn, task_id),
                           {"reason": reason, "kind": kind,
                            "expected_run_id": expected_run_id}))
        return self.block_result


# =============================================================================
# Test helpers
# =============================================================================

def _create_calls(fake):
    """Return list of kwargs dicts for every create_task call."""
    return [kw for (method, _, kw) in fake.calls if method == "create_task"]


def _calls(fake, method_name):
    """Return list of (args, kwargs) for every call matching method_name."""
    return [(args, kw) for (m, args, kw) in fake.calls if m == method_name]


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


def _run_handler(args, create_ids, block_result=True, task_id="t_caller"):
    """Convenience: run kanban_chains with a FakeKanbanDB, return (parsed, fake)."""
    fake = FakeKanbanDB(create_ids=create_ids, block_result=block_result)
    with patch.object(kc_tools, "_kb", return_value=fake):
        result = kc_tools.kanban_chains(args=args, task_id=task_id)
    return json.loads(result), fake


# =============================================================================
# 1. Schema tests
# =============================================================================

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
        for opt in ("after", "blackboard"):
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


# =============================================================================
# 2. Handler importable + helpers present
# =============================================================================

class TestHandlerExists(unittest.TestCase):

    def test_handler_callable(self):
        self.assertTrue(hasattr(kc_tools, "kanban_chains"))
        self.assertTrue(callable(kc_tools.kanban_chains))

    def test_helpers_present(self):
        for name in ("_board", "_kb", "_run_id", "_my_card_id",
                     "_author", "_validate", "_container_section"):
            self.assertTrue(hasattr(kc_tools, name), f"missing helper {name}")


# =============================================================================
# 3. Simple topology (1 chain, 1 step, no after)
# =============================================================================

class TestSimpleTopology(unittest.TestCase):

    def test_single_chain_single_step(self):
        parsed, fake = _run_handler(
            args={"goal": "ship feature", "chains": [[_chain_step()]]},
            create_ids=["t_root", "t_c0"],
        )
        self.assertEqual(parsed["status"], "blocked")
        self.assertEqual(parsed["root_id"], "t_root")
        self.assertEqual(parsed["chains"], [["t_c0"]])
        self.assertEqual(parsed.get("after", []), [])
        self.assertEqual(parsed["terminal_ids"], ["t_c0"])

        creates = _create_calls(fake)
        self.assertEqual(len(creates), 2)  # root + 1 step

        # step parented on root
        self.assertEqual(creates[1]["parents"], ["t_root"])

        # caller linked as child of the chain terminal
        links = _calls(fake, "link_tasks")
        self.assertEqual(len(links), 1)
        link_args = links[0][0]
        self.assertEqual(link_args[1], "t_c0")      # parent
        self.assertEqual(link_args[2], "t_caller")  # child

        # caller blocked with dependency
        blocks = _calls(fake, "block_task")
        self.assertEqual(len(blocks), 1)
        block_kw = blocks[0][1]
        self.assertEqual(block_kw["kind"], "dependency")
        self.assertIn("t_c0", block_kw["reason"])


# =============================================================================
# 4. Multi-chain (2 chains, 1 step each)
# =============================================================================

class TestMultiChain(unittest.TestCase):

    def test_two_chains_each_one_step(self):
        parsed, fake = _run_handler(
            args={"goal": "parallel work", "chains": [
                [_chain_step(title="A")],
                [_chain_step(title="B")],
            ]},
            create_ids=["t_root", "t_c0", "t_c1"],
        )
        self.assertEqual(parsed["chains"], [["t_c0"], ["t_c1"]])
        self.assertEqual(parsed["terminal_ids"], ["t_c0", "t_c1"])

        # caller linked to BOTH chain terminals
        links = _calls(fake, "link_tasks")
        link_parents = sorted(l[0][1] for l in links)
        self.assertEqual(link_parents, ["t_c0", "t_c1"])
        for l in links:
            self.assertEqual(l[0][2], "t_caller")

        # both chain steps parented on root
        creates = _create_calls(fake)
        self.assertEqual(creates[1]["parents"], ["t_root"])
        self.assertEqual(creates[2]["parents"], ["t_root"])


# =============================================================================
# 5. Chain with multiple steps (intra-chain parenting)
# =============================================================================

class TestChainMultipleSteps(unittest.TestCase):

    def test_step1_parented_on_step0(self):
        parsed, fake = _run_handler(
            args={"goal": "sequential", "chains": [
                [_chain_step(title="first"), _chain_step(title="second")],
            ]},
            create_ids=["t_root", "t_s0", "t_s1"],
        )
        self.assertEqual(parsed["chains"], [["t_s0", "t_s1"]])
        self.assertEqual(parsed["terminal_ids"], ["t_s1"])

        creates = _create_calls(fake)
        # step[0] -> root, step[1] -> step[0]
        self.assertEqual(creates[1]["parents"], ["t_root"])
        self.assertEqual(creates[2]["parents"], ["t_s0"])


# =============================================================================
# 6. After fan-in sequence
# =============================================================================

class TestAfterFanIn(unittest.TestCase):

    def test_after_step0_fans_in_from_chain_terminals(self):
        parsed, fake = _run_handler(
            args={
                "goal": "synth after",
                "chains": [
                    [_chain_step(title="A")],
                    [_chain_step(title="B")],
                ],
                "after": [{"assignee": "synth", "title": "merge"}],
            },
            create_ids=["t_root", "t_c0", "t_c1", "t_a0"],
        )
        self.assertEqual(parsed["after"], ["t_a0"])
        self.assertEqual(parsed["terminal_ids"], ["t_a0"])

        creates = _create_calls(fake)
        # after[0] parented on ALL chain terminals via parents=
        self.assertEqual(creates[3]["parents"], ["t_c0", "t_c1"])

        # caller linked to the after terminal only
        links = _calls(fake, "link_tasks")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0][1], "t_a0")
        self.assertEqual(links[0][0][2], "t_caller")


# =============================================================================
# 7. After with multiple steps (intra-after parenting)
# =============================================================================

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
            create_ids=["t_root", "t_c0", "t_a0", "t_a1"],
        )
        self.assertEqual(parsed["after"], ["t_a0", "t_a1"])
        self.assertEqual(parsed["terminal_ids"], ["t_a1"])

        creates = _create_calls(fake)
        # after[0] (creates[2]) parented on chain terminals; after[1] parented on after[0]
        self.assertEqual(creates[2]["parents"], ["t_c0"])
        self.assertEqual(creates[3]["parents"], ["t_a0"])

        # caller linked to last after step only
        links = _calls(fake, "link_tasks")
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0][0][1], "t_a1")
        self.assertEqual(links[0][0][2], "t_caller")


# =============================================================================
# 8. Container block (image_tag -> container setup in body)
# =============================================================================

class TestContainerBlock(unittest.TestCase):

    def test_first_step_gets_container_setup(self):
        parsed, fake = _run_handler(
            args={
                "goal": "containerized chains",
                "chains": [[_chain_step(title="worker")]],
                "blackboard": {"image_tag": "qa-test:latest", "container_port": 3000},
            },
            create_ids=["t_root", "t_c0"],
        )
        creates = _create_calls(fake)
        chain_body = creates[1]["body"]
        self.assertIn("## Container", chain_body)
        self.assertIn("qa-test:latest", chain_body)
        self.assertIn("podman run -d", chain_body)


# =============================================================================
# 9. Port allocation (base_port + chain_index)
# =============================================================================

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
            create_ids=["t_root", "t_c0", "t_c1", "t_c2"],
        )
        creates = _create_calls(fake)
        ports = []
        workers = []
        for c in creates[1:]:  # skip root
            body = c["body"]
            self.assertIn("Port: ", body)
            ports.append(_after(body, "Port: "))
            workers.append(_after(body, "qa-worker-"))
        # base_port default 18081 -> 18081, 18082, 18083
        self.assertEqual(ports, ["18081", "18082", "18083"])
        self.assertEqual(workers, ["1", "2", "3"])

    def test_custom_base_port(self):
        parsed, fake = _run_handler(
            args={
                "goal": "custom port",
                "chains": [[_chain_step(title="c0")], [_chain_step(title="c1")]],
                "blackboard": {"image_tag": "img:1", "base_port": 20000},
            },
            create_ids=["t_root", "t_c0", "t_c1"],
        )
        creates = _create_calls(fake)
        self.assertIn("Port: 20000", creates[1]["body"])
        self.assertIn("Port: 20001", creates[2]["body"])


def _after(text, marker):
    """Return the trailing token in `text` that immediately follows `marker`."""
    idx = text.index(marker) + len(marker)
    rest = text[idx:]
    return rest.split()[0] if rest.split() else ""


# =============================================================================
# 10. Block success (block_task returns True -> status=blocked)
# =============================================================================

class TestBlockSuccess(unittest.TestCase):

    def test_block_ok_returns_blocked(self):
        parsed, fake = _run_handler(
            args={"goal": "block ok", "chains": [[_chain_step()]]},
            create_ids=["t_root", "t_c0"],
            block_result=True,
        )
        self.assertEqual(parsed["status"], "blocked")

        blocks = _calls(fake, "block_task")
        self.assertEqual(len(blocks), 1)
        block_args = blocks[0][0]
        self.assertEqual(block_args[1], "t_caller")
        self.assertEqual(blocks[0][1]["kind"], "dependency")


# =============================================================================
# 11. Block failure (block_task returns False -> error)
# =============================================================================

class TestBlockFailure(unittest.TestCase):

    def test_block_fail_returns_error(self):
        parsed, fake = _run_handler(
            args={"goal": "block fail", "chains": [[_chain_step()]]},
            create_ids=["t_root", "t_c0"],
            block_result=False,
        )
        self.assertIn("error", parsed)
        self.assertIn("Block failed", parsed["error"])
        # Cards were still created
        self.assertEqual(parsed["root_id"], "t_root")


# =============================================================================
# 12. Validation errors
# =============================================================================

class TestValidationErrors(unittest.TestCase):

    def _expect_error(self, args):
        fake = FakeKanbanDB(create_ids=[])
        with patch.object(kc_tools, "_kb", return_value=fake):
            result = kc_tools.kanban_chains(args=args, task_id="t_caller")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        # validation must not call any kanban_db method
        actual_kb_calls = [c for c in fake.calls if c[0] != "connect_closing"]
        # connect_closing shouldn't be called either since validation returns early
        self.assertEqual(fake.calls, [], "validation must not call kanban_db at all")

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
        self._expect_error({
            "goal": "x",
            "chains": [[_chain_step()]],
            "after": [{"title": "no assignee"}],
        })


# =============================================================================
# 13. Skill flag (skills= in create_task)
# =============================================================================

class TestSkillFlag(unittest.TestCase):

    def test_skill_passed_as_list(self):
        parsed, fake = _run_handler(
            args={"goal": "skilled", "chains": [[_chain_step(skill="tdd")]]},
            create_ids=["t_root", "t_c0"],
        )
        creates = _create_calls(fake)
        chain_create = creates[1]
        self.assertEqual(chain_create["skills"], ["tdd"])


# =============================================================================
# 14. Workspace flag (workspace_path= in create_task)
# =============================================================================

class TestWorkspaceFlag(unittest.TestCase):

    def test_workspace_path_passed(self):
        parsed, fake = _run_handler(
            args={"goal": "ws", "chains": [[_chain_step(workspace_path="/repo/app")]]},
            create_ids=["t_root", "t_c0"],
        )
        creates = _create_calls(fake)
        chain_create = creates[1]
        self.assertEqual(chain_create["workspace_path"], "/repo/app")


# =============================================================================
# 15. Plugin registration
# =============================================================================

class TestPluginRegistration(unittest.TestCase):

    def test_init_registers_kanban_chains(self):
        src = (PLUGIN_DIR / "__init__.py").read_text()
        self.assertIn("kanban_chains", src)
        self.assertIn("KANBAN_CHAINS", src)

    def test_plugin_yaml_lists_kanban_chains(self):
        src = (PLUGIN_DIR / "plugin.yaml").read_text()
        self.assertRegex(src, r"name:\s*kanban_chains")
        self.assertIn("- kanban_chains", src)


# =============================================================================
# 16. Compile check
# =============================================================================

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


# =============================================================================
# 17. Root card completed after create
# =============================================================================

class TestRootCompleted(unittest.TestCase):

    def test_complete_called_on_root(self):
        parsed, fake = _run_handler(
            args={"goal": "complete root", "chains": [[_chain_step()]]},
            create_ids=["t_root", "t_c0"],
        )
        completes = _calls(fake, "complete_task")
        self.assertEqual(len(completes), 1)
        # complete_task(conn, "t_root", ...)
        self.assertEqual(completes[0][0][1], "t_root")
        self.assertEqual(completes[0][1]["summary"],
                         "Chains topology planned; root remains the shared blackboard.")


# =============================================================================
# 18. Blackboard comment on root with [swarm:blackboard] prefix
# =============================================================================

class TestBlackboardComment(unittest.TestCase):

    def test_comment_made_when_blackboard_provided(self):
        parsed, fake = _run_handler(
            args={
                "goal": "shared ctx",
                "chains": [[_chain_step()]],
                "blackboard": {"image_tag": "img:1", "env_facts": "node 20"},
            },
            create_ids=["t_root", "t_c0"],
        )
        comments = _calls(fake, "add_comment")
        self.assertEqual(len(comments), 1)
        # add_comment(conn, "t_root", author, text)
        comment_args = comments[0][0]
        self.assertEqual(comment_args[1], "t_root")
        payload_text = comment_args[3]
        self.assertTrue(payload_text.startswith("[swarm:blackboard]"))

    def test_no_comment_when_no_blackboard(self):
        parsed, fake = _run_handler(
            args={"goal": "no bb", "chains": [[_chain_step()]]},
            create_ids=["t_root", "t_c0"],
        )
        comments = _calls(fake, "add_comment")
        self.assertEqual(comments, [])


# =============================================================================
# 19. Regression: port string coercion (int() fix)
# =============================================================================

class TestPortAllocationStringCoercion(unittest.TestCase):
    """Regression: base_port/container_port passed as string from LLM caused
    TypeError at port = base_port + ci. Fix: int() coercion before arithmetic."""

    def test_base_port_string_does_not_crash(self):
        parsed, fake = _run_handler(
            args={
                "goal": "string port coercion",
                "chains": [
                    [_chain_step(title="c0")],
                    [_chain_step(title="c1")],
                ],
                "blackboard": {"image_tag": "img:1", "base_port": "18081"},
            },
            create_ids=["t_root", "t_c0", "t_c1"],
        )
        self.assertNotIn("error", parsed, f"Handler crashed on string base_port: {parsed}")
        creates = _create_calls(fake)
        self.assertIn("Port: 18081", creates[1]["body"])
        self.assertIn("Port: 18082", creates[2]["body"])

    def test_container_port_string_does_not_crash(self):
        parsed, fake = _run_handler(
            args={
                "goal": "string container port",
                "chains": [[_chain_step(title="c0")]],
                "blackboard": {"image_tag": "img:1", "container_port": "3000", "base_port": "18081"},
            },
            create_ids=["t_root", "t_c0"],
        )
        self.assertNotIn("error", parsed, f"Handler crashed on string ports: {parsed}")


# =============================================================================
# Runner
# =============================================================================

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
        TestBlockSuccess,             # 10
        TestBlockFailure,             # 11
        TestValidationErrors,         # 12
        TestSkillFlag,                # 13
        TestWorkspaceFlag,            # 14
        TestPluginRegistration,       # 15
        TestCompileCheck,             # 16
        TestRootCompleted,            # 17
        TestBlackboardComment,        # 18
        TestPortAllocationStringCoercion,  # 19
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
