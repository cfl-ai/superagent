@echo off
REM SuperAgent 桌面版一键启动
cd /d "%~dp0"
where python >nul 2>nul || (echo [错误] 未找到 Python，请先安装 Python 3.10+ & pause & exit /b 1)
echo 正在启动 SuperAgent 服务...
start "SuperAgent Server" python -m superagent serve --host 127.0.0.1 --port 8000
timeout /t 2 /nobreak >nul
start "" http://localhost:8000
echo.
echo ✅ SuperAgent 已启动，浏览器已打开 http://localhost:8000
echo    服务窗口标题为 "SuperAgent Server"，关闭它即停止服务。
pause
