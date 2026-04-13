@echo off
:: BO Commander — Compile Java Admin SDK Bridge
:: =============================================
:: Run this from: D:\bo-commander\claude\bo-commander\bridges\

setlocal

:: ── Config ────────────────────────────────────────────────────────────────
set "BOE_DIR=D:\SAP BO\SAP BO"
set "SDK_LIB=%BOE_DIR%\SAP BusinessObjects Enterprise XI 4.0\java\lib"

:: Get current folder WITHOUT trailing backslash (fixes -d path issue)
set "OUT_DIR=%~dp0"
if "%OUT_DIR:~-1%"=="\" set "OUT_DIR=%OUT_DIR:~0,-1%"

:: Java tools
if defined JAVA_HOME (
    set "JAVAC=%JAVA_HOME%\bin\javac.exe"
    set "JAR_CMD=%JAVA_HOME%\bin\jar.exe"
) else (
    set "JAVAC=javac"
    set "JAR_CMD=jar"
)

echo.
echo BO Commander - Java Admin SDK Bridge Compiler
echo ===============================================
echo SDK lib : %SDK_LIB%
echo Out dir : %OUT_DIR%
echo Output  : %OUT_DIR%\ServerManager.jar
echo.

:: Check SDK dir exists
if not exist "%SDK_LIB%" (
    echo [ERROR] SDK lib not found: %SDK_LIB%
    echo Please check BOE_DIR in this script.
    pause
    exit /b 1
)

:: Compile
echo [1/3] Compiling ServerManager.java ...
"%JAVAC%" -cp "%SDK_LIB%\*" -d "%OUT_DIR%" "%OUT_DIR%\ServerManager.java"
if errorlevel 1 (
    echo.
    echo [ERROR] Compilation failed.
    echo Check that SDK lib exists: %SDK_LIB%
    pause
    exit /b 1
)
echo [1/3] Compiled OK

:: Package JAR
echo [2/3] Packaging ServerManager.jar ...
"%JAR_CMD%" cf "%OUT_DIR%\ServerManager.jar" -C "%OUT_DIR%" com
if errorlevel 1 (
    echo [ERROR] JAR creation failed.
    pause
    exit /b 1
)
echo [2/3] JAR created OK

:: Quick test
echo [3/3] Testing (expect: Usage line) ...
java -cp "%SDK_LIB%\*;%OUT_DIR%\ServerManager.jar" com.bocommander.ServerManager 2>&1

echo.
echo =====================================================
echo  SUCCESS - ServerManager.jar is ready.
echo.
echo  Add to your .env file:
echo  JAVA_BRIDGE_JAR=%OUT_DIR%\ServerManager.jar
echo  JAVA_SDK_CLASSPATH=%SDK_LIB%\*
echo =====================================================
echo.
pause
