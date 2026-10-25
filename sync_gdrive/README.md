# Caricamento file ufficio -> Google Drive (senza installare nulla)

Script Windows che copia un file dalla cartella condivisa dell'ufficio
**direttamente su Google Drive nel cloud**, solo se il file è cambiato.
Non serve Google Drive per desktop né diritti di amministratore: si usa
[rclone](https://rclone.org), un singolo file `.exe` portatile.

> ⚠️ Prima di usarlo verifica che le regole del tuo ufficio consentano di
> copiare quel file su un account Google personale.

## 1. Preparazione (una sola volta)

1. Crea una cartella, ad esempio `C:\Script\SyncDrive` (oppure nella tua
   cartella Documenti) e copia dentro i due file `.bat`.
2. Scarica rclone per Windows da https://rclone.org/downloads/
   (*Windows – Intel/AMD – 64 Bit*), apri lo zip ed estrai **solo**
   `rclone.exe` nella stessa cartella degli script.
3. Fai doppio clic su `configura_google_drive.bat`: si apre il browser,
   accedi con il tuo account Google e clicca *Consenti*. Quando il browser
   mostra "Success" puoi chiuderlo.
   Viene creato il file `rclone.conf` (contiene l'autorizzazione al tuo
   Drive: non condividerlo e non lasciarlo in una cartella di rete).

Il permesso concesso è limitato (`drive.file`): rclone può vedere e
modificare **solo i file che carica lui**, non il resto del tuo Drive.

## 2. Configurazione dello script

Apri `sincronizza_file_gdrive.bat` con il Blocco note e modifica:

| Variabile          | Esempio                                         |
|--------------------|-------------------------------------------------|
| `CARTELLA_ORIGINE` | `\\server\condivisa\Ufficio` oppure `Z:\Ufficio` |
| `NOME_FILE`        | `monitoraggio_verifiche.ods`                    |
| `CARTELLA_DRIVE`   | `Ufficio` (cartella su Drive, creata se manca)  |

Il percorso della cartella condivisa lo trovi in Esplora file cliccando
sulla barra dell'indirizzo.

## 3. Uso manuale

Doppio clic su `sincronizza_file_gdrive.bat` prima di uscire dall'ufficio.
La finestra mostra l'esito e si chiude dopo 5 secondi. Lo storico è in
`sincronizza_file_gdrive.log`, nella stessa cartella.

## 4. Esecuzione automatica (Utilità di pianificazione)

Da un Prompt dei comandi (non serve essere amministratore), sostituendo il
percorso; esempio ogni giorno feriale alle 17:30:

```bat
schtasks /Create /TN "Carica file su Google Drive" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:30 /TR "\"C:\Script\SyncDrive\sincronizza_file_gdrive.bat\" /silenzioso"
```

Oppure ogni ora durante la giornata lavorativa:

```bat
schtasks /Create /TN "Carica file su Google Drive" /SC HOURLY /ST 08:00 /DU 10:00 /TR "\"C:\Script\SyncDrive\sincronizza_file_gdrive.bat\" /silenzioso"
```

I giorni vanno scritti in inglese (`MON,TUE,...`) anche su Windows in italiano.
Con `/silenzioso` lo script non attende la pressione di un tasto.
Per eliminare l'attività: `schtasks /Delete /TN "Carica file su Google Drive"`.

## Problemi comuni

- **"rclone.exe" bloccato dall'antivirus / criteri aziendali**: in quel caso
  non è possibile eseguire programmi esterni sul PC; va chiesto all'IT.
- **Il browser non si apre durante la configurazione**: copia nel browser
  l'indirizzo `http://127.0.0.1:53682/auth...` mostrato nella finestra.
- **Errore di token scaduto** (dopo molti mesi o cambio password): riesegui
  `configura_google_drive.bat` dopo aver cancellato `rclone.conf`.
- **Sul web il file compare doppio**: succede solo se lo carichi anche a mano
  nella stessa cartella; lascia che sia solo lo script a caricarlo.
