"""
Crea l'anagrafica dei soggetti (ditte e liberi professionisti) nel
database creato da ods_a_sqlite.py, usando Partita IVA e Codice Fiscale
per riconoscere quando righe diverse si riferiscono allo stesso soggetto.

Regole:
- due righe sono lo stesso soggetto se hanno la stessa P.IVA valida
  OPPURE lo stesso Codice Fiscale valido;
- il nome NON viene mai usato per unire soggetti (serve solo come
  etichetta): due omonimi con codici diversi restano separati;
- i casi dubbi non vengono decisi in automatico ma elencati nella tabella
  "revisione_ditte" e nel file revisione_ditte.csv (si apre con Calc).

Cosa crea o aggiorna nel database:
- tabella "ditte": un soggetto per riga, con P.IVA e Codice Fiscale;
- tabella "ditte_nomi": tutti i modi in cui il nome è scritto nel foglio;
- colonna "richieste.ditta_id": collegamento di ogni richiesta al soggetto;
- tabella "revisione_ditte": casi da controllare a mano;
- viste "v_stato_attuale" e "v_in_scadenza_30gg", che ora raggruppano
  per soggetto (ditta_id) invece che per nome.

Lo script ricostruisce l'anagrafica da capo ogni volta: correggete i
codici nel foglio (o nella tabella richieste) e rilanciatelo.
Serve SOLO nella fase di migrazione: quando inizierete a inserire le
richieste da Base, l'anagrafica andrà gestita dalla tabella "ditte".

Uso:
    python crea_anagrafica_ditte.py --db "verifiche.sqlite"
    python crea_anagrafica_ditte.py --db "..." --csv "C:\\percorso\\revisione_ditte.csv"
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict

GRAVE = "DA CONTROLLARE"
INFO = "INFORMAZIONE"

ETICHETTE_CAMPI = {
    "partita_iva": "Partita IVA non valida",
    "codice_fiscale": "Codice fiscale non valido",
    "cf_piva": "Codice fiscale / P.IVA non valido",
}


# ----------------------------------------------------------------------
# CONTROLLO DEI CODICI
# ----------------------------------------------------------------------

def piva_valida(s):
    """Controllo della cifra finale di una partita IVA (11 cifre). Lo stesso
    algoritmo vale per il codice fiscale numerico di società ed enti."""
    if not re.fullmatch(r"\d{11}", s) or s == "0" * 11:
        return False
    somma = 0
    for i, c in enumerate(s[:10]):
        n = int(c)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        somma += n
    return (10 - somma % 10) % 10 == int(s[10])


_CF_DISPARI = {
    "0": 1, "1": 0, "2": 5, "3": 7, "4": 9, "5": 13, "6": 15, "7": 17, "8": 19, "9": 21,
    "A": 1, "B": 0, "C": 5, "D": 7, "E": 9, "F": 13, "G": 15, "H": 17, "I": 19, "J": 21,
    "K": 2, "L": 4, "M": 18, "N": 20, "O": 11, "P": 3, "Q": 6, "R": 8, "S": 12, "T": 14,
    "U": 16, "V": 10, "W": 22, "X": 25, "Y": 24, "Z": 23,
}
# cifre ammesse al posto dei numeri nei codici "omocodici"
_CF_SCHEMA = re.compile(r"[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]")


def cf_persona_valido(s):
    """Controllo del codice fiscale di 16 caratteri (persone fisiche)."""
    if not _CF_SCHEMA.fullmatch(s):
        return False
    somma = 0
    for i, c in enumerate(s[:15]):
        if i % 2 == 0:
            somma += _CF_DISPARI[c]
        else:
            somma += int(c) if c.isdigit() else ord(c) - ord("A")
    return chr(ord("A") + somma % 26) == s[15]


def pulisci(valore):
    """Maiuscolo, senza spazi/punti/trattini/barre e senza prefisso IT."""
    s = re.sub(r"[\s.\-/]", "", (valore or "").upper())
    if re.fullmatch(r"IT\d{11}", s):
        s = s[2:]
    return s


def completa_zeri(s):
    """Una P.IVA numerica con meno di 11 cifre ha quasi sempre perso gli zeri
    iniziali (la cella è stata trattata come numero): li rimette."""
    if re.fullmatch(r"\d{7,10}", s):
        return s.zfill(11)
    return s


def analizza_codice(valore, campo):
    """Restituisce (tipo, codice, nota):
    tipo = 'piva' | 'cf' | None (vuoto) | 'errato'.
    campo = 'partita_iva' | 'codice_fiscale' | 'cf_piva'."""
    grezzo = (valore or "").strip()
    s = pulisci(grezzo)
    if not s:
        return None, None, None
    nota = None
    if re.fullmatch(r"\d{7,10}", s):
        completo = completa_zeri(s)
        if piva_valida(completo):
            nota = f"zeri iniziali aggiunti: {grezzo} -> {completo}"
            s = completo
    if len(s) == 16 and campo != "partita_iva":
        return ("cf", s, nota) if cf_persona_valido(s) else ("errato", grezzo, None)
    if len(s) == 11 and piva_valida(s):
        # nel campo codice fiscale un codice di 11 cifre è il CF di una società
        return ("cf" if campo == "codice_fiscale" else "piva"), s, nota
    return "errato", grezzo, None


# ----------------------------------------------------------------------
# NORMALIZZAZIONE DEI NOMI (stessa funzione di interroga_verifiche.py)
# Usata SOLO per segnalare possibili omonimi, mai per unire soggetti.
# ----------------------------------------------------------------------

def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\([^)]*\)", " ", s)
    for w in ["mandante", "mandataria", "mandatario", "capogruppo"]:
        s = re.sub(rf"\b{w}\b", " ", s)
    s = re.sub(r"s\.?\s?r\.?\s?l\.?\s?s\.?", "srls", s)
    s = re.sub(r"s\.?\s?r\.?\s?l\.?", "srl", s)
    s = re.sub(r"s\.?\s?p\.?\s?a\.?", "spa", s)
    s = re.sub(r"s\.?\s?c\.?\s?a\.?\s?r\.?\s?l\.?", "scarl", s)
    s = re.sub(r"soc\.?\s?coop\.?", "soc coop", s)
    s = re.sub(r"\b(ing|arch|geol|avv|prof|dott)\b\.?", " ", s)
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ----------------------------------------------------------------------
# ABBINAMENTO
# ----------------------------------------------------------------------

class Gruppi:
    """Union-find: unisce i codici che compaiono sulla stessa riga."""

    def __init__(self):
        self.padre = {}

    def trova(self, x):
        self.padre.setdefault(x, x)
        while self.padre[x] != x:
            self.padre[x] = self.padre[self.padre[x]]
            x = self.padre[x]
        return x

    def unisci(self, a, b):
        ra, rb = self.trova(a), self.trova(b)
        if ra != rb:
            self.padre[rb] = ra


def righe_txt(righe):
    numeri = sorted({r["riga_ods"] for r in righe if r["riga_ods"] is not None})
    altre = sum(1 for r in righe if r["riga_ods"] is None)
    testo = ", ".join(str(n) for n in numeri)
    if altre:
        testo += (", " if testo else "") + f"{altre} righe inserite nel database"
    return testo


def abbina(righe, colonne_codici):
    """Restituisce (soggetti, non_collegate, revisione).
    soggetti: lista di dict con righe, piva, cf, nomi.
    revisione: lista di dict (gravita, problema, righe, ...)."""
    revisione = []
    gruppi = Gruppi()
    codici_riga = {}

    for r in righe:
        codici = []
        for campo in colonne_codici:
            tipo, codice, nota = analizza_codice(r[campo], campo)
            if tipo in ("piva", "cf"):
                codici.append((tipo, codice))
                if nota:
                    revisione.append(dict(
                        gravita=INFO, problema=f"P.IVA/CF corretto ({nota})",
                        righe=[r], ditta=r["ditta"], suggerimento="Correggere il dato nel foglio"))
            elif tipo == "errato":
                revisione.append(dict(
                    gravita=GRAVE,
                    problema=f"{ETICHETTE_CAMPI[campo]}: {codice}",
                    righe=[r], ditta=r["ditta"],
                    suggerimento="Verificare il codice (cifra di controllo errata o formato sbagliato)"))
        codici_riga[r["id"]] = codici
        # si unisce sul codice e non sul tipo: il CF numerico di una società
        # coincide con la sua P.IVA, quindi una riga con il solo CF e una con
        # la sola P.IVA vengono riconosciute come lo stesso soggetto
        for _, c in codici[1:]:
            gruppi.unisci(codici[0][1], c)
        if codici:
            gruppi.trova(codici[0][1])

    per_gruppo = defaultdict(list)
    non_collegate = []
    for r in righe:
        codici = codici_riga[r["id"]]
        if codici:
            per_gruppo[gruppi.trova(codici[0][1])].append(r)
        else:
            non_collegate.append(r)

    soggetti = []
    for radice, membri in per_gruppo.items():
        piva_c, cf_c = Counter(), Counter()
        for r in membri:
            for tipo, codice in codici_riga[r["id"]]:
                (piva_c if tipo == "piva" else cf_c)[codice] += 1
        # nome più frequente; a parità il più recente
        conteggio = Counter((r["ditta"] or "").strip() for r in membri if (r["ditta"] or "").strip())
        def chiave_nome(nome):
            recente = max((r["data_richiesta"] or "", r["id"]) for r in membri
                          if (r["ditta"] or "").strip() == nome)
            return (conteggio[nome], recente)
        denominazione = max(conteggio, key=chiave_nome) if conteggio else "(senza nome)"
        s = dict(
            righe=membri,
            piva=piva_c.most_common(1)[0][0] if piva_c else None,
            cf=cf_c.most_common(1)[0][0] if cf_c else None,
            denominazione=denominazione,
            nomi=conteggio,
            tipo="persona fisica" if any(len(c) == 16 for c in cf_c) else "società/ente",
        )
        soggetti.append(s)
        if len(piva_c) > 1 or len(cf_c) > 1:
            dettagli = []
            if len(piva_c) > 1:
                dettagli.append("P.IVA " + ", ".join(sorted(piva_c)))
            if len(cf_c) > 1:
                dettagli.append("CF " + ", ".join(sorted(cf_c)))
            revisione.append(dict(
                gravita=GRAVE,
                problema="Stesso soggetto collegato a codici diversi: " + "; ".join(dettagli),
                righe=membri, soggetto=s, ditta=denominazione,
                suggerimento="Errore di battitura o soggetto che ha cambiato P.IVA: correggere o confermare"))

    soggetti.sort(key=lambda s: norm(s["denominazione"]))
    return soggetti, non_collegate, revisione


# ----------------------------------------------------------------------
# DATABASE
# ----------------------------------------------------------------------

def colonne_tabella(con, tabella):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{tabella}")')]


VISTE_SQL = """
CREATE VIEW v_stato_attuale AS
WITH ordinate AS (
    SELECT r.*,
           ROW_NUMBER() OVER (
               PARTITION BY COALESCE('id:' || r.ditta_id, 'nome:' || r.ditta), r.tipo_richiesta
               ORDER BY r.data_richiesta DESC, r.id DESC
           ) AS n
    FROM richieste r
    WHERE r.ditta_id IS NOT NULL OR (r.ditta IS NOT NULL AND r.ditta <> '')
)
SELECT o.id, o.riga_ods, o.ditta_id,
       COALESCE(d.denominazione, o.ditta) AS ditta,
       d.partita_iva, d.codice_fiscale,
       o.tipo_richiesta, {interventi} AS interventi,
       o.data_richiesta, o.ricevuto, o.data_scadenza, {regolarita} AS regolarita,
       CASE
           WHEN o.data_richiesta IS NULL THEN 'NESSUNA RICHIESTA'
           WHEN o.ricevuto IS NULL OR o.ricevuto < o.data_richiesta THEN 'IN ATTESA'
           WHEN o.data_scadenza IS NULL THEN 'RICEVUTA, SENZA SCADENZA'
           WHEN o.data_scadenza < date('now', 'localtime') THEN 'SCADUTA'
           ELSE 'VALIDA'
       END AS stato,
       -- la scadenza vale solo se la risposta è arrivata dopo la richiesta
       CASE
           WHEN o.ricevuto IS NOT NULL AND o.data_richiesta IS NOT NULL
                AND o.ricevuto >= o.data_richiesta
           THEN o.data_scadenza
       END AS scadenza_valida
FROM ordinate o
LEFT JOIN ditte d ON d.id = o.ditta_id
WHERE o.n = 1;

CREATE VIEW v_in_scadenza_30gg AS
SELECT *
FROM v_stato_attuale
WHERE stato = 'VALIDA'
  AND scadenza_valida <= date('now', 'localtime', '+30 day')
ORDER BY scadenza_valida;
"""


def ricostruisci(con, soggetti, non_collegate, revisione):
    cur = con.cursor()
    colonne = colonne_tabella(con, "richieste")

    cur.execute("DROP VIEW IF EXISTS v_in_scadenza_30gg")
    cur.execute("DROP VIEW IF EXISTS v_stato_attuale")
    if "ditta_id" in colonne:
        cur.execute("UPDATE richieste SET ditta_id = NULL")
    cur.execute("DROP TABLE IF EXISTS revisione_ditte")
    cur.execute("DROP TABLE IF EXISTS ditte_nomi")
    cur.execute("DROP TABLE IF EXISTS ditte")

    cur.execute("""
        CREATE TABLE ditte (
            id INTEGER PRIMARY KEY,
            denominazione TEXT NOT NULL,
            partita_iva TEXT UNIQUE,
            codice_fiscale TEXT UNIQUE,
            tipo TEXT
        )""")
    cur.execute("""
        CREATE TABLE ditte_nomi (
            ditta_id INTEGER NOT NULL REFERENCES ditte(id),
            nome TEXT NOT NULL,
            n_righe INTEGER NOT NULL,
            PRIMARY KEY (ditta_id, nome)
        )""")
    cur.execute("""
        CREATE TABLE revisione_ditte (
            id INTEGER PRIMARY KEY,
            gravita TEXT,
            problema TEXT,
            righe_ods TEXT,
            ditta TEXT,
            ditta_id INTEGER,
            suggerimento TEXT
        )""")
    if "ditta_id" not in colonne:
        cur.execute("ALTER TABLE richieste ADD COLUMN ditta_id INTEGER REFERENCES ditte(id)")

    for s in soggetti:
        cur.execute(
            "INSERT INTO ditte (denominazione, partita_iva, codice_fiscale, tipo) VALUES (?, ?, ?, ?)",
            (s["denominazione"], s["piva"], s["cf"], s["tipo"]))
        s["id"] = cur.lastrowid
        cur.executemany("INSERT INTO ditte_nomi VALUES (?, ?, ?)",
                        [(s["id"], nome, n) for nome, n in s["nomi"].items()])
        cur.executemany("UPDATE richieste SET ditta_id = ? WHERE id = ?",
                        [(s["id"], r["id"]) for r in s["righe"]])

    # stesso nome (normalizzato) attribuito a soggetti con codici diversi
    per_nome = defaultdict(set)
    for s in soggetti:
        for nome in s["nomi"]:
            if norm(nome):
                per_nome[norm(nome)].add(s["id"])
    for nome_n, ids in sorted(per_nome.items()):
        if len(ids) > 1:
            coinvolti = [s for s in soggetti if s["id"] in ids]
            revisione.append(dict(
                gravita=GRAVE,
                problema="Stesso nome con codici diversi: "
                         + "; ".join(f"id {s['id']} P.IVA {s['piva'] or '-'} CF {s['cf'] or '-'}" for s in coinvolti),
                righe=[r for s in coinvolti for r in s["righe"]],
                ditta=coinvolti[0]["denominazione"],
                suggerimento="Omonimi (lasciare così) oppure codice sbagliato in una delle righe"))

    for r in non_collegate:
        simili = sorted(per_nome.get(norm(r["ditta"]), set()))
        revisione.append(dict(
            gravita=GRAVE,
            problema="Nessun codice valido: richiesta non collegata a un soggetto",
            righe=[r], ditta=r["ditta"],
            suggerimento=("Possibile soggetto con lo stesso nome: id " + ", ".join(map(str, simili))
                          if simili else "Inserire P.IVA o codice fiscale nel foglio")))

    righe_revisione = []
    for v in revisione:
        ditta_id = v.get("soggetto", {}).get("id") if v.get("soggetto") else None
        righe_revisione.append((v["gravita"], v["problema"], righe_txt(v["righe"]),
                                v["ditta"], ditta_id, v["suggerimento"]))
    righe_revisione.sort(key=lambda x: (x[0] != GRAVE, x[1]))
    cur.executemany(
        "INSERT INTO revisione_ditte (gravita, problema, righe_ods, ditta, ditta_id, suggerimento) "
        "VALUES (?, ?, ?, ?, ?, ?)", righe_revisione)

    cur.executescript(VISTE_SQL.format(
        interventi="o.interventi" if "interventi" in colonne else "NULL",
        regolarita="o.regolarita" if "regolarita" in colonne else "NULL"))
    cur.execute("CREATE INDEX IF NOT EXISTS idx_richieste_ditta_id ON richieste (ditta_id, tipo_richiesta, data_richiesta)")
    con.commit()
    return righe_revisione


def scrivi_csv(percorso, righe_revisione):
    # utf-8-sig e ";" perché Calc lo apra direttamente con accenti corretti
    with open(percorso, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Gravità", "Problema", "Righe del foglio", "Ditta", "Id soggetto", "Suggerimento"])
        w.writerows(righe_revisione)


# ----------------------------------------------------------------------
# PROGRAMMA PRINCIPALE
# ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Crea l'anagrafica ditte da P.IVA e codice fiscale")
    parser.add_argument("--db", required=True, help="Database creato da ods_a_sqlite.py")
    parser.add_argument("--csv", help="Dove salvare l'elenco dei casi da controllare "
                                      "(predefinito: revisione_ditte.csv accanto al database)")
    parser.add_argument("--forza", action="store_true",
                        help="Ricostruisce anche se nel database ci sono richieste inserite a mano")
    args = parser.parse_args()

    if not os.path.isfile(args.db):
        print(f"Database non trovato: {args.db}")
        sys.exit(1)
    percorso_csv = args.csv or os.path.join(os.path.dirname(os.path.abspath(args.db)), "revisione_ditte.csv")

    con = sqlite3.connect(args.db, timeout=30)
    try:
        colonne = colonne_tabella(con, "richieste")
        colonne_codici = [c for c in ("partita_iva", "codice_fiscale", "cf_piva") if c in colonne]
        if not colonne_codici:
            print("Nel database non ci sono colonne di Partita IVA o Codice Fiscale.")
            print("Intestazioni importate dal foglio:")
            for intest, nome in con.execute("SELECT intestazione_ods, nome_sql FROM colonne_origine"):
                print(f"  {intest!r} -> {nome}")
            print("Rilanciate ods_a_sqlite.py dopo aver controllato i nomi delle colonne, "
                  "oppure segnalatemi l'intestazione esatta.")
            sys.exit(1)

        if "ditta_id" in colonne and not args.forza:
            manuali = con.execute(
                "SELECT COUNT(*) FROM richieste WHERE riga_ods IS NULL AND ditta_id IS NOT NULL").fetchone()[0]
            if manuali:
                print(f"Ci sono {manuali} richieste inserite nel database e collegate a un soggetto.")
                print("Ricostruire l'anagrafica perderebbe quei collegamenti. "
                      "Usate --forza solo se siete sicuri.")
                sys.exit(1)

        campi = ", ".join(["id", "riga_ods", "ditta", "data_richiesta"] + colonne_codici)
        con.row_factory = sqlite3.Row
        righe = [dict(r) for r in con.execute(f"SELECT {campi} FROM richieste ORDER BY id")]
        con.row_factory = None

        soggetti, non_collegate, revisione = abbina(righe, colonne_codici)
        righe_revisione = ricostruisci(con, soggetti, non_collegate, revisione)
    finally:
        con.close()

    scrivi_csv(percorso_csv, righe_revisione)

    collegate = sum(len(s["righe"]) for s in soggetti)
    da_controllare = Counter(p for g, p, *_ in righe_revisione if g == GRAVE)
    informazioni = sum(1 for g, *_ in righe_revisione if g == INFO)
    print(f"Colonne dei codici usate: {', '.join(colonne_codici)}")
    print(f"Soggetti creati nella tabella ditte : {len(soggetti)}")
    print(f"  di cui persone fisiche            : {sum(1 for s in soggetti if s['tipo'] == 'persona fisica')}")
    print(f"  con più modi di scrivere il nome  : {sum(1 for s in soggetti if len(s['nomi']) > 1)}")
    print(f"Richieste collegate a un soggetto   : {collegate} su {len(righe)}")
    print(f"Richieste NON collegate             : {len(non_collegate)}")
    print(f"Casi da controllare                 : {sum(da_controllare.values())}")
    for problema, n in sorted(Counter(p.split(':')[0] for p in da_controllare.elements()).items()):
        print(f"  {problema}: {n}")
    print(f"Correzioni automatiche (solo info)  : {informazioni}")
    print(f"Elenco dettagliato: {percorso_csv}")


if __name__ == "__main__":
    main()
