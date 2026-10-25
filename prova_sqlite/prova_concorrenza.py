"""
Prova di scrittura contemporanea sul database SQLite nella cartella di
rete. Va lanciato NELLO STESSO MOMENTO su due PC (voi e il collega),
puntando allo stesso file.

Ogni PC scrive molte righe in una tabella di prova separata
("prova_concorrenza"), che non tocca i dati veri. Alla fine lo script
controlla che il database sia integro e che nessuna riga sia andata persa.

Uso:
    python prova_concorrenza.py --db "\\\\server\\condivisa\\verifiche.sqlite"
    python prova_concorrenza.py --db "..." --scritture 500
    python prova_concorrenza.py --db "..." --pulisci     (cancella la tabella di prova)
"""

import argparse
import os
import socket
import sqlite3
import sys
import time

ATTESA_BLOCCO_SECONDI = 30


def connetti(percorso_db):
    con = sqlite3.connect(percorso_db, timeout=ATTESA_BLOCCO_SECONDI)
    con.execute("PRAGMA journal_mode=DELETE")
    return con


def main():
    parser = argparse.ArgumentParser(description="Prova di scrittura contemporanea su SQLite")
    parser.add_argument("--db", required=True, help="Percorso del database sulla cartella di rete")
    parser.add_argument("--scritture", type=int, default=300, help="Numero di righe da scrivere")
    parser.add_argument("--pulisci", action="store_true", help="Cancella la tabella di prova ed esce")
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        print(f"Database non trovato: {args.db}")
        sys.exit(1)

    pc = socket.gethostname()
    con = connetti(args.db)

    if args.pulisci:
        con.execute("DROP TABLE IF EXISTS prova_concorrenza")
        con.commit()
        con.close()
        print("Tabella di prova cancellata.")
        return

    con.execute("""
        CREATE TABLE IF NOT EXISTS prova_concorrenza (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pc TEXT NOT NULL,
            progressivo INTEGER NOT NULL,
            scritto_il TEXT NOT NULL
        )""")
    con.commit()
    gia_presenti = con.execute(
        "SELECT COUNT(*) FROM prova_concorrenza WHERE pc = ?", (pc,)).fetchone()[0]

    print(f"PC: {pc} - scrivo {args.scritture} righe (una transazione breve per riga)...")
    errori, attesa_massima = 0, 0.0
    inizio = time.time()
    for i in range(1, args.scritture + 1):
        t0 = time.time()
        try:
            # come farebbe una macro: apre, scrive, conferma subito
            con.execute(
                "INSERT INTO prova_concorrenza (pc, progressivo, scritto_il) "
                "VALUES (?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now', 'localtime'))",
                (pc, i))
            con.commit()
        except sqlite3.OperationalError as e:
            errori += 1
            con.rollback()
            print(f"  errore alla riga {i}: {e}")
        attesa_massima = max(attesa_massima, time.time() - t0)
        if i % 50 == 0:
            print(f"  {i} righe scritte")
    durata = time.time() - inizio

    scritte = con.execute(
        "SELECT COUNT(*) FROM prova_concorrenza WHERE pc = ?", (pc,)).fetchone()[0] - gia_presenti
    integrita = con.execute("PRAGMA integrity_check").fetchone()[0]
    per_pc = con.execute(
        "SELECT pc, COUNT(*) FROM prova_concorrenza GROUP BY pc ORDER BY pc").fetchall()
    con.close()

    print()
    print(f"Durata: {durata:.1f} s - attesa massima per una scrittura: {attesa_massima:.2f} s")
    print(f"Righe attese: {args.scritture} - righe trovate: {scritte} - errori: {errori}")
    print(f"Controllo integrità del database: {integrita}")
    print("Righe nella tabella di prova per PC:")
    for nome, n in per_pc:
        print(f"  {nome}: {n}")
    print()
    if integrita == "ok" and errori == 0 and scritte == args.scritture:
        print("ESITO: OK")
    else:
        print("ESITO: PROBLEMI RILEVATI - non usate ancora il database per i dati veri")
        sys.exit(2)


if __name__ == "__main__":
    main()
