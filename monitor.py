diff --git a/monitor.py b/monitor.py
index f9a4c988171a7aae4e8bd0cd54ae0ea2ed3bee75..bc03d59f0771f8aa77fd7244f93b383fbb498cf1 100644
--- a/monitor.py
+++ b/monitor.py
@@ -1,1114 +1,707 @@
-import requests
-import pandas as pd
-import time
-import threading
-import os
 import json
-import psycopg2
-import psycopg2.extras
-from datetime import datetime
-from flask import Flask, request, jsonify
-
-# v6.3 + PostgreSQL — dados persistentes entre restarts
-
-HELIUS_API_KEY = "4f586430-90ef-4c8f-9800-b98bfe5f1151"
-TELEGRAM_TOKEN = "8319320909:AAFnhGkFS1YxhthhE4RolutJScEjBCjIvrA"
-TELEGRAM_CHAT  = "-5284184650"
-DASHBOARD_KEY  = "neide12"
-DATABASE_URL   = os.environ.get("DATABASE_URL", "postgresql://postgres:OgNvgWkjcpuFxZPHBaASjCKnLNsXKlpI@switchyard.proxy.rlwy.net:47120/railway")
-
-CARTEIRAS = {
-    "GijFWw4oNyh9ko3FaZforNsi3jk6wDovARpkKahPD4o5": "carteira_A",
-    "ANfB2knFb7pC7jKadHnSP4xKZ31KJGNLhWRo89LWsFeW": "carteira_B",
-    "43C9gHfJ7YgqKv5ft3hodFgumydv1nEiNHD1PuANufk5": "carteira_C",
-    "EvGpkcSBfhp5K9SNP48wVtfNXdKYRBiK3kvMkB66kU3Q": "carteira_D",
-}
-
-TIPO_CARTEIRA = {
-    "carteira_A": "bot",
-    "carteira_B": "bot",
-    "carteira_C": "humano",
-    "carteira_D": "humano",
-}
-
-TOKENS_IGNORAR = {
-    "So11111111111111111111111111111111111111112",
-    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
-    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
-    "8S4Hk9bMLTTCBzBrFGSRcPbHiWbVXKpmWHvEMPEELXXt",
-    "11111111111111111111111111111111",
-}
-
-# Estado em memória (cache — o banco é a fonte de verdade)
-estado = {
-    nome: {
-        "tokens_conhecidos": set(),
-        "registros":         [],
-        "pendentes":         {},
-    }
-    for nome in set(CARTEIRAS.values())
-}
+import os
+import sqlite3
+from contextlib import closing
+from datetime import date, datetime
+from pathlib import Path
+from typing import Any
 
-mints_globais     = {}
-signatures_vistas = set()
-app = Flask(__name__)
+from flask import Flask, jsonify, render_template, request, send_from_directory
+from werkzeug.utils import secure_filename
 
-@app.after_request
-def add_cors(response):
-    response.headers["Access-Control-Allow-Origin"]  = "*"
-    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
-    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
-    return response
-
-
-# ══════════════════════════════════════════════════════════
-# BANCO DE DADOS
-# ══════════════════════════════════════════════════════════
-def get_conn():
-    return psycopg2.connect(DATABASE_URL)
-
-
-def init_db():
-    with get_conn() as conn:
-        with conn.cursor() as cur:
-            cur.execute("""
-                CREATE TABLE IF NOT EXISTS registros (
-                    id              SERIAL PRIMARY KEY,
-                    data_compra     TIMESTAMP,
-                    carteira        TEXT,
-                    tipo_carteira   TEXT,
-                    token_mint      TEXT,
-                    nome            TEXT,
-                    dex             TEXT,
-                    fonte_dados     TEXT,
-                    quantidade      FLOAT,
-                    signature       TEXT,
-                    tipo            TEXT,
-                    is_multi        BOOLEAN DEFAULT FALSE,
-                    p_t0            FLOAT,
-                    mc_t0           FLOAT,
-                    liq_t0          FLOAT,
-                    volume_t0       FLOAT,
-                    txns5m_t0       INT,
-                    buys_t0         INT,
-                    sells_t0        INT,
-                    net_momentum_t0 INT,
-                    idade_min       FLOAT,
-                    token_antigo    TEXT,
-                    ratio_vol_mc_t0 FLOAT,
-                    score_qualidade INT,
-                    holders_count   INT,
-                    top1_pct        FLOAT,
-                    top10_pct       FLOAT,
-                    dev_saiu        BOOLEAN,
-                    bc_progress     FLOAT,
-                    p_t1 FLOAT, mc_t1 FLOAT, liq_t1 FLOAT, volume_t1 FLOAT,
-                    txns5m_t1 INT, buys_t1 INT, sells_t1 INT,
-                    ratio_vol_mc_t1 FLOAT, var_t1 FLOAT, veredito_t1 TEXT,
-                    p_t2 FLOAT, mc_t2 FLOAT, liq_t2 FLOAT, volume_t2 FLOAT,
-                    txns5m_t2 INT, buys_t2 INT, sells_t2 INT,
-                    ratio_vol_mc_t2 FLOAT, var_t2 FLOAT, veredito_t2 TEXT,
-                    p_t3 FLOAT, mc_t3 FLOAT, liq_t3 FLOAT, volume_t3 FLOAT,
-                    txns5m_t3 INT, buys_t3 INT, sells_t3 INT,
-                    ratio_vol_mc_t3 FLOAT, var_t3 FLOAT, veredito_t3 TEXT,
-                    mc_pico         FLOAT,
-                    var_pico        FLOAT,
-                    categoria_final TEXT,
-                    var_desde_compra FLOAT
-                )
-            """)
-            cur.execute("CREATE INDEX IF NOT EXISTS idx_token_mint ON registros(token_mint)")
-            cur.execute("CREATE INDEX IF NOT EXISTS idx_carteira ON registros(carteira)")
-            cur.execute("CREATE INDEX IF NOT EXISTS idx_data ON registros(data_compra)")
-            cur.execute("""
-                CREATE TABLE IF NOT EXISTS signatures (
-                    sig TEXT PRIMARY KEY
-                )
-            """)
-        conn.commit()
-    log("✅ Banco de dados inicializado")
-
-
-def db_insert(reg):
-    with get_conn() as conn:
-        with conn.cursor() as cur:
-            cur.execute("""
-                INSERT INTO registros (
-                    data_compra, carteira, tipo_carteira, token_mint, nome, dex,
-                    fonte_dados, quantidade, signature, tipo, is_multi,
-                    p_t0, mc_t0, liq_t0, volume_t0, txns5m_t0, buys_t0, sells_t0,
-                    net_momentum_t0, idade_min, token_antigo, ratio_vol_mc_t0,
-                    score_qualidade, holders_count, top1_pct, top10_pct,
-                    dev_saiu, bc_progress, mc_pico, categoria_final,
-                    var_desde_compra
-                ) VALUES (
-                    %(data_compra)s, %(carteira)s, %(tipo_carteira)s, %(token_mint)s,
-                    %(nome)s, %(dex)s, %(fonte_dados)s, %(quantidade)s, %(signature)s,
-                    %(tipo)s, %(is_multi)s, %(p_t0)s, %(mc_t0)s, %(liq_t0)s,
-                    %(volume_t0)s, %(txns5m_t0)s, %(buys_t0)s, %(sells_t0)s,
-                    %(net_momentum_t0)s, %(idade_min)s, %(token_antigo)s,
-                    %(ratio_vol_mc_t0)s, %(score_qualidade)s, %(holders_count)s,
-                    %(top1_pct)s, %(top10_pct)s, %(dev_saiu)s, %(bc_progress)s,
-                    %(mc_pico)s, %(categoria_final)s, %(var_desde_compra)s
-                ) RETURNING id
-            """, reg)
-            row_id = cur.fetchone()[0]
-        conn.commit()
-    return row_id
-
-
-def db_update_checkpoint(row_id, checkpoint, preco, mc, liq, volume, txns, buys, sells, ratio, var, veredito, mc_pico):
-    n = checkpoint  # t1, t2, t3
-    with get_conn() as conn:
-        with conn.cursor() as cur:
-            cur.execute(f"""
-                UPDATE registros SET
-                    p_{n}=%s, mc_{n}=%s, liq_{n}=%s, volume_{n}=%s,
-                    txns5m_{n}=%s, buys_{n}=%s, sells_{n}=%s,
-                    ratio_vol_mc_{n}=%s, var_{n}=%s, veredito_{n}=%s,
-                    mc_pico=%s
-                WHERE id=%s
-            """, (preco, mc, liq, volume, txns, buys, sells, ratio, var, veredito, mc_pico, row_id))
-        conn.commit()
+BASE_DIR = Path(__file__).resolve().parent
+DB_PATH = BASE_DIR / "silk_manager.db"
+UPLOAD_DIR = BASE_DIR / "uploads"
+UPLOAD_DIR.mkdir(exist_ok=True)
 
+ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "svg", "ai", "cdr"}
 
-def db_update_final(row_id, mc_pico, var_pico, categoria):
-    with get_conn() as conn:
-        with conn.cursor() as cur:
-            cur.execute("""
-                UPDATE registros SET mc_pico=%s, var_pico=%s, categoria_final=%s
-                WHERE id=%s
-            """, (mc_pico, var_pico, categoria, row_id))
+app = Flask(__name__)
+app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15MB
+
+
+def get_conn() -> sqlite3.Connection:
+    conn = sqlite3.connect(DB_PATH)
+    conn.row_factory = sqlite3.Row
+    return conn
+
+
+def init_db() -> None:
+    with closing(get_conn()) as conn:
+        cur = conn.cursor()
+        cur.executescript(
+            """
+            CREATE TABLE IF NOT EXISTS clients (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                name TEXT NOT NULL,
+                company TEXT,
+                phone TEXT,
+                email TEXT,
+                address TEXT,
+                document TEXT,
+                notes TEXT,
+                created_at TEXT NOT NULL
+            );
+
+            CREATE TABLE IF NOT EXISTS quotes (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                client_id INTEGER NOT NULL,
+                product_type TEXT NOT NULL,
+                quantity INTEGER NOT NULL,
+                colors_count INTEGER NOT NULL,
+                value REAL NOT NULL,
+                notes TEXT,
+                status TEXT NOT NULL DEFAULT 'orçamento',
+                created_at TEXT NOT NULL,
+                FOREIGN KEY(client_id) REFERENCES clients(id)
+            );
+
+            CREATE TABLE IF NOT EXISTS orders (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                client_id INTEGER NOT NULL,
+                quote_id INTEGER,
+                order_date TEXT NOT NULL,
+                due_date TEXT NOT NULL,
+                status TEXT NOT NULL,
+                product_type TEXT NOT NULL,
+                total_quantity INTEGER NOT NULL,
+                sizes TEXT,
+                colors_count INTEGER NOT NULL,
+                pantone_codes TEXT,
+                print_image_path TEXT,
+                attachments TEXT,
+                notes TEXT,
+                material_origin TEXT NOT NULL,
+                price REAL NOT NULL,
+                created_at TEXT NOT NULL,
+                updated_at TEXT NOT NULL,
+                FOREIGN KEY(client_id) REFERENCES clients(id),
+                FOREIGN KEY(quote_id) REFERENCES quotes(id)
+            );
+
+            CREATE TABLE IF NOT EXISTS order_history (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                order_id INTEGER NOT NULL,
+                changed_at TEXT NOT NULL,
+                changed_by TEXT NOT NULL,
+                field_name TEXT NOT NULL,
+                old_value TEXT,
+                new_value TEXT,
+                FOREIGN KEY(order_id) REFERENCES orders(id)
+            );
+
+            CREATE TABLE IF NOT EXISTS financial_entries (
+                id INTEGER PRIMARY KEY AUTOINCREMENT,
+                kind TEXT NOT NULL,
+                client_or_vendor TEXT,
+                value REAL NOT NULL,
+                entry_date TEXT NOT NULL,
+                category TEXT,
+                order_id INTEGER,
+                notes TEXT,
+                created_at TEXT NOT NULL,
+                FOREIGN KEY(order_id) REFERENCES orders(id)
+            );
+            """
+        )
         conn.commit()
 
 
-def db_update_multi(row_id):
-    with get_conn() as conn:
-        with conn.cursor() as cur:
-            cur.execute("UPDATE registros SET is_multi=TRUE WHERE id=%s", (row_id,))
+def seed_data() -> None:
+    with closing(get_conn()) as conn:
+        cur = conn.cursor()
+        cur.execute("SELECT COUNT(*) as total FROM clients")
+        if cur.fetchone()["total"] > 0:
+            return
+
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+        today = date.today().strftime("%Y-%m-%d")
+        tomorrow = date.fromordinal(date.today().toordinal() + 1).strftime("%Y-%m-%d")
+
+        cur.execute(
+            """INSERT INTO clients (name, company, phone, email, address, document, notes, created_at)
+               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+            (
+                "Joana Silva",
+                "Brinde Sul",
+                "(11) 99999-1001",
+                "joana@brindesul.com",
+                "Rua das Oficinas, 88 - SP",
+                "12.345.678/0001-90",
+                "Cliente com recorrência mensal",
+                now,
+            ),
+        )
+        client_id = cur.lastrowid
+
+        cur.execute(
+            """INSERT INTO quotes (client_id, product_type, quantity, colors_count, value, notes, status, created_at)
+               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+            (client_id, "Ecobag algodão", 1200, 2, 6840.0, "Impressão frente e verso", "aprovado", now),
+        )
+        quote_id = cur.lastrowid
+
+        cur.execute(
+            """INSERT INTO orders (
+                client_id, quote_id, order_date, due_date, status, product_type, total_quantity,
+                sizes, colors_count, pantone_codes, print_image_path, attachments, notes,
+                material_origin, price, created_at, updated_at
+            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
+            (
+                client_id,
+                quote_id,
+                today,
+                tomorrow,
+                "aguardando produção",
+                "Ecobag algodão",
+                1200,
+                json.dumps({"único": 1200}, ensure_ascii=False),
+                2,
+                "Pantone 186 C, Pantone Black C",
+                None,
+                json.dumps([]),
+                "Prioridade: evento no final de semana",
+                "fornecido pelo cliente",
+                6840.0,
+                now,
+                now,
+            ),
+        )
+        order_id = cur.lastrowid
+
+        cur.execute(
+            """INSERT INTO financial_entries
+               (kind, client_or_vendor, value, entry_date, category, order_id, notes, created_at)
+               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+            (
+                "entrada",
+                "Brinde Sul",
+                3420.0,
+                today,
+                "pagamento parcial",
+                order_id,
+                "50% na aprovação",
+                now,
+            ),
+        )
         conn.commit()
 
 
-def db_carregar_estado():
-    """Carrega dados do banco para memória ao iniciar."""
-    try:
-        with get_conn() as conn:
-            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
-                cur.execute("SELECT sig FROM signatures")
-                for row in cur.fetchall():
-                    signatures_vistas.add(row["sig"])
-
-                cur.execute("SELECT * FROM registros ORDER BY data_compra")
-                rows = cur.fetchall()
-
-        log(f"📂 Carregando {len(rows)} registros do banco...")
-        for row in rows:
-            reg = dict(row)
-            # Normaliza nomes de colunas para compatibilidade com código existente
-            reg["var_t1_%"] = reg.pop("var_t1", None)
-            reg["var_t2_%"] = reg.pop("var_t2", None)
-            reg["var_t3_%"] = reg.pop("var_t3", None)
-            reg["var_pico_%"] = reg.pop("var_pico", None)
-            if reg.get("data_compra"):
-                reg["data_compra"] = reg["data_compra"].strftime("%Y-%m-%d %H:%M:%S")
-
-            nome = reg.get("carteira")
-            if nome and nome in estado:
-                idx = len(estado[nome]["registros"])
-                estado[nome]["registros"].append(reg)
-                estado[nome]["tokens_conhecidos"].add(reg["token_mint"])
-                # Tokens ainda pendentes (sem categoria final ou aguardando)
-                if reg.get("categoria_final") == "⏳ aguardando" and reg.get("tipo") == "COMPRA":
-                    mint = reg["token_mint"]
-                    db_id = reg["id"]
-                    # Calcular quanto tempo passou desde a compra
-                    try:
-                        dt_compra = datetime.strptime(reg["data_compra"], "%Y-%m-%d %H:%M:%S")
-                        segundos_passados = (datetime.now() - dt_compra).total_seconds()
-                    except:
-                        segundos_passados = 9999
-
-                    # Se passou mais de 2 horas, finalizar como sem dados
-                    if segundos_passados > 7200:
-                        log(f"⚠️  Token preso há {segundos_passados/3600:.1f}h — finalizando: {reg.get('nome','?')}")
-                        cat = "❓ DADOS INCOMPLETOS — restart perdeu checkpoints"
-                        try:
-                            db_update_final(db_id, reg.get("mc_pico") or reg.get("mc_t0") or 0, None, cat)
-                            reg["categoria_final"] = cat
-                        except Exception as e:
-                            log(f"⚠️  Erro ao finalizar token preso: {e}")
-                        continue  # não adiciona aos pendentes
-
-                    # Reagendar checkpoints restantes
-                    estado[nome]["pendentes"][mint] = {"idx": idx, "db_id": db_id}
-                    # Checkpoints principais
-                    if reg.get("mc_t1") is None:
-                        delay = max(0, 300 - segundos_passados)
-                        threading.Timer(delay, checar_checkpoint, args=[nome, mint, "t1"]).start()
-                    if reg.get("mc_t2") is None:
-                        delay = max(0, 900 - segundos_passados)
-                        threading.Timer(delay, checar_checkpoint, args=[nome, mint, "t2"]).start()
-                    if reg.get("mc_t3") is None:
-                        delay = max(0, 2700 - segundos_passados)
-                        threading.Timer(delay, checar_checkpoint, args=[nome, mint, "t3"]).start()
-                    # Snapshots intermediários de pico
-                    if segundos_passados < 120:
-                        threading.Timer(max(0, 120 - segundos_passados), atualizar_pico, args=[nome, mint, "2min"]).start()
-                    if segundos_passados < 600:
-                        threading.Timer(max(0, 600 - segundos_passados), atualizar_pico, args=[nome, mint, "10min"]).start()
-                    if segundos_passados < 1500:
-                        threading.Timer(max(0, 1500 - segundos_passados), atualizar_pico, args=[nome, mint, "25min"]).start()
-
-        log(f"✅ Estado restaurado — {sum(len(estado[n]['registros']) for n in estado)} registros em memória")
-    except Exception as e:
-        log(f"⚠️  Erro ao carregar estado do banco: {e}")
-
-
-def db_sig_add(sig):
-    try:
-        with get_conn() as conn:
-            with conn.cursor() as cur:
-                cur.execute("INSERT INTO signatures(sig) VALUES(%s) ON CONFLICT DO NOTHING", (sig,))
-            conn.commit()
-    except:
-        pass
+def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
+    return {k: row[k] for k in row.keys()}
 
 
-def log(msg):
-    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)
+def allowed_file(filename: str) -> bool:
+    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
 
 
-def telegram(msg):
-    try:
-        r = requests.post(
-            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
-            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "HTML"},
-            timeout=10,
+def save_history(order_id: int, field_name: str, old: Any, new: Any) -> None:
+    if str(old) == str(new):
+        return
+    with closing(get_conn()) as conn:
+        conn.execute(
+            """INSERT INTO order_history (order_id, changed_at, changed_by, field_name, old_value, new_value)
+               VALUES (?, ?, ?, ?, ?, ?)""",
+            (
+                order_id,
+                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
+                "sistema",
+                field_name,
+                "" if old is None else str(old),
+                "" if new is None else str(new),
+            ),
         )
-        if r.status_code != 200:
-            log(f"Telegram erro {r.status_code}: {r.text[:100]}")
-    except Exception as e:
-        log(f"Telegram erro: {e}")
-
-
-def telegram_documento(caminho, caption=""):
-    try:
-        with open(caminho, "rb") as f:
-            requests.post(
-                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
-                data={"chat_id": TELEGRAM_CHAT, "caption": caption, "parse_mode": "HTML"},
-                files={"document": f},
-                timeout=30,
+        conn.commit()
+
+
+@app.route("/")
+def index():
+    return render_template("index.html")
+
+
+@app.route("/uploads/<path:filename>")
+def uploaded_file(filename: str):
+    return send_from_directory(UPLOAD_DIR, filename)
+
+
+@app.route("/api/clients", methods=["GET", "POST"])
+def clients_handler():
+    if request.method == "POST":
+        data = request.json
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+        with closing(get_conn()) as conn:
+            cur = conn.execute(
+                """INSERT INTO clients (name, company, phone, email, address, document, notes, created_at)
+                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+                (
+                    data["name"],
+                    data.get("company"),
+                    data.get("phone"),
+                    data.get("email"),
+                    data.get("address"),
+                    data.get("document"),
+                    data.get("notes"),
+                    now,
+                ),
             )
-    except Exception as e:
-        log(f"Telegram doc erro: {e}")
-
-
-def calcular_momentum(buys, sells):
-    buys = buys or 0
-    sells = sells or 0
-    total = buys + sells
-    if total == 0:
-        return None, 0
-    net = buys - sells
-    blocos = round(buys / total * 8)
-    barra = "🟢" * blocos + "⬜" * (8 - blocos)
-    sinal = "+" if net >= 0 else ""
-    return f"{barra} {sinal}{net} ({buys}B / {sells}S)", net
-
-
-def classificar_momentum(net, total):
-    if not total: return ""
-    if net >= 10:  return "🔥 Comprando forte"
-    if net >= 5:   return "📈 Pressão compradora"
-    if net >= 0:   return "➡️  Equilibrado"
-    if net >= -5:  return "📉 Pressão vendedora"
-    return "🧊 Vendendo forte"
-
-
-def calcular_score(mc_t0, liq_t0, txns, ratio_vol_mc, idade_min, dex):
-    score = 0
-    if ratio_vol_mc and ratio_vol_mc >= 3:     score += 3
-    elif ratio_vol_mc and ratio_vol_mc >= 1.5: score += 2
-    elif ratio_vol_mc and ratio_vol_mc >= 1:   score += 1
-    if txns and 100 <= txns <= 450:            score += 2
-    elif txns and txns < 100:                  score += 1
-    elif txns and txns > 500:                  score -= 2
-    if liq_t0 == 0:                            score += 2
-    if idade_min and idade_min <= 15:          score += 2
-    elif idade_min and idade_min <= 30:        score += 1
-    if dex == "pumpfun":                       score += 1
-    if ratio_vol_mc and ratio_vol_mc < 0.8:    score -= 2
-    score = max(0, min(10, score))
-    if score >= 7:   return score, "🟢", "ALTA CONFIANÇA"
-    elif score >= 4: return score, "🟡", "MODERADO"
-    else:            return score, "🔴", "BAIXA CONFIANÇA"
-
-
-def veredito_parcial(mc_anterior, mc_atual, tempo):
-    if not mc_anterior or not mc_atual or mc_anterior == 0:
-        return "❓ sem dados"
-    var = (mc_atual - mc_anterior) / mc_anterior * 100
-    if   var >  200: return f"🚀 +{var:.0f}% em {tempo} — EXPLOSIVO"
-    elif var >   50: return f"📈 +{var:.0f}% em {tempo} — FORTE"
-    elif var >   10: return f"📊 +{var:.0f}% em {tempo} — SUBINDO"
-    elif var >  -10: return f"➡️  {var:.0f}% em {tempo} — ESTÁVEL"
-    elif var >  -50: return f"📉 {var:.0f}% em {tempo} — FRAQUEJANDO"
-    else:            return f"💀 {var:.0f}% em {tempo} — COLAPSANDO"
-
-
-def categoria_final(reg):
-    mc0 = reg.get("mc_t0") or 0
-    mc1 = reg.get("mc_t1") or 0
-    mc2 = reg.get("mc_t2") or 0
-    mc3 = reg.get("mc_t3") or 0
-    if mc0 == 0: return "❓ SEM DADOS"
-
-    var_t1 = reg.get("var_t1_%")
-    var_t2 = reg.get("var_t2_%")
-    var_t3 = reg.get("var_t3_%")
-
-    # Detectar morte após pico: T1 alto mas T2/T3 zerados ou muito negativos
-    t2_morreu = mc2 == 0 or (var_t2 is not None and var_t2 < -70)
-    t3_morreu = mc3 == 0 or (var_t3 is not None and var_t3 < -70)
-
-    if var_t1 and var_t1 > 50 and t2_morreu:
-        return "🎯 PUMP & DUMP — Morreu após T1"
-    if var_t1 and var_t1 > 50 and mc3 > 0 and t3_morreu:
-        return "🎯 PUMP & DUMP — Morreu após pico"
-
-    pico = max(mc1, mc2, mc3)
-    var_pico  = (pico - mc0) / mc0 * 100 if mc0 else 0
-    var_final = (mc3  - mc0) / mc0 * 100 if mc0 and mc3 else None
-
-    if   var_pico > 200 and var_final and var_final >  100: return "🏆 VENCEDOR — Subiu forte e manteve"
-    elif var_pico > 200 and var_final and var_final <    0: return "🎯 PUMP & DUMP — Subiu e colapsou"
-    elif var_pico >  50 and var_final and var_final >   20: return "📈 BOM TRADE — Crescimento sólido"
-    elif var_pico >  50 and var_final and var_final <  -20: return "⚠️  ARMADILHA — Pico rápido e queda"
-    elif var_final and var_final >  20:                     return "📊 CRESCIMENTO ESTÁVEL"
-    elif var_final and var_final > -20:                     return "➡️  LATERAL — Pouco movimento"
-    elif var_final is not None:                             return "💀 MORREU — Queda consistente"
-    else:                                                   return "❓ DADOS INCOMPLETOS"
-
-
-def get_dados_token(mint):
-    preco = mc = liq = volume = 0
-    dex = nome = "?"
-    txns_5min = buys_5min = sells_5min = 0
-    idade_min = None
-    fonte = "dexscreener"
-    try:
-        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{mint}", timeout=8)
-        pairs = r.json().get("pairs") or []
-        if pairs:
-            par        = sorted(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0) or 0, reverse=True)[0]
-            preco      = float(par["priceUsd"]) if par.get("priceUsd") else None
-            mc         = par.get("marketCap") or 0
-            liq        = par.get("liquidity", {}).get("usd") or 0
-            volume     = par.get("volume", {}).get("h24") or 0
-            dex        = par.get("dexId", "?")
-            nome       = par.get("baseToken", {}).get("name", "?")
-            m5         = par.get("txns", {}).get("m5", {})
-            buys_5min  = m5.get("buys", 0)
-            sells_5min = m5.get("sells", 0)
-            txns_5min  = buys_5min + sells_5min
-            criado_ts  = par.get("pairCreatedAt")
-            if criado_ts:
-                idade_min = round((time.time() - criado_ts / 1000) / 60, 1)
-            if mc > 0:
-                return preco, mc, liq, volume, dex, nome, txns_5min, idade_min, fonte, buys_5min, sells_5min
-    except:
-        pass
-    fonte = "pumpfun"
-    dex   = "pumpfun"
-    try:
-        r = requests.post(
-            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
-            json={"jsonrpc": "2.0", "id": 1, "method": "getAsset", "params": {"id": mint}},
-            timeout=8,
-        )
-        if r.status_code == 200:
-            asset     = r.json().get("result", {})
-            nome      = asset.get("content", {}).get("metadata", {}).get("name", "?")
-            criado_ts = asset.get("createdAt")
-            if criado_ts:
-                idade_min = round((time.time() - criado_ts) / 60, 1)
-    except:
-        pass
-    try:
-        r = requests.post(
-            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
-            json={"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]},
-            timeout=8,
-        )
-        if r.status_code == 200:
-            result      = r.json().get("result", {}).get("value", {})
-            supply      = float(result.get("uiAmount", 0))
-            sol_price   = get_sol_price()
-            tokens_sold = max(0, 1_000_000_000 - supply)
-            virtual_sol = 30 + (tokens_sold / 1_000_000_000) * 800
-            preco_sol   = virtual_sol / (793_000_000 - tokens_sold) if tokens_sold < 793_000_000 else 0
-            preco       = preco_sol * sol_price if sol_price else None
-            mc          = round(preco * 1_000_000_000, 0) if preco else 0
-            liq         = round(virtual_sol * sol_price, 0) if sol_price else 0
-    except:
-        pass
-    return preco, mc, liq, volume, dex, nome, txns_5min, idade_min, fonte, buys_5min, sells_5min
-
-
-def get_sol_price():
-    try:
-        r = requests.get(
-            "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd",
-            timeout=5,
-        )
-        return r.json().get("solana", {}).get("usd", 0)
-    except:
-        return 0
-
-
-def get_holder_data(mint, liq_t0=0, dev_wallet=None):
-    holders_count = top1_pct = top10_pct = dev_saiu = bc_progress = None
-    if liq_t0 == 0:
-        try:
-            r = requests.get(
-                f"https://frontend-api.pump.fun/coins/{mint}",
-                timeout=8, headers={"User-Agent": "Mozilla/5.0"},
+            conn.commit()
+        return jsonify({"id": cur.lastrowid, "message": "Cliente criado com sucesso."}), 201
+
+    with closing(get_conn()) as conn:
+        rows = conn.execute(
+            """
+            SELECT c.*,
+                COUNT(DISTINCT o.id) AS total_orders,
+                COUNT(DISTINCT q.id) AS total_quotes,
+                COALESCE(SUM(o.price), 0) AS total_purchased,
+                MAX(o.order_date) AS last_order_date
+            FROM clients c
+            LEFT JOIN orders o ON o.client_id = c.id
+            LEFT JOIN quotes q ON q.client_id = c.id
+            GROUP BY c.id
+            ORDER BY c.name
+            """
+        ).fetchall()
+    return jsonify([row_to_dict(row) for row in rows])
+
+
+@app.route("/api/quotes", methods=["GET", "POST"])
+def quotes_handler():
+    if request.method == "POST":
+        data = request.json
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+        with closing(get_conn()) as conn:
+            cur = conn.execute(
+                """INSERT INTO quotes (client_id, product_type, quantity, colors_count, value, notes, status, created_at)
+                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+                (
+                    data["client_id"],
+                    data["product_type"],
+                    data["quantity"],
+                    data["colors_count"],
+                    data["value"],
+                    data.get("notes"),
+                    data.get("status", "orçamento"),
+                    now,
+                ),
             )
-            if r.status_code == 200:
-                data          = r.json()
-                holders_count = data.get("holder_count")
-                bc_progress   = data.get("bonding_curve_progress")
-                dev_wallet_bc = data.get("creator")
-                if dev_wallet_bc:
-                    try:
-                        r2 = requests.get(
-                            f"https://frontend-api.pump.fun/coins/{mint}/holders",
-                            timeout=8, headers={"User-Agent": "Mozilla/5.0"},
-                        )
-                        if r2.status_code == 200:
-                            holders_list = r2.json()
-                            top_wallets  = [h.get("owner", "") for h in holders_list[:20]]
-                            dev_saiu     = dev_wallet_bc not in top_wallets
-                            total_supply = 1_000_000_000
-                            # Endereços conhecidos de LP e bonding curve — excluir do cálculo
-                            LP_ADDRESSES = {
-                                "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",  # pump.fun bonding curve
-                                "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1", # raydium LP
-                                "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", # raydium authority
-                            }
-                            holders_validos = [h for h in holders_list if h.get("owner","") not in LP_ADDRESSES]
-                            if holders_validos:
-                                top10_pct = round(sum(h.get("balance", 0) for h in holders_validos[:10]) / total_supply * 100, 1)
-                                # top1 excluindo LP (para referência interna, não exibido)
-                                top1_pct  = round(holders_validos[0].get("balance", 0) / total_supply * 100, 1)
-                    except:
-                        pass
-        except Exception as e:
-            log(f"pump.fun holder erro: {e}")
-        return holders_count, top1_pct, top10_pct, dev_saiu, bc_progress
-    try:
-        r = requests.post(
-            f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
-            json={"jsonrpc": "2.0", "id": 1, "method": "getTokenSupply", "params": [mint]},
-            timeout=8,
+            conn.commit()
+        return jsonify({"id": cur.lastrowid, "message": "Orçamento salvo."}), 201
+
+    q = request.args.get("q", "")
+    with closing(get_conn()) as conn:
+        rows = conn.execute(
+            """
+            SELECT q.*, c.name AS client_name
+            FROM quotes q
+            JOIN clients c ON c.id = q.client_id
+            WHERE c.name LIKE ? OR q.product_type LIKE ?
+            ORDER BY q.created_at DESC
+            """,
+            (f"%{q}%", f"%{q}%"),
+        ).fetchall()
+    return jsonify([row_to_dict(row) for row in rows])
+
+
+@app.route("/api/quotes/<int:quote_id>/convert", methods=["POST"])
+def convert_quote(quote_id: int):
+    data = request.json or {}
+    due_date = data.get("due_date", date.today().strftime("%Y-%m-%d"))
+    with closing(get_conn()) as conn:
+        quote = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
+        if not quote:
+            return jsonify({"error": "Orçamento não encontrado."}), 404
+
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+        cur = conn.execute(
+            """INSERT INTO orders (
+                client_id, quote_id, order_date, due_date, status, product_type, total_quantity,
+                sizes, colors_count, pantone_codes, print_image_path, attachments, notes,
+                material_origin, price, created_at, updated_at
+            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
+            (
+                quote["client_id"],
+                quote_id,
+                date.today().strftime("%Y-%m-%d"),
+                due_date,
+                "aprovado",
+                quote["product_type"],
+                quote["quantity"],
+                json.dumps({"único": quote["quantity"]}, ensure_ascii=False),
+                quote["colors_count"],
+                "",
+                None,
+                json.dumps([]),
+                quote["notes"],
+                "vendido pela empresa",
+                quote["value"],
+                now,
+                now,
+            ),
         )
-        total_supply = 0
-        if r.status_code == 200:
-            total_supply = float(r.json().get("result", {}).get("value", {}).get("uiAmount", 0))
-        if total_supply > 0:
-            r2 = requests.post(
-                f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}",
-                json={"jsonrpc": "2.0", "id": 1, "method": "getTokenLargestAccounts", "params": [mint]},
-                timeout=8,
-            )
-            if r2.status_code == 200:
-                accounts = r2.json().get("result", {}).get("value", [])
-                if accounts:
-                    # Filtrar endereços de LP conhecidos
-                    LP_KNOWN = {
-                        "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
-                        "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1",
-                        "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1",
-                        "HVh6wHNBAsG3pq1Bj5oCzRjoWKVogEDHwUHkRz3ekFgt",  # raydium pool
-                    }
-                    accs_validos = [a for a in accounts if a.get("address","") not in LP_KNOWN]
-                    holders_count = len(accs_validos)
-                    if accs_validos:
-                        top10_pct = round(sum(float(a.get("uiAmount", 0)) for a in accs_validos[:10]) / total_supply * 100, 1)
-                        top1_pct  = round(float(accs_validos[0].get("uiAmount", 0)) / total_supply * 100, 1)
-                    if dev_wallet:
-                        dev_saiu = dev_wallet not in [a.get("address", "") for a in accs_validos]
-    except Exception as e:
-        log(f"helius holder erro: {e}")
-    return holders_count, top1_pct, top10_pct, dev_saiu, bc_progress
-
-
-def extrair_mudancas_token(tx, carteira_addr):
-    mudancas = {}
-    for conta in tx.get("accountData", []):
-        for change in conta.get("tokenBalanceChanges", []):
-            if change.get("userAccount") != carteira_addr:
-                continue
-            mint = change.get("mint", "")
-            if not mint or mint in TOKENS_IGNORAR:
-                continue
-            raw = change.get("rawTokenAmount", {})
+        conn.execute("UPDATE quotes SET status = 'aprovado' WHERE id = ?", (quote_id,))
+        conn.commit()
+    return jsonify({"order_id": cur.lastrowid, "message": "Orçamento convertido em pedido."})
+
+
+@app.route("/api/orders", methods=["GET", "POST"])
+def orders_handler():
+    if request.method == "POST":
+        data = request.form if request.form else request.json
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+
+        image_name = None
+        attachments = []
+        if "print_image" in request.files:
+            img = request.files["print_image"]
+            if img and allowed_file(img.filename):
+                image_name = f"{datetime.now().timestamp()}_{secure_filename(img.filename)}"
+                img.save(UPLOAD_DIR / image_name)
+
+        if "attachments" in request.files:
+            for file in request.files.getlist("attachments"):
+                if file and allowed_file(file.filename):
+                    file_name = f"{datetime.now().timestamp()}_{secure_filename(file.filename)}"
+                    file.save(UPLOAD_DIR / file_name)
+                    attachments.append(file_name)
+
+        sizes = data.get("sizes")
+        if isinstance(sizes, str):
             try:
-                amount = int(raw.get("tokenAmount", "0")) / (10 ** int(raw.get("decimals", 0)))
-            except:
-                continue
-            if amount != 0:
-                mudancas[mint] = mudancas.get(mint, 0) + amount
-    for transfer in tx.get("tokenTransfers", []):
-        mint     = transfer.get("mint", "")
-        to_acc   = transfer.get("toUserAccount", "")
-        from_acc = transfer.get("fromUserAccount", "")
-        if not mint or mint in TOKENS_IGNORAR:
-            continue
-        try:
-            amount = float(transfer.get("tokenAmount", 0))
-        except:
-            continue
-        if amount == 0:
-            continue
-        if to_acc == carteira_addr:
-            mudancas[mint] = mudancas.get(mint, 0) + amount
-        elif from_acc == carteira_addr:
-            mudancas[mint] = mudancas.get(mint, 0) - amount
-    return [{"mint": m, "amount": a} for m, a in mudancas.items()]
-
-
-def checar_multi_carteira(mint, nome_token, carteira_atual, mc_t0, liq_t0,
-                           ratio_vol_mc, idade_min, score, score_emoji, score_desc,
-                           holders_count=None, top1_pct=None, top10_pct=None,
-                           dev_saiu=None, bc_progress=None,
-                           buys_5min=0, sells_5min=0):
-    agora = time.time()
-    if mint not in mints_globais:
-        mints_globais[mint] = {}
-    mints_globais[mint][carteira_atual] = agora
-
-    recentes = {
-        c: ts for c, ts in mints_globais[mint].items()
-        if c != carteira_atual and (agora - ts) / 60 <= 60
-    }
-    if not recentes:
-        return False
-
-    timing_s = min(int(agora - ts) for ts in recentes.values())
-    if timing_s < 120:
-        timing_str = f"⚡ {timing_s}s"
-        urgencia   = "🚨🚨 SINCRONIZADO"
-    elif timing_s < 600:
-        timing_str = f"~{timing_s//60}min"
-        urgencia   = "🚨 MULTI-CARTEIRA"
-    else:
-        timing_str = f"{timing_s//60}min"
-        urgencia   = "ℹ️ MULTI-CARTEIRA"
-
-    todas   = list(recentes.keys()) + [carteira_atual]
-    humanos = [c for c in todas if TIPO_CARTEIRA.get(c) == "humano"]
-    # Salvar detalhes do multi para o dashboard
-    mints_globais[mint]["__multi_info__"] = {
-        "carteiras": todas,
-        "timing_s": timing_s,
-        "urgencia_nivel": 1 if timing_s < 120 else 2 if timing_s < 600 else 3,
-        "tem_humano": len(humanos) > 0,
-        "n_humanos": len(humanos),
-        "humanos": humanos,
-    }
-    if humanos:
-        urgencia = "⭐" * len(humanos) + " " + urgencia
-
-    def label(c):
-        i = "👤" if TIPO_CARTEIRA.get(c) == "humano" else "🤖"
-        return f"{i} <b>{c}</b>"
-
-    linhas = [f"  • {label(c)} comprou há {round((agora-ts)/60,1)} min" for c, ts in recentes.items()]
-
-    holder_linha = ""
-    if holders_count:         holder_linha += f"\n👥 Holders: <b>{holders_count}</b>"
-    if top1_pct is not None:  holder_linha += f" | Top: <b>{top1_pct}%</b>"
-    if top10_pct is not None: holder_linha += f" | Top10: <b>{top10_pct}%</b>"
-    if dev_saiu is True:      holder_linha += "\n✅ Dev saiu"
-    elif dev_saiu is False:   holder_linha += "\n⚠️ Dev ainda segura"
-    if bc_progress is not None: holder_linha += f"\n📈 BC: <b>{bc_progress:.0f}%</b>"
-
-    momentum_linha = ""
-    barra, net = calcular_momentum(buys_5min, sells_5min)
-    if barra:
-        momentum_linha = f"\n🔄 {barra}\n    {classificar_momentum(net, buys_5min + sells_5min)}"
-
-    icone = "👤" if TIPO_CARTEIRA.get(carteira_atual) == "humano" else "🤖"
-
-    telegram(
-        f"{urgencia}\n\n"
-        f"Token: <b>{nome_token}</b>\n"
-        f"Mint: <code>{mint}</code>\n\n"
-        f"{icone} <b>{carteira_atual}</b> comprou agora\n"
-        + "\n".join(linhas) + "\n\n"
-        f"⏱ Timing: <b>{timing_str}</b>\n\n"
-        f"💰 MC: <b>${mc_t0:,.0f}</b>\n"
-        f"💧 Liq: <b>${liq_t0:,.0f}</b>\n"
-        f"📊 Vol/MC: <b>{ratio_vol_mc:.1f}x</b>\n"
-        f"🕐 Idade: <b>{idade_min:.0f} min</b>"
-        f"{holder_linha}"
-        f"{momentum_linha}\n\n"
-        f"Score: {score_emoji} <b>{score}/10 — {score_desc}</b>\n\n"
-        f"🔗 https://pump.fun/{mint}"
-    )
-    log(f"🚨 MULTI: {nome_token} | {carteira_atual} + {list(recentes.keys())} | {timing_str}")
-    return True
-
-
-def processar_venda(carteira_addr, nome, mint, amount_vendido, tx):
-    est = estado[nome]
-    reg = next((r for r in est["registros"] if r.get("token_mint") == mint), None)
-    _, mc_atual, _, _, _, nome_token, _, _, _, _, _ = get_dados_token(mint)
-    nome_token = reg["nome"] if reg else nome_token
-    variacao = None
-    if reg and reg.get("p_t0"):
-        preco_atual, _, _, _, _, _, _, _, _, _, _ = get_dados_token(mint)
-        if preco_atual:
-            variacao = round((preco_atual - reg["p_t0"]) / reg["p_t0"] * 100, 2)
-    log(f"🔴 [{nome}] VENDA: {nome_token} | MC: ${mc_atual:,.0f} | variação: {f'{variacao:+.1f}%' if variacao is not None else '—'}")
-    data = datetime.fromtimestamp(tx.get("timestamp", time.time())).strftime("%Y-%m-%d %H:%M:%S")
-    reg_venda = {
-        "data_compra": data, "carteira": nome, "tipo_carteira": TIPO_CARTEIRA.get(nome, "?"),
-        "token_mint": mint, "nome": nome_token, "dex": "venda", "fonte_dados": "venda",
-        "quantidade": round(abs(amount_vendido), 4), "signature": tx.get("signature", ""),
-        "tipo": "VENDA", "is_multi": False,
-        "p_t0": None, "mc_t0": mc_atual, "liq_t0": None, "volume_t0": None,
-        "txns5m_t0": None, "buys_t0": None, "sells_t0": None, "net_momentum_t0": None,
-        "idade_min": None, "token_antigo": None, "ratio_vol_mc_t0": None,
-        "score_qualidade": None, "holders_count": None, "top1_pct": None,
-        "top10_pct": None, "dev_saiu": None, "bc_progress": None,
-        "mc_pico": None, "categoria_final": "🔴 VENDA", "var_desde_compra": variacao,
+                json.loads(sizes)
+            except json.JSONDecodeError:
+                sizes = json.dumps({"único": data.get("total_quantity", 0)}, ensure_ascii=False)
+
+        with closing(get_conn()) as conn:
+            cur = conn.execute(
+                """INSERT INTO orders (
+                    client_id, quote_id, order_date, due_date, status, product_type, total_quantity,
+                    sizes, colors_count, pantone_codes, print_image_path, attachments, notes,
+                    material_origin, price, created_at, updated_at
+                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
+                (
+                    int(data["client_id"]),
+                    data.get("quote_id"),
+                    data.get("order_date", date.today().strftime("%Y-%m-%d")),
+                    data["due_date"],
+                    data.get("status", "orçamento"),
+                    data["product_type"],
+                    int(data["total_quantity"]),
+                    sizes if sizes else json.dumps({"único": int(data["total_quantity"])}, ensure_ascii=False),
+                    int(data["colors_count"]),
+                    data.get("pantone_codes", ""),
+                    image_name,
+                    json.dumps(attachments, ensure_ascii=False),
+                    data.get("notes", ""),
+                    data.get("material_origin", "fornecido pelo cliente"),
+                    float(data["price"]),
+                    now,
+                    now,
+                ),
+            )
+            conn.commit()
+        return jsonify({"id": cur.lastrowid, "message": "Pedido criado com sucesso."}), 201
+
+    filters = {
+        "client": request.args.get("client"),
+        "status": request.args.get("status"),
+        "product": request.args.get("product"),
+        "date": request.args.get("date"),
     }
-    est["registros"].append(reg_venda)
-    try:
-        db_insert(reg_venda)
-    except Exception as e:
-        log(f"⚠️  DB insert venda erro: {e}")
-
-
-def agendar_checkpoints(nome, mint):
-    # Checkpoints principais — gravam dados no banco e dashboard
-    threading.Timer(5  * 60, checar_checkpoint, args=[nome, mint, "t1"]).start()
-    threading.Timer(15 * 60, checar_checkpoint, args=[nome, mint, "t2"]).start()
-    threading.Timer(45 * 60, checar_checkpoint, args=[nome, mint, "t3"]).start()
-    # Snapshots intermediários — só atualizam mc_pico se for maior
-    threading.Timer(2  * 60, atualizar_pico, args=[nome, mint, "2min"]).start()
-    threading.Timer(10 * 60, atualizar_pico, args=[nome, mint, "10min"]).start()
-    threading.Timer(25 * 60, atualizar_pico, args=[nome, mint, "25min"]).start()
-
-
-def atualizar_pico(nome, mint, label):
-    """Verifica o MC atual e atualiza mc_pico se for maior — sem alterar checkpoints."""
-    est = estado[nome]
-    if mint not in est["pendentes"]:
-        return
-    info = est["pendentes"][mint]
-    reg  = est["registros"][info["idx"]]
-    db_id = info.get("db_id")
-    try:
-        _, mc_atual, _, _, _, _, _, _, _, _, _ = get_dados_token(mint)
-        if not mc_atual or mc_atual == 0:
-            return
-        mc_pico_atual = reg.get("mc_pico") or 0
-        if mc_atual > mc_pico_atual:
-            reg["mc_pico"] = mc_atual
-            log(f"  📈 [{nome}] Pico atualizado {label}: {reg['nome'][:20]} | MC: ${mc_atual:,.0f} (era ${mc_pico_atual:,.0f})")
-            if db_id:
-                with get_conn() as conn:
-                    with conn.cursor() as cur:
-                        cur.execute("UPDATE registros SET mc_pico=%s WHERE id=%s", (mc_atual, db_id))
-                    conn.commit()
-    except Exception as e:
-        log(f"⚠️  atualizar_pico erro [{label}]: {e}")
-
-
-def checar_checkpoint(nome, mint, checkpoint):
-    est = estado[nome]
-    if mint not in est["pendentes"]:
-        return
-    info  = est["pendentes"][mint]
-    reg   = est["registros"][info["idx"]]
-    db_id = info.get("db_id")
-    preco, mc, liq, volume, _, _, txns_5min, _, _, buys, sells = get_dados_token(mint)
-    ratio = round(volume / reg["mc_t0"], 2) if reg.get("mc_t0", 0) > 0 else None
-
-    if checkpoint == "t1":
-        var_t1 = round((preco - reg["p_t0"]) / reg["p_t0"] * 100, 2) if preco and reg.get("p_t0") else None
-        veredito = veredito_parcial(reg["mc_t0"], mc, "5min")
-        mc_pico = max(mc, reg.get("mc_pico") or 0)
-        reg.update({
-            "p_t1": preco, "mc_t1": mc, "liq_t1": liq, "volume_t1": volume,
-            "txns5m_t1": txns_5min, "buys_t1": buys, "sells_t1": sells,
-            "ratio_vol_mc_t1": ratio, "var_t1_%": var_t1,
-            "veredito_t1": veredito, "mc_pico": mc_pico,
-        })
-        if db_id:
-            db_update_checkpoint(db_id, "t1", preco, mc, liq, volume, txns_5min, buys, sells, ratio, var_t1, veredito, mc_pico)
-        log(f"  ⏱️  [{nome}] T1 {reg['nome'][:20]} | MC: ${mc:,.0f} | {veredito}")
-        if reg.get("is_multi") and var_t1:
-            if var_t1 >= 100:
-                telegram(f"🚨 <b>SAÍDA — T1 EXPLOSIVO</b>\n\nToken: <b>{reg['nome']}</b>\n📈 T1: <b>+{var_t1:.0f}%</b> em 5min\n💰 MC: <b>${mc:,.0f}</b>\n\n⚠️ <i>Considere realizar lucro.</i>\n\n🔗 https://pump.fun/{reg['token_mint']}")
-            elif var_t1 >= 50:
-                telegram(f"⚠️ <b>SAÍDA — T1 FORTE</b>\n\nToken: <b>{reg['nome']}</b>\n📈 T1: <b>+{var_t1:.0f}%</b> em 5min\n💰 MC: <b>${mc:,.0f}</b>\n\n💡 <i>Considere realizar parte.</i>\n\n🔗 https://pump.fun/{reg['token_mint']}")
-
-    elif checkpoint == "t2":
-        var_t2 = round((preco - reg["p_t0"]) / reg["p_t0"] * 100, 2) if preco and reg.get("p_t0") else None
-        veredito = veredito_parcial(reg.get("mc_t1"), mc, "15min")
-        mc_pico = max(mc, reg.get("mc_pico") or 0)
-        reg.update({
-            "p_t2": preco, "mc_t2": mc, "liq_t2": liq, "volume_t2": volume,
-            "txns5m_t2": txns_5min, "buys_t2": buys, "sells_t2": sells,
-            "ratio_vol_mc_t2": ratio, "var_t2_%": var_t2,
-            "veredito_t2": veredito, "mc_pico": mc_pico,
-        })
-        if db_id:
-            db_update_checkpoint(db_id, "t2", preco, mc, liq, volume, txns_5min, buys, sells, ratio, var_t2, veredito, mc_pico)
-        log(f"  ⏱️  [{nome}] T2 {reg['nome'][:20]} | MC: ${mc:,.0f} | {veredito}")
-
-    elif checkpoint == "t3":
-        var_t3 = round((preco - reg["p_t0"]) / reg["p_t0"] * 100, 2) if preco and reg.get("p_t0") else None
-        veredito = veredito_parcial(reg.get("mc_t2"), mc, "45min")
-        mc_pico = max(mc, reg.get("mc_pico") or 0)
-        var_pico = round((mc_pico - reg["mc_t0"]) / reg["mc_t0"] * 100, 2) if reg.get("mc_t0") else None
-        cat = categoria_final({**reg, "mc_t3": mc})
-        reg.update({
-            "p_t3": preco, "mc_t3": mc, "liq_t3": liq, "volume_t3": volume,
-            "txns5m_t3": txns_5min, "buys_t3": buys, "sells_t3": sells,
-            "ratio_vol_mc_t3": ratio, "var_t3_%": var_t3,
-            "veredito_t3": veredito, "mc_pico": mc_pico,
-            "var_pico_%": var_pico, "categoria_final": cat,
-        })
-        if db_id:
-            db_update_checkpoint(db_id, "t3", preco, mc, liq, volume, txns_5min, buys, sells, ratio, var_t3, veredito, mc_pico)
-            db_update_final(db_id, mc_pico, var_pico, cat)
-        log(f"  ✅ [{nome}] FINAL {reg['nome'][:20]} | MC: ${mc:,.0f} | {cat}")
-        del est["pendentes"][mint]
-
-
-def processar_tx(tx, carteira_addr, nome):
-    est = estado[nome]
-    if tx.get("type") == "TRANSFER" and tx.get("source") == "SYSTEM_PROGRAM":
-        return
-    for mudanca in extrair_mudancas_token(tx, carteira_addr):
-        mint   = mudanca["mint"]
-        amount = mudanca["amount"]
-        if amount == 0:
-            continue
-        if amount < 0:
-            processar_venda(carteira_addr, nome, mint, amount, tx)
-            continue
-        if mint in est["tokens_conhecidos"]:
-            continue
-        est["tokens_conhecidos"].add(mint)
-
-        data = datetime.fromtimestamp(tx.get("timestamp", time.time())).strftime("%Y-%m-%d %H:%M:%S")
-        # Buscar dados com retentativa — tokens novos podem não estar indexados imediatamente
-        preco_t0, mc_t0, liq_t0, volume_t0, dex, nome_token, txns_5min, idade_min, fonte, buys_5min, sells_5min = get_dados_token(mint)
-        if not mc_t0 or mc_t0 == 0:
-            log(f"  ⏳ MC=0 na primeira tentativa para {nome_token[:20]}, aguardando 30s...")
-            time.sleep(30)
-            preco_t0, mc_t0, liq_t0, volume_t0, dex, nome_token, txns_5min, idade_min, fonte, buys_5min, sells_5min = get_dados_token(mint)
-        if not mc_t0 or mc_t0 == 0:
-            log(f"  ⏳ MC=0 na segunda tentativa, aguardando 60s...")
-            time.sleep(60)
-            preco_t0, mc_t0, liq_t0, volume_t0, dex, nome_token, txns_5min, idade_min, fonte, buys_5min, sells_5min = get_dados_token(mint)
-        if not mc_t0 or mc_t0 == 0:
-            log(f"  ⏳ MC=0 na terceira tentativa, aguardando 2min...")
-            time.sleep(120)
-            preco_t0, mc_t0, liq_t0, volume_t0, dex, nome_token, txns_5min, idade_min, fonte, buys_5min, sells_5min = get_dados_token(mint)
-
-        ratio_vol_mc_t0 = round(volume_t0 / mc_t0, 2) if mc_t0 > 0 else None
-        token_antigo    = "sim" if (idade_min and idade_min > 1440) else "não"
-        score, score_emoji, score_desc = calcular_score(mc_t0, liq_t0, txns_5min, ratio_vol_mc_t0, idade_min, dex)
-
-        holders_count = top1_pct = top10_pct = dev_saiu = bc_progress = None
-        try:
-            holders_count, top1_pct, top10_pct, dev_saiu, bc_progress = get_holder_data(mint, liq_t0=liq_t0)
-        except Exception as e:
-            log(f"holders erro [{nome_token}]: {e}")
-
-        flag_antigo = f" ⚠️ TOKEN ANTIGO ({idade_min/1440:.0f}d)" if token_antigo == "sim" else ""
-        # Token sem MC — registra no mints_globais para alertas multi funcionarem
-        if not mc_t0 or mc_t0 == 0:
-            log(f"⚠️  [{nome}] {nome_token} | MC=0 — token não indexado, ignorando checkpoints")
-            agora_ts = time.time()
-            if mint not in mints_globais:
-                mints_globais[mint] = {}
-            mints_globais[mint][nome] = agora_ts
-            outras = {c: ts for c, ts in mints_globais[mint].items()
-                      if c != nome and (agora_ts - ts) / 60 <= 60}
-            if outras:
-                outras_str = ", ".join(outras.keys())
-                timing_s = min(int(agora_ts - ts) for ts in outras.values())
-                telegram(
-                    f"🚨 <b>ALERTA MULTI-CARTEIRA</b> (MC não disponível)\n\n"
-                    f"Token: <b>{nome_token}</b>\n"
-                    f"Carteiras: <b>{outras_str}</b> + <b>{nome}</b>\n"
-                    f"⏱ Timing: <b>{timing_s}s</b>\n"
-                    f"⚠️ MC não indexado ainda\n\n"
-                    f"🔗 https://pump.fun/{mint}"
-                )
-            reg_sem_dados = {
-                "data_compra": data, "carteira": nome, "tipo_carteira": TIPO_CARTEIRA.get(nome, "?"),
-                "token_mint": mint, "nome": nome_token, "dex": dex, "fonte_dados": fonte,
-                "quantidade": round(amount, 4), "signature": tx.get("signature", ""),
-                "tipo": "COMPRA", "is_multi": False,
-                "p_t0": None, "mc_t0": 0, "liq_t0": liq_t0, "volume_t0": volume_t0,
-                "txns5m_t0": txns_5min, "buys_t0": buys_5min, "sells_t0": sells_5min,
-                "net_momentum_t0": 0, "idade_min": idade_min, "token_antigo": token_antigo,
-                "ratio_vol_mc_t0": None, "score_qualidade": 0,
-                "holders_count": None, "top1_pct": None, "top10_pct": None,
-                "dev_saiu": None, "bc_progress": None,
-                "p_t1": None, "mc_t1": None, "liq_t1": None, "volume_t1": None,
-                "txns5m_t1": None, "buys_t1": None, "sells_t1": None,
-                "ratio_vol_mc_t1": None, "var_t1_%": None, "veredito_t1": None,
-                "p_t2": None, "mc_t2": None, "liq_t2": None, "volume_t2": None,
-                "txns5m_t2": None, "buys_t2": None, "sells_t2": None,
-                "ratio_vol_mc_t2": None, "var_t2_%": None, "veredito_t2": None,
-                "p_t3": None, "mc_t3": None, "liq_t3": None, "volume_t3": None,
-                "txns5m_t3": None, "buys_t3": None, "sells_t3": None,
-                "ratio_vol_mc_t3": None, "var_t3_%": None, "veredito_t3": None,
-                "mc_pico": 0, "var_pico_%": None, "var_desde_compra": None,
-                "categoria_final": "❓ SEM DADOS — MC não disponível",
-            }
-            est["registros"].append(reg_sem_dados)
-            try:
-                db_insert(reg_sem_dados)
-            except Exception as e:
-                log(f"⚠️  DB insert sem dados erro: {e}")
-            continue
-
-        log(f"🆕 [{nome}] {nome_token} | {dex} | MC: ${mc_t0:,.0f} | Score: {score}/10{flag_antigo}")
-
-        reg = {
-            "data_compra": data, "carteira": nome, "tipo_carteira": TIPO_CARTEIRA.get(nome, "?"),
-            "token_mint": mint, "nome": nome_token, "dex": dex, "fonte_dados": fonte,
-            "quantidade": round(amount, 4), "signature": tx.get("signature", ""),
-            "tipo": "COMPRA", "is_multi": False,
-            "p_t0": preco_t0, "mc_t0": mc_t0, "liq_t0": liq_t0, "volume_t0": volume_t0,
-            "txns5m_t0": txns_5min, "buys_t0": buys_5min, "sells_t0": sells_5min,
-            "net_momentum_t0": (buys_5min or 0) - (sells_5min or 0),
-            "idade_min": idade_min, "token_antigo": token_antigo,
-            "ratio_vol_mc_t0": ratio_vol_mc_t0, "score_qualidade": score,
-            "holders_count": holders_count, "top1_pct": top1_pct,
-            "top10_pct": top10_pct, "dev_saiu": dev_saiu, "bc_progress": bc_progress,
-            "p_t1": None, "mc_t1": None, "liq_t1": None, "volume_t1": None,
-            "txns5m_t1": None, "buys_t1": None, "sells_t1": None,
-            "ratio_vol_mc_t1": None, "var_t1_%": None, "veredito_t1": None,
-            "p_t2": None, "mc_t2": None, "liq_t2": None, "volume_t2": None,
-            "txns5m_t2": None, "buys_t2": None, "sells_t2": None,
-            "ratio_vol_mc_t2": None, "var_t2_%": None, "veredito_t2": None,
-            "p_t3": None, "mc_t3": None, "liq_t3": None, "volume_t3": None,
-            "txns5m_t3": None, "buys_t3": None, "sells_t3": None,
-            "ratio_vol_mc_t3": None, "var_t3_%": None, "veredito_t3": None,
-            "mc_pico": mc_t0, "var_pico_%": None, "var_desde_compra": None,
-            "categoria_final": "⏳ aguardando",
+    query = """
+        SELECT o.*, c.name AS client_name
+        FROM orders o
+        JOIN clients c ON c.id = o.client_id
+        WHERE 1=1
+    """
+    params: list[Any] = []
+    if filters["client"]:
+        query += " AND c.name LIKE ?"
+        params.append(f"%{filters['client']}%")
+    if filters["status"]:
+        query += " AND o.status = ?"
+        params.append(filters["status"])
+    if filters["product"]:
+        query += " AND o.product_type LIKE ?"
+        params.append(f"%{filters['product']}%")
+    if filters["date"]:
+        query += " AND o.order_date = ?"
+        params.append(filters["date"])
+
+    query += " ORDER BY o.due_date ASC"
+    with closing(get_conn()) as conn:
+        rows = conn.execute(query, params).fetchall()
+    return jsonify([row_to_dict(row) for row in rows])
+
+
+@app.route("/api/orders/<int:order_id>", methods=["GET", "PATCH"])
+def order_detail(order_id: int):
+    if request.method == "PATCH":
+        data = request.json
+        allowed = {
+            "status",
+            "due_date",
+            "notes",
+            "pantone_codes",
+            "colors_count",
+            "price",
+            "material_origin",
         }
+        fields = {k: v for k, v in data.items() if k in allowed}
+        if not fields:
+            return jsonify({"error": "Nenhum campo válido para atualização."}), 400
 
-        idx = len(est["registros"])
-        est["registros"].append(reg)
+        with closing(get_conn()) as conn:
+            existing = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
+            if not existing:
+                return jsonify({"error": "Pedido não encontrado."}), 404
 
-        db_id = None
-        try:
-            db_id = db_insert(reg)
-        except Exception as e:
-            log(f"⚠️  DB insert erro: {e}")
+            for field, value in fields.items():
+                save_history(order_id, field, existing[field], value)
 
-        est["pendentes"][mint] = {"idx": idx, "db_id": db_id}
+            set_clause = ", ".join([f"{f} = ?" for f in fields])
+            values = list(fields.values()) + [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), order_id]
+            conn.execute(f"UPDATE orders SET {set_clause}, updated_at = ? WHERE id = ?", values)
+            conn.commit()
+        return jsonify({"message": "Pedido atualizado com sucesso."})
+
+    with closing(get_conn()) as conn:
+        order = conn.execute(
+            """
+            SELECT o.*, c.name as client_name
+            FROM orders o
+            JOIN clients c ON c.id = o.client_id
+            WHERE o.id = ?
+            """,
+            (order_id,),
+        ).fetchone()
+        if not order:
+            return jsonify({"error": "Pedido não encontrado."}), 404
+
+        history = conn.execute(
+            "SELECT * FROM order_history WHERE order_id = ? ORDER BY changed_at DESC",
+            (order_id,),
+        ).fetchall()
+
+    return jsonify({"order": row_to_dict(order), "history": [row_to_dict(row) for row in history]})
+
+
+@app.route("/api/production/today")
+def production_today():
+    today = date.today().strftime("%Y-%m-%d")
+    with closing(get_conn()) as conn:
+        in_production = conn.execute(
+            """
+            SELECT o.*, c.name AS client_name
+            FROM orders o
+            JOIN clients c ON c.id = o.client_id
+            WHERE o.status IN ('aguardando produção', 'Amostra', 'em produção')
+            ORDER BY o.due_date
+            """
+        ).fetchall()
+        due_today = conn.execute(
+            """
+            SELECT o.*, c.name AS client_name
+            FROM orders o
+            JOIN clients c ON c.id = o.client_id
+            WHERE o.due_date = ?
+            ORDER BY o.status
+            """,
+            (today,),
+        ).fetchall()
+        delayed = conn.execute(
+            """
+            SELECT o.*, c.name AS client_name
+            FROM orders o
+            JOIN clients c ON c.id = o.client_id
+            WHERE o.due_date < ? AND o.status != 'finalizado'
+            ORDER BY o.due_date
+            """,
+            (today,),
+        ).fetchall()
+
+    return jsonify(
+        {
+            "in_production": [row_to_dict(row) for row in in_production],
+            "due_today": [row_to_dict(row) for row in due_today],
+            "delayed": [row_to_dict(row) for row in delayed],
+        }
+    )
 
-        is_multi = checar_multi_carteira(
-            mint, nome_token, nome, mc_t0, liq_t0,
-            ratio_vol_mc_t0 or 0, idade_min or 0,
-            score, score_emoji, score_desc,
-            holders_count=holders_count, top1_pct=top1_pct,
-            top10_pct=top10_pct, dev_saiu=dev_saiu, bc_progress=bc_progress,
-            buys_5min=buys_5min, sells_5min=sells_5min,
-        )
-        est["registros"][idx]["is_multi"] = bool(is_multi)
-        if is_multi and db_id:
-            try:
-                db_update_multi(db_id)
-            except:
-                pass
-
-        agendar_checkpoints(nome, mint)
-
-
-def enviar_csv_diario():
-    log("📤 Enviando CSV diário...")
-    todos = []
-    for nome in set(CARTEIRAS.values()):
-        todos.extend(estado[nome]["registros"])
-    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
-    if not todos:
-        telegram("📊 <b>Relatório diário</b>\n\nNenhum registro ainda.")
-        threading.Timer(24 * 60 * 60, enviar_csv_diario).start()
-        return
-    caminho = "monitoramento_consolidado.csv"
-    pd.DataFrame(todos).to_csv(caminho, index=False)
-    compras = sum(1 for r in todos if r.get("tipo") == "COMPRA")
-    vendas  = sum(1 for r in todos if r.get("tipo") == "VENDA")
-    multis  = sum(1 for r in todos if r.get("is_multi"))
-    telegram_documento(caminho, caption=(
-        f"📊 <b>Relatório consolidado</b>\nGerado em: {agora}\n\n"
-        f"Compras: <b>{compras}</b> | Vendas: <b>{vendas}</b>\nMulti: <b>{multis}</b>"
-    ))
-    threading.Timer(24 * 60 * 60, enviar_csv_diario).start()
-
-
-# ══════════════════════════════════════════════════════════
-# ROTAS
-# ══════════════════════════════════════════════════════════
-@app.route("/webhook", methods=["POST"])
-def webhook():
-    try:
-        txs = request.get_json()
-        if not txs:
-            return jsonify({"ok": True})
-        for tx in txs:
-            sig = tx.get("signature", "")
-            if sig in signatures_vistas:
-                continue
-            if sig:
-                signatures_vistas.add(sig)
-                threading.Thread(target=db_sig_add, args=[sig], daemon=True).start()
-            for acc in tx.get("accountData", []):
-                addr = acc.get("account", "")
-                if addr in CARTEIRAS:
-                    processar_tx(tx, addr, CARTEIRAS[addr])
-                    break
-        return jsonify({"ok": True})
-    except Exception as e:
-        import traceback
-        log(f"Webhook erro: {e}\n{traceback.format_exc()}")
-        return jsonify({"ok": False}), 500
-
-
-@app.route("/", methods=["GET"])
-def health():
-    total   = sum(len(estado[n]["registros"]) for n in estado)
-    pend    = sum(len(estado[n]["pendentes"]) for n in estado)
-    compras = sum(1 for n in estado for r in estado[n]["registros"] if r.get("tipo") == "COMPRA")
-    vendas  = sum(1 for n in estado for r in estado[n]["registros"] if r.get("tipo") == "VENDA")
-    multis  = sum(1 for n in estado for r in estado[n]["registros"] if r.get("is_multi"))
-    return jsonify({
-        "status": "running v6.3+db", "registros": total,
-        "compras": compras, "vendas": vendas,
-        "multis": multis, "pendentes": pend,
-    })
-
-
-@app.route("/dados", methods=["GET"])
-def dados():
-    if request.args.get("key") != DASHBOARD_KEY:
-        return jsonify({"erro": "nao autorizado"}), 401
-
-    todos = []
-    for n in estado:
-        todos.extend(estado[n]["registros"])
-    todos_sorted = sorted(todos, key=lambda r: r.get("data_compra", ""), reverse=True)
-
-    ativos = []
-    for n in estado:
-        for mint, info in estado[n]["pendentes"].items():
-            ativos.append(dict(estado[n]["registros"][info["idx"]]))
-
-    # Agrupar multis por token_mint — mostrar todas as carteiras por token
-    multis_raw = [r for r in todos_sorted if r.get("is_multi") and r.get("tipo") == "COMPRA"]
-    multis_por_mint = {}
-    for r in multis_raw:
-        m = r["token_mint"]
-        if m not in multis_por_mint:
-            multis_por_mint[m] = []
-        multis_por_mint[m].append(r)
-
-    multis = []
-    for mint_m, regs_m in list(multis_por_mint.items())[:50]:
-        # Registro base = o mais recente
-        base = regs_m[0]
-        # Info extra do mints_globais se disponível
-        info_m = mints_globais.get(mint_m, {}).get("__multi_info__", {})
-        # Montar lista de entradas de cada carteira
-        entradas = []
-        for r in regs_m:
-            entradas.append({
-                "carteira": r["carteira"],
-                "tipo_carteira": TIPO_CARTEIRA.get(r["carteira"], "?"),
-                "mc_t0": r.get("mc_t0"),
-                "data_compra": r.get("data_compra"),
-                "var_t1_%": r.get("var_t1_%"),
-                "var_t2_%": r.get("var_t2_%"),
-                "var_t3_%": r.get("var_t3_%"),
-                "score_qualidade": r.get("score_qualidade"),
-            })
-        multi_entry = dict(base)
-        multi_entry["entradas"] = entradas
-        multi_entry["n_carteiras"] = len(regs_m)
-        multi_entry["tem_humano"] = any(TIPO_CARTEIRA.get(r["carteira"]) == "humano" for r in regs_m)
-        multi_entry["timing_s"] = info_m.get("timing_s")
-        multis.append(multi_entry)
-
-    stats = {}
-    for n in set(CARTEIRAS.values()):
-        regs_n      = [r for r in todos if r.get("carteira") == n and r.get("tipo") == "COMPRA"]
-        finalizados = [r for r in regs_n if r.get("categoria_final") and "aguardando" not in r.get("categoria_final", "")]
-        vencedores  = [r for r in finalizados if r.get("var_pico_%") and r["var_pico_%"] > 20]
-        winrate     = round(len(vencedores) / len(finalizados) * 100, 1) if finalizados else 0
-        stats[n] = {
-            "tipo": TIPO_CARTEIRA.get(n, "?"),
-            "total": len(regs_n),
-            "finalizados": len(finalizados),
-            "vencedores": len(vencedores),
-            "winrate": winrate,
+
+@app.route("/api/financial", methods=["GET", "POST"])
+def financial_handler():
+    if request.method == "POST":
+        data = request.json
+        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
+        with closing(get_conn()) as conn:
+            cur = conn.execute(
+                """INSERT INTO financial_entries
+                   (kind, client_or_vendor, value, entry_date, category, order_id, notes, created_at)
+                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
+                (
+                    data["kind"],
+                    data.get("client_or_vendor"),
+                    float(data["value"]),
+                    data["entry_date"],
+                    data.get("category"),
+                    data.get("order_id"),
+                    data.get("notes"),
+                    now,
+                ),
+            )
+            conn.commit()
+        return jsonify({"id": cur.lastrowid, "message": "Lançamento financeiro criado."}), 201
+
+    with closing(get_conn()) as conn:
+        rows = conn.execute("SELECT * FROM financial_entries ORDER BY entry_date DESC").fetchall()
+        totals = conn.execute(
+            """
+            SELECT
+                SUM(CASE WHEN kind = 'entrada' THEN value ELSE 0 END) AS total_entries,
+                SUM(CASE WHEN kind = 'saida' THEN value ELSE 0 END) AS total_expenses
+            FROM financial_entries
+            """
+        ).fetchone()
+    return jsonify(
+        {
+            "entries": [row_to_dict(row) for row in rows],
+            "summary": {
+                "total_entries": totals["total_entries"] or 0,
+                "total_expenses": totals["total_expenses"] or 0,
+                "balance": (totals["total_entries"] or 0) - (totals["total_expenses"] or 0),
+            },
         }
+    )
 
-    return jsonify({
-        "status":    "ok",
-        "versao":    "v6.3+db",
-        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
-        "resumo": {
-            "total_registros": len(todos),
-            "compras": sum(1 for r in todos if r.get("tipo") == "COMPRA"),
-            "vendas":  sum(1 for r in todos if r.get("tipo") == "VENDA"),
-            "multis":  len(multis),
-            "ativos":  len(ativos),
-        },
-        "stats_carteiras": stats,
-        "tokens_ativos":   ativos,
-        "alertas_multi":   multis,
-        "historico":       [r for r in todos_sorted if r.get("categoria_final") and "aguardando" not in r.get("categoria_final", "")][:200],
-    })
-
-
-# ══════════════════════════════════════════════════════════
-# STARTUP
-# ══════════════════════════════════════════════════════════
-def startup():
-    time.sleep(3)
-    init_db()
-    db_carregar_estado()
-    total = sum(len(estado[n]["registros"]) for n in estado)
-    telegram(
-        f"🚀 <b>Monitor v6.3 + PostgreSQL iniciado!</b>\n\n"
-        f"📂 {total} registros restaurados do banco\n\n"
-        "🤖 carteira_A | 🤖 carteira_B\n"
-        "👤 carteira_C | 👤 carteira_D"
+
+@app.route("/api/dashboard")
+def dashboard_handler():
+    current_month = datetime.now().strftime("%Y-%m")
+    with closing(get_conn()) as conn:
+        kpis = conn.execute(
+            """
+            SELECT
+                COALESCE(SUM(CASE WHEN strftime('%Y-%m', order_date) = ? THEN price ELSE 0 END), 0) AS monthly_revenue,
+                SUM(CASE WHEN status IN ('aguardando produção', 'Amostra', 'em produção') THEN 1 ELSE 0 END) AS in_production,
+                SUM(CASE WHEN status = 'finalizado' THEN 1 ELSE 0 END) AS delivered,
+                SUM(CASE WHEN due_date < date('now') AND status != 'finalizado' THEN 1 ELSE 0 END) AS delayed
+            FROM orders
+            """,
+            (current_month,),
+        ).fetchone()
+
+        top_clients = conn.execute(
+            """
+            SELECT c.name, COALESCE(SUM(o.price), 0) AS total
+            FROM clients c
+            LEFT JOIN orders o ON o.client_id = c.id
+            GROUP BY c.id
+            ORDER BY total DESC
+            LIMIT 5
+            """
+        ).fetchall()
+
+        revenue_chart = conn.execute(
+            """
+            SELECT strftime('%Y-%m', entry_date) AS period, SUM(value) AS total
+            FROM financial_entries
+            WHERE kind = 'entrada'
+            GROUP BY period
+            ORDER BY period
+            """
+        ).fetchall()
+
+        orders_chart = conn.execute(
+            """
+            SELECT strftime('%Y-%m', order_date) AS period, COUNT(*) AS total
+            FROM orders
+            GROUP BY period
+            ORDER BY period
+            """
+        ).fetchall()
+
+        production_evolution = conn.execute(
+            """
+            SELECT status, COUNT(*) AS total
+            FROM orders
+            GROUP BY status
+            ORDER BY total DESC
+            """
+        ).fetchall()
+
+    return jsonify(
+        {
+            "kpis": row_to_dict(kpis),
+            "top_clients": [row_to_dict(row) for row in top_clients],
+            "charts": {
+                "monthly_revenue": [row_to_dict(row) for row in revenue_chart],
+                "order_volume": [row_to_dict(row) for row in orders_chart],
+                "production_evolution": [row_to_dict(row) for row in production_evolution],
+            },
+        }
     )
-    log("✅ Monitor v6.3+db — aguardando transações")
-    threading.Timer(24 * 60 * 60, enviar_csv_diario).start()
+
+
+@app.route("/api/reports")
+def reports_handler():
+    report_type = request.args.get("type", "production")
+    start_date = request.args.get("start")
+    end_date = request.args.get("end")
+
+    with closing(get_conn()) as conn:
+        if report_type == "production":
+            rows = conn.execute(
+                """
+                SELECT o.order_date, o.due_date, o.status, c.name AS client, o.product_type, o.total_quantity
+                FROM orders o
+                JOIN clients c ON c.id = o.client_id
+                ORDER BY o.order_date DESC
+                """
+            ).fetchall()
+        elif report_type == "financial":
+            query = "SELECT * FROM financial_entries WHERE 1=1"
+            params = []
+            if start_date:
+                query += " AND entry_date >= ?"
+                params.append(start_date)
+            if end_date:
+                query += " AND entry_date <= ?"
+                params.append(end_date)
+            query += " ORDER BY entry_date DESC"
+            rows = conn.execute(query, params).fetchall()
+        elif report_type == "orders_by_client":
+            rows = conn.execute(
+                """
+                SELECT c.name AS client, COUNT(o.id) AS total_orders, COALESCE(SUM(o.price),0) AS total_value
+                FROM clients c
+                LEFT JOIN orders o ON o.client_id = c.id
+                GROUP BY c.id
+                ORDER BY total_value DESC
+                """
+            ).fetchall()
+        elif report_type == "revenue_period":
+            query = """
+                SELECT strftime('%Y-%m', entry_date) AS period, SUM(value) AS total
+                FROM financial_entries
+                WHERE kind = 'entrada'
+            """
+            params = []
+            if start_date:
+                query += " AND entry_date >= ?"
+                params.append(start_date)
+            if end_date:
+                query += " AND entry_date <= ?"
+                params.append(end_date)
+            query += " GROUP BY period ORDER BY period"
+            rows = conn.execute(query, params).fetchall()
+        else:
+            rows = conn.execute("SELECT * FROM orders ORDER BY order_date DESC").fetchall()
+
+    return jsonify({"type": report_type, "data": [row_to_dict(row) for row in rows]})
 
 
 if __name__ == "__main__":
-    log("🚀 MONITOR v6.3+DB INICIADO")
-    for addr, nome in CARTEIRAS.items():
-        log(f"   {nome}: {addr[:20]}...")
-    threading.Thread(target=startup, daemon=True).start()
-    port = int(os.environ.get("PORT", 8080))
-    app.run(host="0.0.0.0", port=port)
+    init_db()
+    seed_data()
+    app.run(host="0.0.0.0", port=5000, debug=True)
