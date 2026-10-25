"""
Copia di sicurezza del database SQLite. Usa la funzione di backup di
SQLite, quindi la copia è coerente anche se il collega sta lavorando sul
database in quel momento (una semplice copia del file non lo sarebbe).

Conserva solo le copie più recenti (predefinito: 30).

Uso:
    python backup_sqlite.py --db "\\\\server\\condivisa\\verifiche.sqlite" --cartella "\\\\server\\condivisa\\backup"
    python backup_sqlite.py --db "..." --cartella "..." --conserva 60
"""

import argparse
import glob
import os
import sqlite3
import sys
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description="Backup del database SQLite")
    parser.add_argument("--db", required=True, help="Percorso del database")
    parser.add_argument("--cartella", required=True, help="Cartella in cui salvare le copie")
    parser.add_argument("--conserva", type=int, default=30, help="Numero di copie da conservare")
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        print(f"Database non trovato: {args.db}")
        sys.exit(1)
    os.makedirs(args.cartella, exist_ok=True)

    nome_base = os.path.splitext(os.path.basename(args.db))[0]
    destinazione = os.path.join(
        args.cartella, f"{nome_base}_{datetime.now():%Y-%m-%d_%H%M%S}.sqlite")

    src = sqlite3.connect(args.db, timeout=30)
    dst = sqlite3.connect(destinazione)
    try:
        src.backup(dst)
        esito = dst.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if esito != "ok":
        print(f"ATTENZIONE: la copia {destinazione} non supera il controllo di integrità: {esito}")
        sys.exit(2)
    print(f"Backup creato: {destinazione}")

    copie = sorted(glob.glob(os.path.join(args.cartella, f"{nome_base}_*.sqlite")))
    for vecchia in copie[:-args.conserva] if args.conserva > 0 else []:
        os.remove(vecchia)
        print(f"Rimossa copia vecchia: {vecchia}")


if __name__ == "__main__":
    main()
