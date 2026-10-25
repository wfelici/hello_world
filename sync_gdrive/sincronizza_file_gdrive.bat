@echo off
setlocal

rem ==========================================================================
rem  Sincronizza un file dalla cartella condivisa dell'ufficio a Google Drive
rem
rem  Requisito: Google Drive per desktop installato e con accesso effettuato
rem  (https://www.google.com/drive/download/). Lo script copia il file nella
rem  cartella di Drive montata come unita' (di solito G:), poi e' Drive per
rem  desktop a caricarlo in automatico sul cloud.
rem
rem  Il file viene copiato solo se e' cambiato (data/dimensione diverse).
rem ==========================================================================

rem ---- CONFIGURAZIONE (modifica queste tre righe) --------------------------
set "CARTELLA_ORIGINE=\\server\condivisa\Ufficio"
set "NOME_FILE=monitoraggio_verifiche.ods"
set "CARTELLA_DESTINAZIONE=G:\Il mio Drive\Ufficio"
rem --------------------------------------------------------------------------

set "LOG=%~dp0sincronizza_file_gdrive.log"

echo.
echo [%date% %time%] Avvio sincronizzazione di "%NOME_FILE%"
echo [%date% %time%] Avvio sincronizzazione di "%NOME_FILE%" >> "%LOG%"

if not exist "%CARTELLA_ORIGINE%\%NOME_FILE%" (
    echo ERRORE: file di origine non trovato:
    echo   "%CARTELLA_ORIGINE%\%NOME_FILE%"
    echo   Controlla di essere collegato alla rete dell'ufficio.
    echo [%date% %time%] ERRORE: origine non trovata >> "%LOG%"
    goto :fine_errore
)

for %%D in ("%CARTELLA_DESTINAZIONE%") do set "UNITA_DRIVE=%%~dD"
if not exist "%UNITA_DRIVE%\" (
    echo ERRORE: l'unita' %UNITA_DRIVE% di Google Drive non e' disponibile.
    echo   Avvia Google Drive per desktop ed effettua l'accesso.
    echo [%date% %time%] ERRORE: unita' %UNITA_DRIVE% non disponibile >> "%LOG%"
    goto :fine_errore
)

if not exist "%CARTELLA_DESTINAZIONE%\" mkdir "%CARTELLA_DESTINAZIONE%"

rem /R:5 /W:10 = in caso di file bloccato riprova 5 volte ogni 10 secondi
robocopy "%CARTELLA_ORIGINE%" "%CARTELLA_DESTINAZIONE%" "%NOME_FILE%" /R:5 /W:10 /NP /NJH /NJS /TEE /LOG+:"%LOG%"

rem robocopy: codici da 0 a 7 = successo, da 8 in su = errore
if errorlevel 8 (
    echo ERRORE durante la copia, vedi il log: "%LOG%"
    goto :fine_errore
)
if errorlevel 1 (
    echo OK: file aggiornato su Google Drive.
    echo [%date% %time%] OK: file copiato >> "%LOG%"
) else (
    echo OK: il file su Google Drive era gia' aggiornato.
    echo [%date% %time%] OK: nessuna modifica >> "%LOG%"
)
goto :fine

:fine_errore
endlocal
if /i not "%~1"=="/silenzioso" pause
exit /b 1

:fine
endlocal
if /i not "%~1"=="/silenzioso" timeout /t 5
exit /b 0
