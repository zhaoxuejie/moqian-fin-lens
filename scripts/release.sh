#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   bash scripts/release.sh 1.0.0 --dry-run   仅打印将执行的命令
#   bash scripts/release.sh 1.0.0             更新 CHANGELOG 并创建 tag（不 push）
# 约束：不修改历史提交、不 force push；tag 已存在则拒绝。

NEW_VERSION=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "未知参数：$arg"; exit 1 ;;
    *) NEW_VERSION="$arg" ;;
  esac
done

if [[ -z "$NEW_VERSION" ]]; then
  echo "用法：bash scripts/release.sh <x.y.z> [--dry-run]"
  exit 1
fi

if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "版本号格式错误，需要 x.y.z，例如 1.0.0"
  exit 1
fi

CHANGELOG_FILE="./CHANGELOG.md"
TAG="v${NEW_VERSION}"
DATE=$(date +%Y-%m-%d)

if [[ ! -f "$CHANGELOG_FILE" ]]; then
  echo "缺少 CHANGELOG.md"
  exit 1
fi

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "tag ${TAG} 已存在，拒绝重复发布"
  exit 1
fi

if ! grep -q "^## \[Unreleased\]" "$CHANGELOG_FILE"; then
  echo "CHANGELOG.md 缺少 [Unreleased] 区块"
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] 将执行："
  echo "  1) 在 CHANGELOG.md 的 [Unreleased] 之后插入 ## [${NEW_VERSION}] - ${DATE}"
  echo "  2) git add ${CHANGELOG_FILE}"
  echo "  3) git commit -m \"chore(release): ${TAG}\""
  echo "  4) git tag ${TAG}"
  echo "  （不执行 git push；如需推送请手动执行）"
  exit 0
fi

python - "$CHANGELOG_FILE" "$NEW_VERSION" "$DATE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
version = sys.argv[2]
date = sys.argv[3]
text = path.read_text(encoding="utf-8")
anchor = "## [Unreleased]\n"
if anchor not in text:
    raise SystemExit("CHANGELOG.md 缺少 [Unreleased] 区块")
if f"## [{version}]" in text:
    raise SystemExit(f"CHANGELOG.md 已存在 {version}")
path.write_text(text.replace(anchor, anchor + f"\n## [{version}] - {date}\n", 1), encoding="utf-8")
PY

git add "$CHANGELOG_FILE"
git commit -m "chore(release): ${TAG}" --quiet
git tag "$TAG"

echo "已创建提交与 tag ${TAG}（未 push）"
echo "如需推送：git push && git push --tags"
