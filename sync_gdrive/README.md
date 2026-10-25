# Sincronizzazione file ufficio -> Google Drive

Script Windows che copia un file dalla cartella condivisa dell'ufficio
in una cartella di Google Drive, solo se il file è cambiato.

## 1. Prerequisito: Google Drive per desktop

1. Scarica e installa **Google Drive per desktop**:
   https://www.google.com/drive/download/
2. Accedi con il tuo account Google.
3. Il tuo Drive compare come unità (di solito `G:\Il mio Drive`).
   Tutto quello che viene copiato lì viene caricato sul cloud in automatico.

> Nota: Drive per desktop non permette di sincronizzare direttamente una
> cartella di rete (`\\server\...`), per questo serve lo script.

## 2. Configurazione

Apri `sincronizza_file_gdrive.bat` con il Blocco note e modifica le tre righe
nella sezione CONFIGURAZIONE:

| Variabile               | Esempio                              |
|-------------------------|--------------------------------------|
| `CARTELLA_ORIGINE`      | `\\server\condivisa\Ufficio` oppure `Z:\Ufficio` |
| `NOME_FILE`             | `monitoraggio_verifiche.ods`         |
| `CARTELLA_DESTINAZIONE` | `G:\Il mio Drive\Ufficio`            |

Il percorso esatto della cartella condivisa lo trovi in Esplora file,
cliccando sulla barra dell'indirizzo.

## 3. Uso manuale

Doppio clic su `sincronizza_file_gdrive.bat` prima di uscire dall'ufficio.
La finestra mostra l'esito e si chiude da sola dopo 5 secondi.
Lo storico delle esecuzioni è in `sincronizza_file_gdrive.log`, nella
stessa cartella dello script.

## 4. Esecuzione automatica (Utilità di pianificazione)

Da un Prompt dei comandi (non serve essere amministratore), sostituendo il
percorso dello script; esempio: ogni giorno feriale alle 17:30:

```bat
schtasks /Create /TN "Sincronizza file su Google Drive" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:30 /TR "\"C:\Script\sincronizza_file_gdrive.bat\" /silenzioso"
```

Oppure ogni ora durante la giornata lavorativa:

```bat
schtasks /Create /TN "Sincronizza file su Google Drive" /SC HOURLY /ST 08:00 /DU 10:00 /TR "\"C:\Script\sincronizza_file_gdrive.bat\" /silenzioso"
```

Con `/silenzioso` lo script non aspetta la pressione di un tasto.
Per eliminare l'attività: `schtasks /Delete /TN "Sincronizza file su Google Drive"`.

In alternativa, dall'interfaccia grafica: *Utilità di pianificazione* →
*Crea attività di base* → Azione *Avvia programma* → programma: il file `.bat`,
argomenti: `/silenzioso`.

I giorni vanno scritti in inglese (`MON,TUE,WED,THU,FRI`) anche su Windows in italiano.
