import csv
import datetime
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import unicodedata
import webbrowser
import sys
import os
import subprocess
import uuid
import traceback
import platform
import re
import io
import customtkinter as ctk
import requests
import hmac
import hashlib
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Importação da biblioteca de leitura de PDFs (Fallback se não instalada)
try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# Configuração visual do CustomTkinter (Design Moderno)
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")

# ==============================================================================
# 1. CLASSE DE UTILITÁRIOS
# ==============================================================================
class Utils:
    @staticmethod
    def obter_caminho_recurso(caminho_relativo):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, caminho_relativo)

    @staticmethod
    def normalizar_texto(texto: str) -> str:
        if not texto: return ""
        nfkd = unicodedata.normalize("NFKD", str(texto))
        texto_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
        return texto_sem_acento.lower().strip()

    @staticmethod
    def extrair_grupos_radicais(termo_multiplo: str) -> list:
        grupos = []
        for parte in termo_multiplo.split(','):
            parte = parte.strip()
            if not parte: continue
            palavras = [p for p in Utils.normalizar_texto(parte).split() if len(p) >= 2]
            radicais = []
            for p in palavras:
                rad = p
                if p.endswith("es") and len(p) > 3: rad = p[:-2]
                elif p.endswith("s") and len(p) > 3: rad = p[:-1]
                radicais.append(rad)
            if radicais: grupos.append(radicais)
        return grupos

    @staticmethod
    def texto_atende_busca(texto: str, grupos_radicais: list) -> bool:
        if not grupos_radicais: return True 
        texto_norm = Utils.normalizar_texto(texto)
        for radicais_frase in grupos_radicais:
            if all(rad in texto_norm for rad in radicais_frase):
                return True
        return False

    @staticmethod
    def formatar_data_hora(data_iso: str) -> str:
        if not data_iso: return "Não informada"
        try: return datetime.datetime.fromisoformat(data_iso.split('.')[0]).strftime("%d/%m/%Y %H:%M")
        except: return str(data_iso)[:16].replace("T", " ")

    @staticmethod
    def formatar_moeda(valor):
        if not valor: return "Não informado"
        try:
            val = float(valor)
            return "Não informado" if val == 0.0 else f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except: return "Não informado"

    @staticmethod
    def formatar_data_api(data_str):
        try:
            p = data_str.strip().split("/")
            if len(p) == 3: return f"{p[2]}{p[1].zfill(2)}{p[0].zfill(2)}"
        except: pass
        return data_str

# ==============================================================================
# 2. CLASSE DO TERMINAL SECRETO DE DEPURAÇÃO
# ==============================================================================
class TerminalSecreto(ctk.CTkToplevel):
    def __init__(self, master, historico_inicial):
        super().__init__(master)
        self.title("Terminal de Logs Detalhado - Administrador")
        self.geometry("900x550")
        self.configure(fg_color="#0a0a0a")
        self.transient(master)

        lbl_titulo = ctk.CTkLabel(self, text="Terminal de Depuração - Monitor de Backend", text_color="#2ecc71", font=("Consolas", 14, "bold"))
        lbl_titulo.pack(anchor="w", padx=10, pady=5)

        self.txt_terminal = ctk.CTkTextbox(self, font=("Consolas", 11), fg_color="#121212", text_color="#2ecc71")
        self.txt_terminal.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        if historico_inicial:
            self.txt_terminal.insert("end", "\n".join(historico_inicial) + "\n")
            self.txt_terminal.see("end")

    def registrar_linha(self, linha_log):
        self.txt_terminal.insert("end", f"{linha_log}\n")
        self.txt_terminal.see("end")


# ==============================================================================
# 3. CLASSE DE GERENCIAMENTO DE BANCO DE DADOS
# ==============================================================================
class DatabaseManager:
    def __init__(self, db_path, logger_func, chave_seguranca):
        self.db_path = db_path
        self.log = logger_func
        self.chave_seguranca = chave_seguranca
        self.cache_historico = {}
        self.iniciar_banco()

    def iniciar_banco(self):
        self.log("[SQLITE] Inicializando banco de dados...", apenas_terminal=True)
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""CREATE TABLE IF NOT EXISTS editais_itens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    orgao TEXT, uf TEXT, objeto_contrato TEXT, desc_item TEXT, 
                    quantidade REAL, vlr_unit_est TEXT, vlr_total_est TEXT, 
                    vlr_unit_hom TEXT, vlr_total_hom TEXT, data_publicacao TEXT, 
                    data_abertura TEXT, data_encerramento TEXT, cnpj TEXT, 
                    ano INTEGER, sequencial INTEGER, numero_compra TEXT, uasg TEXT, 
                    numero_item INTEGER, modalidade_id TEXT, modalidade_nome TEXT, 
                    portal_nome TEXT, data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                    UNIQUE(cnpj, ano, sequencial, numero_item, desc_item) ON CONFLICT REPLACE
                )""")
                
                try: cursor.execute("ALTER TABLE editais_itens ADD COLUMN analise_ia TEXT")
                except sqlite3.OperationalError: pass # Coluna já existe
                
                cursor.execute("CREATE TABLE IF NOT EXISTS usuario_licenca (id INTEGER PRIMARY KEY AUTOINCREMENT, token TEXT NOT NULL)")
                cursor.execute("CREATE TABLE IF NOT EXISTS api_keys (provedor TEXT PRIMARY KEY, chave TEXT)")
                # Novas tabelas para Alertas e Notificações
                cursor.execute("""CREATE TABLE IF NOT EXISTS alertas_config (
                    id INTEGER PRIMARY KEY DEFAULT 1, email_destino TEXT, email_remetente TEXT, 
                    senha_app TEXT, palavras_chave TEXT, uf_filtro TEXT, modalidade_filtro TEXT
                )""")
                cursor.execute("""CREATE TABLE IF NOT EXISTS alertas_notificacoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, chave_edital TEXT UNIQUE, 
                    orgao TEXT, objeto TEXT, link TEXT, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                    lida BOOLEAN DEFAULT FALSE
                )""")
                conn.commit()
        except Exception as e:
            self.log(f"[SQLITE ERROR] Falha ao iniciar DB: {e}", apenas_terminal=True)

    def criptografar_texto(self, texto):
        if not texto: return ""
        key = self.chave_seguranca
        cifrado = bytes([c ^ key[i % len(key)] for i, c in enumerate(texto.encode('utf-8'))])
        return base64.b64encode(cifrado).decode('utf-8')

    def descriptografar_texto(self, texto_cifrado):
        if not texto_cifrado: return ""
        try:
            key = self.chave_seguranca
            decoded = base64.b64decode(texto_cifrado)
            return bytes([c ^ key[i % len(key)] for i, c in enumerate(decoded)]).decode('utf-8')
        except: return ""

    def salvar_api_key(self, provedor, chave):
        cifrada = self.criptografar_texto(chave)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO api_keys (provedor, chave) VALUES (?, ?)", (provedor, cifrada))
            conn.commit()

    def obter_api_key(self, provedor):
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.cursor().execute("SELECT chave FROM api_keys WHERE provedor = ?", (provedor,)).fetchone()
                return self.descriptografar_texto(row[0]) if row else ""
        except: return ""
    # ----------------------------------------

    def obter_cnpj_licenciado(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT token FROM usuario_licenca ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if not row: return None
                
                token_bruto = base64.b64decode(row[0].encode()).decode()
                cnpj_salvo, data_validade, assinatura_salva = token_bruto.split('|')
                if hmac.new(self.chave_seguranca, f"{cnpj_salvo}|{data_validade}".encode(), hashlib.sha256).hexdigest() != assinatura_salva: return None
                if datetime.datetime.now().strftime("%Y-%m-%d") > data_validade[:10]: return None
                return cnpj_salvo
        except: return None 

    def salvar_licenca(self, cnpj, data_validade):
        dados_licenca = f"{cnpj}|{data_validade}"
        assinatura = hmac.new(self.chave_seguranca, dados_licenca.encode(), hashlib.sha256).hexdigest()
        token_seguro = base64.b64encode(f"{dados_licenca}|{assinatura}".encode()).decode()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM usuario_licenca")
            cursor.execute("INSERT INTO usuario_licenca (token) VALUES (?)", (token_seguro,))
            conn.commit()

    def salvar_item_edital(self, item_dict):
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""INSERT OR REPLACE INTO editais_itens (
                    orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, 
                    vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, 
                    data_abertura, data_encerramento, cnpj, ano, sequencial, 
                    numero_compra, uasg, numero_item, modalidade_id, modalidade_nome, portal_nome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                    item_dict.get("Orgao"), item_dict.get("UF"), item_dict.get("ObjetoContrato"), 
                    item_dict.get("DescItem"), item_dict.get("Qtd"), item_dict.get("Vlr Unit Est"), 
                    item_dict.get("Vlr Total Est"), item_dict.get("Vlr Unit Hom"), item_dict.get("Vlr Total Hom"), 
                    item_dict.get("Data Pub"), item_dict.get("Data Abertura"), item_dict.get("Data Encerramento"), 
                    item_dict.get("CNPJ", ""), item_dict.get("Ano", 0), item_dict.get("Sequencial", 0), 
                    item_dict.get("NumeroCompra", ""), item_dict.get("UASG", ""), item_dict.get("NumeroItem", 0), 
                    item_dict.get("ModalidadeID", ""), item_dict.get("ModalidadeNome", ""), item_dict.get("PortalNome", "")
                ))
                conn.commit()
        except Exception as e:
            self.log(f"[SQLITE ERROR] Falha ao salvar item: {e}", apenas_terminal=True)

    def salvar_analise_ia(self, cnpj, ano, seq, analise):
        try:
            with sqlite3.connect(self.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE editais_itens SET analise_ia = ? WHERE cnpj = ? AND ano = ? AND sequencial = ?", (analise, cnpj, ano, seq))
                conn.commit()
        except Exception as e:
            self.log(f"[DB IA] Erro ao salvar análise no banco: {e}", apenas_terminal=True)

    def carregar_analise_ia(self, cnpj, ano, seq):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT analise_ia FROM editais_itens WHERE cnpj = ? AND ano = ? AND sequencial = ? AND analise_ia IS NOT NULL LIMIT 1", (cnpj, ano, seq))
                row = cursor.fetchone()
                return row[0] if row else None
        except: return None

    def executar_leitura(self, sql, params):
        self.log(f"[SQL EXEC] Query: {sql} | Params: {params}", apenas_terminal=True)
        with sqlite3.connect(self.db_path) as conn:
            return conn.cursor().execute(sql, params).fetchall()

    def obter_historico_precos(self, desc_item, orgao, uf_atual):
        cache_key = (desc_item, orgao, uf_atual)
        if cache_key in self.cache_historico:
            return self.cache_historico[cache_key]
        
        try:
            um_ano_atras = (datetime.datetime.now() - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT orgao, uf, vlr_unit_hom FROM editais_itens WHERE desc_item = ? AND data_publicacao >= ? ORDER BY data_publicacao DESC", (desc_item, um_ano_atras))
                linhas = cursor.fetchall()
            
            soma_orgao, qtd_orgao, soma_geral, qtd_geral = 0.0, 0, 0.0, 0
            ultimo_orgao, ultimo_regiao = "Sem Histórico", "Sem Histórico"
            
            for row in linhas:
                orgao_db, uf_db, vlr_str = row[0], row[1], row[2]
                if not vlr_str or vlr_str == "Não informado": continue
                
                try: val_float = float(vlr_str.replace("R$ ", "").replace(".", "").replace(",", "."))
                except: continue
                if val_float <= 0: continue
                
                if orgao_db == orgao:
                    soma_orgao += val_float
                    qtd_orgao += 1
                    if ultimo_orgao == "Sem Histórico": ultimo_orgao = Utils.formatar_moeda(val_float)
                else:
                    soma_geral += val_float
                    qtd_geral += 1
                    
                if uf_db == uf_atual and ultimo_regiao == "Sem Histórico":
                    ultimo_regiao = Utils.formatar_moeda(val_float)
                    
            media_org = Utils.formatar_moeda(soma_orgao / qtd_orgao) if qtd_orgao > 0 else "Sem Histórico"
            media_ger = Utils.formatar_moeda(soma_geral / qtd_geral) if qtd_geral > 0 else "Sem Histórico"
            
            retorno = (media_org, media_ger, ultimo_orgao, ultimo_regiao)
            self.cache_historico[cache_key] = retorno
            return retorno
        except Exception as e:
            self.log(f"[DB] Erro ao calcular histórico: {e}", apenas_terminal=True)
            return "Sem Histórico", "Sem Histórico", "Sem Histórico", "Sem Histórico"

    def obter_config_alertas(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.cursor().execute("SELECT email_destino, email_remetente, senha_app, palavras_chave, uf_filtro, modalidade_filtro FROM alertas_config WHERE id=1").fetchone()
                if row: return {"destino": row[0], "remetente": row[1], "senha": self.descriptografar_texto(row[2]), "palavras": row[3], "uf": row[4], "modalidade": row[5]}
        except: pass
        return {"destino": "", "remetente": "", "senha": "", "palavras": "", "uf": "Todas", "modalidade": ""}

    def salvar_config_alertas(self, dest, remet, senha, pal, uf, mod):
        senha_cifrada = self.criptografar_texto(senha) if senha else ""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO alertas_config (id, email_destino, email_remetente, senha_app, palavras_chave, uf_filtro, modalidade_filtro) VALUES (1, ?, ?, ?, ?, ?, ?)", (dest, remet, senha_cifrada, pal, uf, mod))
            conn.commit()

    def registrar_notificacao_nova(self, chave_edital, orgao, objeto, link):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("INSERT INTO alertas_notificacoes (chave_edital, orgao, objeto, link) VALUES (?, ?, ?, ?)", (chave_edital, orgao, objeto, link))
                conn.commit()
                return True # Nova mesmo
        except sqlite3.IntegrityError:
            return False # Já estava notificada

    def obter_notificacoes(self, apenas_nao_lidas=True):
        with sqlite3.connect(self.db_path) as conn:
            sql = "SELECT id, orgao, objeto, link, lida FROM alertas_notificacoes" + (" WHERE lida=0" if apenas_nao_lidas else "") + " ORDER BY id DESC LIMIT 50"
            return conn.cursor().execute(sql).fetchall()

    def marcar_notificacoes_lidas(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE alertas_notificacoes SET lida=1 WHERE lida=0")
            conn.commit()
    
    
    def limpar_cache(self):
        self.cache_historico = {}


# ==============================================================================
# 4. CLASSE PRINCIPAL DO APP
# ==============================================================================
class BuscadorPNCP(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.versao_local = "9.4.0"
        self.title(f"Buscador Multi-Portal de Licitações & Preços - Compras Públicas | Versão {self.versao_local}")
        self.geometry("1180x920")
        
        try: self.iconbitmap(Utils.obter_caminho_recurso("icone.ico"))
        except: pass

        self.url_api_versao = "https://meu-validador-licencas.vercel.app/api/versao"
        self.url_api_licenca = "https://meu-validador-licencas.vercel.app/api/valida"
        self.chave_seguranca = b'kM7hQ7uX1x4qW8zF3rN9mT2vP5yC8aD4gG6jH9kL1sM=' 

        self.historico_debug = []
        self.cancelar_busca = False
        self.cancelar_carga = False
        self.is_carga_running = False
        self.mostrar_carga_no_grid = False 
        self.item_selecionado_doc = None
        self.resultados_pncp = []
        self.cnpj_ativo = None
        self.janela_terminal = None
        self.palavras_chave_empresa = [] 

        self.db = DatabaseManager("licitacoes_pncp_v10.db", self.registrar_log, self.chave_seguranca)

        self.withdraw()
        self.after(200, self._rotina_de_arranque)

    # ---------------------------------------------------------
    # SISTEMA DE LOGS INTERNOS
    # ---------------------------------------------------------
    def registrar_log(self, mensagem, apenas_terminal=False):
        hora_atual = datetime.datetime.now().strftime('%H:%M:%S')
        linha_log = f"[{hora_atual}] {mensagem}"
        print(linha_log.strip())
        
        self.historico_debug.append(linha_log)
        if len(self.historico_debug) > 1500: self.historico_debug.pop(0)
        
        if not apenas_terminal and hasattr(self, "txt_logs"): 
            self.after(0, lambda m=linha_log: [self.txt_logs.insert("end", f"{m}\n"), self.txt_logs.see("end")])
            
        if self.janela_terminal and self.janela_terminal.winfo_exists():
            self.after(0, lambda m=linha_log: self.janela_terminal.registrar_linha(m))

    def _abrir_prompt_terminal(self, event=None):
        janela_senha = ctk.CTkToplevel(self)
        janela_senha.title("Acesso Restrito - Manutenção")
        janela_senha.geometry("350x180")
        janela_senha.transient(self)
        janela_senha.grab_set()

        ctk.CTkLabel(janela_senha, text="🛠️ Modo de Suporte\n\nIntroduza a Senha Mestra:", font=("Segoe UI", 12, "bold")).pack(pady=(20, 10))
        ent_senha = ctk.CTkEntry(janela_senha, width=200, show="*")
        ent_senha.pack(pady=5)
        ent_senha.focus()

        def validar(e=None):
            if ent_senha.get() == "suporte@2026":
                janela_senha.destroy()
                if not self.janela_terminal or not self.janela_terminal.winfo_exists():
                    self.janela_terminal = TerminalSecreto(self, self.historico_debug)
                else: self.janela_terminal.focus()
            else:
                messagebox.showerror("Acesso Negado", "Palavra-passe incorreta.")
                janela_senha.destroy()

        ent_senha.bind("<Return>", validar)
        ctk.CTkButton(janela_senha, text="Aceder", command=validar, fg_color="#c0392b", hover_color="#e74c3c").pack(pady=15)

    # ---------------------------------------------------------
    # ARRANQUE E VERIFICAÇÕES DE REDE
    # ---------------------------------------------------------
    def _rotina_de_arranque(self):
        if not self.verificar_versao_inicial(): return 
        self.cnpj_ativo = self.db.obter_cnpj_licenciado()

        if not self.cnpj_ativo:
            self.solicitar_registro_cnpj()
        else:
            sucesso, _ = self.validar_licenca_online(self.cnpj_ativo, silencioso=True)
            if sucesso: self.iniciar_sistema_principal()
            else: self.solicitar_registro_cnpj()

    def verificar_versao_inicial(self):
        try:
            self.registrar_log("[SYSTEM] Verificando atualizações OTA...", apenas_terminal=True)
            res = requests.get(self.url_api_versao, timeout=5)
            if res.status_code != 200: return True 
            dados = res.json()
            versao_nuvem = dados.get("versao_atual", self.versao_local)
            versao_minima = dados.get("versao_minima_obrigatoria", "0.0")
            link_download = dados.get("url_download")

            if float(self.versao_local) < float(versao_minima):
                messagebox.showerror("Atualização Obrigatória", f"A sua versão foi descontinuada.\nO sistema será atualizado agora para a versão {versao_nuvem}.")
                self.executar_download_e_atualizacao(link_download)
                return False 
            elif float(self.versao_local) < float(versao_nuvem):
                if messagebox.askyesno("Atualização Disponível", f"Nova versão {versao_nuvem} encontrada!\n\nDeseja atualizar o sistema agora? (Recomendado)"):
                    self.executar_download_e_atualizacao(link_download)
                    return False
            return True
        except: return True 

    def executar_download_e_atualizacao(self, link_download):
        try:
            self.registrar_log(f"[OTA] Baixando nova versão de: {link_download}", apenas_terminal=True)
            janela_aviso = ctk.CTkToplevel(self)
            janela_aviso.title("A Atualizar")
            janela_aviso.geometry("300x100")
            janela_aviso.attributes('-topmost', True)
            ctk.CTkLabel(janela_aviso, text="A transferir a nova versão...\nPor favor, aguarde.", font=("Segoe UI", 14, "bold")).pack(expand=True)
            self.update()

            caminho_exe_atual = os.path.abspath(sys.argv[0]) 
            pasta_atual = os.path.dirname(caminho_exe_atual)
            nome_exe_original = os.path.basename(caminho_exe_atual)
            caminho_novo_exe = os.path.join(pasta_atual, "atualizacao_temp.exe")
            caminho_script_bat = os.path.join(pasta_atual, "atualizador.bat")

            resposta_download = requests.get(link_download, stream=True)
            with open(caminho_novo_exe, 'wb') as f:
                for chunk in resposta_download.iter_content(chunk_size=8192): f.write(chunk)

            conteudo_bat = f"""@echo off\ntimeout /t 2 /nobreak > NUL\ndel "{caminho_exe_atual}"\nren "{caminho_novo_exe}" "{nome_exe_original}"\nstart "" "{caminho_exe_atual}"\ndel "%~f0"\n"""
            with open(caminho_script_bat, "w", encoding="utf-8") as bat_file: bat_file.write(conteudo_bat)

            subprocess.Popen(caminho_script_bat, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
            sys.exit()
        except Exception as e:
            messagebox.showerror("Erro na Atualização", f"Falha ao transferir a atualização: {e}\n\nFaça o download manualmente.")
            sys.exit()

    def validar_licenca_online(self, cnpj_licenca: str, silencioso=False):
        if not self.url_api_licenca or "SUA-URL-AQUI" in self.url_api_licenca:
            if not silencioso: messagebox.showerror("Erro de Configuração", "A URL da API da Vercel não foi configurada.")
            return False, None

        payload = {"cnpj": cnpj_licenca, "hwid": str(uuid.getnode()), "maquina": platform.node(), "data_acesso": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "versao_atual": self.versao_local}
        self.registrar_log(f"[AUTH] Validando licença para CNPJ: {cnpj_licenca}", apenas_terminal=True)
        try:
            response = requests.post(self.url_api_licenca, json=payload, timeout=10)
            try: dados = response.json()
            except:
                if not silencioso: messagebox.showerror("Erro de Servidor", "A API da Vercel falhou. Verifique a URL.")
                return False, None
            if response.status_code == 200 and dados.get("status") == "success": return True, dados.get("data_validade", "2099-12-31")
            else:
                if not silencioso: messagebox.showerror("Licença Inválida", f"Falha na validação:\n{dados.get('message', 'Negado')}")
                return False, None
        except Exception as e:
            if not silencioso: messagebox.showerror("Erro de Conexão", f"Falha de internet:\n{e}")
            return False, None

    def solicitar_registro_cnpj(self):
        self.janela_login = ctk.CTkToplevel(self)
        self.janela_login.title("Ativação de Licença")
        self.janela_login.geometry("500x250")
        self.janela_login.transient(self)
        self.janela_login.grab_set()
        self.janela_login.protocol("WM_DELETE_WINDOW", sys.exit)

        ctk.CTkLabel(self.janela_login, text="Sistema Protegido\n\nPor favor, informe o CNPJ da sua empresa:", font=("Segoe UI", 14, "bold")).pack(pady=(20, 15))
        self.ent_cnpj_login = ctk.CTkEntry(self.janela_login, width=300, placeholder_text="Digite apenas números")
        self.ent_cnpj_login.pack(pady=10)
        self.ent_cnpj_login.bind("<Return>", lambda e: self.confirmar_registro_online())
        self.btn_ativar = ctk.CTkButton(self.janela_login, text="Validar Online", fg_color="#27ae60", hover_color="#2ecc71", font=("Segoe UI", 12, "bold"), command=self.confirmar_registro_online)
        self.btn_ativar.pack(pady=20)

    def confirmar_registro_online(self):
        cnpj = self.ent_cnpj_login.get().strip()
        if len(cnpj) < 11: return messagebox.showwarning("Aviso", "CNPJ ou CPF inválido.")
        self.btn_ativar.configure(text="A validar...", state="disabled")
        self.janela_login.update()
        
        sucesso, data_validade = self.validar_licenca_online(cnpj, silencioso=False)
        if sucesso:
            try:
                self.db.salvar_licenca(cnpj, data_validade)
                self.cnpj_ativo = cnpj
                messagebox.showinfo("Sucesso", "Licença ativada com sucesso!")
                self.janela_login.destroy()
                self.iniciar_sistema_principal()
            except Exception as e:
                messagebox.showerror("Erro de Segurança", f"Falha ao gerar token: {e}")
                self.btn_ativar.configure(text="Validar Online", state="normal")
        else: self.btn_ativar.configure(text="Validar Online", state="normal")

    # ---------------------------------------------------------
    # CLIENTE HTTP CENTRALIZADO (Mecanismo Anti-429)
    # ---------------------------------------------------------
    def _renovar_sessao_http(self):
        self.registrar_log("[NETWORK] SESSÃO HTTP RENOVADA.", apenas_terminal=True)
        self.http_session = requests.Session()
        self.http_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json, text/plain, */*", "Referer": "https://pncp.gov.br/"})

    def _get_com_retentativa(self, url, params, max_tentativas=5, timeout=15, tipo_operacao="busca"):
        self.registrar_log(f"[HTTP GET] Iniciando request -> {url}", apenas_terminal=True)
        self.registrar_log(f"           [PARAMS] {params}", apenas_terminal=True)
        
        time.sleep(0.15) 
        
        for tentativa in range(1, max_tentativas + 1):
            if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
            try: 
                res = self.http_session.get(url, params=params, timeout=(3.0, timeout))
                
                if res.status_code == 429:
                    tempo_espera = tentativa * 3 
                    self.registrar_log(f"[HTTP 429] 🛑 RATE LIMIT DO PNCP ALCANÇADO! Pausando por {tempo_espera}s...", apenas_terminal=True)
                    self.registrar_log(f"🛑 O Governo limitou o acesso por excesso de requisições. O robô vai aguardar {tempo_espera}s...", apenas_terminal=False)
                    for _ in range(int(tempo_espera * 10)):
                        if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
                        time.sleep(0.1)
                    continue 
                
                corpo_resumo = res.text[:250].replace('\n', ' ') if res.text else "Sem conteúdo"
                self.registrar_log(f"[HTTP {res.status_code}] <- Retorno: {corpo_resumo} | Tamanho: {len(res.content)} bytes", apenas_terminal=True)
                
                return res
            except Exception as e:
                if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
                if tentativa == max_tentativas: raise e
                
                self.registrar_log(f"⏳ Instabilidade na rede. Tentativa {tentativa}/{max_tentativas} aguardando...", apenas_terminal=False) 
                self.registrar_log(f"[HTTP RETRY] Falha: {e}. Aguardando...", apenas_terminal=True)
                for _ in range(20):
                    if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
                    time.sleep(0.1)
        return None

    # ---------------------------------------------------------
    # INTELIGÊNCIA ARTIFICIAL: PERFIL CNAE (BACKGROUND)
    # ---------------------------------------------------------
    def _carregar_perfil_empresa_background(self):
        if not self.cnpj_ativo: return
        cnpj_limpo = "".join(filter(str.isdigit, self.cnpj_ativo))
        try:
            self.registrar_log(f"[IA-CNAE] Construindo perfil silencioso para CNPJ {cnpj_limpo}...", apenas_terminal=True)
            url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
            res = requests.get(url, timeout=10)
            
            if res.status_code == 200:
                dados = res.json()
                descricoes = [dados.get("cnae_fiscal_descricao", "")]
                for cnae_sec in dados.get("cnaes_secundarios", []):
                    descricoes.append(cnae_sec.get("descricao", ""))

                palavras_ignoradas = {"comercio", "varejista", "atacadista", "de", "e", "artigos", "servicos", "manutencao", "reparacao", "fabricacao", "para", "em", "geral", "outros", "outras", "nao", "especificados", "anteriormente", "uso", "pecas", "acessorios", "instalacao", "construcao", "equipamentos", "maquinas", "aparelhos", "suprimentos", "produtos", "fornecimento"}
                
                self.palavras_chave_empresa = []
                for desc in descricoes:
                    if not desc: continue
                    palavras = Utils.normalizar_texto(desc).split()
                    for p in palavras:
                        p_limpa = re.sub(r'[^a-z]', '', p)
                        if len(p_limpa) > 2 and p_limpa not in palavras_ignoradas and p_limpa not in self.palavras_chave_empresa:
                            self.palavras_chave_empresa.append(p_limpa)

                self.registrar_log(f"[IA-CNAE] Flag de aderência ativa. Palavras mapeadas: {self.palavras_chave_empresa}", apenas_terminal=True)
        except Exception as e:
            self.registrar_log(f"[IA-CNAE ERROR] Falha ao criar perfil invisível: {e}", apenas_terminal=True)

    # ---------------------------------------------------------
    # ANÁLISE DE EDITAL E DOWNLOAD DE PDF
    # ---------------------------------------------------------
    def abrir_janela_arquivos(self):
        if not self.item_selecionado_doc: return
        cnpj, ano, seq = self.item_selecionado_doc
        self.btn_arquivos.configure(text="Aguarde...", state="disabled")
        url_arquivos = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
        threading.Thread(target=self._buscar_arquivos_thread, args=(url_arquivos,), daemon=True).start()

    def _buscar_arquivos_thread(self, url):
        try:
            res = self._get_com_retentativa(url, params={"pagina": 1, "tamanhoPagina": 100}, timeout=15, tipo_operacao="busca")
            if res and res.status_code == 200:
                dados = res.json()
                self.after(0, lambda: self.mostrar_janela_arquivos(dados.get("data", []) if isinstance(dados, dict) else (dados if isinstance(dados, list) else [])))
            else: self.after(0, lambda: messagebox.showinfo("Ficheiros", "Nenhum documento anexado foi encontrado."))
        except Exception as e: self.after(0, lambda erro=str(e): messagebox.showerror("Erro", f"Erro de conexão: {erro}"))
        finally: self.after(0, lambda: self.btn_arquivos.configure(text="📂 Ver Arquivos\n(PDF/Anexos)", state="normal"))

    def mostrar_janela_arquivos(self, arquivos):
        janela_arq = ctk.CTkToplevel(self)
        janela_arq.title("Documentos Oficiais")
        janela_arq.geometry("750x450")
        janela_arq.transient(self)
        if not arquivos:
            ctk.CTkLabel(janela_arq, text="⚠️ Sem anexos para download.", font=("Segoe UI", 14)).pack(pady=30)
            return
        lbl_info = ctk.CTkLabel(janela_arq, text="Lista de Documentos:", font=("Segoe UI", 12, "bold"))
        lbl_info.pack(pady=10, padx=10, anchor="w")
        frame_lista = ctk.CTkScrollableFrame(janela_arq)
        frame_lista.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for arq in arquivos:
            frame_item = ctk.CTkFrame(frame_lista, fg_color="#ecf0f1", corner_radius=5)
            frame_item.pack(fill="x", pady=5, padx=2)
            titulo, tipo, url_doc = arq.get("titulo", "S/ Título"), arq.get("tipoDocumentoNome", "Anexo"), arq.get("url", "")
            ctk.CTkLabel(frame_item, text=f"[{tipo}] {titulo}", font=("Segoe UI", 11, "bold"), text_color="#2c3e50", anchor="w", justify="left", wraplength=550).pack(side="left", padx=10, pady=10, fill="x", expand=True)
            if url_doc: ctk.CTkButton(frame_item, text="Baixar", width=100, fg_color="#2980b9", command=lambda u=url_doc: webbrowser.open(u)).pack(side="right", padx=10, pady=10)

    # NOVO MOTOR DE ANÁLISE: MULTI-PDF E CACHE NO BANCO
    def abrir_janela_analise(self):
        if not self.item_selecionado_doc: return
        cnpj, ano, seq = self.item_selecionado_doc
        
        self.btn_analise.configure(text="⏳ A preparar IA...", state="disabled", fg_color="#e17055")
        threading.Thread(target=self._iniciar_analise_com_delay, args=(cnpj, ano, seq), daemon=True).start()

    def _iniciar_analise_com_delay(self, cnpj, ano, seq):
        self.registrar_log("⏳ A segurar requisição (Timeout de segurança)...", apenas_terminal=True)
        time.sleep(2.0) 
        self.after(0, lambda: self.btn_analise.configure(text="🧠 A processar IA...", fg_color="#00cec9"))
        self._analisar_edital_thread(cnpj, ano, seq)

    def _analisar_edital_thread(self, cnpj, ano, seq):
        try:
            self.registrar_log("🤖 A transferir Resumo Base do PNCP...")
            url_compra = f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
            
            res = self._get_com_retentativa(url_compra, params={}, timeout=10, tipo_operacao="busca")
            
            objeto = info_comp = ""
            amparo = julgamento = modo_disputa = "N/I"
            valor_total = 0.0

            if res and res.status_code == 200:
                dados = res.json()
                objeto = dados.get("objetoCompra", "") or dados.get("objeto", "Não informado")
                info_comp = dados.get("informacaoComplementar", "") or "Sem informações complementares adicionais."
                amparo = dados.get("amparoLegal", {}).get("nome", "Não informado")
                julgamento = dados.get("criterioJulgamento", {}).get("nome", "Não informado")
                modo_disputa = dados.get("modoDisputa", {}).get("nome", "Não informado")
                valor_total = dados.get("valorTotalEstimado", 0.0)
            else:
                self.registrar_log("⚠️ Fallback ativado. Usando BD Local...")
                linhas = self.db.executar_leitura("SELECT objeto_contrato, vlr_total_est, modalidade_nome FROM editais_itens WHERE cnpj=? AND ano=? AND sequencial=? LIMIT 1", (cnpj, ano, seq))
                if linhas:
                    objeto = linhas[0][0]
                    modo_disputa = linhas[0][2]
                    try:
                        v_str = str(linhas[0][1]).replace("R$ ", "").replace(".", "").replace(",", ".")
                        valor_total = float(v_str) if v_str != "Não informado" else 0.0
                    except: valor_total = 0.0
                else:
                    self.after(0, lambda: messagebox.showinfo("Análise", "Dados indisponíveis."))
                    return

            texto_completo = f"{objeto}\n{info_comp}\n"
            fonte_detalhe = "🌐 Resumo PNCP"
            
            # ETAPA 2: LISTAR ARQUIVOS E VARREDURA MULTI-PDF
            self.registrar_log("🤖 Procurando ficheiros e anexos do Edital...")
            url_arquivos = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
            res_arq = self._get_com_retentativa(url_arquivos, params={"pagina":1, "tamanhoPagina":50}, timeout=10, tipo_operacao="busca")
            
            arquivos_lista = []
            pdf_texto_puro = ""

            if res_arq and res_arq.status_code == 200:
                dados_arq = res_arq.json()
                if isinstance(dados_arq, dict): arquivos_lista = dados_arq.get("data", [])
                elif isinstance(dados_arq, list): arquivos_lista = dados_arq
                    
                if HAS_PYPDF and arquivos_lista:
                    self.registrar_log("📄 Lendo múltiplos PDFs...")
                    pdfs_lidos = 0
                    for arq in arquivos_lista:
                        titulo = (arq.get("titulo", "")).lower()
                        tipo = (arq.get("tipoDocumentoNome", "")).lower()
                        url_pdf = arq.get("url")
                        
                        # Tenta extrair até 4 PDFs relevantes para ter visão geral sem estourar limite da IA
                        if url_pdf and pdfs_lidos < 4:
                            if "edital" in titulo or "termo" in titulo or "anexo" in titulo or url_pdf.endswith(".pdf"):
                                try:
                                    res_pdf = self.http_session.get(url_pdf, timeout=20)
                                    if res_pdf.status_code == 200:
                                        pdf_file = io.BytesIO(res_pdf.content)
                                        leitor = pypdf.PdfReader(pdf_file)
                                        
                                        # Identificador visual para o texto extraído
                                        pdf_texto_puro += f"\n\n{'='*40}\nDOCUMENTO: {titulo.upper()}\n{'='*40}\n"
                                        
                                        # Lê no máximo 30 páginas por PDF para não saturar
                                        for i in range(min(30, len(leitor.pages))): 
                                            ext = leitor.pages[i].extract_text()
                                            if ext: 
                                                pdf_texto_puro += f"\n--- PÁG {i+1} ---\n" + ext
                                        pdfs_lidos += 1
                                except Exception as epdf:
                                    self.registrar_log(f"⚠️ Erro ao ler PDF {titulo}: {epdf}", apenas_terminal=True)
                                    
                    if pdf_texto_puro.strip():
                        texto_completo += "\n" + pdf_texto_puro
                        fonte_detalhe += f" + 📄 Leitura de {pdfs_lidos} ficheiro(s) PDF"
                    else:
                        pdf_texto_puro = "⚠️ O texto dos PDFs não pôde ser extraído."

            # =====================================================================
            # ETAPA 3: IA GENERATIVA (Validada pela Nuvem / Vercel)
            # =====================================================================
            analise_salva = self.db.carregar_analise_ia(cnpj, ano, seq)
            
            if analise_salva:
                self.registrar_log("✅ Análise instantânea: Carregada da Base de Dados Local (Sem consumir limite da Nuvem).")
                relatorio = analise_salva
            else:
                self.registrar_log("🔄 Verificando permissões e limites na Nuvem...")
                
                # 1. Bate na API para incrementar o contador e pegar as chaves
                url_api_ia = self.url_api_licenca.replace("/valida", "/ia_uso") # Constrói a URL dinamicamente
                payload_ia = {"cnpj": self.cnpj_ativo, "maquina": platform.node(), "incrementar": True}
                
                try:
                    res_api = requests.post(url_api_ia, json=payload_ia, timeout=10)
                    dados_api = res_api.json()
                    
                    if dados_api.get("status") == "error":
                        msg_erro = dados_api.get("message", "Bloqueado pelo servidor.")
                        self.registrar_log(f"🛑 {msg_erro}")
                        self.after(0, lambda m=msg_erro: messagebox.showwarning("Limite de IA", m))
                        return # Aborta a análise
                        
                    chave_dots = dados_api.get("chave_dots", "")
                    chave_gemini = dados_api.get("chave_gemini", "")
                    usos_hj = dados_api.get("usos_hoje", 0)
                    limite_hj = dados_api.get("limite_diario", 0)
                    
                    self.registrar_log(f"✅ Autorizado! Consumo atual do CNPJ hoje: {usos_hj} de {limite_hj} análises permitidas.")
                    
                    if not chave_dots and not chave_gemini:
                        relatorio = "⚠️ O Administrador ainda não configurou as chaves de IA na nuvem."
                        self.after(0, lambda: self.mostrar_janela_analise(relatorio, pdf_texto_puro, arquivos_lista))
                        return
                except Exception as e:
                    self.registrar_log(f"⚠️ Erro ao validar limites na nuvem: {e}")
                    self.after(0, lambda: messagebox.showerror("Erro de Servidor", "Não foi possível conectar ao gestor de licenças."))
                    return

                # --- Início do Pedido ao OpenRouter/Gemini ---
                resposta_ia = ""
                modelo_usado = ""
                erro_txt = ""

                prompt = f"""
                Aja como um advogado especialista em Licitações Públicas no Brasil.
                Analise o texto do edital (e seus anexos) fornecido abaixo e extraia os pontos críticos com base nas informações literais encontradas.
                Formate a sua resposta em tópicos claros. Use emojis para ilustrar. 
                Se uma informação não estiver explícita, responda rigorosamente "Não mencionado no texto extraído".
                Não invente dados.
                
                Por favor, traga exatamente estes tópicos:
                - 📦 Objeto Resumido: (Qual é o principal foco da contratação em 2 frases?)
                - 📍 Local de Entrega/Execução: 
                - ⏳ Prazo de Entrega e Vigência:
                - 📦 Regime de Fornecimento: (Único, parcelado, contínuo ou sob demanda?)
                - 💸 Prazo e Condição de Pagamento:
                - 🧪 Exigência de Amostras:
                - 🛡️ Garantia Contratual: (Exige caução ou seguro-garantia?)
                - 💰 Qualificação Econômico-Financeira: (Exige balanço patrimonial ou capital mínimo?)
                - 🗺️ Vistoria/Visita Técnica:
                - 🏢 Participação Exclusiva ou Cotas para ME/EPP:
                - 📜 Certificações/Registros Específicos: (ANVISA, INMETRO, CREA, Alvarás, etc.)
                - 🤝 Subcontratação: (É permitida?)

                --- TEXTO DO EDITAL E ANEXOS PARA ANÁLISE ---
                {texto_completo[:100000]} 
                """

                # TENTA DOTS PRIMEIRO (Via OpenRouter)
                if chave_dots:
                    self.registrar_log("🧠 Iniciando análise via DOTS (Dots-3 Note Preview)...")
                    try:
                        url_dots = "https://openrouter.ai/api/v1/chat/completions" 
                        payload_dots = {
                            "model": "dots-studio/dots-3-note-preview:free",
                            "messages": [{"role": "user", "content": prompt}],
                            "reasoning": {"enabled": True}
                        }
                        headers_dots = {
                            "Authorization": f"Bearer {chave_dots.strip()}", 
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://seu-sistema.com", 
                            "X-Title": "Buscador PNCP"
                        }
                        
                        res_dots = requests.post(url_dots, json=payload_dots, headers=headers_dots, timeout=90)
                        
                        if res_dots.status_code == 200:
                            dados_dots = res_dots.json()
                            resposta_ia = dados_dots.get("choices", [{}])[0].get("message", {}).get("content", "")
                            modelo_usado = "Dots-3 Note Preview (OpenRouter - Primário)"
                        else:
                            erro_txt += f"• DOTS ({res_dots.status_code}): {res_dots.text}\n"
                            self.registrar_log(f"⚠️ Falha no DOTS: HTTP {res_dots.status_code}. Saltando para Fallback...", apenas_terminal=True)
                    except Exception as e:
                        erro_txt += f"• Erro conexão DOTS: {str(e)}\n"
                        self.registrar_log(f"⚠️ Erro no DOTS: {e}. Saltando para Fallback...", apenas_terminal=True)

                # SE DOTS FALHOU, TENTA GOOGLE GEMINI (Fallback)
                if not resposta_ia and chave_gemini:
                    self.registrar_log("🧠 Iniciando análise via Google Gemini (Fallback)...")
                    try:
                        url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={chave_gemini.strip()}"
                        payload_gemini = {"contents": [{"parts": [{"text": prompt}]}]}
                        
                        for tentativa in range(1, 4):
                            res_gemini = requests.post(url_gemini, json=payload_gemini, timeout=60)
                            
                            if res_gemini.status_code == 200:
                                resposta_ia = res_gemini.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                modelo_usado = "Google Gemini (Secundário/Fallback)"
                                break 
                            elif res_gemini.status_code in [503, 429]:
                                time.sleep(tentativa * 4)
                            else:
                                erro_txt += f"• Gemini ({res_gemini.status_code}): {res_gemini.text}\n"
                                break 
                    except Exception as e:
                        erro_txt += f"• Erro conexão Gemini: {str(e)}\n"
                
                # COMPILA O RESULTADO
                if resposta_ia:
                    relatorio = f"🧠 ANÁLISE INTELIGENTE | Processado por: IA\n"
                    relatorio += f"📡 FONTES ANALISADAS: {fonte_detalhe}\n"
                    relatorio += "="*80 + "\n\n"
                    relatorio += f"1️⃣ INFORMAÇÕES GERAIS E CONTRATUAIS\n"
                    relatorio += f"• Amparo Legal (Lei): {amparo}\n"
                    relatorio += f"• Modo de Disputa: {modo_disputa}\n"
                    relatorio += f"• Critério de Julgamento: {julgamento}\n"
                    relatorio += f"• Valor Total Estimado Global: {Utils.formatar_moeda(valor_total)}\n\n"
                    relatorio += "-"*80 + "\n"
                    relatorio += resposta_ia
                    relatorio += "\n" + "="*80 + "\n\n"
                    
                    self.db.salvar_analise_ia(cnpj, ano, seq, relatorio)
                else:
                    relatorio = f"⚠️ FALHA TOTAL NOS SERVIDORES DE IA.\n\nTentativas falhadas:\n{erro_txt}"
            # =====================================================================
            
            self.after(0, lambda: self.mostrar_janela_analise(relatorio, pdf_texto_puro, arquivos_lista))

        except Exception as e:
            self.registrar_log(f"[ANALISE ERROR] {e}", apenas_terminal=True)
            self.after(0, lambda erro=str(e): messagebox.showerror("Erro", f"Erro na análise: {erro}"))
        finally:
            self.after(0, lambda: self.btn_analise.configure(
                text="✨ Analisar com IA", 
                state="normal", 
                fg_color=self.cor_ia_normal
            ))

    def mostrar_janela_analise(self, relatorio_texto, texto_pdf, arquivos):
        janela_an = ctk.CTkToplevel(self)
        janela_an.title("Painel de Análise e Documentos Oficiais")
        janela_an.geometry("1000x750")
        janela_an.transient(self)
        
        tabview = ctk.CTkTabview(janela_an)
        tabview.pack(fill="both", expand=True, padx=10, pady=10)

        tab_resumo = tabview.add("📊 Resumo Inteligente (IA)")
        tab_texto_pdf = tabview.add("📄 Texto Extraído dos PDFs")
        tab_arquivos = tabview.add("📂 Listagem de Arquivos/Download")

        txt_resumo = ctk.CTkTextbox(tab_resumo, font=("Consolas", 13), fg_color="#fdfdfd", text_color="#2c3e50")
        txt_resumo.pack(fill="both", expand=True, padx=5, pady=5)
        txt_resumo.insert("end", relatorio_texto)
        txt_resumo.configure(state="disabled")

        txt_pdf = ctk.CTkTextbox(tab_texto_pdf, font=("Consolas", 11), fg_color="#fdfdfd", text_color="#34495e")
        txt_pdf.pack(fill="both", expand=True, padx=5, pady=5)
        txt_pdf.insert("end", texto_pdf)
        txt_pdf.configure(state="disabled")

        if not arquivos:
            ctk.CTkLabel(tab_arquivos, text="⚠️ Nenhum anexo foi disponibilizado no sistema do PNCP.", font=("Segoe UI", 14)).pack(pady=30)
        else:
            lbl_info = ctk.CTkLabel(tab_arquivos, text="Documentos originais associados à contratação:", font=("Segoe UI", 12, "bold"))
            lbl_info.pack(pady=10, padx=10, anchor="w")
            
            frame_lista = ctk.CTkScrollableFrame(tab_arquivos)
            frame_lista.pack(fill="both", expand=True, padx=5, pady=(0, 10))
            
            for arq in arquivos:
                frame_item = ctk.CTkFrame(frame_lista, fg_color="#ecf0f1", corner_radius=5)
                frame_item.pack(fill="x", pady=5, padx=2)
                
                titulo = arq.get("titulo", "S/ Título")
                tipo = arq.get("tipoDocumentoNome", "Anexo")
                url_doc = arq.get("url", "")
                
                ctk.CTkLabel(frame_item, text=f"[{tipo}]\n{titulo}", font=("Segoe UI", 11, "bold"), text_color="#2c3e50", anchor="w", justify="left", wraplength=700).pack(side="left", padx=10, pady=10, fill="x", expand=True)
                if url_doc: 
                    ctk.CTkButton(frame_item, text="📥 Abrir / Download", width=140, fg_color="#2980b9", hover_color="#1a5276", font=("Segoe UI", 11, "bold"), command=lambda u=url_doc: webbrowser.open(u)).pack(side="right", padx=10, pady=10)
    
    def _enviar_telemetria_background(self, qtd_editais):
        if not getattr(self, "cnpj_ativo", None) or qtd_editais <= 0: return
        try:
            url_telemetria = self.url_api_licenca.replace("/valida", "/telemetria")
            payload = {"cnpj": self.cnpj_ativo, "maquina": platform.node(), "qtd_editais": qtd_editais}
            requests.post(url_telemetria, json=payload, timeout=5)
        except: pass

    # ---------------------------------------------------------
    # UI COMPLETA (Interface Gráfica e Menus)
    # ---------------------------------------------------------
    def iniciar_sistema_principal(self):
        self.deiconify() 
        try: self.state('zoomed')
        except: self.attributes('-zoomed', True)

        self.config_precos = {
            "vlr_unit_est": tk.BooleanVar(value=True), "vlr_total_est": tk.BooleanVar(value=True), 
            "vlr_unit_hom": tk.BooleanVar(value=True), "vlr_total_hom": tk.BooleanVar(value=True),
            "media_orgao": tk.BooleanVar(value=True), "media_geral": tk.BooleanVar(value=True),
            "ultimo_orgao": tk.BooleanVar(value=True), "ultimo_regiao": tk.BooleanVar(value=True)
        }
        
        self.lista_portais_comuns = ["Compras.gov.br", "Portal de Compras Públicas", "BLL", "Licitações-e", "BEC", "Licitar Digital", "AZ Informática", "BBMNET", "BNC", "Portal de Compras da Caixa", "Licitanet", "Abase Sistemas", "Compras RS", "Compras SC", "Compras GO", "Ammfoco", "TCE", "Prefeitura"]
        self.vars_portais = {portal: tk.BooleanVar(value=False) for portal in self.lista_portais_comuns}
        self.vars_portais["Todos"] = tk.BooleanVar(value=True) 
        self.categorias_map = {"Todas": "", "Cessão": "1", "Compras": "2", "Informática (TIC)": "3", "Internacional": "4", "Locação Imóveis": "5", "Mão de Obra": "6", "Obras": "7", "Serviços": "8", "Serviços de Engenharia": "9", "Serviços de Saúde": "10", "Alienação de bens móveis/imóveis": "11"}
        self.modalidades_map = {"Principais (Pregão, Dispensa, Conc.)": "", "1 - Leilão Eletrônico": "1", "2 - Diálogo Competitivo": "2", "3 - Concurso": "3", "4 - Concorrência Eletrônica": "4", "5 - Concorrência Presencial": "5", "6 - Pregão Eletrônico": "6", "7 - Pregão Presencial": "7", "8 - Dispensa de Licitação": "8", "9 - Inexigibilidade": "9", "10 - Manifestação de Interesse": "10", "11 - Pré-qualificação": "11", "12 - Credenciamento": "12", "13 - Leilão Presencial": "13"}
        self.lista_ufs = ["Todas", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
        
        self._renovar_sessao_http()
        self.criar_menu_superior()
        self.criar_interface()

        self.bind('<Control-T>', self._abrir_prompt_terminal)
        self.bind('<Control-t>', self._abrir_prompt_terminal)
        self.registrar_log("[SYSTEM] Sistema iniciado. UI Carregada.", apenas_terminal=True)

        threading.Thread(target=self._carregar_perfil_empresa_background, daemon=True).start()
        threading.Thread(target=self._carregar_perfil_empresa_background, daemon=True).start()
        
        # INICIA O RADAR INVISÍVEL
        self.iniciar_motor_radar_background()

    def criar_menu_superior(self):
        self.menubar = tk.Menu(self)
        self.menu_opcoes = tk.Menu(self.menubar, tearoff=0)
        self.menu_opcoes.add_command(label="Configurar Colunas da Tabela", command=self.abrir_menu_configuracao)
        self.menu_opcoes.add_separator()
        self.menubar.add_cascade(label="Opções", menu=self.menu_opcoes)
        
        self.menu_sync = tk.Menu(self.menubar, tearoff=0)
        self.menu_sync.add_command(label="Sincronizar Banco de Dados (API)", command=self.abrir_janela_carga)
        self.menu_sync.add_separator()
        self.menu_sync.add_command(label="Parar Atualização", command=self.parar_carga_background, state="disabled")
        self.menubar.add_cascade(label="Atualização", menu=self.menu_sync)
        self.config(menu=self.menubar)
        self.menu_opcoes.add_separator()
        self.menu_opcoes.add_command(label="Radar Automático e E-mail", command=self.abrir_menu_radar)

    def abrir_menu_configuracao(self):
        janela_config = ctk.CTkToplevel(self)
        janela_config.title("Configurar Colunas de Preço")
        janela_config.geometry("380x350")
        janela_config.transient(self) 
        janela_config.grab_set() 
        lbl_titulo = ctk.CTkLabel(janela_config, text="Selecione as colunas a apresentar:", font=("Segoe UI", 12, "bold"))
        lbl_titulo.pack(pady=(15, 10))
        ctk.CTkCheckBox(janela_config, text="Valor Unitário Estimado", variable=self.config_precos["vlr_unit_est"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Total Estimado", variable=self.config_precos["vlr_total_est"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Unitário Homologado", variable=self.config_precos["vlr_unit_hom"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Total Homologado", variable=self.config_precos["vlr_total_hom"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Média do Órgão (Últ. 12 meses)", variable=self.config_precos["media_orgao"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Média Geral (Últ. 12 meses)", variable=self.config_precos["media_geral"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Último Preço Vencedor (Próprio Órgão)", variable=self.config_precos["ultimo_orgao"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Último Preço Vencedor (Região/UF)", variable=self.config_precos["ultimo_regiao"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkButton(janela_config, text="Aplicar e Fechar", command=lambda: [self.aplicar_colunas_grid(), janela_config.destroy()]).pack(pady=20)

    def set_estado_menu_carga(self, em_andamento: bool):
        self.is_carga_running = em_andamento
        if em_andamento:
            self.menu_sync.entryconfig("Sincronizar Banco de Dados (API)", state="disabled")
            self.menu_sync.entryconfig("Parar Atualização", state="normal")
            self.chk_base_local.select()
            self.chk_base_local.configure(state="disabled")
        else:
            self.menu_sync.entryconfig("Sincronizar Banco de Dados (API)", state="normal")
            self.menu_sync.entryconfig("Parar Atualização", state="disabled")
            self.chk_base_local.configure(state="normal")

    def abrir_janela_carga(self):
        janela = ctk.CTkToplevel(self)
        janela.title("Atualização - Sincronizar Base Local")
        janela.geometry("600x650")
        janela.transient(self) 
        janela.grab_set() 

        lbl_titulo = ctk.CTkLabel(janela, text="Defina os Filtros para Descarregar os Dados:", font=("Segoe UI", 14, "bold"))
        lbl_titulo.pack(pady=(15, 10))
        frame_filtros = ctk.CTkFrame(janela, fg_color="transparent")
        frame_filtros.pack(fill="x", padx=20, pady=5)

        data_atual = datetime.datetime.now()
        dt_ini_str = (data_atual - datetime.timedelta(days=7)).strftime("%d/%m/%Y")
        dt_fim_str = data_atual.strftime("%d/%m/%Y")

        ctk.CTkLabel(frame_filtros, text="Data Publicação (Início):").grid(row=0, column=0, sticky="w", pady=5)
        ent_dt_ini = ctk.CTkEntry(frame_filtros, width=130)
        ent_dt_ini.insert(0, dt_ini_str)
        ent_dt_ini.grid(row=0, column=1, sticky="w", padx=10, pady=5)

        ctk.CTkLabel(frame_filtros, text="Data Publicação (Fim):").grid(row=0, column=2, sticky="e", pady=5)
        ent_dt_fim = ctk.CTkEntry(frame_filtros, width=130)
        ent_dt_fim.insert(0, dt_fim_str)
        ent_dt_fim.grid(row=0, column=3, sticky="w", padx=10, pady=5)

        ctk.CTkLabel(frame_filtros, text="Estado (UF) do Órgão:").grid(row=1, column=0, sticky="w", pady=10)
        combo_uf = ctk.CTkOptionMenu(frame_filtros, values=self.lista_ufs, width=130)
        combo_uf.set("Todas")
        combo_uf.grid(row=1, column=1, sticky="w", padx=10, pady=10)

        ctk.CTkLabel(frame_filtros, text="Categoria do Processo:").grid(row=1, column=2, sticky="e", pady=10)
        combo_cat = ctk.CTkOptionMenu(frame_filtros, values=list(self.categorias_map.keys()), width=200)
        combo_cat.set("Todas")
        combo_cat.grid(row=1, column=3, sticky="w", padx=10, pady=10)

        ctk.CTkLabel(frame_filtros, text="Modalidade de Contratação:").grid(row=2, column=0, sticky="w", pady=10)
        combo_mod = ctk.CTkOptionMenu(frame_filtros, values=list(self.modalidades_map.keys()), width=250)
        combo_mod.set("Principais (Pregão, Dispensa, Conc.)")
        combo_mod.grid(row=2, column=1, columnspan=3, sticky="w", padx=10, pady=10)

        vars_portais_carga = {p: tk.BooleanVar(value=False) for p in self.lista_portais_comuns}
        vars_portais_carga["Todos"] = tk.BooleanVar(value=True)

        def _chk_todos_click():
            if vars_portais_carga["Todos"].get():
                for p in self.lista_portais_comuns: vars_portais_carga[p].set(False)
        def _chk_ind_click():
            if any(vars_portais_carga[p].get() for p in self.lista_portais_comuns): vars_portais_carga["Todos"].set(False)
            else: vars_portais_carga["Todos"].set(True)

        ctk.CTkLabel(janela, text="Selecione os Portais alvo:").pack(anchor="w", padx=20, pady=(10, 0))
        frame_scroll_portais = ctk.CTkScrollableFrame(janela, height=150)
        frame_scroll_portais.pack(fill="x", padx=20, pady=5)

        ctk.CTkCheckBox(frame_scroll_portais, text="Todos os Portais", variable=vars_portais_carga["Todos"], command=_chk_todos_click, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=5)
        ctk.CTkFrame(frame_scroll_portais, height=2, fg_color="gray").pack(fill="x", pady=2)
        for portal in self.lista_portais_comuns: ctk.CTkCheckBox(frame_scroll_portais, text=portal, variable=vars_portais_carga[portal], command=_chk_ind_click).pack(anchor="w", padx=15, pady=2)

        def processar_inicio():
            d_ini = Utils.formatar_data_api(ent_dt_ini.get().strip())
            d_fim = Utils.formatar_data_api(ent_dt_fim.get().strip())
            uf = combo_uf.get()
            cat_id = self.categorias_map.get(combo_cat.get())
            mod_id = self.modalidades_map.get(combo_mod.get())
            p_sel = [] if vars_portais_carga["Todos"].get() else [p for p in self.lista_portais_comuns if vars_portais_carga[p].get()]
                
            self.cancelar_carga = False
            self.set_estado_menu_carga(True)
            self.mostrar_carga_no_grid = True 
            self.lbl_status.configure(text="A sincronizar banco de dados... (Pode usar a pesquisa local à vontade)", text_color="#8e44ad")
            threading.Thread(target=self._executar_carga_base_thread, args=(d_ini, d_fim, cat_id, mod_id, uf, p_sel), daemon=True).start()
            janela.destroy()

        btn_iniciar = ctk.CTkButton(janela, text="🚀 Iniciar Sincronização em Segundo Plano", fg_color="#8e44ad", hover_color="#732d91", font=("Segoe UI", 12, "bold"), command=processar_inicio)
        btn_iniciar.pack(pady=20)

    def parar_carga_background(self):
        if not messagebox.askyesno("Parar", "Deseja parar a Atualização?\nOs dados já salvos no banco não serão perdidos."): return
        self.cancelar_carga = True
        self.lbl_status.configure(text="A interromper processo...", text_color="#e74c3c")
        try: self.http_session.close()
        except: pass
        self._renovar_sessao_http()
        self.set_estado_menu_carga(False)
        self.registrar_log("🛑 Atualização em massa cancelada instantaneamente pelo utilizador.")

    def criar_interface(self):
        # 🎨 MELHORIA DE DESIGN WINDOWS XP -> SISTEMA MODERNO FLAT
        style = ttk.Style()
        style.theme_use("clam") # Remove visual antigo 3D
        style.configure("Treeview", rowheight=35, font=("Segoe UI", 10), borderwidth=0, background="#ffffff", fieldbackground="#ffffff", foreground="#2f3640")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#f1f2f6", foreground="#2c3e50", borderwidth=0, padding=4)
        style.map("Treeview", background=[('selected', '#e0f7fa')], foreground=[('selected', '#000000')]) # Seleção moderna
        style.map("Treeview.Heading", background=[('active', '#dcdde1')])

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_pesquisa = self.tabview.add("🔍 Pesquisa e Portais")
        self.tab_logs = self.tabview.add("📜 Logs do Sistema")

        self.frame_busca = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_busca.pack(fill="x", padx=10, pady=5)

        self.lbl_termo = ctk.CTkLabel(self.frame_busca, text="Produto/Serviço (Termo de busca):", font=("Segoe UI", 12, "bold"))
        self.lbl_termo.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.ent_termo = ctk.CTkEntry(self.frame_busca, width=350, placeholder_text="Deixe vazio para extrair todo o Edital")
        self.ent_termo.grid(row=0, column=1, columnspan=2, sticky="we", padx=5, pady=5)
        self.ent_termo.bind("<Return>", lambda e: self.iniciar_busca())

        self.lbl_alvo = ctk.CTkLabel(self.frame_busca, text="Onde buscar o termo:")
        self.lbl_alvo.grid(row=0, column=3, sticky="e", padx=5, pady=5)
        self.combo_alvo = ctk.CTkOptionMenu(self.frame_busca, values=["Todos", "Apenas no Item", "Apenas no Objeto do Edital"], width=180)
        self.combo_alvo.set("Todos")
        self.combo_alvo.grid(row=0, column=4, sticky="w", padx=5, pady=5)

        self.btn_buscar = ctk.CTkButton(self.frame_busca, text="🔍 Pesquisar", command=self.iniciar_busca, font=("Segoe UI", 12, "bold"))
        self.btn_buscar.grid(row=0, column=5, padx=10, pady=5)
        self.default_btn_buscar_fg = self.btn_buscar.cget("fg_color")
        self.default_btn_buscar_hover = self.btn_buscar.cget("hover_color")

        data_atual = datetime.datetime.now()
        data_ini_padrao = (data_atual - datetime.timedelta(days=7)).strftime("%d/%m/%Y")
        data_fim_padrao = data_atual.strftime("%d/%m/%Y")

        self.lbl_data_ini = ctk.CTkLabel(self.frame_busca, text="Data Publicação (Início):")
        self.lbl_data_ini.grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.ent_data_ini = ctk.CTkEntry(self.frame_busca, width=120)
        self.ent_data_ini.insert(0, data_ini_padrao)
        self.ent_data_ini.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        self.lbl_data_fim = ctk.CTkLabel(self.frame_busca, text="Data Publicação (Fim):")
        self.lbl_data_fim.grid(row=1, column=2, sticky="e", padx=5, pady=5)
        self.ent_data_fim = ctk.CTkEntry(self.frame_busca, width=120)
        self.ent_data_fim.insert(0, data_fim_padrao)
        self.ent_data_fim.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        self.lbl_status_edital = ctk.CTkLabel(self.frame_busca, text="Status do Edital:")
        self.lbl_status_edital.grid(row=1, column=4, sticky="e", padx=5, pady=5)
        self.combo_status = ctk.CTkOptionMenu(self.frame_busca, values=["Todos", "Encerradas", "A Receber/Recebendo Proposta"], width=180)
        self.combo_status.set("Todos")
        self.combo_status.grid(row=1, column=5, sticky="w", padx=5, pady=5)

        self.lbl_portal = ctk.CTkLabel(self.frame_busca, text="Portais de Compra:")
        self.lbl_portal.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.btn_portal = ctk.CTkButton(self.frame_busca, text="Selecionar", width=120, fg_color="#3498db", hover_color="#2980b9", command=self.abrir_menu_portais)
        self.btn_portal.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        self.lbl_categoria = ctk.CTkLabel(self.frame_busca, text="Categoria do Processo:")
        self.lbl_categoria.grid(row=2, column=2, sticky="e", padx=5, pady=5)
        self.combo_categoria = ctk.CTkOptionMenu(self.frame_busca, values=list(self.categorias_map.keys()), width=150)
        self.combo_categoria.set("Todas")
        self.combo_categoria.grid(row=2, column=3, sticky="w", padx=5, pady=5)

        self.lbl_modalidade = ctk.CTkLabel(self.frame_busca, text="Modalidade Contratação:")
        self.lbl_modalidade.grid(row=2, column=4, sticky="e", padx=5, pady=5)
        self.combo_modalidade = ctk.CTkOptionMenu(self.frame_busca, values=list(self.modalidades_map.keys()), width=180)
        self.combo_modalidade.set("Principais (Pregão, Dispensa, Conc.)")
        self.combo_modalidade.grid(row=2, column=5, sticky="w", padx=5, pady=5)

        self.lbl_uf = ctk.CTkLabel(self.frame_busca, text="Estado (UF) do Órgão:")
        self.lbl_uf.grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.combo_uf = ctk.CTkOptionMenu(self.frame_busca, values=self.lista_ufs, width=80)
        self.combo_uf.set("Todas")
        self.combo_uf.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        self.lbl_edital = ctk.CTkLabel(self.frame_busca, text="Nº Edital (Ex: 10/2024):")
        self.lbl_edital.grid(row=3, column=2, sticky="e", padx=5, pady=5)
        self.ent_edital = ctk.CTkEntry(self.frame_busca, width=120)
        self.ent_edital.grid(row=3, column=3, sticky="w", padx=5, pady=5)
        self.ent_edital.bind("<Return>", lambda e: self.iniciar_busca())

        self.lbl_uasg = ctk.CTkLabel(self.frame_busca, text="UASG / CNPJ do Órgão:")
        self.lbl_uasg.grid(row=3, column=4, sticky="e", padx=5, pady=5)
        self.ent_uasg = ctk.CTkEntry(self.frame_busca, width=150)
        self.ent_uasg.grid(row=3, column=5, sticky="w", padx=5, pady=5)
        self.ent_uasg.bind("<Return>", lambda e: self.iniciar_busca())

        self.chk_base_local = ctk.CTkCheckBox(self.frame_busca, text="💾 Buscar apenas na Base Local (Obrigatório durante a Sincronização)", font=("Segoe UI", 11, "bold"))
        self.chk_base_local.grid(row=4, column=0, columnspan=6, sticky="w", padx=5, pady=5)

        self.frame_head_tabela = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_head_tabela.pack(fill="x", padx=10, pady=(15, 2))
        self.lbl_titulo_tabela = ctk.CTkLabel(self.frame_head_tabela, text="Resultados da Pesquisa / Sincronização (Duplo clique abre online):", font=("Segoe UI", 12, "bold"))
        self.lbl_titulo_tabela.pack(side="left", padx=5)
        self.lbl_status = ctk.CTkLabel(self.frame_head_tabela, text="Pronto para buscar.", text_color="#2ecc71", font=("Segoe UI", 11, "italic"))
        self.lbl_status.pack(side="left", padx=25)
        
        # Botões de Ação no Topo
        self.btn_exportar = ctk.CTkButton(self.frame_head_tabela, text="📊 Exportar Excel", state="disabled", fg_color="#27ae60", width=130, command=self.exportar_excel)
        self.btn_exportar.pack(side="right", padx=5)

        self.cor_ia_normal = "#6c5ce7" 
        self.cor_ia_hover = "#a29bfe"  
        self.btn_analise = ctk.CTkButton(
            self.frame_head_tabela, 
            text="✨ Analisar com IA", 
            width=140, 
            fg_color=self.cor_ia_normal, hover_color=self.cor_ia_hover, 
            state="disabled", font=("Segoe UI", 12, "bold"), 
            command=self.abrir_janela_analise
        )
        self.btn_analise.pack(side="right", padx=(5, 5))
        # --- NOVO BOTÃO SININHO (Notificações) ---
        self.btn_notificacoes = ctk.CTkButton(
            self.frame_head_tabela, text="🔔 (0)", width=60, 
            fg_color="#e67e22", hover_color="#d35400", font=("Segoe UI", 12, "bold"),
            command=self.abrir_janela_notificacoes
        )
        self.btn_notificacoes.pack(side="right", padx=(5, 15))

        # Tabela Modernizada
        self.frame_tabela = ctk.CTkFrame(self.tab_pesquisa)
        self.frame_tabela.pack(fill="both", expand=True, padx=10, pady=2)

        colunas = ("orgao", "uf", "portal", "edital", "objeto", "qtd", "vlr_unit_est", "vlr_total_est", "vlr_unit_hom", "vlr_total_hom", "media_orgao", "media_geral", "ultimo_orgao", "ultimo_regiao", "data", "data_abertura", "data_encerramento", "cnpj", "ano", "seq", "modalidade_nome", "objeto_contrato")
        self.tree = ttk.Treeview(self.frame_tabela, columns=colunas, show="headings")
        
        self.tree.heading("orgao", text="Órgão / Unidade")
        self.tree.heading("uf", text="UF")
        self.tree.heading("portal", text="Portal")
        self.tree.heading("edital", text="Edital (Num/Ano)")
        self.tree.heading("objeto", text="Descrição do Item / Objeto")
        self.tree.heading("qtd", text="Qtd")
        self.tree.heading("vlr_unit_est", text="Unit. Estimado")
        self.tree.heading("vlr_total_est", text="Total Estimado")
        self.tree.heading("vlr_unit_hom", text="Unit. Homologado")
        self.tree.heading("vlr_total_hom", text="Total Homologado")
        self.tree.heading("ultimo_orgao", text="Últ. Preço (Órgão)")
        self.tree.heading("ultimo_regiao", text="Últ. Preço (Região)")
        self.tree.heading("data", text="Data Pub.")
        self.tree.heading("data_abertura", text="Abertura")
        self.tree.heading("data_encerramento", text="Encerramento")
        self.tree.heading("media_orgao", text="Média Órgão (12m)")
        self.tree.heading("media_geral", text="Média Geral (12m)")
                
        self.tree.tag_configure('aderente', background='#d4efdf')

        for col in colunas:
            self.tree.heading(col, text=self.tree.heading(col)["text"], command=lambda c=col: self._ordenar_coluna(c, False))

        self.tree.column("orgao", width=180, minwidth=120, stretch=tk.YES)
        self.tree.column("uf", width=40, anchor="center", minwidth=40, stretch=tk.YES)
        self.tree.column("portal", width=120, anchor="w", minwidth=80, stretch=tk.YES)
        self.tree.column("edital", width=110, anchor="center", minwidth=80, stretch=tk.YES)
        self.tree.column("objeto", width=250, minwidth=150, stretch=tk.YES)
        self.tree.column("qtd", width=50, anchor="center", minwidth=50, stretch=tk.YES)
        self.tree.column("vlr_unit_est", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_total_est", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_unit_hom", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_total_hom", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("media_orgao", width=110, anchor="e", minwidth=90, stretch=tk.YES)
        self.tree.column("media_geral", width=110, anchor="e", minwidth=90, stretch=tk.YES)
        self.tree.column("ultimo_orgao", width=110, anchor="e", minwidth=90, stretch=tk.YES)
        self.tree.column("ultimo_regiao", width=110, anchor="e", minwidth=90, stretch=tk.YES)
        self.tree.column("data", width=90, anchor="center", minwidth=80, stretch=tk.YES)
        self.tree.column("data_abertura", width=130, anchor="center", minwidth=90, stretch=tk.YES)
        self.tree.column("data_encerramento", width=130, anchor="center", minwidth=90, stretch=tk.YES)

        self.aplicar_colunas_grid()

        scrollbar_y = ttk.Scrollbar(self.frame_tabela, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(self.frame_tabela, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=scrollbar_y.set, xscroll=scrollbar_x.set)
        scrollbar_x.pack(side="bottom", fill="x")
        scrollbar_y.pack(side="right", fill="y")
        self.tree.pack(side="top", fill="both", expand=True)

        self.frame_detalhes = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_detalhes.pack(fill="x", padx=10, pady=(2, 10))

        self.txt_detalhes = ctk.CTkTextbox(self.frame_detalhes, height=100, font=("Segoe UI", 12), text_color="#2c3e50")
        self.txt_detalhes.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.txt_detalhes.insert("end", "Selecione um item na tabela acima para visualizar a descrição multilinha aqui.")
        self.txt_detalhes.configure(state="disabled")

        self.btn_arquivos = ctk.CTkButton(
            self.frame_detalhes, text="📂 Ver Arquivos\n(PDF/Anexos)", width=140, height=100,
            fg_color="#d35400", hover_color="#e67e22", state="disabled", font=("Segoe UI", 12, "bold"), command=self.abrir_janela_arquivos
        )
        self.btn_arquivos.pack(side="right", padx=(5, 0))

        self.tree.bind("<<TreeviewSelect>>", self._ao_selecionar_tabela)
        self.tree.bind("<Double-1>", self._ao_duplo_clique_tabela)
        
        self.txt_logs = ctk.CTkTextbox(self.tab_logs, font=("Consolas", 11))
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=10)

    def _ordenar_coluna(self, col, reverse):
        lista = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        def converter_valor(val):
            if not val or val in ("Não informado", "N/I", "Sem Histórico"): return -1
            if "R$" in val:
                try: return float(val.replace("R$ ", "").replace(".", "").replace(",", "."))
                except: pass
            if len(val) >= 10 and val[2] == '/' and val[5] == '/':
                try: return datetime.datetime.strptime(val[:16], "%d/%m/%Y %H:%M").timestamp()
                except:
                    try: return datetime.datetime.strptime(val[:10], "%d/%m/%Y").timestamp()
                    except: pass
            try: return float(val)
            except: return val.lower()

        lista.sort(key=lambda t: converter_valor(t[0]), reverse=reverse)
        for index, (val, k) in enumerate(lista): self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self._ordenar_coluna(col, not reverse))

    def aplicar_colunas_grid(self):
        colunas_visiveis = ["orgao", "uf", "portal", "edital", "objeto", "qtd"]
        if self.config_precos.get("vlr_unit_est", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("vlr_unit_est")
        if self.config_precos.get("vlr_total_est", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("vlr_total_est")
        if self.config_precos.get("vlr_unit_hom", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("vlr_unit_hom")
        if self.config_precos.get("vlr_total_hom", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("vlr_total_hom")
        if self.config_precos.get("media_orgao", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("media_orgao")
        if self.config_precos.get("media_geral", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("media_geral")
        if self.config_precos.get("ultimo_orgao", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("ultimo_orgao")
        if self.config_precos.get("ultimo_regiao", tk.BooleanVar(value=True)).get(): colunas_visiveis.append("ultimo_regiao")
        colunas_visiveis.extend(["data", "data_abertura", "data_encerramento"])
        self.tree.configure(displaycolumns=colunas_visiveis)

    def _on_chk_todos_portais_click(self):
        if self.vars_portais["Todos"].get():
            for p in self.lista_portais_comuns: self.vars_portais[p].set(False)

    def _on_chk_portal_click(self):
        if any(self.vars_portais[p].get() for p in self.lista_portais_comuns): self.vars_portais["Todos"].set(False)
        else: self.vars_portais["Todos"].set(True)

    def abrir_menu_portais(self):
        janela_portais = ctk.CTkToplevel(self)
        janela_portais.title("Filtro de Portais")
        janela_portais.geometry("380x480")
        janela_portais.transient(self) 
        janela_portais.grab_set() 
        lbl_titulo = ctk.CTkLabel(janela_portais, text="Selecione os portais para a busca:", font=("Segoe UI", 12, "bold"))
        lbl_titulo.pack(pady=(15, 5))
        frame_scroll = ctk.CTkScrollableFrame(janela_portais)
        frame_scroll.pack(fill="both", expand=True, padx=15, pady=5)
        ctk.CTkCheckBox(frame_scroll, text="Qualquer Portal (Todos)", font=("Segoe UI", 12, "bold"), variable=self.vars_portais["Todos"], command=self._on_chk_todos_portais_click).pack(anchor="w", padx=5, pady=10)
        ctk.CTkFrame(frame_scroll, height=2, fg_color="gray").pack(fill="x", pady=5)
        for portal in self.lista_portais_comuns: ctk.CTkCheckBox(frame_scroll, text=portal, variable=self.vars_portais[portal], command=self._on_chk_portal_click).pack(anchor="w", padx=20, pady=4)
        ctk.CTkButton(janela_portais, text="Confirmar Filtro", command=janela_portais.destroy).pack(pady=15)

    def obter_portais_selecionados(self):
        if self.vars_portais["Todos"].get(): return []
        return [p for p in self.lista_portais_comuns if self.vars_portais[p].get()]

    def exportar_excel(self):
        if not self.tree.get_children():
            messagebox.showinfo("Exportar", "Não há dados na tabela para exportar.")
            return
        caminho_arquivo = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("Arquivo Excel (CSV)", "*.csv"), ("Todos os Arquivos", "*.*")], title="Salvar Planilha de Exportação")
        if not caminho_arquivo: return
        try:
            with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                colunas_id = self.tree["columns"]
                writer.writerow([self.tree.heading(col)["text"] for col in colunas_id])
                for row_id in self.tree.get_children(): writer.writerow(self.tree.item(row_id)["values"])
            messagebox.showinfo("Exportação Concluída", f"O ficheiro foi gerado com sucesso em:\n{caminho_arquivo}")
        except Exception as e: messagebox.showerror("Erro na Exportação", f"Falha ao gerar o ficheiro:\n{e}")

    def cancelar_busca_manual(self):
        self.cancelar_busca = True
        self.lbl_status.configure(text="Busca cancelada.", text_color="#e74c3c")
        self.btn_buscar.configure(text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal")
        self.btn_exportar.configure(state="normal" if len(self.tree.get_children()) > 0 else "disabled")
        try: self.http_session.close()
        except: pass
        self._renovar_sessao_http()
        self.registrar_log("🛑 Pesquisa interrompida instantaneamente.")

    def _ao_selecionar_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 22:
            orgao, uf, portal, edital_resumo, desc_item_completo = valores[0], valores[1], valores[2], valores[3], valores[4]
            media_org, media_ger = valores[10], valores[11]
            ult_org, ult_reg = valores[12], valores[13]
            data_abertura, data_encerramento = valores[14], valores[15]
            cnpj, ano, seq, mod_nome, objeto_geral = valores[17], valores[18], valores[19], valores[20], valores[21]
            
            self.item_selecionado_doc = (cnpj, ano, seq)
            self.btn_arquivos.configure(state="normal")
            self.btn_analise.configure(state="normal")
            
            aderencia_msg = "\n\n💡 PRODUTO ADERENTE: Este item tem alta probabilidade de corresponder aos serviços do seu CNPJ!" if desc_item_completo.startswith("⭐") else ""

            texto_exibicao = f"🏢 ÓRGÃO: {orgao} ({uf})   |   🌐 PORTAL: {portal}\n📄 EDITAL: {edital_resumo}  |  ⚖️ MODALIDADE: {mod_nome}  |  🔗 Link: https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}\n⏰ DISPUTA: Abertura em {data_abertura} - Encerramento em {data_encerramento}\n📊 PREÇO MÉDIO: No Órgão ({media_org})  |  Geral ({media_ger})\n🏆 ÚLTIMO VENCEDOR: No Órgão ({ult_org})  |  Na Região/UF ({ult_reg})\n🎯 OBJETO GERAL: {objeto_geral}\n📦 DESCRIÇÃO DO ITEM: {desc_item_completo}{aderencia_msg}"
            self.txt_detalhes.configure(state="normal")
            self.txt_detalhes.delete("1.0", "end")
            self.txt_detalhes.insert("end", texto_exibicao)
            self.txt_detalhes.configure(state="disabled")

    def _ao_duplo_clique_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 20: webbrowser.open(f"https://pncp.gov.br/app/editais/{valores[17]}/{valores[18]}/{valores[19]}")
        
    def atualizar_sininho(self):
        nao_lidas = len(self.db.obter_notificacoes(apenas_nao_lidas=True))
        cor = "#e74c3c" if nao_lidas > 0 else "#95a5a6"
        texto = f"🔔 ({nao_lidas})"
        if hasattr(self, 'btn_notificacoes'):
            self.btn_notificacoes.configure(text=texto, fg_color=cor)

    def abrir_janela_notificacoes(self):
        janela_notif = ctk.CTkToplevel(self)
        janela_notif.title("Central de Notificações - Radar Automático")
        janela_notif.geometry("800x500")
        janela_notif.transient(self)
        
        lbl_titulo = ctk.CTkLabel(janela_notif, text="Oportunidades Encontradas pelo Radar:", font=("Segoe UI", 14, "bold"))
        lbl_titulo.pack(pady=10)
        
        frame_lista = ctk.CTkScrollableFrame(janela_notif)
        frame_lista.pack(fill="both", expand=True, padx=10, pady=10)
        
        notificacoes = self.db.obter_notificacoes(apenas_nao_lidas=False)
        if not notificacoes:
            ctk.CTkLabel(frame_lista, text="Nenhuma oportunidade nova encontrada ainda.").pack(pady=20)
        else:
            for notif in notificacoes:
                cor_fundo = "#ecf0f1" if notif[4] else "#d4efdf" # Verde se não lida
                frame_item = ctk.CTkFrame(frame_lista, fg_color=cor_fundo, corner_radius=5)
                frame_item.pack(fill="x", pady=5, padx=2)
                ctk.CTkLabel(frame_item, text=f"🏢 {notif[1]}\n🎯 {notif[2]}", font=("Segoe UI", 11), justify="left", wraplength=600).pack(side="left", padx=10, pady=10, fill="x", expand=True)
                ctk.CTkButton(frame_item, text="Abrir Link", width=100, command=lambda u=notif[3]: webbrowser.open(u)).pack(side="right", padx=10)
        
        self.db.marcar_notificacoes_lidas()
        self.atualizar_sininho()

    def abrir_menu_radar(self):
        janela_radar = ctk.CTkToplevel(self)
        janela_radar.title("Configurar Radar Automático e Alertas")
        janela_radar.geometry("500x550")
        janela_radar.transient(self)
        janela_radar.grab_set()

        config = self.db.obter_config_alertas()

        st_frame = ctk.CTkScrollableFrame(janela_radar)
        st_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkLabel(st_frame, text="1. Filtros de Busca Automática", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(10,5))
        ctk.CTkLabel(st_frame, text="Palavras-Chave (separadas por vírgula):").pack(anchor="w")
        ent_pal = ctk.CTkEntry(st_frame, width=450)
        ent_pal.insert(0, config["palavras"]); ent_pal.pack(pady=5)
        
        col1, col2 = ctk.CTkFrame(st_frame, fg_color="transparent"), ctk.CTkFrame(st_frame, fg_color="transparent")
        col1.pack(fill="x"); col2.pack(fill="x", pady=5)
        ctk.CTkLabel(col1, text="Estado (UF):").pack(side="left")
        combo_uf = ctk.CTkOptionMenu(col1, values=self.lista_ufs, width=100); combo_uf.set(config["uf"] or "Todas"); combo_uf.pack(side="left", padx=10)
        
        ctk.CTkLabel(col2, text="Modalidade:").pack(side="left")
        combo_mod = ctk.CTkOptionMenu(col2, values=list(self.modalidades_map.keys()), width=200); combo_mod.set(config["modalidade"] or "Principais (Pregão, Dispensa, Conc.)"); combo_mod.pack(side="left", padx=10)

        ctk.CTkLabel(st_frame, text="2. Configuração de E-mail (Gmail)", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(20,5))
        ctk.CTkLabel(st_frame, text="E-mail de Destino (Quem recebe):").pack(anchor="w")
        ent_dest = ctk.CTkEntry(st_frame, width=450)
        ent_dest.insert(0, config["destino"]); ent_dest.pack(pady=5)

        ctk.CTkLabel(st_frame, text="Seu E-mail Remetente (Conta do Sistema):").pack(anchor="w")
        ent_remet = ctk.CTkEntry(st_frame, width=450)
        ent_remet.insert(0, config["remetente"]); ent_remet.pack(pady=5)

        ctk.CTkLabel(st_frame, text="Senha de App do Gmail (Não é a senha normal!):").pack(anchor="w")
        ent_senha = ctk.CTkEntry(st_frame, width=450, show="*")
        ent_senha.insert(0, config["senha"]); ent_senha.pack(pady=5)

        def salvar():
            self.db.salvar_config_alertas(ent_dest.get(), ent_remet.get(), ent_senha.get(), ent_pal.get(), combo_uf.get(), combo_mod.get())
            messagebox.showinfo("Sucesso", "Radar configurado! O sistema buscará as oportunidades em background.")
            janela_radar.destroy()
            
        ctk.CTkButton(st_frame, text="💾 Salvar e Ativar Radar", fg_color="#27ae60", hover_color="#2ecc71", command=salvar).pack(pady=20)    

    # ---------------------------------------------------------
    # OPERAÇÕES DE BUSCA E SINCRONIZAÇÃO
    # ---------------------------------------------------------
    def _executar_carga_base_thread(self, data_inicio, data_fim, categoria_id, modalidade_id, uf_selecionada, portais_selecionados):
        if self.mostrar_carga_no_grid: self.after(0, self._limpar_tabela)
        url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
        modalidades = [int(modalidade_id)] if modalidade_id else [8, 6, 4]
        contratacoes_processadas = set()
        novos_itens = 0
        self.registrar_log(f"🚀 Iniciando ATUALIZAÇÃO EM MASSA (Background) - UF: {uf_selecionada} | Modalidades: {modalidades}")

        for cod_modalidade in modalidades:
            if self.cancelar_carga: break
            pag = 1
            while True: 
                if self.cancelar_carga: break
                params = {"dataInicial": data_inicio, "dataFinal": data_fim, "codigoModalidadeContratacao": str(cod_modalidade), "pagina": str(pag), "tamanhoPagina": "50"}
                if categoria_id: params["codigoCategoriaProcesso"] = categoria_id
                if uf_selecionada != "Todas": params["uf"] = uf_selecionada

                try:
                    res = self._get_com_retentativa(url_base, params=params, timeout=30, tipo_operacao="carga")
                    if not res or res.status_code != 200: break 
                    lista_contratos = res.json().get("data", []) or []
                    if not lista_contratos: break
                    self.registrar_log(f"A descarregar Edital (Modalidade {cod_modalidade}) - Página {pag}...")
                    self.after(0, lambda p=pag: self.lbl_status.configure(text=f"A Atualizar Banco em Massa (Mod {cod_modalidade} | Pág {p}). Sistema Livre...", text_color="#8e44ad"))
                    novos_itens += self._obter_e_salvar_itens_paginados(lista_contratos, contratacoes_processadas, cod_modalidade, portais_selecionados=portais_selecionados, tipo_operacao="carga")
                    if res.json().get("paginasRestantes", 0) <= 0: break
                    pag += 1
                except Exception as e: 
                    self.registrar_log(f"⚠️ Erro no processamento em lote da página {pag}: {e}", apenas_terminal=True)
                    break

        if self.cancelar_carga: self.after(0, lambda: self.lbl_status.configure(text=f"Atualização interrompida. {novos_itens} guardados.", text_color="#f39c12"))
        else: self.after(0, lambda: self.lbl_status.configure(text=f"Atualização invisível concluída! {novos_itens} editais salvos.", text_color="#2ecc71"))
        self.after(0, lambda: self.set_estado_menu_carga(False))

    def iniciar_busca(self):
        termo = self.ent_termo.get().strip()
        edital_busca = self.ent_edital.get().strip()
        uasg_busca = self.ent_uasg.get().strip()
        
        if not termo and not edital_busca and not uasg_busca:
            return messagebox.showwarning("Aviso", "Informe o Produto/Serviço, o Nº do Edital ou a UASG/CNPJ.")
            
        self.cancelar_busca = False
        self.mostrar_carga_no_grid = False 
        self.db.limpar_cache()
        self.btn_buscar.configure(text="⏹ Parar Busca", fg_color="#e74c3c", hover_color="#c0392b", command=self.cancelar_busca_manual)
        
        self.btn_arquivos.configure(state="disabled")
        self.btn_analise.configure(state="disabled")

        if self.is_carga_running or self.chk_base_local.get() == 1:
            if self.is_carga_running:
                self.chk_base_local.select()
                self.chk_base_local.configure(state="disabled")
                self.lbl_status.configure(text="Busca Local forçada (Atualização em massa em andamento)...", text_color="#f39c12")
            else:
                self.lbl_status.configure(text="Consultando Base Local...", text_color="#f39c12")
            threading.Thread(target=self._buscar_local_db_thread, args=(termo, self.combo_uf.get(), self.modalidades_map.get(self.combo_modalidade.get()), self.combo_alvo.get(), self.obter_portais_selecionados(), edital_busca, uasg_busca), daemon=True).start()
        else:
            self.lbl_status.configure(text="Consultando API do PNCP...", text_color="#f39c12")
            threading.Thread(target=self._buscar_api_pncp_thread, args=(termo, Utils.formatar_data_api(self.ent_data_ini.get().strip()), Utils.formatar_data_api(self.ent_data_fim.get().strip()), self.combo_status.get(), self.modalidades_map.get(self.combo_modalidade.get()), self.combo_uf.get(), self.combo_alvo.get(), self.obter_portais_selecionados(), edital_busca, uasg_busca), daemon=True).start()

    def _buscar_local_db_thread(self, termo, uf_selecionada, modalidade_id, alvo_busca, portais_selecionados, edital_busca, uasg_busca):
        self.after(0, self._limpar_tabela)
        self.after(0, lambda: [self.txt_detalhes.configure(state="normal"), self.txt_detalhes.delete("1.0", "end"), self.txt_detalhes.configure(state="disabled")])
        
        grupos_busca = Utils.extrair_grupos_radicais(termo)
        count = 0
        self.registrar_log("🔎 Buscando na Base Local...")

        edital_limpo = edital_busca.strip()
        busca_num = ""
        busca_ano = ""
        if edital_limpo:
            partes = edital_limpo.split('/')
            busca_num = "".join(filter(str.isdigit, partes[0])).lstrip('0')
            if len(partes) > 1: busca_ano = "".join(filter(str.isdigit, partes[1]))
                
        uasg_limpa = "".join(filter(str.isalnum, uasg_busca)).lower()

        try:
            sql, params = "SELECT orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, data_abertura, data_encerramento, cnpj, ano, sequencial, numero_compra, uasg, modalidade_nome, portal_nome FROM editais_itens WHERE 1=1", []
            if uf_selecionada != "Todas": sql += " AND uf = ?"; params.append(uf_selecionada)
            if modalidade_id: sql += " AND modalidade_id = ?"; params.append(modalidade_id)
            if portais_selecionados:
                sql += f" AND ({' OR '.join(['portal_nome LIKE ?' for _ in portais_selecionados])})"
                for p in portais_selecionados: params.append(f"%{p}%")
            
            linhas = self.db.executar_leitura(sql, params)
            
            for row in linhas:
                if self.cancelar_busca: break
                if busca_num:
                    num_c_bruto = str(row[15])
                    num_c = "".join(filter(str.isdigit, num_c_bruto.split('|')[0] if '|' in num_c_bruto else num_c_bruto)).lstrip('0')
                    proc_c = "".join(filter(str.isdigit, num_c_bruto.split('|')[1] if '|' in num_c_bruto else "")).lstrip('0')
                    seq_c = "".join(filter(str.isdigit, str(row[14]))).lstrip('0')
                    ano_c = str(row[13])
                    
                    if busca_ano and ano_c and busca_ano != ano_c: continue
                    if busca_num != num_c and busca_num != seq_c and busca_num != proc_c:
                        if not (num_c == busca_num + ano_c) and not (seq_c == busca_num + ano_c) and not (proc_c == busca_num + ano_c):
                            continue
                        
                if uasg_limpa:
                    texto_orgao = "".join([c for c in f"{row[0]}{row[12]}{row[16]}" if c.isalnum()]).lower()
                    if uasg_limpa not in texto_orgao: continue
                
                texto_alvo = row[3] if alvo_busca == "Apenas no Item" else (row[2] if alvo_busca == "Apenas no Objeto do Edital" else f"{row[3]} {row[2]}")
                if not Utils.texto_atende_busca(texto_alvo, grupos_busca): continue
                
                edital_exibicao = str(row[15]).split('|')[0] if '|' in str(row[15]) else str(row[15])
                if not edital_exibicao: edital_exibicao = str(row[14])
                
                media_org, media_ger, ult_org, ult_reg = self.db.obter_historico_precos(row[3], row[0], row[1])
                
                self.after(0, lambda r=row, ed_ex=edital_exibicao, mo=media_org, mg=media_ger, uo=ult_org, ur=ult_reg: self._adicionar_item_tabela(r[0], r[1], r[18], f"{ed_ex}/{r[13]}", r[3], r[4], r[5], r[6], r[7], r[8], mo, mg, uo, ur, r[9], r[10], r[11], r[12], r[13], r[14], r[17], r[2]))
                count += 1
                
            if not self.cancelar_busca: self.after(0, lambda: self._finalizar_busca_ui(count, f"{count} itens encontrados na Base Local."))
        except Exception as e: self.after(0, lambda erro=str(e): self._finalizar_busca_com_erro(erro))

    def _buscar_api_pncp_thread(self, termo, data_inicio, data_fim, status_busca, modalidade_id, uf_selecionada, alvo_busca, portais_selecionados, edital_busca, uasg_busca):
        self.after(0, self._limpar_tabela)
        self.after(0, lambda: [self.txt_detalhes.configure(state="normal"), self.txt_detalhes.delete("1.0", "end"), self.txt_detalhes.configure(state="disabled")])
        self.resultados_pncp = []
        try:
            grupos_busca = Utils.extrair_grupos_radicais(termo)
            self.registrar_log("🔎 Iniciando busca no PNCP Web...")
            url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta" if status_busca == "A Receber/Recebendo Proposta" else "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
            params_base = {"dataFinal": data_fim} if status_busca == "A Receber/Recebendo Proposta" else {"dataInicial": data_inicio, "dataFinal": data_fim}
            if uf_selecionada != "Todas": params_base["uf"] = uf_selecionada
            
            modalidades_buscar = [int(modalidade_id)] if modalidade_id else ([8, 6, 4] if not edital_busca and not uasg_busca else list(range(1, 15)))
            self.registrar_log(f"[API ROUTINE] Modalidades em fila de busca: {modalidades_buscar}", apenas_terminal=True)
            
            for cod_modalidade in modalidades_buscar:
                if self.cancelar_busca: break
                pag = 1
                while True: 
                    if self.cancelar_busca: break
                    params = params_base.copy()
                    params.update({"codigoModalidadeContratacao": str(cod_modalidade), "pagina": str(pag), "tamanhoPagina": "50"})
                    res = self._get_com_retentativa(url_base, params=params, timeout=15, tipo_operacao="busca")
                    if not res or res.status_code != 200 or not res.json().get("data"): break
                    self._obter_e_salvar_itens_paginados(res.json().get("data"), set(), cod_modalidade, alvo_busca=alvo_busca, grupos_busca=grupos_busca, portais_selecionados=portais_selecionados, edital_busca=edital_busca, uasg_busca=uasg_busca, chaves_cadastradas=set(), tipo_operacao="busca")
                    if res.json().get("paginasRestantes", 0) <= 0: break
                    pag += 1
            
            if not self.cancelar_busca:
                msg = f"{len(self.resultados_pncp)} itens online listados."
                if len(self.resultados_pncp) == 0 and (edital_busca or uasg_busca):
                    msg += " (Dica: Aumente o período da 'Data de Publicação' caso o edital seja antigo)"
                self.after(0, lambda: self._finalizar_busca_ui(len(self.resultados_pncp), msg))
        except Exception as e: 
            self.after(0, lambda erro=str(e): self._finalizar_busca_com_erro(erro))

    def _obter_e_salvar_itens_paginados(self, lista_contratos, contratacoes_processadas, cod_modalidade, alvo_busca="Todos", grupos_busca=None, portais_selecionados=None, edital_busca="", uasg_busca="", chaves_cadastradas=None, tipo_operacao="busca"):
        if chaves_cadastradas is None: chaves_cadastradas = set()
        itens_salvos_count, mod_nome = 0, next((k for k, v in self.modalidades_map.items() if v == str(cod_modalidade)), "Não informada")

        edital_limpo = edital_busca.strip()
        busca_num = ""
        busca_ano = ""
        if edital_limpo:
            partes = edital_limpo.split('/')
            busca_num = "".join(filter(str.isdigit, partes[0])).lstrip('0')
            if len(partes) > 1: busca_ano = "".join(filter(str.isdigit, partes[1]))
                
        uasg_limpa = "".join(filter(str.isalnum, uasg_busca)).lower()

        for contrato in lista_contratos:
            if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
            portal_nome = contrato.get("usuarioNome", "Não informado")
            if portais_selecionados and not any(ps.lower() in portal_nome.lower() for ps in portais_selecionados): continue 
            
            cnpj = contrato.get("orgaoEntidade", {}).get("cnpj")
            ano = contrato.get("anoCompra")
            seq = contrato.get("sequencialCompra")
            chave_edital = f"{cnpj}_{ano}_{seq}"
            
            if chave_edital in contratacoes_processadas: continue
            
            orgao = contrato.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
            numero_compra = str(contrato.get("numeroCompra", ""))
            numero_processo = str(contrato.get("numeroProcesso", ""))
            codigo_unidade = str(contrato.get("unidadeOrgao", {}).get("codigoUnidade", ""))

            if busca_num:
                num_c = "".join(filter(str.isdigit, numero_compra)).lstrip('0')
                seq_c = "".join(filter(str.isdigit, str(seq))).lstrip('0')
                proc_c = "".join(filter(str.isdigit, numero_processo)).lstrip('0')
                ano_c = str(ano)
                
                if busca_ano and ano_c and busca_ano != ano_c: continue
                    
                if busca_num != num_c and busca_num != seq_c and busca_num != proc_c:
                    if not (num_c == busca_num + ano_c) and not (seq_c == busca_num + ano_c) and not (proc_c == busca_num + ano_c):
                        continue
                    
            if uasg_limpa:
                texto_orgao = "".join([c for c in f"{orgao}{cnpj}{codigo_unidade}" if c.isalnum()]).lower()
                if uasg_limpa not in texto_orgao: continue

            contratacoes_processadas.add(chave_edital)

            uf = contrato.get("unidadeOrgao", {}).get("ufSigla", "-")
            data_pub = str(contrato.get("dataPublicacaoPncp", ""))[:10]
            objeto_contrato = contrato.get("objeto", "")

            data_abertura = Utils.formatar_data_hora(contrato.get("dataAberturaProposta"))
            data_encerramento = Utils.formatar_data_hora(contrato.get("dataEncerramentoProposta"))

            if cnpj and ano and seq:
                pag_item = 1
                while True:
                    if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
                    try:
                        res_i = self._get_com_retentativa(f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens", {"pagina": pag_item, "tamanhoPagina": 500}, timeout=25, tipo_operacao=tipo_operacao)
                        if not res_i or res_i.status_code != 200: break
                        
                        itens_json = res_i.json()
                        for it in (itens_json.get("data", []) if isinstance(itens_json, dict) else itens_json):
                            if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
                            num_item = it.get("numeroItem", 0)
                            mat_nome = it.get("materialOuServicoNome", "") or (it.get("materialOuServico").get("nome", "") if isinstance(it.get("materialOuServico"), dict) else "")
                            desc_bruta = it.get("descricao", "")
                            desc_item = f"{mat_nome} - {desc_bruta}" if mat_nome and desc_bruta else (mat_nome or desc_bruta or objeto_contrato)
                            
                            texto_alvo = desc_item if alvo_busca == "Apenas no Item" else (objeto_contrato if alvo_busca == "Apenas no Objeto do Edital" else f"{desc_item} {objeto_contrato}")
                            
                            if grupos_busca and not Utils.texto_atende_busca(texto_alvo, grupos_busca): continue

                            chave_u = f"{cnpj}_{ano}_{seq}_{num_item}"
                            if chave_u not in chaves_cadastradas:
                                chaves_cadastradas.add(chave_u)
                                qtd, v_u_est, v_t_est, v_u_hom, v_t_hom = float(it.get("quantidade", 1)), it.get("valorUnitarioEstimado"), it.get("valorTotalEstimado"), it.get("valorUnitarioHomologado"), it.get("valorTotalHomologado") or it.get("valorTotal")
                                
                                reg = {"Orgao": orgao, "UF": uf, "ObjetoContrato": objeto_contrato, "DescItem": desc_item, "Qtd": qtd, "Vlr Unit Est": Utils.formatar_moeda(v_u_est), "Vlr Total Est": Utils.formatar_moeda(v_t_est), "Vlr Unit Hom": Utils.formatar_moeda(v_u_hom), "Vlr Total Hom": Utils.formatar_moeda(v_t_hom), "Data Pub": data_pub, "Data Abertura": data_abertura, "Data Encerramento": data_encerramento, "CNPJ": cnpj, "Ano": ano, "Sequencial": seq, "NumeroCompra": f"{numero_compra}|{numero_processo}", "UASG": codigo_unidade, "NumeroItem": num_item, "ModalidadeID": str(cod_modalidade), "ModalidadeNome": mod_nome, "PortalNome": portal_nome}
                                
                                media_org, media_ger, ult_org, ult_reg = self.db.obter_historico_precos(desc_item, orgao, uf)

                                if tipo_operacao == "busca" or (tipo_operacao == "carga" and self.mostrar_carga_no_grid):
                                    self.resultados_pncp.append(reg)
                                    edital_exibicao = numero_compra if numero_compra else str(seq)
                                    if numero_processo and numero_processo != numero_compra: edital_exibicao += f" (Proc: {numero_processo})"
                                    
                                    self.after(0, lambda r=reg, ed_ex=edital_exibicao, mo=media_org, mg=media_ger, uo=ult_org, ur=ult_reg: self._adicionar_item_tabela(r["Orgao"], r["UF"], r["PortalNome"], f"{ed_ex}/{r['Ano']}", r["DescItem"], r["Qtd"], r["Vlr Unit Est"], r["Vlr Total Est"], r["Vlr Unit Hom"], r["Vlr Total Hom"], mo, mg, uo, ur, r["Data Pub"], r["Data Abertura"], r["Data Encerramento"], r["CNPJ"], r["Ano"], r["Sequencial"], r["ModalidadeNome"], r["ObjetoContrato"]))
                                    self.after(0, lambda: self.tree.yview_moveto(1))
                                    
                                self.db.salvar_item_edital(reg)
                                itens_salvos_count += 1
                                
                                if tipo_operacao == "carga" and itens_salvos_count % 50 == 0:
                                    self.registrar_log(f"🔄 Carga Background: {itens_salvos_count} itens processados e guardados na Base Local...")
                        
                        if (itens_json.get("paginasRestantes", 0) if isinstance(itens_json, dict) else 0) <= 0: break
                        pag_item += 1
                    except Exception:
                        self.registrar_log(f"⚠️ Aviso: Falha ao baixar itens do edital {seq}/{ano}. Saltando...")
                        break
        if itens_salvos_count > 0:
            threading.Thread(target=self._enviar_telemetria_background, args=(itens_salvos_count,), daemon=True).start()
            
        return itens_salvos_count

    def _adicionar_item_tabela(self, orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, media_orgao, media_geral, ult_org, ult_reg, data_pub, data_abertura, data_encerramento, cnpj, ano, seq, mod_nome, obj_contrato):
        tags = ()
        texto_alvo = Utils.normalizar_texto(f"{desc} {obj_contrato}")
        
        if hasattr(self, 'palavras_chave_empresa') and self.palavras_chave_empresa:
            palavras_texto = set(re.findall(r'[a-z]+', texto_alvo))
            if any(p in palavras_texto for p in self.palavras_chave_empresa):
                tags = ('aderente',)
                desc = f"⭐ {desc}"

        self.tree.insert("", "end", values=(orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, media_orgao, media_geral, ult_org, ult_reg, data_pub, data_abertura, data_encerramento, cnpj, ano, seq, mod_nome, obj_contrato), tags=tags)

    def _limpar_tabela(self):
        for row in self.tree.get_children(): self.tree.delete(row)

    def _finalizar_busca_ui(self, qtd, msg_status):
        self.btn_buscar.configure(text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal")
        if not self.is_carga_running: self.lbl_status.configure(text=msg_status, text_color="#2ecc71" if qtd > 0 else "#e74c3c")
        self.btn_exportar.configure(state="normal" if qtd > 0 else "disabled")

    def _finalizar_busca_com_erro(self, msg_erro):
        if not self.is_carga_running: self.lbl_status.configure(text="Erro ao executar busca.", text_color="#e74c3c")
        self.btn_buscar.configure(text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal")
        messagebox.showerror("Erro na Busca", f"Falha na consulta: {msg_erro}")
        
    def iniciar_motor_radar_background(self):
        # Atualiza o sino logo que abre o app
        self.atualizar_sininho()
        # Inicia a thread infinita
        threading.Thread(target=self._loop_radar_automatico, daemon=True).start()

    def _loop_radar_automatico(self):
        time.sleep(30) # Espera 30 segundos após abrir o programa antes da primeira verificação
        while True:
            config = self.db.obter_config_alertas()
            palavras_raw = config.get("palavras", "").strip()
            
            if palavras_raw and config.get("remetente") and config.get("senha") and config.get("destino"):
                self.registrar_log("📡 [RADAR] Iniciando varredura automática silenciosa...", apenas_terminal=True)
                
                try:
                    # Configura a busca para HOJE
                    hoje_str = datetime.datetime.now().strftime("%Y%m%d")
                    mod_id = self.modalidades_map.get(config.get("modalidade", ""), "")
                    uf = config.get("uf", "Todas")
                    grupos_busca = Utils.extrair_grupos_radicais(palavras_raw)
                    
                    url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
                    params = {"dataInicial": hoje_str, "dataFinal": hoje_str, "pagina": "1", "tamanhoPagina": "200"}
                    if mod_id: params["codigoModalidadeContratacao"] = mod_id
                    if uf != "Todas": params["uf"] = uf

                    res = self._get_com_retentativa(url_base, params=params, timeout=15, tipo_operacao="busca")
                    novas_oportunidades = []
                    
                    if res and res.status_code == 200:
                        lista_contratos = res.json().get("data", [])
                        for contrato in lista_contratos:
                            orgao = contrato.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
                            objeto = contrato.get("objeto", "")
                            
                            if Utils.texto_atende_busca(objeto, grupos_busca):
                                cnpj = contrato.get("orgaoEntidade", {}).get("cnpj")
                                ano = contrato.get("anoCompra")
                                seq = contrato.get("sequencialCompra")
                                chave = f"{cnpj}_{ano}_{seq}"
                                link = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
                                
                                # Se inseriu no banco (não era repetida), guarda para enviar email
                                if self.db.registrar_notificacao_nova(chave, orgao, objeto, link):
                                    novas_oportunidades.append({"orgao": orgao, "objeto": objeto, "link": link})
                    
                    if novas_oportunidades:
                        self.registrar_log(f"🔔 [RADAR] Encontradas {len(novas_oportunidades)} novas oportunidades! Enviando e-mail...", apenas_terminal=False)
                        self.after(0, self.atualizar_sininho)
                        self._enviar_email_radar(config, novas_oportunidades)
                        threading.Thread(target=self._enviar_telemetria_background, args=(len(novas_oportunidades),), daemon=True).start()

                except Exception as e:
                    self.registrar_log(f"⚠️ [RADAR ERROR] Falha na varredura: {e}", apenas_terminal=True)
            
            # Dorme por 3 horas (10800 segundos) até à próxima verificação
            time.sleep(10800)

    def _enviar_email_radar(self, config, oportunidades):
        try:
            remetente = config["remetente"]
            senha = config["senha"]
            destino = config["destino"]
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🔔 Radar PNCP: {len(oportunidades)} Novas Oportunidades Encontradas!"
            msg["From"] = remetente
            msg["To"] = destino
            
            html = f"<h2>O Radar Automático encontrou novas licitações para as suas palavras-chave!</h2><hr>"
            for op in oportunidades:
                html += f"<p><b>🏢 Órgão:</b> {op['orgao']}<br>"
                html += f"<b>🎯 Objeto:</b> {op['objeto']}<br>"
                html += f"🔗 <a href='{op['link']}'>Clique aqui para aceder ao Edital no PNCP</a></p><br>"
            
            msg.attach(MIMEText(html, "html"))
            
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(remetente, senha)
                server.send_message(msg)
                
            self.registrar_log("✅ [RADAR] E-mail enviado com sucesso!", apenas_terminal=True)
        except Exception as e:
            self.registrar_log(f"⚠️ [RADAR EMAIL ERROR] Falha ao enviar e-mail: {e}", apenas_terminal=True)

if __name__ == "__main__":
    try:
        app = BuscadorPNCP()
        app.mainloop()
    except Exception:
        root_error = tk.Tk()
        root_error.withdraw()
        messagebox.showerror("Falha Crítica", f"O sistema não conseguiu iniciar:\n{traceback.format_exc()}")