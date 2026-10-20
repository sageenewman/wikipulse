"""Decide whether a SQL statement only reads. Used by `make query` (streaming/query.py).

A guard against mistakes, not against an attacker: whoever runs `make query` can also run
Spark directly. Bronze is the copy everything else is rebuilt from, so a typed DELETE or
DROP must not reach it, and a table must never be deleted without its checkpoint.
"""

from __future__ import annotations

import re

READ_STATEMENTS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
WRITE_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "REPLACE",
    "CALL",
}

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_QUOTED = re.compile(r"'(?:[^'\\]|\\.)*'|`[^`]*`|\"(?:[^\"\\]|\\.)*\"")
_WORD = re.compile(r"[A-Za-z_]+")


def is_read_only(sql: str) -> bool:
    """True if the statement starts with a read keyword and contains no write keyword.

    Comments and quoted text are ignored, so a title like 'Drop' in a filter is not a
    write. A WITH statement can end in an INSERT, so keywords are checked throughout.
    """
    code = _QUOTED.sub(" ", _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql)))
    words = [w.upper() for w in _WORD.findall(code)]
    if not words or words[0] not in READ_STATEMENTS:
        return False
    return not WRITE_KEYWORDS.intersection(words)
