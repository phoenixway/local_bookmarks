from __future__ import annotations

from dataclasses import dataclass, field
import re


THINK_CLASS_INCOMPLETE = "malformed_incomplete_think"
THINK_CLASS_VERBOSE = "malformed_verbose_or_nested_think"
CONTROL_TAGS = ("intent", "subgoal", "fact", "finding", "decision", "path", "progress")
DISALLOWED_INSIDE_THINK_TAGS = ("action", "intent", "subgoal", "fact", "finding", "decision", "path", "progress", "memory_update_done")
READ_ONLY_ACTIONS = {"read_file", "read_chunk", "extract_symbol", "read_file_skeleton", "search_content", "search_files", "list_directory"}
TARGETED_EDIT_ACTIONS = {"edit_file"}


@dataclass
class ThinkValidationResult:
    valid: bool
    error_class: str | None = None
    reasons: list[str] = field(default_factory=list)
    think_text: str = ""


@dataclass
class ThinkRecoveryResult:
    decision: str
    error: str | None = None
    message: str | None = None
    malformed_think_count: int = 0
    malformed_think_class_count: int = 0
    compact_think_required_next_turn: bool = False
    dispatch_action: str | None = None
    diagnostic: dict[str, object] = field(default_factory=dict)


@dataclass
class IntentThinkState:
    malformed_think_count: int = 0
    malformed_think_class_count: dict[str, int] = field(default_factory=dict)
    compact_think_required_next_turn: bool = False


class ThinkGuardRuntime:
    def __init__(self) -> None:
        self._intent_state: dict[str, IntentThinkState] = {}

    def get_state(self, intent_id: str) -> IntentThinkState:
        return self._intent_state.setdefault(intent_id, IntentThinkState())

    def validate_compact_think(self, response_text: str) -> ThinkValidationResult:
        think_match = re.search(r"<think>(.*?)</think>", response_text, re.DOTALL)
        if not think_match:
            return ThinkValidationResult(valid=False, error_class=THINK_CLASS_INCOMPLETE, reasons=["missing_think_block"])

        think_text = think_match.group(1)
        reasons: list[str] = []
        error_class: str | None = None

        if "<think>" in think_text or response_text.count("<think>") != 1 or response_text.count("</think>") != 1:
            reasons.append("nested_think")
            error_class = THINK_CLASS_VERBOSE

        for tag in DISALLOWED_INSIDE_THINK_TAGS:
            if f"<{tag}" in think_text:
                reasons.append(f"{tag}_inside_think")
                error_class = THINK_CLASS_VERBOSE

        if "```" in think_text:
            reasons.append("code_fence_inside_think")
            error_class = THINK_CLASS_VERBOSE

        think_lines = think_text.splitlines()
        if any(re.match(r"^\s*#{1,6}\s+", line) for line in think_lines):
            reasons.append("markdown_heading_inside_think")
            error_class = THINK_CLASS_VERBOSE
        if any(re.match(r"^\s*\d+\.\s+", line) for line in think_lines):
            reasons.append("numbered_plan_inside_think")
            error_class = THINK_CLASS_VERBOSE

        if len(think_text) > 800:
            reasons.append("think_too_long")
            error_class = THINK_CLASS_VERBOSE

        if not all(marker in think_text for marker in ("!", "?", "→")):
            reasons.append("missing_compact_markers")
            if error_class is None:
                error_class = THINK_CLASS_INCOMPLETE

        return ThinkValidationResult(
            valid=not reasons,
            error_class=error_class,
            reasons=reasons,
            think_text=think_text,
        )

    def record_valid_compact_think(self, intent_id: str) -> None:
        state = self.get_state(intent_id)
        state.malformed_think_count = 0
        state.malformed_think_class_count.clear()
        state.compact_think_required_next_turn = False

    def handle_response(
        self,
        *,
        intent_id: str,
        response_text: str,
        allowed_actions: set[str],
        last_valid_tool_evidence: str,
        fresh_exact_evidence_for_edit: bool = False,
    ) -> ThinkRecoveryResult:
        validation = self.validate_compact_think(response_text)
        if validation.valid:
            self.record_valid_compact_think(intent_id)
            return ThinkRecoveryResult(decision="ok")

        state = self.get_state(intent_id)
        state.malformed_think_count += 1
        class_count = state.malformed_think_class_count.get(validation.error_class or THINK_CLASS_INCOMPLETE, 0) + 1
        state.malformed_think_class_count[validation.error_class or THINK_CLASS_INCOMPLETE] = class_count

        if state.malformed_think_count == 1:
            return ThinkRecoveryResult(
                decision="recover",
                error=validation.error_class,
                message="Keep the think block compact and exact.",
                malformed_think_count=state.malformed_think_count,
                malformed_think_class_count=class_count,
            )

        if state.malformed_think_count == 2:
            state.compact_think_required_next_turn = True
            return ThinkRecoveryResult(
                decision="recover",
                error=validation.error_class,
                message="No plans. No explanations. Three lines max.",
                malformed_think_count=state.malformed_think_count,
                malformed_think_class_count=class_count,
                compact_think_required_next_turn=True,
            )

        if state.malformed_think_count == 3:
            return ThinkRecoveryResult(
                decision="recover",
                error=validation.error_class,
                message="<think>\n! ...\n? ...\n→ ...\n</think>\n<memory_update_done />\n<action>...</action>",
                malformed_think_count=state.malformed_think_count,
                malformed_think_class_count=class_count,
                compact_think_required_next_turn=True,
            )

        safe_action = self._extract_safe_action(
            response_text=response_text,
            allowed_actions=allowed_actions,
            fresh_exact_evidence_for_edit=fresh_exact_evidence_for_edit,
        )
        if safe_action is not None:
            return ThinkRecoveryResult(
                decision="dispatch_action_only",
                error=validation.error_class,
                malformed_think_count=state.malformed_think_count,
                malformed_think_class_count=class_count,
                compact_think_required_next_turn=True,
                dispatch_action=safe_action,
            )

        return ThinkRecoveryResult(
            decision="diagnostic_stop",
            error="malformed_think_escalation_exhausted",
            malformed_think_count=state.malformed_think_count,
            malformed_think_class_count=class_count,
            compact_think_required_next_turn=True,
            diagnostic={
                "active_intent_id": intent_id,
                "last_valid_tool_evidence": last_valid_tool_evidence,
                "required_next_safe_action": "Emit one compact think skeleton or one safe allowed action backed by fresh evidence.",
            },
        )

    def _extract_safe_action(
        self,
        *,
        response_text: str,
        allowed_actions: set[str],
        fresh_exact_evidence_for_edit: bool,
    ) -> str | None:
        outside_think = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL)

        if any(f"<{tag}" in outside_think for tag in CONTROL_TAGS):
            return None

        action_matches = re.findall(r"(<action>.*?</action>)", outside_think, flags=re.DOTALL)
        if len(action_matches) != 1:
            return None

        action_block = action_matches[0]
        name_match = re.search(r'"type"\s*:\s*"([^"]+)"', action_block)
        if not name_match:
            return None
        action_name = name_match.group(1)
        if action_name not in allowed_actions:
            return None
        if action_name in READ_ONLY_ACTIONS:
            return action_block
        if action_name in TARGETED_EDIT_ACTIONS and fresh_exact_evidence_for_edit:
            return action_block
        return None
