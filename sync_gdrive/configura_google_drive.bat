@echo off
rem ==========================================================================
rem  Configurazione iniziale (da eseguire UNA SOLA VOLTA).
rem  Collega rclone al tuo account Google: si aprira' il browser per l'accesso.
rem  Il collegamento viene salvato in rclone.conf accanto a questo script.
rem ==========================================================================

set "RCLONE=%~dp0rclone.exe"
if not exist "%RCLONE%" (
    echo ERRORE: rclone.exe non trovato in "%~dp0"
    echo   Scaricalo da https://rclone.org/downloads/ e mettilo accanto allo script.
    pause
    exit /b 1
)

rem scope=drive.file: rclone vede e modifica SOLO i file caricati da lui,
rem non il resto del tuo Google Drive.
"%RCLONE%" config create gdrive drive scope=drive.file --config "%~dp0rclone.conf"

if errorlevel 1 (
    echo ERRORE durante la configurazione.
    pause
    exit /b 1
)
echo.
echo Configurazione completata. Prova ora sincronizza_file_gdrive.bat
pause
