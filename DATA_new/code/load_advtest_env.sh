#!/usr/bin/env bash
# 在 bash 里加载 KEY=VAL 环境文件（忽略 # 注释行）。
#
# 用法（在 DATA_new/code 目录下）:
#   set -a && source ./load_advtest_env.sh && set +a
# 或显式指定文件:
#   source ./load_advtest_env.sh /path/to/your.env
#
# 默认顺序: 参数路径 > 同目录 advtest_rebuild.local.env > official_pipeline/advtest_runtime.env
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" != "" ]]; then
  ENVF="$1"
elif [[ -f "$DIR/advtest_rebuild.local.env" ]]; then
  ENVF="$DIR/advtest_rebuild.local.env"
elif [[ -f "$DIR/official_pipeline/advtest_runtime.env" ]]; then
  ENVF="$DIR/official_pipeline/advtest_runtime.env"
else
  echo "未找到环境文件。请任选其一:" >&2
  echo "  1) 在 $DIR 放置 advtest_rebuild.local.env" >&2
  echo "  2) 或: source $DIR/load_advtest_env.sh official_pipeline/advtest_runtime.env" >&2
  exit 1
fi

if [[ ! -f "$ENVF" ]]; then
  echo "Not found: $ENVF" >&2
  exit 1
fi
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" || "$line" == \#* ]] && continue
  [[ "$line" != *=* ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  key="${key%"${key##*[![:space:]]}"}"
  val="${val#"${val%%[![:space:]]*}"}"
  val="${val%"${val##*[![:space:]]}"}"
  export "$key"="$val"
done < "$ENVF"
echo "Loaded: $ENVF"
