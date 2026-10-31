from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from core.errors import AppError, ErrorCode

STATEMENTS = ("income", "balance", "cashflow")
UNITS = ("元", "%")
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
DEFAULT_PATH = Path(__file__).with_name("accounts.yaml")


@dataclass(frozen=True)
class Account:
    code: str
    label: str
    statement: str
    aliases: tuple[str, ...]
    unit: str = "元"
    required: bool = False


@dataclass(frozen=True)
class Schema:
    version: str
    accounts: tuple[Account, ...]
    by_code: dict[str, Account]
    alias_index: dict[str, str]
    metric_requirements: dict[str, tuple[str, ...]]
    core_rows: tuple[str, ...] = ()

    def resolve(self, text: str) -> Account | None:
        code = self.alias_index.get(text.strip())
        return self.by_code.get(code) if code else None

    def accounts_for_statement(self, statement: str) -> tuple[Account, ...]:
        return tuple(account for account in self.accounts if account.statement == statement)

    def required_accounts(self) -> tuple[Account, ...]:
        return tuple(account for account in self.accounts if account.required)


def _fail(message: str, **detail: Any) -> None:
    raise AppError(ErrorCode.INVALID_PARAMS, message, detail)


def _require(condition: bool, message: str, **detail: Any) -> None:
    if not condition:
        _fail(message, **detail)


def load_accounts(path: str | Path | None = None) -> Schema:
    source = Path(path) if path is not None else DEFAULT_PATH
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("科目 Schema 文件不存在", path=str(source))
    except yaml.YAMLError as exc:
        _fail("科目 Schema YAML 解析失败", path=str(source), error=str(exc))

    _require(isinstance(raw, dict), "科目 Schema 顶层必须是对象", path=str(source))
    version = raw.get("version")
    _require(isinstance(version, str) and version, "缺少 version", path=str(source))

    entries = raw.get("accounts")
    _require(isinstance(entries, list) and entries, "accounts 必须是非空列表", path=str(source))

    accounts: list[Account] = []
    by_code: dict[str, Account] = {}
    alias_index: dict[str, str] = {}

    for index, entry in enumerate(entries):
        where = {"path": str(source), "index": index}
        _require(isinstance(entry, dict), "科目条目必须是对象", **where)

        code = entry.get("code")
        _require(isinstance(code, str) and bool(code), "缺少 code", **where)
        _require(bool(CODE_PATTERN.match(code)), "code 必须是小写字母开头的 snake_case", code=code, **where)
        _require(code not in by_code, "code 重复", code=code, **where)

        label = entry.get("label")
        _require(isinstance(label, str) and bool(label.strip()), "缺少 label", code=code, **where)

        statement = entry.get("statement")
        _require(statement in STATEMENTS, "statement 取值非法", code=code, statement=statement, **where)

        unit = entry.get("unit", "元")
        _require(unit in UNITS, "unit 取值非法", code=code, unit=unit, **where)

        aliases = entry.get("aliases")
        _require(
            isinstance(aliases, list) and aliases and all(isinstance(a, str) and a.strip() for a in aliases),
            "aliases 必须是非空字符串列表",
            code=code,
            **where,
        )

        account = Account(
            code=code,
            label=label.strip(),
            statement=statement,
            aliases=tuple(alias.strip() for alias in aliases),
            unit=unit,
            required=bool(entry.get("required", False)),
        )
        accounts.append(account)
        by_code[code] = account

        for alias in account.aliases:
            if alias in alias_index and alias_index[alias] != code:
                _fail(
                    "别名冲突：同一别名指向多个科目",
                    alias=alias,
                    first=alias_index[alias],
                    second=code,
                    **where,
                )
            alias_index[alias] = code

    requirements_raw = raw.get("metric_requirements") or {}
    _require(isinstance(requirements_raw, dict), "metric_requirements 必须是对象", path=str(source))
    core_raw = raw.get("core_rows") or []
    _require(isinstance(core_raw, list) and core_raw, "core_rows 必须是非空列表", path=str(source))
    core_rows: list[str] = []
    for code in core_raw:
        _require(code in by_code, "core_rows 引用了不存在的科目", code=code, path=str(source))
        core_rows.append(code)

    requirements: dict[str, tuple[str, ...]] = {}
    for metric, codes in requirements_raw.items():
        _require(
            isinstance(codes, list) and codes,
            "指标依赖必须是非空列表",
            metric=metric,
            path=str(source),
        )
        for code in codes:
            _require(code in by_code, "指标引用了不存在的科目", metric=metric, code=code, path=str(source))
        requirements[str(metric)] = tuple(codes)

    return Schema(
        version=version,
        accounts=tuple(accounts),
        by_code=by_code,
        alias_index=alias_index,
        metric_requirements=requirements,
        core_rows=tuple(core_rows),
    )
