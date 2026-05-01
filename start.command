#!/usr/bin/env bash
# macOS 원클릭 실행 — Finder에서 더블클릭 OR 터미널에서 ./start.command
# 백엔드(8000) + 프론트엔드(5173)를 별도 터미널 창에서 띄움.
# 각 터미널 창을 닫으면 해당 서버 종료.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$PROJECT_DIR/Frontend"

# 사전 검증 — 의존성 체크 (없으면 안내 후 종료)
if ! command -v python3 >/dev/null 2>&1; then
    echo "❌ python3 가 없습니다. https://www.python.org/downloads/ 설치 후 재시도."
    read -n 1 -s -r -p "엔터 누르면 종료..."
    exit 1
fi

if ! command -v node >/dev/null 2>&1; then
    echo "❌ node 가 없습니다. https://nodejs.org/ 설치 후 재시도."
    read -n 1 -s -r -p "엔터 누르면 종료..."
    exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "⚠️  .env 파일이 없습니다. 다음 키들이 필요합니다 (없는 키는 비워둬도 OK — 해당 기능만 비활성):"
    echo "   GEMINI_API_KEY, GROQ_API_KEY, NAVER_DATALAB_CLIENT_ID, NAVER_DATALAB_CLIENT_SECRET"
    echo "   DISCORD_WEBHOOK_URL, NAVER_SHOP_CLIENT_ID, NAVER_SHOP_CLIENT_SECRET"
    read -n 1 -s -r -p "엔터 누르면 계속 (.env 없이 시작)..."
fi

# Frontend/node_modules 없으면 자동 install
if [ ! -d "$WEB_DIR/node_modules" ]; then
    echo "📦 처음 실행 — npm install 진행 (1~2분)..."
    (cd "$WEB_DIR" && npm install)
fi

# 두 터미널 창을 osascript로 띄움 — 새 창에서 각 서버 실행
echo "🚀 백엔드 + 프론트엔드 새 터미널 창에서 실행..."

osascript <<EOF
tell application "Terminal"
    activate
    do script "cd '$PROJECT_DIR' && echo '[Backend] uvicorn :8000' && python3 -m uvicorn app.main:app --reload --port 8000"
    do script "cd '$WEB_DIR' && echo '[Frontend] vite :5173' && npm run dev"
end tell
EOF

# 서버 ready까지 대기 후 브라우저 자동 오픈
echo "⏳ 서버 준비 대기..."
for i in $(seq 1 60); do
    if curl -fsS http://localhost:5173/ >/dev/null 2>&1 && curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ 준비 완료. 브라우저 오픈."
        open "http://localhost:5173"
        exit 0
    fi
    sleep 1
done

echo "⚠️  60초 안에 ready 신호가 안 왔습니다. 두 터미널 창의 로그를 확인해주세요."
echo "    (uvicorn은 임베딩 모델 로딩에 ~5초 걸리고, 첫 실행 npm install 후 vite 시작에 시간 걸릴 수 있음)"
read -n 1 -s -r -p "엔터 누르면 이 창 종료..."
