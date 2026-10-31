import yaml
import pytest

from core.errors import AppError, ErrorCode
from schema import STATEMENTS, UNITS, load_accounts
from schema.loader import DEFAULT_PATH

SCHEMA = load_accounts()


def test_default_schema_loads():
    assert SCHEMA.version
    assert len(SCHEMA.accounts) >= 60


def test_account_codes_are_unique_and_snake_case():
    codes = [account.code for account in SCHEMA.accounts]
    assert len(codes) == len(set(codes))
    assert all(code.replace("_", "").isalnum() for code in codes)


def test_every_account_has_alias_and_valid_fields():
    for account in SCHEMA.accounts:
        assert account.aliases, account.code
        assert account.statement in STATEMENTS, account.code
        assert account.unit in UNITS, account.code
        assert account.label.strip()


def test_metric_requirements_cover_twenty_metrics():
    assert len(SCHEMA.metric_requirements) == 20
    for metric, codes in SCHEMA.metric_requirements.items():
        assert codes, metric
        for code in codes:
            assert code in SCHEMA.by_code, f"{metric} -> {code}"


def test_resolve_exact_alias():
    assert SCHEMA.resolve("营业总收入").code == "revenue_total"
    assert SCHEMA.resolve("  销售费用 ") is not None
    assert SCHEMA.resolve("不存在的科目") is None


def test_required_accounts_exist_for_core_statements():
    required = {account.code for account in SCHEMA.required_accounts()}
    assert {"revenue_total", "total_assets", "ocf_net"} <= required
    assert any(account.statement == "income" for account in SCHEMA.required_accounts())
    assert any(account.statement == "balance" for account in SCHEMA.required_accounts())
    assert any(account.statement == "cashflow" for account in SCHEMA.required_accounts())


def test_accounts_for_statement_filters():
    income = SCHEMA.accounts_for_statement("income")
    assert income and all(account.statement == "income" for account in income)


def _write(tmp_path, payload) -> str:
    path = tmp_path / "accounts.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return str(path)


def _base_payload() -> dict:
    return {
        "version": "1.0.0",
        "accounts": [
            {"code": "revenue", "label": "营业收入", "statement": "income", "aliases": ["营业收入"]},
            {"code": "net_profit", "label": "净利润", "statement": "income", "aliases": ["净利润"]},
        ],
        "core_rows": ["revenue"],
        "metric_requirements": {"revenue": ["revenue"]},
    }


def test_duplicate_code_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"].append(
        {"code": "revenue", "label": "重复", "statement": "income", "aliases": ["重复"]}
    )
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert exc_info.value.msg == "code 重复"
    assert exc_info.value.detail["code"] == "revenue"


def test_alias_conflict_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"].append(
        {"code": "other", "label": "其他", "statement": "income", "aliases": ["营业收入"]}
    )
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert "别名冲突" in exc_info.value.msg
    assert exc_info.value.detail["alias"] == "营业收入"


def test_invalid_statement_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"][0]["statement"] = "unknown"
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert exc_info.value.msg == "statement 取值非法"


def test_invalid_code_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"][0]["code"] = "RevenueTotal"
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert "snake_case" in exc_info.value.msg


def test_missing_aliases_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"][0]["aliases"] = []
    with pytest.raises(AppError):
        load_accounts(_write(tmp_path, payload))


def test_unknown_metric_account_is_rejected(tmp_path):
    payload = _base_payload()
    payload["metric_requirements"]["rot"] = ["not_exists"]
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert exc_info.value.msg == "指标引用了不存在的科目"


def test_invalid_unit_is_rejected(tmp_path):
    payload = _base_payload()
    payload["accounts"][0]["unit"] = "块"
    with pytest.raises(AppError) as exc_info:
        load_accounts(_write(tmp_path, payload))
    assert exc_info.value.msg == "unit 取值非法"


def test_invalid_yaml_is_rejected(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text("accounts: [", encoding="utf-8")
    with pytest.raises(AppError) as exc_info:
        load_accounts(path)
    assert "YAML" in exc_info.value.msg


def test_missing_file_is_rejected(tmp_path):
    with pytest.raises(AppError) as exc_info:
        load_accounts(tmp_path / "nope.yaml")
    assert exc_info.value.code == ErrorCode.INVALID_PARAMS


def test_config_change_takes_effect_without_code_change(tmp_path):
    payload = _base_payload()
    payload["accounts"].append(
        {"code": "new_account", "label": "新科目", "statement": "income", "aliases": ["新科目"]}
    )
    schema = load_accounts(_write(tmp_path, payload))
    assert schema.resolve("新科目").code == "new_account"


def test_default_file_exists():
    assert DEFAULT_PATH.exists()
def test_core_rows_are_defined_and_resolvable():
    assert len(SCHEMA.core_rows) == 60
    for code in SCHEMA.core_rows:
        assert code in SCHEMA.by_code
