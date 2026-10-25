# Note per Claude

## Computer di Walter

- Il computer su cui Walter usa l'app Claude Desktop è il suo **computer
  personale**, non quello dell'ufficio.
- Sul computer dell'ufficio **non è possibile installare l'app Claude
  Desktop** e Walter **non ha diritti di amministratore**; l'ufficio
  informatico non va coinvolto.
- Quindi: file d'ufficio (es. `monitoraggio_verifiche.ods`) e cartella
  condivisa di rete non sono raggiungibili da Claude né con il controllo del
  computer. Script e istruzioni vanno preparati perché Walter li copi sul PC
  dell'ufficio (chiavetta, posta o download da GitHub) e li lanci lì con
  WinPython, senza installare nulla che richieda l'amministratore.

## Progetto in corso

- `prova_sqlite/`: prova di migrazione del monitoraggio verifiche da Calc a
  un database SQLite sulla cartella condivisa, usato da due persone tramite
  LibreOffice Base (driver ODBC) e script Python. Istruzioni in
  `prova_sqlite/GUIDA.md`.
