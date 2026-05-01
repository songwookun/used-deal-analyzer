@echo off
rem Windows 원클릭 실행 — 더블클릭 OR cmd에서 start.bat
rem 백엔드(8000) + 프론트엔드(5173)를 별도 cmd 창에서 띄움.
rem 각 cmd 창을 닫으면 해당 서버 종료.

setlocal
set PROJECT_DIR=%~dp0
set WEB_DIR=%PROJECT_DIR%Frontend

rem 사전 검증
where python >nul 2>nul
if errorlevel 1 (
    echo [X] python 이 없습니다. https://www.python.org/downloads/ 설치 후 재시도.
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo [X] node 가 없습니다. https://nodejs.org/ 설치 후 재시도.
    pause
    exit /b 1
)

if not exist "%PROJECT_DIR%.env" (
    echo [!] .env 파일이 없습니다. 다음 키들이 필요합니다 ^(비워둬도 OK^):
    echo     GEMINI_API_KEY, GROQ_API_KEY,
    echo     NAVER_DATALAB_CLIENT_ID/SECRET,
    echo     DISCORD_WEBHOOK_URL,
    echo     NAVER_SHOP_CLIENT_ID/SECRET
    pause
)

if not exist "%WEB_DIR%\node_modules" (
    echo [npm] 처음 실행 - npm install 진행 ^(1~2분^)...
    pushd "%WEB_DIR%"
    call npm install
    popd
)

echo [run] 백엔드 + 프론트엔드 새 cmd 창에서 실행...

start "Backend :8000" cmd /k "cd /d %PROJECT_DIR% && python -m uvicorn app.main:app --reload --port 8000"
start "Frontend :5173" cmd /k "cd /d %WEB_DIR% && npm run dev"

rem 서버 ready까지 폴링 (최대 60초)
echo [wait] 서버 준비 대기...
set /a TRIES=0
:wait_loop
timeout /t 1 /nobreak >nul
curl -fsS http://localhost:8000/health >nul 2>nul
set BE=%errorlevel%
curl -fsS http://localhost:5173/ >nul 2>nul
set FE=%errorlevel%
if %BE%==0 if %FE%==0 goto ready
set /a TRIES+=1
if %TRIES% GEQ 60 goto timeout
goto wait_loop

:ready
echo [ok] 준비 완료. 브라우저 오픈.
start "" http://localhost:5173
exit /b 0

:timeout
echo [warn] 60초 안에 ready 신호가 안 왔습니다. 두 cmd 창 로그를 확인하세요.
pause
exit /b 1
