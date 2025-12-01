@echo off
setlocal ENABLEDELAYEDEXPANSION

REM === DR IA - Instalador y Lanzador completo (Windows) ===

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo ===========================================================
echo =            DR IA - Instalador y Lanzador               =
echo ===========================================================
echo.

REM --- 0) Comprobar que Python existe ---
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se encontro "python" en el PATH.
    echo Instala Python 3.x y vuelve a ejecutar este script.
    pause
    exit /b 1
)

REM --- 1) Crear o reutilizar entorno virtual ---
if exist ".venv\Scripts\python.exe" (
    echo [1/6] Entorno virtual .venv ya existe. Se reutilizara.
) else (
    echo [1/6] Creando entorno virtual .venv...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

REM --- 2) Activar entorno virtual ---
echo [2/6] Activando entorno virtual...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

REM --- 3) Instalar dependencias ---
echo [3/6] Instalando / actualizando dependencias...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se pudieron instalar las dependencias de requirements.txt
    pause
    exit /b 1
)

REM --- 4) Verificar archivo .env ---
if not exist ".env" (
    echo [4/6] No se encontro .env. Creando plantilla basica...
    > .env echo APP_HOST=0.0.0.0
    >> .env echo APP_PORT=8080
    >> .env echo USE_LLM=true
    >> .env echo OPENAI_API_KEY=pon_tu_api_key
    >> .env echo OPENAI_MODEL=gpt-4.1-mini
    >> .env echo WA_PHONE_NUMBER_ID=pon_tu_phone_number_id
    >> .env echo WA_ACCESS_TOKEN=pon_tu_token
    >> .env echo WEBHOOK_VERIFY_TOKEN=pon_tu_token_verificacion
    >> .env echo PUBLIC_BASE_URL=https://tu-ngrok-o-dominio
    >> .env echo DB_PATH=dria_memory.sqlite3
    >> .env echo OUT_DIR=out
    >> .env echo ENV=development
    echo Edita el archivo .env con tus credenciales reales antes de continuar.
    pause
    exit /b 1
)

if not exist "out" (
    mkdir out
)

REM --- 5) Lanzar ngrok si esta instalado ---
echo [5/6] Comprobando ngrok...
where ngrok >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Lanzando ngrok http 8080 en una nueva ventana...
    start "ngrok" ngrok http 8080
    echo Recuerda usar la URL publica de ngrok como webhook en Meta.
) else (
    echo [AVISO] ngrok no esta instalado o no esta en el PATH.
    echo Si quieres exponer el puerto 8080 a Internet, instala ngrok
    echo y anadelo al PATH del sistema.
)

REM --- 6) Lanzar servidor Uvicorn ---
echo [6/6] Iniciando servidor con Uvicorn...
echo.
echo Si quieres detener el servidor, presiona CTRL+C en esta ventana.
echo.

python -m uvicorn app.webhook:app --host 0.0.0.0 --port 8080

echo.
echo ===========================================================
echo =       El servidor Uvicorn se ha detenido (CTRL+C).      =
echo ===========================================================
echo.
pause
endlocal
