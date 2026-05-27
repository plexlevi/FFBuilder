@echo off
setlocal enabledelayedexpansion

set "ROOT_DIR=%~dp0.."
pushd "%ROOT_DIR%" >nul

if "%APP_NAME%"=="" set "APP_NAME=FFBuilder"
if "%VERSION%"=="" set "VERSION=1.0.0"

if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
) else (
  where py >nul 2>nul
  if %errorlevel%==0 (
    set "PYTHON_EXE=py -3"
  ) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
      set "PYTHON_EXE=python"
    ) else (
      echo Python not found.
      popd >nul
      exit /b 1
    )
  )
)

echo Using python: %PYTHON_EXE%

%PYTHON_EXE% -m pip install --upgrade pip pyinstaller
if errorlevel 1 goto :error

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"

set "ENTRYPOINT="
if exist "%ROOT_DIR%\main.py" (
  set "ENTRYPOINT=main.py"
) else if exist "%ROOT_DIR%\__main__.py" (
  set "ENTRYPOINT=__main__.py"
) else (
  echo Build failed: neither main.py nor __main__.py was found in project root.
  goto :error
)

%PYTHON_EXE% -m PyInstaller --noconfirm --clean --windowed --name "%APP_NAME%" --add-data "assets;assets" %ENTRYPOINT%
if errorlevel 1 goto :error

set "APP_DIST=%ROOT_DIR%\dist\%APP_NAME%"
if not exist "%APP_DIST%" (
  echo Build failed: %APP_DIST% not found
  goto :error
)

where ISCC >nul 2>nul
if errorlevel 1 (
  echo Inno Setup compiler not found on PATH. Skipping installer EXE.
  echo Built app folder: %APP_DIST%
  goto :done
)

ISCC "%ROOT_DIR%\installers\windows\installer.iss" /DAppName="%APP_NAME%" /DAppVersion="%VERSION%" /DAppSource="%APP_DIST%" /DOutputDir="%ROOT_DIR%\dist"
if errorlevel 1 goto :error

echo Installer built in %ROOT_DIR%\dist
goto :done

:error
echo Build failed.
popd >nul
exit /b 1

:done
popd >nul
exit /b 0
