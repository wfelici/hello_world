"""
Converte il foglio "Tutti" di monitoraggio_verifiche.ods in un database
SQLite, da usare come prova per il passaggio da Calc a un database
condiviso sulla cartella di rete.

Il file ODS viene SOLO letto: non viene mai modificato.

Cosa crea nel database:
- tabella "richieste": una riga per ogni riga del foglio, con le date
  convertite in vere date (formato AAAA-MM-GG);
- tabella "colonne_origine": corrispondenza tra intestazione originale
  del foglio e nome della colonna nel database;
- tabella "anomalie_import": valori che non è stato possibile
  interpretare (es. una data scritta male), da correggere a mano;
- vista "v_stato_attuale": ultima richiesta per ogni ditta + tipo, con
  lo stato calcolato (VALIDA, SCADUTA, IN ATTESA, ...) secondo la stessa
  regola dello script interroga_verifiche.py;
- vista "v_in_scadenza_30gg": certificazioni valide che scadono entro
  30 giorni.

Usa solo la libreria standard di Python (va bene WinPython così com'è).

Uso:
    python ods_a_sqlite.py --ods "monitoraggio_verifiche.ods" --db "verifiche.sqlite"
    python ods_a_sqlite.py --ods "..." --db "..." --sovrascrivi
"""

import argparse
import os
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime

NS_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
NS_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
NS_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"

TAG_TABLE = f"{{{NS_TABLE}}}table"
TAG_ROW = f"{{{NS_TABLE}}}table-row"
TAG_CELL = f"{{{NS_TABLE}}}table-cell"
TAG_COVERED = f"{{{NS_TABLE}}}covered-table-cell"
TAG_HEADER_ROWS = f"{{{NS_TABLE}}}table-header-rows"
# contenitori che possono racchiudere righe (gruppi/struttura del foglio)
TAG_ROW_CONTAINERS = {
    f"{{{NS_TABLE}}}table-row-group",
    f"{{{NS_TABLE}}}table-rows",
}

NOME_FOGLIO = "Tutti"

# Colonne note: intestazione nel foglio -> (nome nel database, tipo).
# Le colonne del foglio non elencate qui vengono comunque importate,
# con un nome ricavato dall'intestazione.
COLONNE_NOTE = {
    "INTERVENTI": ("interventi", "TEXT"),
    "RTI": ("rti", "TEXT"),
    "AGGIUDICATARIO": ("aggiudicatario", "TEXT"),
    "CIG": ("cig", "TEXT"),
    "CUP": ("cup", "TEXT"),
    "DITTA / LIBERI PROFESSIONISTI": ("ditta", "TEXT"),
    "TIPO RICHIESTA": ("tipo_richiesta", "TEXT"),
    "DATA RICHIESTA": ("data_richiesta", "DATE"),
    "PROTOCOLLO RISPONDENTE": ("protocollo_rispondente", "TEXT"),
    "RICEVUTO": ("ricevuto", "DATE"),
    "DATA SCADENZA": ("data_scadenza", "DATE"),
    "REGOLARITÀ": ("regolarita", "TEXT"),
    "NOTE/CRITICITÀ": ("note", "TEXT"),
}

# Colonne riconosciute anche se l'intestazione è scritta in modi diversi.
# Il confronto avviene sull'intestazione ridotta a sole lettere e cifre
# maiuscole (es. "P. IVA" -> "PIVA", "C.F." -> "CF").
ALIAS_COLONNE = {
    "PARTITAIVA": "partita_iva",
    "PIVA": "partita_iva",
    "CODICEFISCALE": "codice_fiscale",
    "CF": "codice_fiscale",
    # una sola colonna che contiene l'uno o l'altro codice
    "CFPIVA": "cf_piva",
    "PIVACF": "cf_piva",
    "CODICEFISCALEPARTITAIVA": "cf_piva",
    "PARTITAIVACODICEFISCALE": "cf_piva",
    "CODICEFISCALEPIVA": "cf_piva",
    "PIVACODICEFISCALE": "cf_piva",
    "CFPARTITAIVA": "cf_piva",
    "PARTITAIVACF": "cf_piva",
}

# Colonne indispensabili per le viste di stato
COLONNE_OBBLIGATORIE = ["ditta", "tipo_richiesta", "data_richiesta", "ricevuto", "data_scadenza"]

# Limite di sicurezza per righe ripetute (number-rows-repeated) non vuote
MAX_RIPETIZIONI_RIGA = 1000


# ----------------------------------------------------------------------
# LETTURA DEL FILE ODS
# ----------------------------------------------------------------------

class Cella:
    """Testo visualizzato della cella e, se la cella è una data vera di
    Calc, il suo valore in formato AAAA-MM-GG."""

    __slots__ = ("testo", "data_iso")

    def __init__(self, testo="", data_iso=None):
        self.testo = testo
        self.data_iso = data_iso


def leggi_cella(cell):
    if cell.tag == TAG_COVERED:
        # parte "coperta" di una cella unita: occupa una colonna ma è vuota
        return Cella()
    ps = cell.findall(f".//{{{NS_TEXT}}}p")
    testo = " ".join("".join(p.itertext()) for p in ps).strip()
    data_iso = None
    if cell.get(f"{{{NS_OFFICE}}}value-type") == "date":
        valore = cell.get(f"{{{NS_OFFICE}}}date-value", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}", valore):
            data_iso = valore[:10]
    return Cella(testo, data_iso)


def espandi_riga(row):
    """Restituisce la lista delle celle della riga, espandendo le celle
    ripetute (number-columns-repeated) e contando anche le celle unite."""
    risultato = []
    for cell in row:
        if cell.tag not in (TAG_CELL, TAG_COVERED):
            continue
        ripeti = int(cell.get(f"{{{NS_TABLE}}}number-columns-repeated", 1))
        c = leggi_cella(cell)
        if not c.testo and ripeti > 1:
            # celle vuote ripetute (spesso migliaia a fine riga)
            risultato.extend(Cella() for _ in range(min(ripeti, 1024)))
        else:
            risultato.extend(c if i == 0 else Cella(c.testo, c.data_iso) for i in range(ripeti))
    return risultato


def raccogli_righe(elemento, intestazione, dati):
    """Scorre il foglio anche dentro i gruppi di righe e separa le righe
    di intestazione "bloccate" (table-header-rows) da quelle di dati."""
    for figlio in elemento:
        if figlio.tag == TAG_HEADER_ROWS:
            raccogli_righe(figlio, intestazione, intestazione)
        elif figlio.tag == TAG_ROW:
            dati.append(figlio)
        elif figlio.tag in TAG_ROW_CONTAINERS:
            raccogli_righe(figlio, intestazione, dati)


def carica_foglio(percorso_ods, nome_foglio=NOME_FOGLIO):
    """Restituisce (intestazioni, righe) dove righe è una lista di
    (numero_riga_nel_foglio, [Cella, ...])."""
    with zipfile.ZipFile(percorso_ods) as z:
        with z.open("content.xml") as f:
            tree = ET.fromstring(f.read())

    tabelle = tree.iter(TAG_TABLE)
    tabella = None
    for t in tabelle:
        if t.get(f"{{{NS_TABLE}}}name") == nome_foglio:
            tabella = t
            break
    if tabella is None:
        raise ValueError(f"Foglio '{nome_foglio}' non trovato in {percorso_ods}")

    righe_intestazione, righe_dati = [], []
    raccogli_righe(tabella, righe_intestazione, righe_dati)

    if righe_intestazione:
        riga_intestazione = righe_intestazione[0]
        numero_riga = 1 + len(righe_intestazione)
    else:
        if not righe_dati:
            return [], []
        riga_intestazione = righe_dati.pop(0)
        numero_riga = 2
    intestazioni = [c.testo.strip() for c in espandi_riga(riga_intestazione)]

    righe = []
    for r in righe_dati:
        ripeti = int(r.get(f"{{{NS_TABLE}}}number-rows-repeated", 1))
        celle = espandi_riga(r)
        if any(c.testo for c in celle):
            for _ in range(min(ripeti, MAX_RIPETIZIONI_RIGA)):
                righe.append((numero_riga, celle))
                numero_riga += 1
            numero_riga += max(0, ripeti - MAX_RIPETIZIONI_RIGA)
        else:
            numero_riga += ripeti
    return intestazioni, righe


# ----------------------------------------------------------------------
# CONVERSIONE DEI VALORI
# ----------------------------------------------------------------------

def data_da_testo(s):
    """Interpreta una data scritta come testo. Restituisce AAAA-MM-GG o None."""
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def valore_data(cella):
    """(data_iso, ok). ok=False se la cella non è vuota ma non è una data."""
    if cella.data_iso:
        return cella.data_iso, True
    if not cella.testo:
        return None, True
    d = data_da_testo(cella.testo)
    return d, d is not None


def nome_sql(intestazione):
    """Ricava un nome di colonna semplice: minuscole, senza accenti, con _."""
    s = unicodedata.normalize("NFKD", intestazione).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    if not s:
        s = "colonna"
    if s[0].isdigit():
        s = "c_" + s
    return s


def definisci_colonne(intestazioni, righe):
    """Restituisce la lista di (indice, intestazione, nome_sql, tipo)."""
    colonne, usati = [], set()
    for i, intest in enumerate(intestazioni):
        if not intest:
            continue
        compatta = re.sub(r"[^A-Z0-9]", "", nome_sql(intest).upper())
        if intest in COLONNE_NOTE:
            nome, tipo = COLONNE_NOTE[intest]
        elif compatta in ALIAS_COLONNE:
            # codici fiscali e partite IVA restano sempre testo
            nome, tipo = ALIAS_COLONNE[compatta], "TEXT"
        else:
            nome = nome_sql(intest)
            # colonna non prevista: è una data se TUTTI i valori lo sono
            valori = [r[1][i] for r in righe if i < len(r[1]) and r[1][i].testo]
            tipo = "DATE" if valori and all(valore_data(c)[1] for c in valori) else "TEXT"
        base, n = nome, 2
        # "ditta_id" è riservata alla colonna aggiunta da crea_anagrafica_ditte.py
        while nome in usati or nome in ("id", "riga_ods", "ditta_id"):
            nome = f"{base}_{n}"
            n += 1
        usati.add(nome)
        colonne.append((i, intest, nome, tipo))
    return colonne


# ----------------------------------------------------------------------
# CREAZIONE DEL DATABASE
# ----------------------------------------------------------------------

VISTE_SQL = """
CREATE VIEW v_stato_attuale AS
WITH ordinate AS (
    SELECT r.*,
           ROW_NUMBER() OVER (
               PARTITION BY ditta, tipo_richiesta
               ORDER BY data_richiesta DESC, id DESC
           ) AS n
    FROM richieste r
    WHERE ditta IS NOT NULL AND ditta <> ''
)
SELECT id, riga_ods, ditta, tipo_richiesta, interventi_info AS interventi,
       data_richiesta, ricevuto, data_scadenza, regolarita_info AS regolarita,
       CASE
           WHEN data_richiesta IS NULL THEN 'NESSUNA RICHIESTA'
           WHEN ricevuto IS NULL OR ricevuto < data_richiesta THEN 'IN ATTESA'
           WHEN data_scadenza IS NULL THEN 'RICEVUTA, SENZA SCADENZA'
           WHEN data_scadenza < date('now', 'localtime') THEN 'SCADUTA'
           ELSE 'VALIDA'
       END AS stato,
       -- la scadenza vale solo se la risposta è arrivata dopo la richiesta
       CASE
           WHEN ricevuto IS NOT NULL AND data_richiesta IS NOT NULL
                AND ricevuto >= data_richiesta
           THEN data_scadenza
       END AS scadenza_valida
FROM ordinate
WHERE n = 1;

CREATE VIEW v_in_scadenza_30gg AS
SELECT *
FROM v_stato_attuale
WHERE stato = 'VALIDA'
  AND scadenza_valida <= date('now', 'localtime', '+30 day')
ORDER BY scadenza_valida;
"""


def crea_database(percorso_db, colonne, righe):
    con = sqlite3.connect(percorso_db)
    try:
        cur = con.cursor()
        # modalità di journal classica: la modalità WAL NON funziona
        # sulle cartelle di rete
        cur.execute("PRAGMA journal_mode=DELETE")
        cur.execute("PRAGMA foreign_keys=ON")

        definizioni = ",\n    ".join(f'"{nome}" {tipo}' for _, _, nome, tipo in colonne)
        cur.execute(f"""
            CREATE TABLE richieste (
                id INTEGER PRIMARY KEY,
                riga_ods INTEGER,
                {definizioni}
            )""")
        cur.execute("""
            CREATE TABLE colonne_origine (
                nome_sql TEXT PRIMARY KEY,
                intestazione_ods TEXT NOT NULL,
                tipo TEXT NOT NULL
            )""")
        cur.execute("""
            CREATE TABLE anomalie_import (
                id INTEGER PRIMARY KEY,
                riga_ods INTEGER,
                colonna TEXT,
                valore TEXT,
                motivo TEXT
            )""")
        cur.executemany(
            "INSERT INTO colonne_origine VALUES (?, ?, ?)",
            [(nome, intest, tipo) for _, intest, nome, tipo in colonne],
        )

        nomi = ", ".join(f'"{nome}"' for _, _, nome, _ in colonne)
        segnaposto = ", ".join("?" for _ in range(len(colonne) + 1))
        sql_insert = f"INSERT INTO richieste (riga_ods, {nomi}) VALUES ({segnaposto})"
        anomalie = []
        for numero_riga, celle in righe:
            valori = [numero_riga]
            for i, intest, nome, tipo in colonne:
                cella = celle[i] if i < len(celle) else Cella()
                if tipo == "DATE":
                    data, ok = valore_data(cella)
                    if not ok:
                        anomalie.append((numero_riga, intest, cella.testo,
                                         "non è una data riconoscibile"))
                    valori.append(data)
                else:
                    valori.append(cella.testo or None)
            cur.execute(sql_insert, valori)
        cur.executemany(
            "INSERT INTO anomalie_import (riga_ods, colonna, valore, motivo) VALUES (?, ?, ?, ?)",
            anomalie,
        )

        presenti = {nome for _, _, nome, _ in colonne}
        mancanti = [c for c in COLONNE_OBBLIGATORIE if c not in presenti]
        if mancanti:
            print("ATTENZIONE: mancano le colonne " + ", ".join(mancanti)
                  + ": le viste di stato non vengono create.")
        else:
            viste = VISTE_SQL
            # interventi e regolarità sono facoltativi
            viste = viste.replace("interventi_info", "interventi" if "interventi" in presenti else "NULL")
            viste = viste.replace("regolarita_info", "regolarita" if "regolarita" in presenti else "NULL")
            cur.executescript(viste)
            cur.execute("CREATE INDEX idx_richieste_ditta_tipo ON richieste (ditta, tipo_richiesta, data_richiesta)")
            cur.execute("CREATE INDEX idx_richieste_scadenza ON richieste (data_scadenza)")

        con.commit()
        return len(anomalie)
    finally:
        con.close()


# ----------------------------------------------------------------------
# PROGRAMMA PRINCIPALE
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Converte monitoraggio_verifiche.ods in SQLite")
    parser.add_argument("--ods", required=True, help="Percorso di monitoraggio_verifiche.ods")
    parser.add_argument("--db", required=True, help="Percorso del database SQLite da creare")
    parser.add_argument("--foglio", default=NOME_FOGLIO, help="Nome del foglio (predefinito: Tutti)")
    parser.add_argument("--sovrascrivi", action="store_true",
                        help="Cancella e ricrea il database se esiste già")
    args = parser.parse_args()

    if not os.path.isfile(args.ods):
        print(f"File non trovato: {args.ods}")
        sys.exit(1)
    if os.path.exists(args.db):
        if not args.sovrascrivi:
            print(f"Il database {args.db} esiste già. Usa --sovrascrivi per ricrearlo "
                  "(attenzione: le modifiche fatte nel database andranno perse).")
            sys.exit(1)
        os.remove(args.db)

    intestazioni, righe = carica_foglio(args.ods, args.foglio)
    if not intestazioni:
        print("Il foglio è vuoto o senza intestazioni.")
        sys.exit(1)
    colonne = definisci_colonne(intestazioni, righe)

    n_anomalie = crea_database(args.db, colonne, righe)

    print(f"Database creato: {args.db}")
    print(f"  Righe importate : {len(righe)}")
    print(f"  Colonne         : {len(colonne)}")
    for _, intest, nome, tipo in colonne:
        print(f"    {intest!r:40} -> {nome} ({tipo})")
    if n_anomalie:
        print(f"  ATTENZIONE: {n_anomalie} valori non interpretati, vedi la tabella anomalie_import")
    else:
        print("  Nessuna anomalia.")


if __name__ == "__main__":
    main()
