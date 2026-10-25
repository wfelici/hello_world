# Prova: monitoraggio verifiche su database SQLite condiviso

Obiettivo della prova: verificare, **senza diritti di amministratore**, che
due persone possano lavorare contemporaneamente sugli stessi dati,
conservati in un file SQLite sulla cartella condivisa, usando LibreOffice
Base e gli script Python.

Il file `monitoraggio_verifiche.ods` **non viene mai modificato**: la prova
lavora su una copia dei dati. Finché la prova non è conclusa, il file di
lavoro resta quello di Calc.

## Contenuto della cartella

| File | A cosa serve |
|---|---|
| `ods_a_sqlite.py` | Crea il database leggendo il foglio "Tutti" del file ODS |
| `prova_concorrenza.py` | Prova di scrittura contemporanea da due PC |
| `backup_sqlite.py` | Copia di sicurezza del database, valida anche mentre è in uso |

Gli script usano solo la libreria standard di Python: WinPython va bene
così com'è, senza installare pacchetti.

---

## Passo 1: creare il database

Da una finestra CMD, con il Python di WinPython:

```
python ods_a_sqlite.py --ods "C:\percorso\monitoraggio_verifiche.ods" --db "\\server\condivisa\prova\verifiche.sqlite"
```

Lo script stampa l'elenco delle colonne importate e il numero di righe.

Cosa c'è nel database:

| Nome | Tipo | Contenuto |
|---|---|---|
| `richieste` | tabella | Una riga per ogni riga del foglio; `riga_ods` indica la riga di origine |
| `v_stato_attuale` | vista | Ultima richiesta per ditta + tipo, con lo stato: `VALIDA`, `SCADUTA`, `IN ATTESA`, `RICEVUTA, SENZA SCADENZA`, `NESSUNA RICHIESTA` |
| `v_in_scadenza_30gg` | vista | Certificazioni valide che scadono entro 30 giorni |
| `anomalie_import` | tabella | Valori che non è stato possibile interpretare (es. data scritta male) |
| `colonne_origine` | tabella | Corrispondenza tra intestazioni del foglio e nomi delle colonne |

Note:

- Le viste applicano la stessa regola di `interroga_verifiche.py`: la
  scadenza vale **solo se** la risposta (`ricevuto`) è arrivata il giorno
  della richiesta o dopo. Altrimenti la richiesta è `IN ATTESA` e
  `scadenza_valida` resta vuota.
- Le viste raggruppano per nome **esattamente** come è scritto: "BAROZZI
  MATTEO" e "BAROZZI VITO MATTEO" restano due soggetti distinti.
- **Controllate subito `anomalie_import`**. Una riga con la data richiesta
  scritta male risulta `NESSUNA RICHIESTA` finché non la correggete.
- Per ripetere l'importazione da capo aggiungete `--sovrascrivi`.
  **Attenzione:** cancella tutto quello che avete inserito nel database.

## Passo 2: prova di scrittura contemporanea (la più importante)

Serve a capire se la vostra cartella di rete gestisce bene il blocco del
file. Lanciate **contemporaneamente**, voi e il collega, ciascuno dal
proprio PC:

```
python prova_concorrenza.py --db "\\server\condivisa\prova\verifiche.sqlite" --scritture 500
```

- Su entrambi i PC deve comparire `ESITO: OK`, con `errori: 0` e
  `integrità: ok`.
- Ripetete la prova 2 o 3 volte, anche in orari diversi.
- Alla fine cancellate la tabella di prova:
  `python prova_concorrenza.py --db "..." --pulisci`

Se compare `PROBLEMI RILEVATI`, **non usate SQLite in rete per i dati
veri** e fatemi sapere che cosa è stato stampato.

## Passo 3: collegare LibreOffice Base

### Usate il driver ODBC (il driver JDBC non va bene per i formulari)

Ho provato entrambi i collegamenti con LibreOffice 24.2:

| | ODBC (driver SQLite ODBC) | JDBC (sqlite-jdbc) |
|---|---|---|
| Tabelle, viste, query | ✅ | ✅ |
| Macro con istruzioni SQL | ✅ | ✅ |
| **Formulari** (scorrere, modificare, inserire record) | ✅ | ❌ errore "SQLite only supports TYPE_FORWARD_ONLY cursors" |
| Date salvate in modo leggibile da Python | ✅ (`2026-10-03`) | ✅ solo con i parametri giusti nell'indirizzo, altrimenti diventano numeri |

**Quindi serve il driver ODBC.** La prova ODBC l'ho fatta su Linux; la
parte Windows qui sotto (driver senza installazione) è **da verificare**
sui vostri PC.

### 3a. Controllare se il driver è già presente

1. Menu Start → cercate **"Origine dati ODBC (64 bit)"** e apritela. Per
   guardare non servono diritti di amministratore.
2. Scheda **Driver**: se c'è **"SQLite3 ODBC Driver"**, passate al punto 3c.

### 3b. Driver senza installazione (se non è presente)

L'installatore del driver (*SQLite ODBC Driver* di Christian Werner,
<http://www.ch-werner.de/sqliteodbc/>, file `sqliteodbc_w64.exe`)
normalmente richiede l'amministratore. Si può provare questa strada
alternativa:

1. Scaricate `sqliteodbc_w64.exe` (versione **64 bit**, come LibreOffice).
2. **Non eseguitelo**: apritelo con 7-Zip (tasto destro → 7-Zip → Estrai)
   ed estraete i file in una vostra cartella, ad esempio
   `C:\Users\<utente>\sqliteodbc\`.
3. Verificate che nella cartella ci sia `sqlite3odbc.dll`.
4. Create un file di testo `verifiche_dsn.reg` con questo contenuto,
   correggendo i due percorsi (nei file `.reg` ogni `\` va scritta doppia):

   ```
   Windows Registry Editor Version 5.00

   [HKEY_CURRENT_USER\Software\ODBC\ODBC.INI\verifiche]
   "Driver"="C:\\Users\\<utente>\\sqliteodbc\\sqlite3odbc.dll"
   "Database"="\\\\server\\condivisa\\prova\\verifiche.sqlite"
   "Timeout"="10000"

   [HKEY_CURRENT_USER\Software\ODBC\ODBC.INI\ODBC Data Sources]
   "verifiche"="SQLite3 ODBC Driver"
   ```

5. Fate doppio clic sul file `.reg` e confermate. Scrive solo nella parte
   del registro del vostro utente (`HKEY_CURRENT_USER`), che non richiede
   l'amministratore.
6. Il collega ripete i punti 2–5 sul suo PC.

`Timeout=10000` significa che, se il collega sta scrivendo proprio in quel
momento, Base aspetta fino a 10 secondi invece di dare subito errore.

Se questa strada non funziona (Base non vede l'origine dati "verifiche",
oppure dà errore sul driver), fatemelo sapere: vedremo le alternative.

### 3c. Creare il file Base

1. LibreOffice → **File → Nuovo → Database**.
2. **Collega a un database esistente** → **ODBC** → Avanti.
3. Sfoglia → scegliete **verifiche** → Avanti → (nessun utente) → Avanti.
4. Lasciate selezionato **"Sì, registra il database"**, perché serve alle
   macro → Fine.
5. Salvate il file `.odb` **sul vostro PC**, ad esempio
   `Documenti\verifiche.odb`, e **non nella cartella condivisa**: ognuno
   usa la propria copia del `.odb`, mentre i dati stanno nel file
   `.sqlite` comune.

Nella sezione **Tabelle** compaiono `richieste` e le due viste. Fate doppio
clic su `v_stato_attuale` per vedere lo stato di tutte le certificazioni.

### 3d. Formulario di prova

1. **Formulari → Usa procedura guidata per la creazione di formulari**.
2. Tabella `richieste` → aggiungete i campi che usate di più → Fine.
3. Provate a scorrere, modificare e aggiungere una riga.
4. Il collega, nello stesso momento, fa lo stesso dal suo PC. Ricaricando
   (pulsante **Aggiorna** nella barra del formulario) ognuno vede le
   modifiche dell'altro.

## Passo 4: una macro Basic sul database

Esempio di macro che mostra le certificazioni in scadenza. Usa il nome con
cui avete registrato il database al punto 3c (qui `verifiche`):

```basic
Sub CertificazioniInScadenza
    Dim oContesto As Object, oSorgente As Object, oConn As Object
    Dim oIstr As Object, oRis As Object
    Dim sTesto As String

    oContesto = CreateUnoService("com.sun.star.sdb.DatabaseContext")
    oSorgente = oContesto.getByName("verifiche")
    oConn = oSorgente.getConnection("", "")
    oIstr = oConn.createStatement()
    oRis = oIstr.executeQuery("SELECT ditta, tipo_richiesta, scadenza_valida " & _
                              "FROM v_in_scadenza_30gg ORDER BY scadenza_valida")
    Do While oRis.next()
        sTesto = sTesto & oRis.getString(1) & " - " & oRis.getString(2) & _
                 " - scade il " & oRis.getString(3) & Chr(10)
    Loop
    oConn.close()   ' chiudere sempre: libera il file per il collega

    If sTesto = "" Then sTesto = "Nessuna certificazione in scadenza nei prossimi 30 giorni."
    MsgBox sTesto, 64, "In scadenza"
End Sub
```

Al posto dei cicli sulle celle si scrive una sola istruzione SQL. Le
macro che scrivono dati useranno `executeUpdate("INSERT ...")` oppure
`executeUpdate("UPDATE ...")` allo stesso modo.

Nelle query create con l'editor di Base, le funzioni proprie di SQLite
(es. `date('now')`) funzionano solo attivando il pulsante **"Esegui
direttamente il comando SQL"**. Le viste già pronte nel database non hanno
questo problema.

## Passo 5: Python sul database

Gli script Python leggono il database con il modulo `sqlite3`, già incluso
in WinPython:

```python
import sqlite3
con = sqlite3.connect(r"\\server\condivisa\prova\verifiche.sqlite", timeout=30)
for ditta, tipo, stato, scadenza in con.execute(
        "SELECT ditta, tipo_richiesta, stato, scadenza_valida FROM v_stato_attuale "
        "WHERE ditta LIKE ?", ("%ALFA%",)):
    print(ditta, tipo, stato, scadenza)
con.close()
```

## Backup

```
python backup_sqlite.py --db "\\server\condivisa\prova\verifiche.sqlite" --cartella "\\server\condivisa\prova\backup"
```

- Mantiene le ultime 30 copie (modificabile con `--conserva`).
- **Non copiate il file `.sqlite` con Esplora risorse** mentre qualcuno lo
  usa: la copia potrebbe risultare danneggiata. Usate sempre lo script.
- Conviene lanciarlo all'inizio di ogni giornata di lavoro, ad esempio da
  una macro con lo schema già usato per avviare Python da LibreOffice.

## Regole d'uso per due utenti

1. **Mai** attivare la modalità WAL di SQLite: sulle cartelle di rete non
   funziona.
2. Nelle macro: aprire la connessione, scrivere e chiudere subito.
3. Chiudere Base quando non serve: una connessione aperta a lungo può far
   aspettare il collega.
4. Ognuno usa la **propria copia** del file `.odb`.
5. Backup giornaliero con lo script.

## Cosa mi serve sapere dopo la prova

- L'esito di `prova_concorrenza.py` sui due PC.
- Se il driver ODBC era già presente o se ha funzionato la strada senza
  installazione (punto 3b).
- Il numero di righe in `anomalie_import`.
- Se il formulario di prova funziona per entrambi contemporaneamente.

Con questi risultati si può decidere se migrare davvero la procedura e
progettare le tabelle definitive (ditte, interventi, richieste separate).
