#!/usr/bin/env bash
# 安裝／移除「無蝦米複習」開機自動啟動
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/boshiamy-trainer.desktop"

if [[ "${1:-}" == "--uninstall" ]]; then
    rm -f "$DESKTOP_FILE"
    echo "已移除開機自動啟動：$DESKTOP_FILE"
    exit 0
fi

mkdir -p "$AUTOSTART_DIR"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=無蝦米複習
Comment=開機自動跳出的無蝦米打字複習
Exec=python3 $SCRIPT_DIR/trainer.py
X-GNOME-Autostart-Delay=10
EOF

echo "已安裝開機自動啟動：$DESKTOP_FILE"
echo "下次登入時會延遲 10 秒後跳出訓練視窗。"
echo "移除請執行：$0 --uninstall"
