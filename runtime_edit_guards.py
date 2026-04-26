from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
import hashlib
import time
from typing import Iterable


RELEVANT_NEARBY_LINE_DISTANCE = 12
REPEAT_THRESHOLD_FOR_HANDOFF = 3
WRITE_ACTIONS = {"edit_file", "write_file", "write_file_block", "append_file_block"}
IMPORT_AFFECTING_ACTIONS = {"edit_file", "write_file", "write_file_block", "append_file_block"}


def _normalize_line(line: str) -> str:
    return line.strip()


def _normalized_non_empty_lines(text: str) -> list[str]:
    return [_normalize_line(line) for line in text.splitlines() if _normalize_line(line)]


def _hash_text(text: str) -> str:
    normalized = "\n".join(_normalized_non_empty_lines(text))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _unique_preserve_order(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result


def _extract_added_lines(search_text: str, replace_text: str) -> list[str]:
    search_lines = search_text.splitlines()
    replace_lines = replace_text.splitlines()
    matcher = SequenceMatcher(a=search_lines, b=replace_lines)
    added: list[str] = []
    for opcode, _, _, j1, j2 in matcher.get_opcodes():
        if opcode in {"insert", "replace"}:
            added.extend(replace_lines[j1:j2])
    return [line for line in added if _normalize_line(line)]


@dataclass(frozen=True)
class EditFingerprint:
    path: str
    added_lines: tuple[str, ...]
    search_text_hash: str
    replace_text_hash: str
    step: int
    timestamp: float


@dataclass
class ReadSnapshot:
    version: int
    block_hash: str


@dataclass
class GuardResult:
    decision: str
    reason: str | None = None
    message: str | None = None
    normalized_content: str | None = None
    normalized_replace_text: str | None = None
    normalized_imports: bool = False
    terminal: bool = False
    diagnostics: dict[str, object] = field(default_factory=dict)


def ensure_kotlin_imports(path: str, content: str, imports: Iterable[str]) -> GuardResult:
    if not path.endswith(".kt"):
        return GuardResult(decision="ok", normalized_content=content)

    normalized_result = normalize_kotlin_file_content(content)
    if normalized_result.reason == "kotlin_import_after_declaration":
        return normalized_result

    package_line, existing_imports, body_lines = _split_kotlin_file(normalized_result.normalized_content or content)
    requested_imports = {
        _normalize_line(import_line)
        for import_line in imports
        if _normalize_line(import_line)
    }
    merged_imports = sorted(set(existing_imports).union(requested_imports))
    updated_content = _build_kotlin_file(package_line, merged_imports, body_lines)
    changed = updated_content != content
    return GuardResult(
        decision="normalized" if changed else "no_op",
        reason=None if changed else "already_applied_edit",
        message=None if changed else "All requested imports are already present.",
        normalized_content=updated_content,
        normalized_imports=changed,
    )


def normalize_kotlin_file_content(content: str) -> GuardResult:
    package_line, imports, body_lines = _split_kotlin_file(content)
    if _has_import_after_declaration(body_lines):
        return GuardResult(
            decision="blocked",
            reason="kotlin_import_after_declaration",
            message="Import lines appear after Kotlin declarations.",
        )

    unique_imports = _unique_preserve_order(imports)
    unique_imports.sort()
    normalized = _build_kotlin_file(package_line, unique_imports, body_lines)
    changed = normalized != content
    return GuardResult(
        decision="normalized" if changed else "ok",
        normalized_content=normalized,
        normalized_imports=changed,
    )


def _split_kotlin_file(content: str) -> tuple[str | None, list[str], list[str]]:
    lines = content.splitlines()
    package_line: str | None = None
    imports: list[str] = []
    body_start = 0

    index = 0
    while index < len(lines) and not _normalize_line(lines[index]):
        index += 1

    if index < len(lines) and _normalize_line(lines[index]).startswith("package "):
        package_line = _normalize_line(lines[index])
        index += 1

    while index < len(lines) and not _normalize_line(lines[index]):
        index += 1

    import_start = index
    while index < len(lines) and _normalize_line(lines[index]).startswith("import "):
        imports.append(_normalize_line(lines[index]))
        index += 1
    if imports:
        body_start = index
    else:
        body_start = import_start

    body_lines = lines[body_start:]
    while body_lines and not _normalize_line(body_lines[0]):
        body_lines = body_lines[1:]
    return package_line, imports, body_lines


def _build_kotlin_file(package_line: str | None, imports: list[str], body_lines: list[str]) -> str:
    chunks: list[str] = []
    if package_line:
        chunks.append(package_line)
    if imports:
        if chunks:
            chunks.append("")
        chunks.extend(imports)
    trimmed_body = list(body_lines)
    while trimmed_body and not _normalize_line(trimmed_body[0]):
        trimmed_body = trimmed_body[1:]
    if trimmed_body:
        if chunks:
            chunks.append("")
        chunks.extend(trimmed_body)
    if not chunks:
        return ""
    return "\n".join(chunks) + "\n"


def _has_import_after_declaration(body_lines: list[str]) -> bool:
    seen_declaration = False
    for line in body_lines:
        normalized = _normalize_line(line)
        if not normalized:
            continue
        if normalized.startswith("import "):
            if seen_declaration:
                return True
            continue
        seen_declaration = True
    return False


class EditGuardRuntime:
    def __init__(self) -> None:
        self._step = 0
        self._file_versions: dict[str, int] = {}
        self._read_snapshots: dict[str, ReadSnapshot] = {}
        self._successful_insertions: dict[str, list[EditFingerprint]] = {}
        self._duplicate_attempt_counts: dict[tuple[str, tuple[str, ...]], int] = {}
        self._needs_fresh_read: set[str] = set()

    def record_read(self, path: str, content: str) -> None:
        version = self._file_versions.get(path, 0)
        self._read_snapshots[path] = ReadSnapshot(version=version, block_hash=_hash_text(content))
        self._needs_fresh_read.discard(path)

    def record_success(
        self,
        *,
        action: str,
        path: str,
        search_text: str = "",
        replace_text: str = "",
        added_lines: Iterable[str] | None = None,
    ) -> None:
        self._step += 1
        self._file_versions[path] = self._file_versions.get(path, 0) + 1
        self._read_snapshots.pop(path, None)
        self._needs_fresh_read.add(path)

        if action != "edit_file":
            return

        normalized_added_lines = tuple(_normalized_non_empty_lines("\n".join(added_lines or [])))
        if not normalized_added_lines:
            return

        fingerprint = EditFingerprint(
            path=path,
            added_lines=normalized_added_lines,
            search_text_hash=_hash_text(search_text),
            replace_text_hash=_hash_text(replace_text),
            step=self._step,
            timestamp=time.time(),
        )
        self._successful_insertions.setdefault(path, []).append(fingerprint)
        self._duplicate_attempt_counts[(path, normalized_added_lines)] = 0

    def prepare_edit_file(
        self,
        *,
        path: str,
        file_content: str,
        search_text: str,
        replace_text: str,
        fresh_read_performed: bool = False,
    ) -> GuardResult:
        return self._prepare_write_like_action(
            action="edit_file",
            path=path,
            file_content=file_content,
            search_text=search_text,
            replace_text=replace_text,
            fresh_read_performed=fresh_read_performed,
        )

    def prepare_write(
        self,
        *,
        action: str,
        path: str,
        file_content: str,
    ) -> GuardResult:
        return self._prepare_write_like_action(
            action=action,
            path=path,
            file_content=file_content,
            search_text="",
            replace_text=file_content,
            fresh_read_performed=True,
        )

    def _prepare_write_like_action(
        self,
        *,
        action: str,
        path: str,
        file_content: str,
        search_text: str,
        replace_text: str,
        fresh_read_performed: bool,
    ) -> GuardResult:
        if action not in WRITE_ACTIONS:
            return GuardResult(decision="ok")

        if action == "edit_file":
            stale_result = self._require_fresh_read(path, file_content, fresh_read_performed)
            if stale_result is not None:
                return stale_result

        added_lines = _extract_added_lines(search_text, replace_text) if action == "edit_file" else []
        normalized_added_lines = tuple(_normalized_non_empty_lines("\n".join(added_lines)))

        repeated_result = None
        if normalized_added_lines:
            repeated_result = self._detect_repeated_successful_insertion(
                path=path,
                added_lines=normalized_added_lines,
                fresh_read_performed=fresh_read_performed,
                file_content=file_content,
            )
            if repeated_result is not None:
                return repeated_result

        if path.endswith(".kt") and action in IMPORT_AFFECTING_ACTIONS:
            import_result = self._handle_kotlin_imports(
                action=action,
                path=path,
                file_content=file_content,
                search_text=search_text,
                replace_text=replace_text,
            )
            if import_result is not None:
                return import_result

        if normalized_added_lines and self._added_lines_already_exist(file_content, search_text, normalized_added_lines):
            return GuardResult(
                decision="blocked",
                reason="already_applied_edit",
                message="These lines already exist in the file. Do not add them again. Read the current block or continue with the next change.",
            )

        return GuardResult(decision="ok")

    def _require_fresh_read(
        self,
        path: str,
        file_content: str,
        fresh_read_performed: bool,
    ) -> GuardResult | None:
        snapshot = self._read_snapshots.get(path)
        if path in self._needs_fresh_read:
            if not fresh_read_performed:
                return GuardResult(
                    decision="blocked",
                    reason="fresh_read_required",
                    message="Read the current target block before another edit on this file.",
                )
            self.record_read(path, file_content)
            snapshot = self._read_snapshots.get(path)
        if snapshot is None:
            return None
        current_version = self._file_versions.get(path, 0)
        if snapshot.version != current_version:
            if not fresh_read_performed:
                return GuardResult(
                    decision="blocked",
                    reason="fresh_read_required",
                    message="Read the current target block before another edit on this file.",
                )
            self.record_read(path, file_content)
        return None

    def _detect_repeated_successful_insertion(
        self,
        *,
        path: str,
        added_lines: tuple[str, ...],
        fresh_read_performed: bool,
        file_content: str,
    ) -> GuardResult | None:
        previous = self._successful_insertions.get(path, [])
        matching = [item for item in previous if item.added_lines == added_lines]
        if not matching:
            return None

        if fresh_read_performed and not self._all_lines_present(file_content, added_lines):
            return None

        key = (path, added_lines)
        attempt_count = self._duplicate_attempt_counts.get(key, 0) + 1
        self._duplicate_attempt_counts[key] = attempt_count

        latest = matching[-1]
        if attempt_count >= REPEAT_THRESHOLD_FOR_HANDOFF:
            return GuardResult(
                decision="blocked",
                reason="terminal_duplicate_insertion_handoff",
                message="This edit appears to repeat a previous successful insertion on the same file. Read the current target block before attempting another edit.",
                terminal=True,
                diagnostics={
                    "path": path,
                    "duplicated_lines": list(added_lines),
                    "previous_successful_edit_step": latest.step,
                    "recommended_actions": [
                        "run git diff",
                        "normalize imports",
                        "read current import block",
                        "continue with next missing semantic change",
                    ],
                },
            )

        return GuardResult(
            decision="blocked",
            reason="repeated_successful_insertion",
            message="This edit appears to repeat a previous successful insertion on the same file. The previous edit already changed the file. Read the current target block before attempting another edit.",
            diagnostics={"path": path, "previous_successful_edit_step": latest.step},
        )

    def _handle_kotlin_imports(
        self,
        *,
        action: str,
        path: str,
        file_content: str,
        search_text: str,
        replace_text: str,
    ) -> GuardResult | None:
        if action == "edit_file":
            added_lines = _extract_added_lines(search_text, replace_text)
            added_imports = [_normalize_line(line) for line in added_lines if _normalize_line(line).startswith("import ")]
            if not added_imports:
                return None

            package_line, existing_imports, _ = _split_kotlin_file(file_content)
            _ = package_line
            existing_set = set(existing_imports)
            existing_added = [item for item in added_imports if item in existing_set]
            missing_added = [item for item in added_imports if item not in existing_set]

            if existing_added and not missing_added:
                return GuardResult(
                    decision="blocked",
                    reason="duplicate_kotlin_imports_detected",
                    message=f"The requested import lines already exist in `{path.split('/')[-1]}`.\nDo not add them again.\nContinue with the next missing code change, or read the exact block if you are unsure.",
                )

            if missing_added:
                final_content = file_content.replace(search_text, replace_text, 1)
                normalized = normalize_kotlin_file_content(final_content)
                if normalized.reason == "kotlin_import_after_declaration":
                    return normalized
                if normalized.normalized_content is None:
                    return None
                if normalized.normalized_content == file_content:
                    return GuardResult(
                        decision="blocked",
                        reason="duplicate_kotlin_imports_detected",
                        message=f"The requested import lines already exist in `{path.split('/')[-1]}`.\nDo not add them again.\nContinue with the next missing code change, or read the exact block if you are unsure.",
                    )
                return GuardResult(
                    decision="normalized",
                    normalized_replace_text=normalized.normalized_content,
                    normalized_imports=True,
                    message="Kotlin imports were auto-normalized to avoid duplicates.",
                )
            return None

        normalized = normalize_kotlin_file_content(replace_text)
        if normalized.reason == "kotlin_import_after_declaration":
            return normalized
        if normalized.normalized_imports:
            normalized.decision = "normalized"
            normalized.message = "Kotlin imports were auto-normalized to avoid duplicates."
            return normalized
        return None

    def _added_lines_already_exist(
        self,
        file_content: str,
        search_text: str,
        added_lines: tuple[str, ...],
    ) -> bool:
        if not added_lines:
            return False
        if not self._all_lines_present(file_content, added_lines):
            return False

        if not search_text:
            return True

        location = file_content.find(search_text)
        if location < 0:
            return True

        prefix = file_content[:location]
        line_number = prefix.count("\n")
        file_lines = file_content.splitlines()
        search_line_count = len(search_text.splitlines()) or 1
        start = max(0, line_number - RELEVANT_NEARBY_LINE_DISTANCE)
        end = min(len(file_lines), line_number + search_line_count + RELEVANT_NEARBY_LINE_DISTANCE)
        nearby_lines = {_normalize_line(line) for line in file_lines[start:end] if _normalize_line(line)}
        return all(line in nearby_lines for line in added_lines)

    def _all_lines_present(self, file_content: str, added_lines: tuple[str, ...]) -> bool:
        file_lines = set(_normalized_non_empty_lines(file_content))
        return all(line in file_lines for line in added_lines)
