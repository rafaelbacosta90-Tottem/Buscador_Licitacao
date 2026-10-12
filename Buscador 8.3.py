import csv
import datetime
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk, filedialog
import unicodedata
import urllib.parse
import webbrowser
import sys
import uuid
import traceback
import customtkinter as ctk
import requests

# Configuração visual do CustomTkinter
ctk.set_appearance_mode("Light")
ctk.set_default_color_theme("blue")


def normalizar_texto(texto: str) -> str:
    if not texto: return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    texto_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return texto_sem_acento.lower().strip()

def extrair_radicais(termo: str) -> list:
    palavras = [p for p in normalizar_texto(termo).split() if len(p) >= 2]
    radicais = []
    for p in palavras:
        rad = p
        if p.endswith("es") and len(p) > 3: rad = p[:-2]
        elif p.endswith("s") and len(p) > 3: rad = p[:-1]
        radicais.append(rad)
    return radicais

def contem_palavras_chave(texto: str, radicais: list) -> bool:
    if not radicais: return False
    return all(rad in normalizar_texto(texto) for rad in radicais)


class BuscadorPNCP(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Buscador Multi-Portal de Licitações & Preços - Compras Públicas")
        self.geometry("1180x920")

        # ------------------------------------------------------------------
        # COLOQUE AQUI A SUA URL DA VERCEL (com o /api/valida no final)
        # ------------------------------------------------------------------
        self.url_api_licenca = "https://meu-validador-licencas.vercel.app/api/valida"

        self.db_path = "licitacoes_pncp_v9.db"

        self.withdraw()

        # Flags de Multitarefa
        self.cancelar_busca = False
        self.cancelar_carga = False
        self.is_carga_running = False
        self.mostrar_carga_no_grid = False 
        
        self.item_selecionado_doc = None
        self.resultados_pncp = []

        self.after(200, self._rotina_de_arranque)

    def _rotina_de_arranque(self):
        self.setup_db_licenca()
        cnpj_salvo = self.get_cnpj_registrado()

        if not cnpj_salvo:
            self.solicitar_registro_cnpj()
        else:
            if self.validar_licenca_online(cnpj_salvo, silencioso=True):
                self.iniciar_sistema_principal()
            else:
                self.solicitar_registro_cnpj()

    def obter_hwid(self) -> str:
        return str(uuid.getnode())

    def validar_licenca_online(self, cnpj_licenca: str, silencioso=False) -> bool:
        if not self.url_api_licenca or "SUA-URL-AQUI" in self.url_api_licenca:
            if not silencioso: messagebox.showerror("Erro de Configuração", "A URL da API da Vercel não foi configurada.")
            return False

        payload = {"cnpj": cnpj_licenca, "hwid": self.obter_hwid()}
        try:
            response = requests.post(self.url_api_licenca, json=payload, timeout=10)
            try: dados = response.json()
            except:
                if not silencioso: messagebox.showerror("Erro de Servidor", "A API da Vercel falhou. Verifique a URL.")
                return False
                
            if response.status_code == 200 and dados.get("status") == "success": return True
            else:
                if not silencioso: messagebox.showerror("Licença Inválida", f"Falha na validação:\n{dados.get('message', 'Negado')}")
                return False
        except requests.exceptions.RequestException as e:
            if not silencioso: messagebox.showerror("Erro de Conexão", f"Falha de internet:\n{e}")
            return False

    def setup_db_licenca(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE TABLE IF NOT EXISTS usuario_licenca (id INTEGER PRIMARY KEY AUTOINCREMENT, cnpj TEXT NOT NULL, data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
                conn.commit()
        except Exception:
            sys.exit()

    def get_cnpj_registrado(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cnpj FROM usuario_licenca ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None

    def solicitar_registro_cnpj(self):
        self.janela_login = ctk.CTkToplevel(self)
        self.janela_login.title("Ativação de Licença")
        self.janela_login.geometry("500x250")
        self.janela_login.transient(self)
        self.janela_login.grab_set()
        self.janela_login.protocol("WM_DELETE_WINDOW", sys.exit)

        ctk.CTkLabel(self.janela_login, text="Sistema Protegido\n\nPor favor, informe o CNPJ da sua empresa:", font=("Arial", 14, "bold")).pack(pady=(20, 15))
        self.ent_cnpj_login = ctk.CTkEntry(self.janela_login, width=300, placeholder_text="Digite apenas números")
        self.ent_cnpj_login.pack(pady=10)
        self.ent_cnpj_login.bind("<Return>", lambda e: self.confirmar_registro_online())
        self.btn_ativar = ctk.CTkButton(self.janela_login, text="Validar Online", fg_color="#27ae60", hover_color="#2ecc71", font=("Arial", 12, "bold"), command=self.confirmar_registro_online)
        self.btn_ativar.pack(pady=20)

    def confirmar_registro_online(self):
        cnpj = self.ent_cnpj_login.get().strip()
        if len(cnpj) < 11:
            messagebox.showwarning("Aviso", "CNPJ ou CPF inválido.")
            return
            
        self.btn_ativar.configure(text="A validar...", state="disabled")
        self.janela_login.update()
        
        if self.validar_licenca_online(cnpj, silencioso=False):
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM usuario_licenca")
                cursor.execute("INSERT INTO usuario_licenca (cnpj) VALUES (?)", (cnpj,))
                conn.commit()
            messagebox.showinfo("Sucesso", "Licença ativada com sucesso!")
            self.janela_login.destroy()
            self.iniciar_sistema_principal()
        else:
            self.btn_ativar.configure(text="Validar Online", state="normal")

    def iniciar_sistema_principal(self):
        self.deiconify() 
        # Maximizar a janela no arranque
        try:
            self.state('zoomed')
        except:
            self.attributes('-zoomed', True)

        self.config_precos = {"vlr_unit_est": tk.BooleanVar(value=True), "vlr_total_est": tk.BooleanVar(value=True), "vlr_unit_hom": tk.BooleanVar(value=True), "vlr_total_hom": tk.BooleanVar(value=True)}
        self.lista_portais_comuns = ["Compras.gov.br", "Portal de Compras Públicas", "BLL", "Licitações-e", "BEC", "Licitar Digital", "AZ Informática", "BBMNET", "BNC", "Portal de Compras da Caixa", "Licitanet", "Abase Sistemas", "Compras RS", "Compras SC", "Compras GO", "Ammfoco", "TCE", "Prefeitura"]
        self.vars_portais = {portal: tk.BooleanVar(value=False) for portal in self.lista_portais_comuns}
        self.vars_portais["Todos"] = tk.BooleanVar(value=True) 
        self.categorias_map = {"Todas": "", "Cessão": "1", "Compras": "2", "Informática (TIC)": "3", "Internacional": "4", "Locação Imóveis": "5", "Mão de Obra": "6", "Obras": "7", "Serviços": "8", "Serviços de Engenharia": "9", "Serviços de Saúde": "10", "Alienação de bens móveis/imóveis": "11"}
        self.modalidades_map = {"Principais (Pregão, Dispensa, Conc.)": "", "1 - Leilão Eletrônico": "1", "2 - Diálogo Competitivo": "2", "3 - Concurso": "3", "4 - Concorrência Eletrônica": "4", "5 - Concorrência Presencial": "5", "6 - Pregão Eletrônico": "6", "7 - Pregão Presencial": "7", "8 - Dispensa de Licitação": "8", "9 - Inexigibilidade": "9", "10 - Manifestação de Interesse": "10", "11 - Pré-qualificação": "11", "12 - Credenciamento": "12", "13 - Leilão Presencial": "13"}
        self.lista_ufs = ["Todas", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
        self.http_session = requests.Session()
        self.http_session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)", "Accept": "application/json, text/plain, */*", "Referer": "https://pncp.gov.br/"})
        
        self.init_db()
        self.criar_menu_superior()
        self.criar_interface()

    # -------------------------------------------------------------
    # BARRA DE MENUS SUPERIOR
    # -------------------------------------------------------------
    def criar_menu_superior(self):
        self.menubar = tk.Menu(self)

        self.menu_opcoes = tk.Menu(self.menubar, tearoff=0)
        self.menu_opcoes.add_command(label="Configurar Colunas da Tabela", command=self.abrir_menu_configuracao)
        self.menubar.add_cascade(label="Opções", menu=self.menu_opcoes)

        self.menu_sync = tk.Menu(self.menubar, tearoff=0)
        self.menu_sync.add_command(label="Sincronizar Banco de Dados (API)", command=self.abrir_janela_carga)
        self.menu_sync.add_separator()
        self.menu_sync.add_command(label="Parar Atualização", command=self.parar_carga_background, state="disabled")
        self.menubar.add_cascade(label="Atualização", menu=self.menu_sync)

        self.config(menu=self.menubar)

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

    # -------------------------------------------------------------
    # JANELA DE ATUALIZAÇÃO (CARGA)
    # -------------------------------------------------------------
    def abrir_janela_carga(self):
        janela = ctk.CTkToplevel(self)
        janela.title("Atualização - Sincronizar Base Local")
        janela.geometry("600x650")
        janela.transient(self) 
        janela.grab_set() 

        lbl_titulo = ctk.CTkLabel(janela, text="Defina os Filtros para Descarregar os Dados:", font=("Arial", 14, "bold"))
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

        ctk.CTkCheckBox(frame_scroll_portais, text="Todos os Portais", variable=vars_portais_carga["Todos"], command=_chk_todos_click, font=("Arial", 12, "bold")).pack(anchor="w", pady=5)
        ctk.CTkFrame(frame_scroll_portais, height=2, fg_color="gray").pack(fill="x", pady=2)
        for portal in self.lista_portais_comuns: ctk.CTkCheckBox(frame_scroll_portais, text=portal, variable=vars_portais_carga[portal], command=_chk_ind_click).pack(anchor="w", padx=15, pady=2)

        def processar_inicio():
            d_ini = self.formatar_data_api(ent_dt_ini.get().strip())
            d_fim = self.formatar_data_api(ent_dt_fim.get().strip())
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

        btn_iniciar = ctk.CTkButton(janela, text="🚀 Iniciar Sincronização em Segundo Plano", fg_color="#8e44ad", hover_color="#732d91", font=("Arial", 12, "bold"), command=processar_inicio)
        btn_iniciar.pack(pady=20)

    def parar_carga_background(self):
        if not messagebox.askyesno("Parar", "Deseja parar a Atualização?\nOs dados já salvos no banco não serão perdidos."): return
        self.cancelar_carga = True
        self.registrar_log("⚠️ Atualização cancelada pelo usuário.")
        self.lbl_status.configure(text="A interromper processo...", text_color="#e74c3c")

    # -------------------------------------------------------------
    # MÉTODOS DE BANCO DE DADOS
    # -------------------------------------------------------------
    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS editais_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, orgao TEXT, uf TEXT, objeto_contrato TEXT, desc_item TEXT, quantidade REAL, vlr_unit_est TEXT, vlr_total_est TEXT, vlr_unit_hom TEXT, vlr_total_hom TEXT, data_publicacao TEXT, cnpj TEXT, ano INTEGER, sequencial INTEGER, numero_item INTEGER, modalidade_id TEXT, modalidade_nome TEXT, portal_nome TEXT, data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(cnpj, ano, sequencial, numero_item, desc_item) ON CONFLICT REPLACE)")
            conn.commit()

    def salvar_item_db(self, item_dict):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT OR REPLACE INTO editais_itens (orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, cnpj, ano, sequencial, numero_item, modalidade_id, modalidade_nome, portal_nome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    item_dict.get("Orgao"), item_dict.get("UF"), item_dict.get("ObjetoContrato"), item_dict.get("DescItem"), item_dict.get("Qtd"), item_dict.get("Vlr Unit Est"), item_dict.get("Vlr Total Est"), item_dict.get("Vlr Unit Hom"), item_dict.get("Vlr Total Hom"), item_dict.get("Data Pub"), item_dict.get("CNPJ", ""), item_dict.get("Ano", 0), item_dict.get("Sequencial", 0), item_dict.get("NumeroItem", 0), item_dict.get("ModalidadeID", ""), item_dict.get("ModalidadeNome", ""), item_dict.get("PortalNome", "")
                ))
                conn.commit()
        except: pass

    def contar_itens_db(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                return conn.cursor().execute("SELECT COUNT(*) FROM editais_itens").fetchone()[0]
        except: return 0

    # -------------------------------------------------------------
    # CONSTRUÇÃO DA INTERFACE PRINCIPAL
    # -------------------------------------------------------------
    def criar_interface(self):
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", rowheight=30, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"), background="#dcdde1", foreground="#2f3640")

        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_pesquisa = self.tabview.add("🔍 Pesquisa e Portais")
        self.tab_logs = self.tabview.add("📜 Logs do Sistema")

        self.frame_busca = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_busca.pack(fill="x", padx=10, pady=5)

        # --- LINHA 0 ---
        self.lbl_termo = ctk.CTkLabel(self.frame_busca, text="Produto/Serviço (Termo de busca):", font=("Arial", 12, "bold"))
        self.lbl_termo.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.ent_termo = ctk.CTkEntry(self.frame_busca, width=300, placeholder_text="Ex: ALFAJOR, ARROZ, NOTEBOOK")
        self.ent_termo.grid(row=0, column=1, columnspan=2, sticky="we", padx=5, pady=5)
        self.ent_termo.bind("<Return>", lambda e: self.iniciar_busca())

        self.lbl_alvo = ctk.CTkLabel(self.frame_busca, text="Onde buscar o termo:")
        self.lbl_alvo.grid(row=0, column=3, sticky="e", padx=5, pady=5)

        self.combo_alvo = ctk.CTkOptionMenu(self.frame_busca, values=["Todos", "Apenas no Item", "Apenas no Objeto do Edital"], width=180)
        self.combo_alvo.set("Todos")
        self.combo_alvo.grid(row=0, column=4, sticky="w", padx=5, pady=5)

        self.btn_buscar = ctk.CTkButton(self.frame_busca, text="🔍 Pesquisar", command=self.iniciar_busca, font=("Arial", 12, "bold"))
        self.btn_buscar.grid(row=0, column=5, padx=10, pady=5)
        self.default_btn_buscar_fg = self.btn_buscar.cget("fg_color")
        self.default_btn_buscar_hover = self.btn_buscar.cget("hover_color")

        # --- LINHA 1 ---
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

        # --- LINHA 2 ---
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

        # --- LINHA 3 ---
        self.lbl_uf = ctk.CTkLabel(self.frame_busca, text="Estado (UF) do Órgão:")
        self.lbl_uf.grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.combo_uf = ctk.CTkOptionMenu(self.frame_busca, values=self.lista_ufs, width=80)
        self.combo_uf.set("Todas")
        self.combo_uf.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        self.chk_base_local = ctk.CTkCheckBox(self.frame_busca, text="💾 Buscar apenas na Base Local (Obrigatório durante a Sincronização)", font=("Arial", 11, "bold"))
        self.chk_base_local.grid(row=3, column=2, columnspan=3, sticky="w", padx=5, pady=5)

        # --- CABEÇALHO TABELA ---
        self.frame_head_tabela = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_head_tabela.pack(fill="x", padx=10, pady=(15, 2))
        self.lbl_titulo_tabela = ctk.CTkLabel(self.frame_head_tabela, text="Resultados da Pesquisa / Sincronização (Duplo clique para abrir edital):", font=("Arial", 12, "bold"))
        self.lbl_titulo_tabela.pack(side="left", padx=5)
        self.lbl_status = ctk.CTkLabel(self.frame_head_tabela, text="Pronto para buscar.", text_color="#2ecc71", font=("Arial", 11, "italic"))
        self.lbl_status.pack(side="left", padx=25)
        self.btn_exportar = ctk.CTkButton(self.frame_head_tabela, text="📊 Exportar Excel", state="disabled", fg_color="#27ae60", width=130, command=self.exportar_excel)
        self.btn_exportar.pack(side="right", padx=5)

        self.frame_tabela = ctk.CTkFrame(self.tab_pesquisa)
        self.frame_tabela.pack(fill="both", expand=True, padx=10, pady=2)

        colunas = ("orgao", "uf", "portal", "edital", "objeto", "qtd", "vlr_unit_est", "vlr_total_est", "vlr_unit_hom", "vlr_total_hom", "data", "cnpj", "ano", "seq", "modalidade_nome", "objeto_contrato")
        self.tree = ttk.Treeview(self.frame_tabela, columns=colunas, show="headings")
        self.tree.heading("orgao", text="Órgão / Unidade")
        self.tree.heading("uf", text="UF")
        self.tree.heading("portal", text="Portal")
        self.tree.heading("edital", text="Edital (Seq/Ano)")
        self.tree.heading("objeto", text="Descrição do Item / Objeto")
        self.tree.heading("qtd", text="Qtd")
        self.tree.heading("vlr_unit_est", text="Unit. Estimado")
        self.tree.heading("vlr_total_est", text="Total Estimado")
        self.tree.heading("vlr_unit_hom", text="Unit. Homologado")
        self.tree.heading("vlr_total_hom", text="Total Homologado")
        self.tree.heading("data", text="Data Pub.")

        self.tree.column("orgao", width=180, minwidth=120, stretch=tk.YES)
        self.tree.column("uf", width=40, anchor="center", minwidth=40, stretch=tk.YES)
        self.tree.column("portal", width=120, anchor="w", minwidth=80, stretch=tk.YES)
        self.tree.column("edital", width=100, anchor="center", minwidth=80, stretch=tk.YES)
        self.tree.column("objeto", width=250, minwidth=150, stretch=tk.YES)
        self.tree.column("qtd", width=50, anchor="center", minwidth=50, stretch=tk.YES)
        self.tree.column("vlr_unit_est", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_total_est", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_unit_hom", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("vlr_total_hom", width=100, anchor="e", minwidth=80, stretch=tk.YES)
        self.tree.column("data", width=90, anchor="center", minwidth=80, stretch=tk.YES)

        self.aplicar_colunas_grid()

        scrollbar_y = ttk.Scrollbar(self.frame_tabela, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(self.frame_tabela, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=scrollbar_y.set, xscroll=scrollbar_x.set)
        scrollbar_x.pack(side="bottom", fill="x")
        scrollbar_y.pack(side="right", fill="y")
        self.tree.pack(side="top", fill="both", expand=True)

        self.frame_detalhes = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_detalhes.pack(fill="x", padx=10, pady=(2, 10))

        self.txt_detalhes = ctk.CTkTextbox(self.frame_detalhes, height=80, font=("Arial", 12), text_color="#2c3e50")
        self.txt_detalhes.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.txt_detalhes.insert("end", "Selecione um item na tabela acima para visualizar a descrição multilinha aqui.")
        self.txt_detalhes.configure(state="disabled")

        self.btn_arquivos = ctk.CTkButton(
            self.frame_detalhes, text="📂 Ver Arquivos\n(Editais/Anexos)", width=140, height=80,
            fg_color="#d35400", hover_color="#e67e22", state="disabled", font=("Arial", 12, "bold"), command=self.abrir_janela_arquivos
        )
        self.btn_arquivos.pack(side="right")

        self.tree.bind("<<TreeviewSelect>>", self._ao_selecionar_tabela)
        self.tree.bind("<Double-1>", self._ao_duplo_clique_tabela)
        
        self.txt_logs = ctk.CTkTextbox(self.tab_logs, font=("Consolas", 11))
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=10)

    # -------------------------------------------------------------
    # EVENTOS DA INTERFACE
    # -------------------------------------------------------------
    def aplicar_colunas_grid(self):
        colunas_visiveis = ["orgao", "uf", "portal", "edital", "objeto", "qtd"]
        if self.config_precos["vlr_unit_est"].get(): colunas_visiveis.append("vlr_unit_est")
        if self.config_precos["vlr_total_est"].get(): colunas_visiveis.append("vlr_total_est")
        if self.config_precos["vlr_unit_hom"].get(): colunas_visiveis.append("vlr_unit_hom")
        if self.config_precos["vlr_total_hom"].get(): colunas_visiveis.append("vlr_total_hom")
        colunas_visiveis.append("data")
        self.tree.configure(displaycolumns=colunas_visiveis)

    def abrir_menu_configuracao(self):
        janela_config = ctk.CTkToplevel(self)
        janela_config.title("Configurar Colunas de Preço")
        janela_config.geometry("350x250")
        janela_config.transient(self) 
        janela_config.grab_set() 
        lbl_titulo = ctk.CTkLabel(janela_config, text="Selecione as colunas a apresentar:", font=("Arial", 12, "bold"))
        lbl_titulo.pack(pady=(15, 10))
        ctk.CTkCheckBox(janela_config, text="Valor Unitário Estimado", variable=self.config_precos["vlr_unit_est"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Total Estimado", variable=self.config_precos["vlr_total_est"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Unitário Homologado", variable=self.config_precos["vlr_unit_hom"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkCheckBox(janela_config, text="Valor Total Homologado", variable=self.config_precos["vlr_total_hom"]).pack(anchor="w", padx=40, pady=5)
        ctk.CTkButton(janela_config, text="Aplicar e Fechar", command=lambda: [self.aplicar_colunas_grid(), janela_config.destroy()]).pack(pady=20)

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
        lbl_titulo = ctk.CTkLabel(janela_portais, text="Selecione os portais para a busca:", font=("Arial", 12, "bold"))
        lbl_titulo.pack(pady=(15, 5))
        frame_scroll = ctk.CTkScrollableFrame(janela_portais)
        frame_scroll.pack(fill="both", expand=True, padx=15, pady=5)
        ctk.CTkCheckBox(frame_scroll, text="Qualquer Portal (Todos)", font=("Arial", 12, "bold"), variable=self.vars_portais["Todos"], command=self._on_chk_todos_portais_click).pack(anchor="w", padx=5, pady=10)
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
        self.lbl_status.configure(text="A cancelar pesquisa...", text_color="#e74c3c")
        self.btn_buscar.configure(state="disabled")

    def _ao_selecionar_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 16:
            orgao, uf, portal, edital_resumo, desc_item_completo = valores[0], valores[1], valores[2], valores[3], valores[4]
            cnpj, ano, seq, mod_nome, objeto_geral = valores[11], valores[12], valores[13], valores[14], valores[15]
            self.item_selecionado_doc = (cnpj, ano, seq)
            self.btn_arquivos.configure(state="normal")
            texto_exibicao = f"🏢 ÓRGÃO: {orgao} ({uf})   |   🌐 PORTAL: {portal}\n📄 EDITAL: {edital_resumo}  |  ⚖️ MODALIDADE: {mod_nome}  |  🔗 Link: https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}\n🎯 OBJETO GERAL DO EDITAL: {objeto_geral}\n📦 DESCRIÇÃO DO ITEM: {desc_item_completo}"
            self.txt_detalhes.configure(state="normal")
            self.txt_detalhes.delete("1.0", "end")
            self.txt_detalhes.insert("end", texto_exibicao)
            self.txt_detalhes.configure(state="disabled")

    def _ao_duplo_clique_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 14: webbrowser.open(f"https://pncp.gov.br/app/editais/{valores[11]}/{valores[12]}/{valores[13]}")

    def abrir_janela_arquivos(self):
        if not self.item_selecionado_doc: return
        cnpj, ano, seq = self.item_selecionado_doc
        self.btn_arquivos.configure(text="Aguarde...", state="disabled")
        threading.Thread(target=self._buscar_arquivos_thread, args=(f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos",), daemon=True).start()

    def _buscar_arquivos_thread(self, url):
        try:
            res = self._get_com_retentativa(url, params={"pagina": 1, "tamanhoPagina": 100}, timeout=10, tipo_operacao="busca")
            if res and res.status_code == 200:
                dados = res.json()
                self.after(0, lambda: self.mostrar_janela_arquivos(dados.get("data", []) if isinstance(dados, dict) else (dados if isinstance(dados, list) else [])))
            else: self.after(0, lambda: messagebox.showinfo("Ficheiros", "Nenhum documento anexado foi encontrado."))
        except Exception as e: self.after(0, lambda: messagebox.showerror("Erro", f"Erro de conexão: {e}"))
        finally: self.after(0, lambda: self.btn_arquivos.configure(text="📂 Ver Arquivos\n(Editais/Anexos)", state="normal"))

    def mostrar_janela_arquivos(self, arquivos):
        janela_arq = ctk.CTkToplevel(self)
        janela_arq.title("Documentos Oficiais")
        janela_arq.geometry("750x450")
        janela_arq.transient(self)
        if not arquivos:
            ctk.CTkLabel(janela_arq, text="⚠️ Sem anexos para download.", font=("Arial", 14)).pack(pady=30)
            return
        lbl_info = ctk.CTkLabel(janela_arq, text="Lista de Documentos:", font=("Arial", 12, "bold"))
        lbl_info.pack(pady=10, padx=10, anchor="w")
        frame_lista = ctk.CTkScrollableFrame(janela_arq)
        frame_lista.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        for arq in arquivos:
            frame_item = ctk.CTkFrame(frame_lista, fg_color="#ecf0f1", corner_radius=5)
            frame_item.pack(fill="x", pady=5, padx=2)
            titulo, tipo, url_doc = arq.get("titulo", "S/ Título"), arq.get("tipoDocumentoNome", "Anexo"), arq.get("url", "")
            ctk.CTkLabel(frame_item, text=f"[{tipo}] {titulo}", font=("Arial", 11, "bold"), text_color="#2c3e50", anchor="w", justify="left", wraplength=550).pack(side="left", padx=10, pady=10, fill="x", expand=True)
            if url_doc: ctk.CTkButton(frame_item, text="Baixar", width=100, fg_color="#2980b9", command=lambda u=url_doc: webbrowser.open(u)).pack(side="right", padx=10, pady=10)

    def registrar_log(self, mensagem):
        hora_atual = datetime.datetime.now().strftime('%H:%M:%S')
        print(f"[{hora_atual}] {mensagem}".strip())
        if hasattr(self, "txt_logs"): 
            self.after(0, lambda m=mensagem, h=hora_atual: [self.txt_logs.insert("end", f"[{h}] {m}\n"), self.txt_logs.see("end")])

    def formatar_moeda(self, valor):
        if not valor: return "Não informado"
        try:
            val = float(valor)
            return "Não informado" if val == 0.0 else f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except: return "Não informado"

    def formatar_data_api(self, data_str):
        try:
            p = data_str.strip().split("/")
            if len(p) == 3: return f"{p[2]}{p[1].zfill(2)}{p[0].zfill(2)}"
        except: pass
        return data_str
        
    def _get_com_retentativa(self, url, params, max_tentativas=3, timeout=15, tipo_operacao="busca"):
        for tentativa in range(1, max_tentativas + 1):
            if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
            try: return self.http_session.get(url, params=params, timeout=timeout)
            except Exception as e:
                if tentativa == max_tentativas or (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): raise e
                for _ in range(30):
                    if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): return None
                    time.sleep(0.1)

    # -------------------------------------------------------------
    # MOTORES CENTRAIS (BACKGROUND UPDATE E BUSCA MANUAL)
    # -------------------------------------------------------------
    def _executar_carga_base_thread(self, data_inicio, data_fim, categoria_id, modalidade_id, uf_selecionada, portais_selecionados):
        if self.mostrar_carga_no_grid:
            self.after(0, self._limpar_tabela)
            
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
                    res = self._get_com_retentativa(url_base, params=params, timeout=15, tipo_operacao="carga")
                    if not res or res.status_code != 200: break 
                    
                    lista_contratos = res.json().get("data", []) or []
                    if not lista_contratos: break
                    
                    self.registrar_log(f"A descarregar Edital (Modalidade {cod_modalidade}) - Página {pag}...")
                    self.after(0, lambda p=pag: self.lbl_status.configure(text=f"A Atualizar Banco em Massa (Mod {cod_modalidade} | Pág {p}). Sistema Livre...", text_color="#8e44ad"))
                    
                    novos_itens += self._obter_e_salvar_itens_paginados(
                        lista_contratos, contratacoes_processadas, cod_modalidade, 
                        portais_selecionados=portais_selecionados, tipo_operacao="carga"
                    )
                    
                    if res.json().get("paginasRestantes", 0) <= 0: break
                    pag += 1
                except Exception as e: 
                    self.registrar_log(f"⚠️ Erro no processamento em lote da página {pag}: {e}")
                    break

        if self.cancelar_carga: self.after(0, lambda: self.lbl_status.configure(text=f"Atualização interrompida. {novos_itens} guardados.", text_color="#f39c12"))
        else: self.after(0, lambda: self.lbl_status.configure(text=f"Atualização invisível concluída! {novos_itens} editais salvos.", text_color="#2ecc71"))
        self.after(0, lambda: self.set_estado_menu_carga(False))

    def iniciar_busca(self):
        termo = self.ent_termo.get().strip()
        if not termo: return messagebox.showwarning("Aviso", "Informe o produto ou serviço.")
        
        self.cancelar_busca = False
        self.mostrar_carga_no_grid = False 
        
        self.btn_buscar.configure(text="⏹ Parar Busca", fg_color="#e74c3c", hover_color="#c0392b", command=self.cancelar_busca_manual)

        if self.is_carga_running:
            self.chk_base_local.select()
            self.chk_base_local.configure(state="disabled")
            self.lbl_status.configure(text="Busca Local forçada (Atualização em massa em andamento)...", text_color="#f39c12")
            threading.Thread(target=self._buscar_local_db_thread, args=(termo, self.combo_uf.get(), self.modalidades_map.get(self.combo_modalidade.get()), self.combo_alvo.get(), self.obter_portais_selecionados()), daemon=True).start()
        elif self.chk_base_local.get() == 1:
            self.lbl_status.configure(text="Consultando Base Local...", text_color="#f39c12")
            threading.Thread(target=self._buscar_local_db_thread, args=(termo, self.combo_uf.get(), self.modalidades_map.get(self.combo_modalidade.get()), self.combo_alvo.get(), self.obter_portais_selecionados()), daemon=True).start()
        else:
            self.lbl_status.configure(text="Consultando API do PNCP...", text_color="#f39c12")
            threading.Thread(target=self._buscar_api_pncp_thread, args=(termo, self.formatar_data_api(self.ent_data_ini.get().strip()), self.formatar_data_api(self.ent_data_fim.get().strip()), self.combo_status.get(), self.modalidades_map.get(self.combo_modalidade.get()), self.combo_uf.get(), self.combo_alvo.get(), self.obter_portais_selecionados()), daemon=True).start()

    def _buscar_local_db_thread(self, termo, uf_selecionada, modalidade_id, alvo_busca, portais_selecionados):
        self.after(0, self._limpar_tabela)
        self.after(0, lambda: [self.txt_detalhes.configure(state="normal"), self.txt_detalhes.delete("1.0", "end"), self.txt_detalhes.configure(state="disabled"), self.btn_arquivos.configure(state="disabled")])
        radicais_busca, termo_norm, count = extrair_radicais(termo), normalizar_texto(termo), 0
        self.registrar_log(f"🔎 Buscando termo na Base Local: '{termo}'")

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                sql, params = "SELECT orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, cnpj, ano, sequencial, modalidade_nome, portal_nome FROM editais_itens WHERE 1=1", []
                if uf_selecionada != "Todas": sql += " AND uf = ?"; params.append(uf_selecionada)
                if modalidade_id: sql += " AND modalidade_id = ?"; params.append(modalidade_id)
                if portais_selecionados:
                    sql += f" AND ({' OR '.join(['portal_nome LIKE ?' for _ in portais_selecionados])})"
                    for p in portais_selecionados: params.append(f"%{p}%")
                cursor.execute(sql, params)
                linhas = cursor.fetchall()
            for row in linhas:
                if self.cancelar_busca: break
                texto_alvo = row[3] if alvo_busca == "Apenas no Item" else (row[2] if alvo_busca == "Apenas no Objeto do Edital" else f"{row[3]} {row[2]}")
                if (radicais_busca and contem_palavras_chave(texto_alvo, radicais_busca)) or (termo_norm and termo_norm in normalizar_texto(texto_alvo)):
                    self.after(0, lambda r=row: self._adicionar_item_tabela(r[0], r[1], r[14], f"{r[12]}/{r[11]}" if r[12] and r[11] else "N/I", r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[2]))
                    count += 1
            if not self.cancelar_busca: self.after(0, lambda: self._finalizar_busca_ui(count, f"{count} itens encontrados na Base Local."))
        except Exception as e: self.after(0, lambda: self._finalizar_busca_com_erro(str(e)))

    def _buscar_api_pncp_thread(self, termo, data_inicio, data_fim, status_busca, modalidade_id, uf_selecionada, alvo_busca, portais_selecionados):
        self.after(0, self._limpar_tabela)
        self.after(0, lambda: [self.txt_detalhes.configure(state="normal"), self.txt_detalhes.delete("1.0", "end"), self.txt_detalhes.configure(state="disabled"), self.btn_arquivos.configure(state="disabled")])
        self.resultados_pncp = []
        try:
            radicais_busca = extrair_radicais(termo)
            self.registrar_log(f"🔎 Iniciando busca no PNCP Web para o termo: '{termo}'")
            url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta" if status_busca == "A Receber/Recebendo Proposta" else "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
            params_base = {"dataFinal": data_fim} if status_busca == "A Receber/Recebendo Proposta" else {"dataInicial": data_inicio, "dataFinal": data_fim}
            if uf_selecionada != "Todas": params_base["uf"] = uf_selecionada
            for cod_modalidade in ([int(modalidade_id)] if modalidade_id else [8, 6, 4]):
                if self.cancelar_busca: break
                pag = 1
                while True: 
                    if self.cancelar_busca: break
                    params = params_base.copy()
                    params.update({"codigoModalidadeContratacao": str(cod_modalidade), "pagina": str(pag), "tamanhoPagina": "50"})
                    res = self._get_com_retentativa(url_base, params=params, timeout=15, tipo_operacao="busca")
                    if not res or res.status_code != 200 or not res.json().get("data"): break
                    self._obter_e_salvar_itens_paginados(res.json().get("data"), set(), cod_modalidade, alvo_busca=alvo_busca, radicais_busca=radicais_busca, portais_selecionados=portais_selecionados, chaves_cadastradas=set(), tipo_operacao="busca")
                    if res.json().get("paginasRestantes", 0) <= 0: break
                    pag += 1
            if not self.cancelar_busca: self.after(0, lambda: self._finalizar_busca_ui(len(self.resultados_pncp), f"{len(self.resultados_pncp)} itens online listados."))
        except Exception as e: self.after(0, lambda: self._finalizar_busca_com_erro(str(e)))

    def _obter_e_salvar_itens_paginados(self, lista_contratos, contratacoes_processadas, cod_modalidade, alvo_busca="Todos", radicais_busca=None, portais_selecionados=None, chaves_cadastradas=None, tipo_operacao="busca"):
        if chaves_cadastradas is None: chaves_cadastradas = set()
        itens_salvos_count, mod_nome = 0, next((k for k, v in self.modalidades_map.items() if v == str(cod_modalidade)), "Não informada")

        for contrato in lista_contratos:
            if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
            portal_nome = contrato.get("usuarioNome", "Não informado")
            if portais_selecionados and not any(ps.lower() in portal_nome.lower() for ps in portais_selecionados): continue 
            cnpj, ano, seq = contrato.get("orgaoEntidade", {}).get("cnpj"), contrato.get("anoCompra"), contrato.get("sequencialCompra")
            chave_edital = f"{cnpj}_{ano}_{seq}"
            
            if chave_edital in contratacoes_processadas: continue
            contratacoes_processadas.add(chave_edital)

            orgao, uf, data_pub, objeto_contrato = contrato.get("orgaoEntidade", {}).get("razaoSocial", "N/I"), contrato.get("unidadeOrgao", {}).get("ufSigla", "-"), str(contrato.get("dataPublicacaoPncp", ""))[:10], contrato.get("objeto", "")

            if cnpj and ano and seq:
                pag_item = 1
                while True:
                    if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
                    res_i = self._get_com_retentativa(f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens", {"pagina": pag_item, "tamanhoPagina": 500}, timeout=10, tipo_operacao=tipo_operacao)
                    if not res_i or res_i.status_code != 200: break
                    
                    itens_json = res_i.json()
                    for it in (itens_json.get("data", []) if isinstance(itens_json, dict) else itens_json):
                        if (self.cancelar_busca if tipo_operacao == "busca" else self.cancelar_carga): break
                        num_item = it.get("numeroItem", 0)
                        mat_nome = it.get("materialOuServicoNome", "") or (it.get("materialOuServico").get("nome", "") if isinstance(it.get("materialOuServico"), dict) else "")
                        desc_bruta = it.get("descricao", "")
                        desc_item = f"{mat_nome} - {desc_bruta}" if mat_nome and desc_bruta else (mat_nome or desc_bruta or objeto_contrato)
                        
                        if radicais_busca and not contem_palavras_chave(desc_item if alvo_busca == "Apenas no Item" else (objeto_contrato if alvo_busca == "Apenas no Objeto do Edital" else f"{desc_item} {objeto_contrato}"), radicais_busca): continue

                        chave_u = f"{cnpj}_{ano}_{seq}_{num_item}"
                        if chave_u not in chaves_cadastradas:
                            chaves_cadastradas.add(chave_u)
                            qtd, v_u_est, v_t_est, v_u_hom, v_t_hom = float(it.get("quantidade", 1)), it.get("valorUnitarioEstimado"), it.get("valorTotalEstimado"), it.get("valorUnitarioHomologado"), it.get("valorTotalHomologado") or it.get("valorTotal")
                            reg = {"Orgao": orgao, "UF": uf, "ObjetoContrato": objeto_contrato, "DescItem": desc_item, "Qtd": qtd, "Vlr Unit Est": self.formatar_moeda(v_u_est), "Vlr Total Est": self.formatar_moeda(v_t_est), "Vlr Unit Hom": self.formatar_moeda(v_u_hom), "Vlr Total Hom": self.formatar_moeda(v_t_hom), "Data Pub": data_pub, "CNPJ": cnpj, "Ano": ano, "Sequencial": seq, "NumeroItem": num_item, "ModalidadeID": str(cod_modalidade), "ModalidadeNome": mod_nome, "PortalNome": portal_nome}
                            
                            if tipo_operacao == "busca" or (tipo_operacao == "carga" and self.mostrar_carga_no_grid):
                                self.resultados_pncp.append(reg)
                                self.after(0, lambda r=reg: self._adicionar_item_tabela(r["Orgao"], r["UF"], r["PortalNome"], f"{r['Sequencial']}/{r['Ano']}", r["DescItem"], r["Qtd"], r["Vlr Unit Est"], r["Vlr Total Est"], r["Vlr Unit Hom"], r["Vlr Total Hom"], r["Data Pub"], r["CNPJ"], r["Ano"], r["Sequencial"], r["ModalidadeNome"], r["ObjetoContrato"]))
                                self.after(0, lambda: self.tree.yview_moveto(1))
                                
                            self.salvar_item_db(reg)
                            itens_salvos_count += 1
                            
                            if tipo_operacao == "carga" and itens_salvos_count % 50 == 0:
                                self.registrar_log(f"🔄 Atualização em massa: {itens_salvos_count} itens processados e guardados...")
                    
                    if (itens_json.get("paginasRestantes", 0) if isinstance(itens_json, dict) else 0) <= 0: break
                    pag_item += 1
        return itens_salvos_count

    def _limpar_tabela(self):
        for row in self.tree.get_children(): self.tree.delete(row)

    def _adicionar_item_tabela(self, orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, data_pub, cnpj, ano, seq, mod_nome, obj_contrato):
        self.tree.insert("", "end", values=(orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, data_pub, cnpj, ano, seq, mod_nome, obj_contrato))

    def _finalizar_busca_ui(self, qtd, msg_status):
        self.btn_buscar.configure(text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal")
        if not self.is_carga_running: self.lbl_status.configure(text=msg_status, text_color="#2ecc71" if qtd > 0 else "#e74c3c")
        self.btn_exportar.configure(state="normal" if qtd > 0 else "disabled")

    def _finalizar_busca_com_erro(self, msg_erro):
        if not self.is_carga_running: self.lbl_status.configure(text="Erro ao executar busca.", text_color="#e74c3c")
        self.btn_buscar.configure(text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal")
        messagebox.showerror("Erro na Busca", f"Falha na consulta: {msg_erro}")

if __name__ == "__main__":
    try:
        app = BuscadorPNCP()
        app.mainloop()
    except Exception:
        root_error = tk.Tk()
        root_error.withdraw()
        messagebox.showerror("Falha Crítica", f"O sistema não conseguiu iniciar:\n{traceback.format_exc()}")