@echo off
setlocal

rem ==========================================================================
rem  Copia un file dalla cartella condivisa dell'ufficio direttamente su
rem  Google Drive (cloud), senza installare Google Drive per desktop.
rem
rem  Usa rclone (https://rclone.org), un singolo eseguibile che NON richiede
rem  installazione ne' diritti di amministratore: basta mettere rclone.exe
rem  nella stessa cartella di questo script.
rem
rem  Il file viene caricato solo se e' cambiato (data/dimensione diverse).
rem ==========================================================================

rem ---- CONFIGURAZIONE (modifica queste righe) ------------------------------
set "CARTELLA_ORIGINE=\\server\condivisa\Ufficio"
set "NOME_FILE=monitoraggio_verifiche.ods"
rem Cartella su Google Drive (verra' creata se non esiste)
set "CARTELLA_DRIVE=Ufficio"
rem Nome del collegamento creato con "rclone config"
set "REMOTO=gdrive"
rem --------------------------------------------------------------------------

set "RCLONE=%~dp0rclone.exe"
set "RCLONE_CONF=%~dp0rclone.conf"
set "LOG=%~dp0sincronizza_file_gdrive.log"

echo.
echo [%date% %time%] Avvio caricamento di "%NOME_FILE%"
echo [%date% %time%] Avvio caricamento di "%NOME_FILE%" >> "%LOG%"

if not exist "%RCLONE%" (
    echo ERRORE: rclone.exe non trovato in "%~dp0"
    echo   Scaricalo da https://rclone.org/downloads/ e mettilo accanto allo script.
    echo [%date% %time%] ERRORE: rclone.exe mancante >> "%LOG%"
    goto :fine_errore
)

if not exist "%RCLONE_CONF%" (
    echo ERRORE: configurazione non trovata: "%RCLONE_CONF%"
    echo   Esegui prima configura_google_drive.bat
    echo [%date% %time%] ERRORE: rclone.conf mancante >> "%LOG%"
    goto :fine_errore
)

if not exist "%CARTELLA_ORIGINE%\%NOME_FILE%" (
    echo ERRORE: file di origine non trovato:
    echo   "%CARTELLA_ORIGINE%\%NOME_FILE%"
    echo   Controlla di essere collegato alla rete dell'ufficio.
    echo [%date% %time%] ERRORE: origine non trovata >> "%LOG%"
    goto :fine_errore
)

rem copyto carica il file solo se e' diverso da quello gia' presente su Drive
"%RCLONE%" copyto "%CARTELLA_ORIGINE%\%NOME_FILE%" "%REMOTO%:%CARTELLA_DRIVE%/%NOME_FILE%" ^
    --config "%RCLONE_CONF%" --retries 5 --low-level-retries 10 ^
    --stats-one-line -v --log-file "%LOG%"

if errorlevel 1 (
    echo ERRORE durante il caricamento, vedi il log: "%LOG%"
    goto :fine_errore
)
echo OK: il file su Google Drive e' aggiornato.
echo [%date% %time%] OK >> "%LOG%"
goto :fine

:fine_errore
endlocal
if /i not "%~1"=="/silenzioso" pause
exit /b 1

:fine
endlocal
if /i not "%~1"=="/silenzioso" timeout /t 5
exit /b 0
