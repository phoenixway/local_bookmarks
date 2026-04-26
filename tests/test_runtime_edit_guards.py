from runtime_edit_guards import EditGuardRuntime, ensure_kotlin_imports


KOTLIN_BASE = """package com.example.localbookmarks.ui

import android.content.Intent
import android.net.Uri

class BookmarksScreen
"""


def test_edit_file_existing_single_import_is_blocked() -> None:
    runtime = EditGuardRuntime()
    runtime.record_read("BookmarksScreen.kt", KOTLIN_BASE)

    search_text = "import android.net.Uri"
    replace_text = "import android.net.Uri\nimport android.content.Intent"

    result = runtime.prepare_edit_file(
        path="BookmarksScreen.kt",
        file_content=KOTLIN_BASE,
        search_text=search_text,
        replace_text=replace_text,
    )

    assert result.reason == "duplicate_kotlin_imports_detected"


def test_edit_file_two_existing_imports_is_blocked() -> None:
    runtime = EditGuardRuntime()
    runtime.record_read("BookmarksScreen.kt", KOTLIN_BASE)

    search_text = "import android.net.Uri"
    replace_text = "import android.net.Uri\nimport android.content.Intent\nimport android.net.Uri"

    result = runtime.prepare_edit_file(
        path="BookmarksScreen.kt",
        file_content=KOTLIN_BASE,
        search_text=search_text,
        replace_text=replace_text,
    )

    assert result.reason == "duplicate_kotlin_imports_detected"


def test_edit_file_mixed_imports_normalizes_to_missing_only() -> None:
    runtime = EditGuardRuntime()
    runtime.record_read("BookmarksScreen.kt", KOTLIN_BASE)

    search_text = "import android.net.Uri"
    replace_text = (
        "import android.net.Uri\n"
        "import android.content.Intent\n"
        "import androidx.compose.ui.Modifier"
    )

    result = runtime.prepare_edit_file(
        path="BookmarksScreen.kt",
        file_content=KOTLIN_BASE,
        search_text=search_text,
        replace_text=replace_text,
    )

    assert result.decision == "normalized"
    assert result.normalized_replace_text is not None
    assert result.normalized_replace_text.count("import android.content.Intent") == 1
    assert result.normalized_replace_text.count("import androidx.compose.ui.Modifier") == 1


def test_write_file_block_repeated_imports_are_auto_normalized() -> None:
    runtime = EditGuardRuntime()
    content = """package com.example.localbookmarks.ui

import android.content.Intent
import android.content.Intent
import android.net.Uri

class BookmarksScreen
"""

    result = runtime.prepare_write(
        action="write_file_block",
        path="BookmarksScreen.kt",
        file_content=content,
    )

    assert result.decision == "normalized"
    assert result.normalized_content is not None
    assert result.normalized_content.count("import android.content.Intent") == 1


def test_kotlin_import_after_declaration_is_blocked() -> None:
    runtime = EditGuardRuntime()
    content = """package com.example.localbookmarks.ui

class BookmarksScreen
import android.content.Intent
"""

    result = runtime.prepare_write(
        action="write_file",
        path="BookmarksScreen.kt",
        file_content=content,
    )

    assert result.reason == "kotlin_import_after_declaration"


def test_successful_edit_history_blocks_repeated_insertion() -> None:
    runtime = EditGuardRuntime()
    file_content = "package a\n\nclass Example\n"
    runtime.record_read("Example.kt", file_content)

    search_text = "class Example"
    replace_text = "class Example\n\nfun added() = Unit"
    result = runtime.prepare_edit_file(
        path="Example.kt",
        file_content=file_content,
        search_text=search_text,
        replace_text=replace_text,
    )
    assert result.decision == "ok"

    runtime.record_success(
        action="edit_file",
        path="Example.kt",
        search_text=search_text,
        replace_text=replace_text,
        added_lines=["fun added() = Unit"],
    )

    result = runtime.prepare_edit_file(
        path="Example.kt",
        file_content=replace_text.replace("package a", "package a\n"),
        search_text=search_text,
        replace_text=replace_text,
        fresh_read_performed=True,
    )

    assert result.reason == "repeated_successful_insertion"


def test_second_edit_after_write_requires_fresh_read() -> None:
    runtime = EditGuardRuntime()
    original = "package a\n\nclass Example\n"
    runtime.record_read("Example.kt", original)
    runtime.record_success(
        action="edit_file",
        path="Example.kt",
        search_text="class Example",
        replace_text="class Example\n\nfun added() = Unit",
        added_lines=["fun added() = Unit"],
    )

    result = runtime.prepare_edit_file(
        path="Example.kt",
        file_content="package a\n\nclass Example\n\nfun added() = Unit\n",
        search_text="class Example",
        replace_text="class Example\n\nfun added() = Unit\n\nfun second() = Unit",
    )

    assert result.reason == "fresh_read_required"


def test_fresh_read_allows_new_non_duplicate_edit() -> None:
    runtime = EditGuardRuntime()
    original = "package a\n\nclass Example\n"
    updated = "package a\n\nclass Example\n\nfun added() = Unit\n"
    runtime.record_read("Example.kt", original)
    runtime.record_success(
        action="edit_file",
        path="Example.kt",
        search_text="class Example",
        replace_text=updated,
        added_lines=["fun added() = Unit"],
    )
    runtime.record_read("Example.kt", updated)

    result = runtime.prepare_edit_file(
        path="Example.kt",
        file_content=updated,
        search_text="fun added() = Unit",
        replace_text="fun added() = Unit\n\nfun second() = Unit",
        fresh_read_performed=True,
    )

    assert result.decision == "ok"


def test_duplicate_import_recovery_message_is_specific() -> None:
    runtime = EditGuardRuntime()
    runtime.record_read("BookmarksScreen.kt", KOTLIN_BASE)

    result = runtime.prepare_edit_file(
        path="BookmarksScreen.kt",
        file_content=KOTLIN_BASE,
        search_text="import android.net.Uri",
        replace_text="import android.net.Uri\nimport android.content.Intent",
    )

    assert "already exist" in (result.message or "")
    assert "Do not add them again" in (result.message or "")


def test_repeated_duplicate_insertion_triggers_terminal_handoff() -> None:
    runtime = EditGuardRuntime()
    original = "package a\n\nclass Example\n"
    updated = "package a\n\nclass Example\n\nfun added() = Unit\n"
    runtime.record_read("Example.kt", original)
    runtime.record_success(
        action="edit_file",
        path="Example.kt",
        search_text="class Example",
        replace_text=updated,
        added_lines=["fun added() = Unit"],
    )

    for _ in range(2):
        result = runtime.prepare_edit_file(
            path="Example.kt",
            file_content=updated,
            search_text="class Example",
            replace_text="class Example\n\nfun added() = Unit",
            fresh_read_performed=True,
        )
        assert result.reason == "repeated_successful_insertion"

    result = runtime.prepare_edit_file(
        path="Example.kt",
        file_content=updated,
        search_text="class Example",
        replace_text="class Example\n\nfun added() = Unit",
        fresh_read_performed=True,
    )

    assert result.reason == "terminal_duplicate_insertion_handoff"
    assert result.terminal is True
    assert result.diagnostics["path"] == "Example.kt"


def test_ensure_kotlin_imports_is_noop_when_all_exist() -> None:
    result = ensure_kotlin_imports(
        "BookmarksScreen.kt",
        KOTLIN_BASE,
        ["import android.content.Intent", "import android.net.Uri"],
    )

    assert result.decision == "no_op"
    assert result.reason == "already_applied_edit"
