from runtime_think_guards import THINK_CLASS_VERBOSE, ThinkGuardRuntime


def test_second_verbose_failure_sets_compact_required_next_turn() -> None:
    runtime = ThinkGuardRuntime()
    response = "<think>\n# Plan\n1. Do this\n</think>\n<memory_update_done />"

    first = runtime.handle_response(
        intent_id="intent-1",
        response_text=response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )
    second = runtime.handle_response(
        intent_id="intent-1",
        response_text=response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )

    assert first.decision == "recover"
    assert second.compact_think_required_next_turn is True
    assert second.message == "No plans. No explanations. Three lines max."


def test_third_failure_returns_strict_skeleton_recovery() -> None:
    runtime = ThinkGuardRuntime()
    response = "<think>\n# Plan\n1. Do this\n</think>\n<memory_update_done />"

    for _ in range(2):
        runtime.handle_response(
            intent_id="intent-2",
            response_text=response,
            allowed_actions={"read_file"},
            last_valid_tool_evidence="read_file path.kt:10-20",
        )

    third = runtime.handle_response(
        intent_id="intent-2",
        response_text=response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )

    assert third.decision == "recover"
    assert "<think>" in (third.message or "")
    assert "<action>...</action>" in (third.message or "")


def test_fourth_failure_stops_with_diagnostic() -> None:
    runtime = ThinkGuardRuntime()
    response = "<think>\n# Plan\n1. Do this\n</think>\n<memory_update_done />"

    for _ in range(3):
        runtime.handle_response(
            intent_id="intent-3",
            response_text=response,
            allowed_actions={"read_file"},
            last_valid_tool_evidence="read_file path.kt:10-20",
        )

    fourth = runtime.handle_response(
        intent_id="intent-3",
        response_text=response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )

    assert fourth.decision == "diagnostic_stop"
    assert fourth.error == "malformed_think_escalation_exhausted"
    assert fourth.diagnostic["active_intent_id"] == "intent-3"


def test_valid_compact_think_clears_counter() -> None:
    runtime = ThinkGuardRuntime()
    bad_response = "<think>\n# Plan\n1. Do this\n</think>\n<memory_update_done />"
    valid_response = "<think>\n! Exact path known.\n? Need current block.\n→ read_file.\n</think>\n<memory_update_done />"

    runtime.handle_response(
        intent_id="intent-4",
        response_text=bad_response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )
    ok = runtime.handle_response(
        intent_id="intent-4",
        response_text=valid_response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )

    state = runtime.get_state("intent-4")
    assert ok.decision == "ok"
    assert state.malformed_think_count == 0
    assert state.compact_think_required_next_turn is False
    assert state.malformed_think_class_count == {}


def test_durable_tags_inside_think_are_invalid() -> None:
    runtime = ThinkGuardRuntime()
    response = "<think>\n! Path known.\n<fact scope=\"intent\">x</fact>\n? Need read.\n→ read_file.\n</think>\n<memory_update_done />"

    result = runtime.handle_response(
        intent_id="intent-5",
        response_text=response,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="read_file path.kt:10-20",
    )

    assert result.error == THINK_CLASS_VERBOSE


def test_fourth_failure_can_dispatch_single_safe_action_only() -> None:
    runtime = ThinkGuardRuntime()
    malformed = (
        "<think>\n# Plan\n1. Do this\n</think>\n"
        "<memory_update_done />\n"
        "<action>{\"type\":\"read_file\",\"path\":\"A.kt\"}</action>"
    )

    for _ in range(3):
        runtime.handle_response(
            intent_id="intent-6",
            response_text=malformed,
            allowed_actions={"read_file"},
            last_valid_tool_evidence="extract_symbol A.kt:10-30",
        )

    fourth = runtime.handle_response(
        intent_id="intent-6",
        response_text=malformed,
        allowed_actions={"read_file"},
        last_valid_tool_evidence="extract_symbol A.kt:10-30",
    )

    assert fourth.decision == "dispatch_action_only"
    assert fourth.dispatch_action is not None
