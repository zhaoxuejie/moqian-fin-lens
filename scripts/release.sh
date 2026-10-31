#!/usr/bin/env bash
set -euo pipefail

# 使用示例：bash scripts/release.sh 1.0.1
NEW_VERSION="$1"
CHANGELOG_FILE="./CHANGELOG.md"

# 简单语义化版本校验
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "版本号格式错误，需要 x.y.z，例如 1.0.0"
    exit 1
fi

DATE=$(date +%Y-%m-%d)

# 检查是否已经存在该tag
if git rev-parse "v${NEW_VERSION}" >/dev/null 2>&1; then
    echo "tag v${NEW_VERSION} 已经存在"
    exit 1
fi

# 替换 Unreleased 区块，插入版本
sed -i.bak "/## \[Unreleased\]/a\\
## [${NEW_VERSION}] - ${DATE}
" "$CHANGELOG_FILE"
rm -f "${CHANGELOG_FILE}.bak"

echo "===== 变更日志已更新 ====="
echo "请检查 CHANGELOG.md，确认内容无误后："
echo "git add CHANGELOG.md"
echo "git commit -m \"chore(release): v${NEW_VERSION}\""
echo "git tag v${NEW_VERSION}"
echo "git push && git push --tags"