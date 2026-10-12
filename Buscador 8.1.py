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
    """Remove acentos, caracteres especiais e converte para minúsculas."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    texto_sem_acento = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return texto_sem_acento.lower().strip()


def extrair_radicais(termo: str) -> list:
    """Extrai os radicais das palavras para tratar plurais."""
    palavras = [p for p in normalizar_texto(termo).split() if len(p) >= 2]
    radicais = []
    for p in palavras:
        rad = p
        if p.endswith("es") and len(p) > 3:
            rad = p[:-2]
        elif p.endswith("s") and len(p) > 3:
            rad = p[:-1]
        radicais.append(rad)
    return radicais


def contem_palavras_chave(texto: str, radicais: list) -> bool:
    """Verifica se todos os radicais buscados estão presentes no texto."""
    if not radicais:
        return False
    texto_norm = normalizar_texto(texto)
    return all(rad in texto_norm for rad in radicais)


class BuscadorPNCP(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title("Buscador Multi-Portal de Licitações & Preços - Compras Públicas")
        self.geometry("1180x920")

        # ------------------------------------------------------------------
        # COLOQUE AQUI A SUA URL DA VERCEL (com o /api/valida no final)
        # ------------------------------------------------------------------
        self.url_api_licenca = "https://meu-validador-licencas.vercel.app/api/valida"

        # Caminho do BD V9 para nova estrutura de licenças focada no CNPJ
        self.db_path = "licitacoes_pncp_v9.db"

        # Oculta a janela principal até a licença online ser validada
        self.withdraw()

        # Variáveis de Estado
        self.cancelar_operacao = False
        self.item_selecionado_doc = None
        self.resultados_pncp = []

        # Para evitar que a requisição de rede congele a criação da interface,
        # mandamos o programa iniciar o ciclo gráfico e só depois fazer a validação.
        self.after(200, self._rotina_de_arranque)

    def _rotina_de_arranque(self):
        """Inicia a verificação de licença apenas após o mainloop estar ativo."""
        self.setup_db_licenca()
        cnpj_salvo = self.get_cnpj_registrado()

        if not cnpj_salvo:
            # Se não tem CNPJ guardado, pede ao utilizador
            self.solicitar_registro_cnpj()
        else:
            # Se já tem CNPJ guardado, valida em background na Vercel
            if self.validar_licenca_online(cnpj_salvo, silencioso=True):
                self.iniciar_sistema_principal()
            else:
                # Se falhar a validação (expirada, noutro PC ou sem net), pede de novo
                self.solicitar_registro_cnpj()

    def obter_hwid(self) -> str:
        """Gera um identificador único baseado no Hardware (Placa mãe/Rede) do PC."""
        return str(uuid.getnode())

    def validar_licenca_online(self, cnpj_licenca: str, silencioso=False) -> bool:
        """Comunica com a API Serverless na Vercel para validar o CNPJ e a validade."""
        if not self.url_api_licenca or "SUA-URL-AQUI" in self.url_api_licenca:
            if not silencioso: messagebox.showerror("Erro de Configuração", "A URL da API da Vercel não foi configurada no código-fonte.")
            return False

        hwid = self.obter_hwid()
        payload = {"cnpj": cnpj_licenca, "hwid": hwid}
        
        try:
            # Tempo de limite de 10 segundos para não travar a aplicação
            response = requests.post(self.url_api_licenca, json=payload, timeout=10)
            
            try:
                dados = response.json()
            except:
                if not silencioso: messagebox.showerror("Erro de Servidor", "A API da Vercel não retornou um formato JSON válido. Verifique se a URL está correta ou se a proteção Vercel Authentication foi desativada.")
                return False
                
            if response.status_code == 200 and dados.get("status") == "success":
                return True
            else:
                if not silencioso:
                    mensagem_erro = dados.get("message", "Acesso negado.")
                    messagebox.showerror("Licença Inválida", f"Falha na validação do sistema:\n{mensagem_erro}")
                return False
                
        except requests.exceptions.RequestException as e:
            if not silencioso:
                messagebox.showerror("Erro de Conexão", f"Não foi possível contactar o servidor de licenças.\nVerifique sua internet ou VPN.\nDetalhe: {e}")
            return False

    def setup_db_licenca(self):
        """Cria a tabela de licença local caso não exista."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS usuario_licenca (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        cnpj TEXT NOT NULL,
                        data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
        except Exception as e:
            messagebox.showerror("Erro Local", f"Falha ao iniciar SQLite local: {e}")
            sys.exit()

    def get_cnpj_registrado(self):
        """Busca o último CNPJ guardado localmente."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT cnpj FROM usuario_licenca ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None

    def solicitar_registro_cnpj(self):
        """Abre a janela de registo de primeiro acesso exigindo o CNPJ."""
        self.janela_login = ctk.CTkToplevel(self)
        self.janela_login.title("Ativação de Licença")
        self.janela_login.geometry("500x250")
        self.janela_login.transient(self)
        self.janela_login.grab_set()
        
        # Se o utilizador fechar a janela no X, encerra a aplicação inteira
        self.janela_login.protocol("WM_DELETE_WINDOW", sys.exit)

        lbl = ctk.CTkLabel(
            self.janela_login, 
            text="Sistema Protegido\n\nPor favor, informe o CNPJ da sua empresa para verificar\na sua licença no nosso servidor online:", 
            font=("Arial", 14, "bold")
        )
        lbl.pack(pady=(20, 15))

        self.ent_cnpj_login = ctk.CTkEntry(self.janela_login, width=300, placeholder_text="Digite apenas números (Ex: 00000000000100)")
        self.ent_cnpj_login.pack(pady=10)
        self.ent_cnpj_login.bind("<Return>", lambda e: self.confirmar_registro_online())

        self.btn_ativar = ctk.CTkButton(self.janela_login, text="Validar Online", fg_color="#27ae60", hover_color="#2ecc71", font=("Arial", 12, "bold"), command=self.confirmar_registro_online)
        self.btn_ativar.pack(pady=20)

    def confirmar_registro_online(self):
        """Valida o CNPJ online e, se for válido (data OK), guarda no SQLite."""
        cnpj = self.ent_cnpj_login.get().strip()
        
        if len(cnpj) < 11:
            messagebox.showwarning("Aviso", "Por favor, introduza um CNPJ ou CPF válido.")
            return
            
        self.btn_ativar.configure(text="A validar...", state="disabled")
        self.janela_login.update()
        
        # Faz a chamada à Vercel (Supabase) enviando o CNPJ
        if self.validar_licenca_online(cnpj, silencioso=False):
            try:
                # Se for sucesso, guarda no banco local para o próximo acesso
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM usuario_licenca")
                    cursor.execute("INSERT INTO usuario_licenca (cnpj) VALUES (?)", (cnpj,))
                    conn.commit()
                    
                messagebox.showinfo("Sucesso", "Licença validada com sucesso!\nO aplicativo será aberto agora.")
                self.janela_login.destroy()
                self.iniciar_sistema_principal()
            except Exception as e:
                messagebox.showerror("Erro", f"Ocorreu um erro ao guardar a licença localmente: {e}")
                self.btn_ativar.configure(text="Validar Online", state="normal")
        else:
            self.btn_ativar.configure(text="Validar Online", state="normal")

    def iniciar_sistema_principal(self):
        """Carrega a interface, variáveis e bibliotecas após a validação bem-sucedida."""
        self.deiconify() # Torna a janela principal visível

        self.config_precos = {
            "vlr_unit_est": tk.BooleanVar(value=True),
            "vlr_total_est": tk.BooleanVar(value=True),
            "vlr_unit_hom": tk.BooleanVar(value=True),
            "vlr_total_hom": tk.BooleanVar(value=True)
        }

        self.lista_portais_comuns = [
            "Compras.gov.br",
            "Portal de Compras Públicas",
            "BLL",
            "Licitações-e",
            "BEC",
            "Licitar Digital",
            "AZ Informática", 
            "BBMNET",          
            "BNC",             
            "Portal de Compras da Caixa",
            "Licitanet",
            "Abase Sistemas",
            "Compras RS",
            "Compras SC",
            "Compras GO",
            "Ammfoco",
            "TCE",
            "Prefeitura"
        ]
        
        self.vars_portais = {portal: tk.BooleanVar(value=False) for portal in self.lista_portais_comuns}
        self.vars_portais["Todos"] = tk.BooleanVar(value=True) 

        self.categorias_map = {
            "Todas": "", "Cessão": "1", "Compras": "2", "Informática (TIC)": "3",
            "Internacional": "4", "Locação Imóveis": "5", "Mão de Obra": "6",
            "Obras": "7", "Serviços": "8", "Serviços de Engenharia": "9",
            "Serviços de Saúde": "10", "Alienação de bens móveis/imóveis": "11"
        }
        
        self.modalidades_map = {
            "Principais (Pregão, Dispensa, Conc.)": "", "1 - Leilão Eletrônico": "1",
            "2 - Diálogo Competitivo": "2", "3 - Concurso": "3", "4 - Concorrência Eletrônica": "4",
            "5 - Concorrência Presencial": "5", "6 - Pregão Eletrônico": "6", "7 - Pregão Presencial": "7",
            "8 - Dispensa de Licitação": "8", "9 - Inexigibilidade": "9", "10 - Manifestação de Interesse": "10",
            "11 - Pré-qualificação": "11", "12 - Credenciamento": "12", "13 - Leilão Presencial": "13"
        }

        self.lista_ufs = [
            "Todas", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", 
            "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", 
            "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"
        ]

        self.http_session = requests.Session()
        self.http_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://pncp.gov.br/"
        })

        self.criar_interface()
        self.init_db()

    # -------------------------------------------------------------
    # MÉTODOS DE BANCO DE DADOS DOS DADOS DE PESQUISA
    # -------------------------------------------------------------
    def init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS editais_itens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        orgao TEXT, uf TEXT, objeto_contrato TEXT, desc_item TEXT, quantidade REAL,
                        vlr_unit_est TEXT, vlr_total_est TEXT, vlr_unit_hom TEXT, vlr_total_hom TEXT,
                        data_publicacao TEXT, cnpj TEXT, ano INTEGER, sequencial INTEGER, numero_item INTEGER,
                        modalidade_id TEXT, modalidade_nome TEXT, portal_nome TEXT, data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(cnpj, ano, sequencial, numero_item, desc_item) ON CONFLICT REPLACE
                    )
                """)
                conn.commit()
            self.registrar_log(f"💾 Banco de Dados SQLite iniciado ({self.db_path}).")
        except Exception as e:
            self.registrar_log(f"❌ Erro ao inicializar SQLite: {e}")

    def salvar_item_db(self, item_dict):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO editais_itens 
                    (orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, cnpj, ano, sequencial, numero_item, modalidade_id, modalidade_nome, portal_nome)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item_dict.get("Orgao"), item_dict.get("UF"), item_dict.get("ObjetoContrato"), item_dict.get("DescItem"),
                    item_dict.get("Qtd"), item_dict.get("Vlr Unit Est"), item_dict.get("Vlr Total Est"), item_dict.get("Vlr Unit Hom"),
                    item_dict.get("Vlr Total Hom"), item_dict.get("Data Pub"), item_dict.get("CNPJ", ""), item_dict.get("Ano", 0),
                    item_dict.get("Sequencial", 0), item_dict.get("NumeroItem", 0), item_dict.get("ModalidadeID", ""),
                    item_dict.get("ModalidadeNome", ""), item_dict.get("PortalNome", "")
                ))
                conn.commit()
        except Exception as e:
            self.registrar_log(f"⚠️ Erro ao gravar item no SQLite: {e}")

    def contar_itens_db(self) -> int:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM editais_itens")
                return cursor.fetchone()[0]
        except Exception:
            return 0

    # -------------------------------------------------------------
    # CONSTRUÇÃO DA INTERFACE (GUI)
    # -------------------------------------------------------------
    def criar_interface(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_pesquisa = self.tabview.add("🔍 Pesquisa e Portais")
        self.tab_logs = self.tabview.add("📜 Logs do Sistema")

        self.frame_busca = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_busca.pack(fill="x", padx=10, pady=5)

        self.lbl_termo = ctk.CTkLabel(self.frame_busca, text="Produto/Serviço:", font=("Arial", 12, "bold"))
        self.lbl_termo.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.ent_termo = ctk.CTkEntry(self.frame_busca, width=400, placeholder_text="Ex: ALFAJOR, ARROZ, NOTEBOOK")
        self.ent_termo.grid(row=0, column=1, columnspan=2, sticky="we", padx=5, pady=5)
        self.ent_termo.bind("<Return>", lambda e: self.iniciar_busca())

        self.combo_alvo = ctk.CTkOptionMenu(
            self.frame_busca,
            values=["Todos", "Apenas no Item", "Apenas no Objeto do Edital"],
            width=200
        )
        self.combo_alvo.set("Todos")
        self.combo_alvo.grid(row=0, column=3, sticky="w", padx=5, pady=5)

        self.btn_buscar = ctk.CTkButton(
            self.frame_busca, text="🔍 Pesquisar", command=self.iniciar_busca, font=("Arial", 12, "bold")
        )
        self.btn_buscar.grid(row=0, column=4, padx=10, pady=5)
        
        self.default_btn_buscar_fg = self.btn_buscar.cget("fg_color")
        self.default_btn_buscar_hover = self.btn_buscar.cget("hover_color")

        data_atual = datetime.datetime.now()
        data_ini_padrao = (data_atual - datetime.timedelta(days=7)).strftime("%d/%m/%Y")
        data_fim_padrao = data_atual.strftime("%d/%m/%Y")

        self.lbl_data_ini = ctk.CTkLabel(self.frame_busca, text="Data Inicial:")
        self.lbl_data_ini.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.ent_data_ini = ctk.CTkEntry(self.frame_busca, width=120)
        self.ent_data_ini.insert(0, data_ini_padrao)
        self.ent_data_ini.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        self.lbl_data_fim = ctk.CTkLabel(self.frame_busca, text="Data Final:")
        self.lbl_data_fim.grid(row=1, column=2, sticky="e", padx=5, pady=5)

        self.ent_data_fim = ctk.CTkEntry(self.frame_busca, width=120)
        self.ent_data_fim.insert(0, data_fim_padrao)
        self.ent_data_fim.grid(row=1, column=3, sticky="w", padx=5, pady=5)

        self.combo_status = ctk.CTkOptionMenu(
            self.frame_busca, values=["Todos", "Encerradas", "A Receber/Recebendo Proposta"], width=220
        )
        self.combo_status.set("Todos")
        self.combo_status.grid(row=1, column=4, sticky="w", padx=5, pady=5)

        self.lbl_portal = ctk.CTkLabel(self.frame_busca, text="Portal/Sistema:")
        self.lbl_portal.grid(row=2, column=0, sticky="w", padx=5, pady=5)
        
        self.btn_portal = ctk.CTkButton(
            self.frame_busca, text="Selecionar Portais", width=180,
            fg_color="#3498db", hover_color="#2980b9",
            command=self.abrir_menu_portais
        )
        self.btn_portal.grid(row=2, column=1, sticky="we", padx=5, pady=5)

        self.lbl_categoria = ctk.CTkLabel(self.frame_busca, text="Categoria:")
        self.lbl_categoria.grid(row=2, column=2, sticky="e", padx=5, pady=5)

        self.combo_categoria = ctk.CTkOptionMenu(
            self.frame_busca, values=list(self.categorias_map.keys()), width=150
        )
        self.combo_categoria.set("Todas")
        self.combo_categoria.grid(row=2, column=3, sticky="w", padx=5, pady=5)

        self.combo_modalidade = ctk.CTkOptionMenu(
            self.frame_busca, values=list(self.modalidades_map.keys()), width=220
        )
        self.combo_modalidade.set("Principais (Pregão, Dispensa, Conc.)")
        self.combo_modalidade.grid(row=2, column=4, sticky="w", padx=5, pady=5)

        self.lbl_uf = ctk.CTkLabel(self.frame_busca, text="Estado (UF):")
        self.lbl_uf.grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.combo_uf = ctk.CTkOptionMenu(
            self.frame_busca, values=self.lista_ufs, width=80
        )
        self.combo_uf.set("Todas")
        self.combo_uf.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        self.chk_base_local = ctk.CTkCheckBox(
            self.frame_busca, text="💾 Usar Base Local", font=("Arial", 11, "bold")
        )
        self.chk_base_local.grid(row=3, column=2, columnspan=2, sticky="w", padx=5, pady=5)

        self.btn_sincronizar = ctk.CTkButton(
            self.frame_busca,
            text="📥 Alimentar Base Local com os Filtros da API",
            fg_color="#8e44ad", hover_color="#732d91", font=("Arial", 11, "bold"),
            command=self.iniciar_carga_base
        )
        self.btn_sincronizar.grid(row=3, column=4, sticky="we", padx=5, pady=5)
        
        self.default_btn_sync_fg = self.btn_sincronizar.cget("fg_color")
        self.default_btn_sync_hover = self.btn_sincronizar.cget("hover_color")

        self.lbl_portais = ctk.CTkLabel(
            self.tab_pesquisa, text="Abrir Busca Direta nos Portais Web:", font=("Arial", 11, "bold")
        )
        self.lbl_portais.pack(anchor="w", padx=15, pady=(5, 2))

        self.frame_portais = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_portais.pack(fill="x", padx=10, pady=2)

        ctk.CTkButton(self.frame_portais, text="Pesquisa de Preços Lite", width=140, command=self.abrir_pesquisa_precos).pack(side="left", padx=5)
        ctk.CTkButton(self.frame_portais, text="PNCP Web", width=100, command=self.abrir_pncp_web).pack(side="left", padx=5)
        ctk.CTkButton(self.frame_portais, text="Compras GO", width=100, command=self.abrir_compras_go).pack(side="left", padx=5)
        ctk.CTkButton(self.frame_portais, text="BEC SP", width=100, command=self.abrir_bec_sp).pack(side="left", padx=5)
        ctk.CTkButton(self.frame_portais, text="🌐 Abrir Todos", fg_color="#1f538d", width=110, command=self.abrir_todos_portais).pack(side="right", padx=5)

        self.frame_head_tabela = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_head_tabela.pack(fill="x", padx=10, pady=(10, 2))

        self.lbl_titulo_tabela = ctk.CTkLabel(
            self.frame_head_tabela, text="Itens e Preços (Clique 1x para ler, 2x para edital):", font=("Arial", 12, "bold")
        )
        self.lbl_titulo_tabela.pack(side="left", padx=5)

        self.btn_config_precos = ctk.CTkButton(
            self.frame_head_tabela, text="⚙️ Configurar Preços", fg_color="#2980b9", width=140,
            command=self.abrir_menu_configuracao
        )
        self.btn_config_precos.pack(side="left", padx=15)

        self.lbl_status = ctk.CTkLabel(
            self.frame_head_tabela, text="Pronto para buscar.", text_color="#2ecc71", font=("Arial", 11, "italic")
        )
        self.lbl_status.pack(side="left", padx=10)

        self.btn_exportar = ctk.CTkButton(
            self.frame_head_tabela, text="📊 Exportar Excel", state="disabled", fg_color="#27ae60", width=130,
            command=self.exportar_excel
        )
        self.btn_exportar.pack(side="right", padx=5)

        self.frame_tabela = ctk.CTkFrame(self.tab_pesquisa)
        self.frame_tabela.pack(fill="both", expand=True, padx=10, pady=2)

        colunas = ("orgao", "uf", "portal", "edital", "objeto", "qtd", 
                   "vlr_unit_est", "vlr_total_est", "vlr_unit_hom", "vlr_total_hom", 
                   "data", "cnpj", "ano", "seq", "modalidade_nome", "objeto_contrato")
        
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

        self.tree.column("orgao", width=180, minwidth=120)
        self.tree.column("uf", width=40, anchor="center", minwidth=40)
        self.tree.column("portal", width=120, anchor="w", minwidth=80)
        self.tree.column("edital", width=100, anchor="center", minwidth=80)
        self.tree.column("objeto", width=250, minwidth=150)
        self.tree.column("qtd", width=50, anchor="center", minwidth=50)
        self.tree.column("vlr_unit_est", width=100, anchor="e", minwidth=80)
        self.tree.column("vlr_total_est", width=100, anchor="e", minwidth=80)
        self.tree.column("vlr_unit_hom", width=100, anchor="e", minwidth=80)
        self.tree.column("vlr_total_hom", width=100, anchor="e", minwidth=80)
        self.tree.column("data", width=90, anchor="center", minwidth=80)

        self.aplicar_colunas_grid()

        scrollbar_y = ttk.Scrollbar(self.frame_tabela, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(self.frame_tabela, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=scrollbar_y.set, xscroll=scrollbar_x.set)

        scrollbar_x.pack(side="bottom", fill="x")
        scrollbar_y.pack(side="right", fill="y")
        self.tree.pack(side="top", fill="both", expand=True)

        self.frame_detalhes = ctk.CTkFrame(self.tab_pesquisa, fg_color="transparent")
        self.frame_detalhes.pack(fill="x", padx=10, pady=(2, 10))

        self.txt_detalhes = ctk.CTkTextbox(self.frame_detalhes, height=70, font=("Arial", 12), text_color="#2c3e50")
        self.txt_detalhes.pack(side="left", fill="both", expand=True, padx=(0, 5))
        self.txt_detalhes.insert("end", "Selecione um item na tabela acima para visualizar a descrição completa aqui.")
        self.txt_detalhes.configure(state="disabled")

        self.btn_arquivos = ctk.CTkButton(
            self.frame_detalhes, text="📂 Ver Arquivos\n(Editais/Anexos)", width=140, height=70,
            fg_color="#d35400", hover_color="#e67e22", state="disabled",
            font=("Arial", 12, "bold"),
            command=self.abrir_janela_arquivos
        )
        self.btn_arquivos.pack(side="right")

        self.tree.bind("<<TreeviewSelect>>", self._ao_selecionar_tabela)
        self.tree.bind("<Double-1>", self._ao_duplo_clique_tabela)

        self.txt_logs = ctk.CTkTextbox(self.tab_logs, font=("Consolas", 11))
        self.txt_logs.pack(fill="both", expand=True, padx=10, pady=10)

        self.registrar_log("Aplicação iniciada e conectada ao validador online Vercel.")

    # -------------------------------------------------------------
    # INTERAÇÕES E FUNÇÕES GERAIS
    # -------------------------------------------------------------
    def _on_chk_todos_portais_click(self):
        if self.vars_portais["Todos"].get():
            for p in self.lista_portais_comuns:
                self.vars_portais[p].set(False)

    def _on_chk_portal_click(self):
        algum_marcado = any(self.vars_portais[p].get() for p in self.lista_portais_comuns)
        if algum_marcado:
            self.vars_portais["Todos"].set(False)
        else:
            self.vars_portais["Todos"].set(True)

    def abrir_menu_portais(self):
        janela_portais = ctk.CTkToplevel(self)
        janela_portais.title("Selecionar Portais / Sistemas Integrados")
        janela_portais.geometry("380x480")
        janela_portais.transient(self) 
        janela_portais.grab_set() 

        lbl_titulo = ctk.CTkLabel(janela_portais, text="Selecione os portais para a busca:", font=("Arial", 12, "bold"))
        lbl_titulo.pack(pady=(15, 5))

        frame_scroll = ctk.CTkScrollableFrame(janela_portais)
        frame_scroll.pack(fill="both", expand=True, padx=15, pady=5)

        chk_todos = ctk.CTkCheckBox(
            frame_scroll, text="Qualquer Portal (Todos)", font=("Arial", 12, "bold"),
            variable=self.vars_portais["Todos"], command=self._on_chk_todos_portais_click
        )
        chk_todos.pack(anchor="w", padx=5, pady=10)

        ctk.CTkFrame(frame_scroll, height=2, fg_color="gray").pack(fill="x", pady=5)

        for portal in self.lista_portais_comuns:
            chk = ctk.CTkCheckBox(
                frame_scroll, text=portal, 
                variable=self.vars_portais[portal], command=self._on_chk_portal_click
            )
            chk.pack(anchor="w", padx=20, pady=4)

        btn_aplicar = ctk.CTkButton(janela_portais, text="Confirmar Filtro", command=janela_portais.destroy)
        btn_aplicar.pack(pady=15)

    def obter_portais_selecionados(self):
        if self.vars_portais["Todos"].get():
            return []
        return [p for p in self.lista_portais_comuns if self.vars_portais[p].get()]

    def exportar_excel(self):
        if not self.tree.get_children():
            messagebox.showinfo("Exportar", "Não há dados na tabela para exportar.")
            return

        caminho_arquivo = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("Arquivo Excel (CSV)", "*.csv"), ("Todos os Arquivos", "*.*")],
            title="Salvar Planilha de Exportação"
        )

        if not caminho_arquivo:
            return

        try:
            with open(caminho_arquivo, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                colunas_id = self.tree["columns"]
                cabecalhos = [self.tree.heading(col)["text"] for col in colunas_id]
                writer.writerow(cabecalhos)
                
                for row_id in self.tree.get_children():
                    valores = self.tree.item(row_id)["values"]
                    writer.writerow(valores)
                    
            self.registrar_log(f"✅ Dados exportados com sucesso para: {caminho_arquivo}")
            messagebox.showinfo("Exportação Concluída", f"O ficheiro foi gerado com sucesso em:\n{caminho_arquivo}\n\nPode abri-lo diretamente no Microsoft Excel.")
        except Exception as e:
            self.registrar_log(f"❌ Erro ao exportar para Excel: {e}")
            messagebox.showerror("Erro na Exportação", f"Falha ao gerar o ficheiro:\n{e}")

    def cancelar_acao(self):
        self.cancelar_operacao = True
        self.registrar_log("⚠️ Sinal de parada enviado pelo usuário. A interromper processo atual...")
        self.lbl_status.configure(text="A cancelar operação (aguarde)...", text_color="#e74c3c")
        self.btn_buscar.configure(state="disabled")
        self.btn_sincronizar.configure(state="disabled")

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

        btn_aplicar = ctk.CTkButton(janela_config, text="Aplicar e Fechar", command=lambda: [self.aplicar_colunas_grid(), janela_config.destroy()])
        btn_aplicar.pack(pady=20)

    def _ao_selecionar_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id:
            return
            
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 16:
            orgao = valores[0]
            uf = valores[1]
            portal = valores[2]
            edital_resumo = valores[3]
            desc_item_completo = valores[4]
            cnpj = valores[11]
            ano = valores[12]
            seq = valores[13]
            mod_nome = valores[14]
            objeto_geral = valores[15]

            self.item_selecionado_doc = (cnpj, ano, seq)
            self.btn_arquivos.configure(state="normal")

            url_edital = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"

            texto_exibicao = f"🏢 ÓRGÃO: {orgao} ({uf})   |   🌐 PORTAL: {portal}\n"
            texto_exibicao += f"📄 EDITAL: {edital_resumo}  |  ⚖️ MODALIDADE: {mod_nome}  |  🔗 Link: {url_edital}\n"
            texto_exibicao += f"🎯 OBJETO GERAL DO EDITAL: {objeto_geral}\n"
            texto_exibicao += f"📦 DESCRIÇÃO DO ITEM: {desc_item_completo}"

            self.txt_detalhes.configure(state="normal")
            self.txt_detalhes.delete("1.0", "end")
            self.txt_detalhes.insert("end", texto_exibicao)
            self.txt_detalhes.configure(state="disabled")

    def _ao_duplo_clique_tabela(self, event):
        item_id = self.tree.focus()
        if not item_id: return
            
        valores = self.tree.item(item_id, "values")
        if len(valores) >= 14:
            cnpj = valores[11]
            ano = valores[12]
            seq = valores[13]
            url_edital = f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"
            self.registrar_log(f"🌐 Abrindo edital no navegador: {url_edital}")
            webbrowser.open(url_edital)

    def abrir_janela_arquivos(self):
        if not self.item_selecionado_doc: return
        cnpj, ano, seq = self.item_selecionado_doc
        url_arquivos = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
        
        self.btn_arquivos.configure(text="Aguarde...", state="disabled")
        threading.Thread(target=self._buscar_arquivos_thread, args=(url_arquivos,), daemon=True).start()

    def _buscar_arquivos_thread(self, url):
        try:
            res = self._get_com_retentativa(url, params={"pagina": 1, "tamanhoPagina": 100}, timeout=10)
            if res and res.status_code == 200:
                dados = res.json()
                lista_arquivos = []
                
                if isinstance(dados, dict) and "data" in dados:
                    lista_arquivos = dados.get("data", [])
                elif isinstance(dados, list):
                    lista_arquivos = dados
                    
                self.after(0, lambda: self.mostrar_janela_arquivos(lista_arquivos))
            else:
                self.after(0, lambda: messagebox.showinfo("Ficheiros", "Nenhum documento anexado foi encontrado para este edital."))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Erro", f"Erro de conexão ao procurar arquivos: {e}"))
        finally:
            self.after(0, lambda: self.btn_arquivos.configure(text="📂 Ver Arquivos\n(Editais/Anexos)", state="normal"))

    def mostrar_janela_arquivos(self, arquivos):
        janela_arq = ctk.CTkToplevel(self)
        janela_arq.title("Documentos Oficiais e Anexos")
        janela_arq.geometry("750x450")
        janela_arq.transient(self)
        
        if not arquivos:
            ctk.CTkLabel(janela_arq, text="⚠️ O Órgão não disponibilizou anexos para download via API neste edital.", font=("Arial", 14)).pack(pady=30)
            return
            
        lbl_info = ctk.CTkLabel(janela_arq, text="Lista de Documentos (Editais, Termos de Referência, Atas, etc.):", font=("Arial", 12, "bold"))
        lbl_info.pack(pady=10, padx=10, anchor="w")
            
        frame_lista = ctk.CTkScrollableFrame(janela_arq)
        frame_lista.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        for arq in arquivos:
            frame_item = ctk.CTkFrame(frame_lista, fg_color="#ecf0f1", corner_radius=5)
            frame_item.pack(fill="x", pady=5, padx=2)
            
            titulo = arq.get("titulo", "Documento Sem Título")
            tipo = arq.get("tipoDocumentoNome", "Anexo")
            url_doc = arq.get("url", "")
            
            lbl_nome = ctk.CTkLabel(
                frame_item, text=f"[{tipo}] {titulo}", font=("Arial", 11, "bold"), text_color="#2c3e50",
                anchor="w", justify="left", wraplength=550
            )
            lbl_nome.pack(side="left", padx=10, pady=10, fill="x", expand=True)
            
            if url_doc:
                btn_baixar = ctk.CTkButton(
                    frame_item, text="Baixar / Ver", width=100, fg_color="#2980b9", command=lambda u=url_doc: webbrowser.open(u)
                )
                btn_baixar.pack(side="right", padx=10, pady=10)

    def abrir_pncp_web(self):
        termo = urllib.parse.quote(self.ent_termo.get().strip())
        url = f"https://pncp.gov.br/app/editais?q={termo}" if termo else "https://pncp.gov.br/app/editais"
        webbrowser.open(url)

    def abrir_pesquisa_precos(self):
        termo = urllib.parse.quote(self.ent_termo.get().strip())
        url = f"https://pesquisadeprecos.comprasnet.gov.br/Pesquisa/Index?termo={termo}" if termo else "https://pesquisadeprecos.comprasnet.gov.br/"
        webbrowser.open(url)

    def abrir_compras_go(self):
        termo = urllib.parse.quote(self.ent_termo.get().strip())
        url = f"https://www.comprasnet.go.gov.br/consultas/licitacoes?termo={termo}" if termo else "https://www.comprasnet.go.gov.br/"
        webbrowser.open(url)

    def abrir_bec_sp(self):
        webbrowser.open("https://www.bec.sp.gov.br/")

    def abrir_todos_portais(self):
        self.abrir_pncp_web()
        self.abrir_pesquisa_precos()
        self.abrir_compras_go()
        self.abrir_bec_sp()

    def registrar_log(self, mensagem):
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{hora}] {mensagem}\n"
        print(log_msg.strip())
        if hasattr(self, "txt_logs"):
            self.after(0, lambda: self._escrever_log(log_msg))

    def _escrever_log(self, log_msg):
        self.txt_logs.insert("end", log_msg)
        self.txt_logs.see("end")

    def formatar_moeda(self, valor):
        if valor is None or valor == 0 or valor == "": return "Não informado"
        try:
            val = float(valor)
            if val == 0.0: return "Não informado"
            return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return "Não informado"

    def formatar_data_api(self, data_str):
        try:
            partes = data_str.strip().split("/")
            if len(partes) == 3: return f"{partes[2]}{partes[1].zfill(2)}{partes[0].zfill(2)}"
        except Exception: pass
        return data_str
        
    def _get_com_retentativa(self, url, params, max_tentativas=3, timeout=15):
        for tentativa in range(1, max_tentativas + 1):
            if self.cancelar_operacao: return None
            try:
                res = self.http_session.get(url, params=params, timeout=timeout)
                return res
            except (requests.exceptions.RequestException, Exception) as e:
                if tentativa == max_tentativas or self.cancelar_operacao: raise e
                self.registrar_log(f"⏳ Rede instável. Retentando... (Tentativa {tentativa}/{max_tentativas})")
                for _ in range(30):
                    if self.cancelar_operacao: return None
                    time.sleep(0.1)

    # -------------------------------------------------------------
    # MOTORES DE PESQUISA E CARGA DE DADOS
    # -------------------------------------------------------------
    def iniciar_carga_base(self):
        data_ini = self.formatar_data_api(self.ent_data_ini.get().strip())
        data_fim = self.formatar_data_api(self.ent_data_fim.get().strip())
        
        uf_selecionada = self.combo_uf.get()
        categoria_nome = self.combo_categoria.get()
        categoria_id = self.categorias_map.get(categoria_nome)
        
        modalidade_nome = self.combo_modalidade.get()
        modalidade_id = self.modalidades_map.get(modalidade_nome)
        portais_selecionados = self.obter_portais_selecionados()

        mensagem_confirmacao = f"Deseja sincronizar a Base Local baixando editais do período selecionado?\n\nEstado: {uf_selecionada}\nCategoria: {categoria_nome}\nModalidade: {modalidade_nome}"
        if portais_selecionados: mensagem_confirmacao += f"\nPortais: {', '.join(portais_selecionados)}"
            
        if not messagebox.askyesno("Confirmar Carga", mensagem_confirmacao):
            return

        self.cancelar_operacao = False
        self.btn_sincronizar.configure(text="⏹ Parar Carga", fg_color="#e74c3c", hover_color="#c0392b", command=self.cancelar_acao)
        self.btn_buscar.configure(state="disabled")
        self.lbl_status.configure(text="Alimentando Base Local (Aguarde)...", text_color="#8e44ad")

        threading.Thread(target=self._executar_carga_base_thread, args=(data_ini, data_fim, categoria_id, modalidade_id, uf_selecionada, portais_selecionados), daemon=True).start()

    def _executar_carga_base_thread(self, data_inicio, data_fim, categoria_id, modalidade_id, uf_selecionada, portais_selecionados):
        url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
        modalidades = [int(modalidade_id)] if modalidade_id else [8, 6, 4]
        contratacoes_processadas = set()
        novos_itens = 0

        self.registrar_log(f"📥 Iniciando Carga Ampla da Base Local - UF: {uf_selecionada} | Modalidade(s): {modalidades}")

        for cod_modalidade in modalidades:
            if self.cancelar_operacao: break
            pag = 1
            while True: 
                if self.cancelar_operacao: break
                
                params = {"dataInicial": data_inicio, "dataFinal": data_fim, "codigoModalidadeContratacao": str(cod_modalidade), "pagina": str(pag), "tamanhoPagina": "50"}
                if categoria_id: params["codigoCategoriaProcesso"] = categoria_id
                if uf_selecionada != "Todas": params["uf"] = uf_selecionada

                try:
                    res = self._get_com_retentativa(url_base, params=params, timeout=15)
                    if not res: break 
                    
                    if res.status_code == 200:
                        data_json = res.json()
                        lista_contratos = data_json.get("data", []) or []
                        if not lista_contratos: break
                        
                        self.registrar_log(f"Lendo Mod {cod_modalidade} | Pág {pag}...")
                        novos_itens += self._obter_e_salvar_itens_paginados(lista_contratos, contratacoes_processadas, cod_modalidade, portais_selecionados=portais_selecionados)
                        
                        paginas_restantes = data_json.get("paginasRestantes", 0)
                        if paginas_restantes <= 0: break
                        pag += 1
                    else:
                        erro_msg = res.text[:200].replace('\n', ' ') if res else "Sem resposta"
                        self.registrar_log(f"⚠️ Erro {res.status_code if res else 'N/A'} na pág {pag} Mod {cod_modalidade}. Detalhe: {erro_msg}")
                        break
                except Exception as e:
                    self.registrar_log(f"⚠️ Falha definitiva de conexão (Mod {cod_modalidade}): {e}")
                    break

        total_db = self.contar_itens_db()
        if self.cancelar_operacao: self.registrar_log("⛔ Operação de Carga cancelada.")
        self.registrar_log(f"✅ Ciclo concluído! {novos_itens} novos itens salvos. Total na Base Local: {total_db} registros.")
        self.after(0, lambda: self._finalizar_carga_ui(total_db))

    def _obter_e_salvar_itens_paginados(self, lista_contratos, contratacoes_processadas, cod_modalidade, alvo_busca="Todos", radicais_busca=None, portais_selecionados=None, chaves_cadastradas=None):
        if chaves_cadastradas is None: chaves_cadastradas = set()
        if portais_selecionados is None: portais_selecionados = []
            
        itens_salvos_count = 0
        mod_nome = "Não informada"
        for k, v in self.modalidades_map.items():
            if v == str(cod_modalidade):
                mod_nome = k
                break

        for contrato in lista_contratos:
            if self.cancelar_operacao: break
            
            portal_nome = contrato.get("usuarioNome", "Não informado")
            if portais_selecionados:
                match = any(ps.lower() in portal_nome.lower() for ps in portais_selecionados)
                if not match: continue 
            
            cnpj = contrato.get("orgaoEntidade", {}).get("cnpj")
            ano = contrato.get("anoCompra")
            seq = contrato.get("sequencialCompra")
            chave_edital = f"{cnpj}_{ano}_{seq}"
            edital_display = f"{seq}/{ano}" if seq and ano else "N/I"

            if chave_edital in contratacoes_processadas: continue
            contratacoes_processadas.add(chave_edital)

            orgao = contrato.get("orgaoEntidade", {}).get("razaoSocial", "N/I")
            uf = contrato.get("unidadeOrgao", {}).get("ufSigla", "-")
            data_pub = str(contrato.get("dataPublicacaoPncp", ""))[:10]
            objeto_contrato = contrato.get("objeto", "")

            if cnpj and ano and seq:
                url_itens = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens"
                pag_item = 1
                
                while True:
                    if self.cancelar_operacao: break
                    try:
                        time.sleep(0.02) 
                        res_i = self._get_com_retentativa(url_itens, {"pagina": pag_item, "tamanhoPagina": 500}, timeout=10)
                        
                        if not res_i: break
                        
                        if res_i.status_code == 200:
                            itens_json = res_i.json()
                            itens_lista = []
                            paginas_restantes = 0
                            
                            if isinstance(itens_json, dict):
                                itens_lista = itens_json.get("data", [])
                                paginas_restantes = itens_json.get("paginasRestantes", 0)
                            elif isinstance(itens_json, list):
                                itens_lista = itens_json

                            for it in itens_lista:
                                if self.cancelar_operacao: break
                                
                                num_item = it.get("numeroItem", 0)
                                mat_nome = it.get("materialOuServicoNome", "")
                                if not mat_nome and isinstance(it.get("materialOuServico"), dict):
                                    mat_nome = it.get("materialOuServico").get("nome", "")
                                    
                                desc_bruta = it.get("descricao", "")
                                
                                desc_item = ""
                                if mat_nome and desc_bruta: desc_item = f"{mat_nome} - {desc_bruta}"
                                elif mat_nome: desc_item = mat_nome
                                elif desc_bruta: desc_item = desc_bruta
                                else: desc_item = objeto_contrato
                                
                                if radicais_busca:
                                    if alvo_busca == "Apenas no Item": texto_alvo = desc_item
                                    elif alvo_busca == "Apenas no Objeto do Edital": texto_alvo = objeto_contrato
                                    else: texto_alvo = f"{desc_item} {objeto_contrato}"
                                        
                                    if not contem_palavras_chave(texto_alvo, radicais_busca): continue

                                chave_u = f"{cnpj}_{ano}_{seq}_{num_item}"
                                if chave_u not in chaves_cadastradas:
                                    chaves_cadastradas.add(chave_u)

                                    qtd = float(it.get("quantidade", 1))
                                    v_u_est = it.get("valorUnitarioEstimado")
                                    v_t_est = it.get("valorTotalEstimado")
                                    v_u_hom = it.get("valorUnitarioHomologado")
                                    v_t_hom = it.get("valorTotalHomologado") or it.get("valorTotal") 

                                    reg = {
                                        "Orgao": orgao, "UF": uf, "ObjetoContrato": objeto_contrato,
                                        "DescItem": desc_item, "Qtd": qtd, "Vlr Unit Est": self.formatar_moeda(v_u_est),
                                        "Vlr Total Est": self.formatar_moeda(v_t_est), "Vlr Unit Hom": self.formatar_moeda(v_u_hom),
                                        "Vlr Total Hom": self.formatar_moeda(v_t_hom), "Data Pub": data_pub, "CNPJ": cnpj,
                                        "Ano": ano, "Sequencial": seq, "NumeroItem": num_item, "ModalidadeID": str(cod_modalidade),
                                        "ModalidadeNome": mod_nome, "PortalNome": portal_nome
                                    }
                                    
                                    if radicais_busca:
                                        self.resultados_pncp.append(reg)
                                        self.after(0, lambda r=reg, ed=edital_display: self._adicionar_item_tabela(
                                            r["Orgao"], r["UF"], r["PortalNome"], ed, r["DescItem"], r["Qtd"],
                                            r["Vlr Unit Est"], r["Vlr Total Est"], r["Vlr Unit Hom"], r["Vlr Total Hom"], r["Data Pub"], 
                                            r["CNPJ"], r["Ano"], r["Sequencial"], r["ModalidadeNome"], r["ObjetoContrato"]
                                        ))
                                        
                                    self.salvar_item_db(reg)
                                    itens_salvos_count += 1
                            
                            total_pags = itens_json.get("totalPaginas", 1) if isinstance(itens_json, dict) else 1
                            if (paginas_restantes > 0 or pag_item < total_pags) and not self.cancelar_operacao:
                                pag_item += 1
                            else:
                                break
                        else:
                            break
                    except Exception:
                        break
                        
        return itens_salvos_count

    def _finalizar_carga_ui(self, total_db):
        self.btn_sincronizar.configure(
            text="📥 Alimentar Base Local com os Filtros da API", 
            fg_color=self.default_btn_sync_fg, hover_color=self.default_btn_sync_hover, command=self.iniciar_carga_base, state="normal"
        )
        self.btn_buscar.configure(state="normal")
        self.lbl_status.configure(text=f"Processo finalizado ({total_db} itens locais).", text_color="#2ecc71")
        messagebox.showinfo("Carga Concluída", f"O processo foi finalizado!\n\nTotal de itens no SQLite: {total_db}")

    def iniciar_busca(self):
        termo = self.ent_termo.get().strip()
        data_ini = self.ent_data_ini.get().strip()
        data_fim = self.ent_data_fim.get().strip()
        status_busca = self.combo_status.get()
        uf_selecionada = self.combo_uf.get()
        alvo_busca = self.combo_alvo.get()
        portais_selecionados = self.obter_portais_selecionados()
        modalidade_nome = self.combo_modalidade.get()
        modalidade_id = self.modalidades_map.get(modalidade_nome)

        if not termo:
            messagebox.showwarning("Aviso", "Por favor, informe o produto ou serviço para busca.")
            return

        self.cancelar_operacao = False
        self.btn_buscar.configure(text="⏹ Parar Busca", fg_color="#e74c3c", hover_color="#c0392b", command=self.cancelar_acao)
        self.btn_sincronizar.configure(state="disabled")

        if self.chk_base_local.get() == 1:
            self.lbl_status.configure(text="Consultando Base Local (SQLite)...", text_color="#f39c12")
            threading.Thread(target=self._buscar_local_db_thread, args=(termo, uf_selecionada, modalidade_id, alvo_busca, portais_selecionados), daemon=True).start()
        else:
            self.lbl_status.configure(text="Consultando API do PNCP...", text_color="#f39c12")
            d_ini_fmt = self.formatar_data_api(data_ini)
            d_fim_fmt = self.formatar_data_api(data_fim)
            threading.Thread(target=self._buscar_api_pncp_thread, args=(termo, d_ini_fmt, d_fim_fmt, status_busca, modalidade_id, uf_selecionada, alvo_busca, portais_selecionados), daemon=True).start()

    def _buscar_local_db_thread(self, termo, uf_selecionada, modalidade_id, alvo_busca, portais_selecionados):
        self.after(0, self._limpar_tabela)
        
        def reset_ui():
            self.txt_detalhes.configure(state="normal")
            self.txt_detalhes.delete("1.0", "end")
            self.txt_detalhes.configure(state="disabled")
            self.btn_arquivos.configure(state="disabled")
            
        self.after(0, reset_ui)
        
        self.resultados_pncp = []
        radicais_busca = extrair_radicais(termo)
        termo_norm = normalizar_texto(termo)
        self.registrar_log(f"🔎 Buscando termo na Base Local (SQLite): '{termo}' | UF: {uf_selecionada} | Alvo: {alvo_busca}")

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                sql = """SELECT orgao, uf, objeto_contrato, desc_item, quantidade, vlr_unit_est, vlr_total_est, vlr_unit_hom, vlr_total_hom, data_publicacao, cnpj, ano, sequencial, modalidade_nome, portal_nome
                         FROM editais_itens WHERE 1=1"""
                params = []
                
                if uf_selecionada != "Todas":
                    sql += " AND uf = ?"
                    params.append(uf_selecionada)
                if modalidade_id:
                    sql += " AND modalidade_id = ?"
                    params.append(modalidade_id)
                if portais_selecionados:
                    placeholders = " OR ".join(["portal_nome LIKE ?" for _ in portais_selecionados])
                    sql += f" AND ({placeholders})"
                    for p in portais_selecionados: params.append(f"%{p}%")
                    
                cursor.execute(sql, params)
                linhas = cursor.fetchall()

            count = 0
            for row in linhas:
                if self.cancelar_operacao: break
                
                orgao, uf, obj_contrato, desc_item, qtd, vlr_u_est, vlr_t_est, vlr_u_hom, vlr_t_hom, data_pub, cnpj, ano, seq, mod_nome, portal_nome = row
                
                if alvo_busca == "Apenas no Item": texto_alvo = desc_item
                elif alvo_busca == "Apenas no Objeto do Edital": texto_alvo = obj_contrato
                else: texto_alvo = f"{desc_item} {obj_contrato}"

                if (radicais_busca and contem_palavras_chave(texto_alvo, radicais_busca)) or (termo_norm and termo_norm in normalizar_texto(texto_alvo)):

                    reg = {
                        "Orgao": orgao, "UF": uf, "ObjetoContrato": obj_contrato, "DescItem": desc_item,
                        "Qtd": qtd, "Vlr Unit Est": vlr_u_est, "Vlr Total Est": vlr_t_est,
                        "Vlr Unit Hom": vlr_u_hom, "Vlr Total Hom": vlr_t_hom, "Data Pub": data_pub,
                        "CNPJ": cnpj, "Ano": ano, "Sequencial": seq, "ModalidadeNome": mod_nome, "PortalNome": portal_nome
                    }
                    self.resultados_pncp.append(reg)
                    edital_display = f"{seq}/{ano}" if seq and ano else "N/I"
                    
                    self.after(0, lambda r=reg, ed=edital_display: self._adicionar_item_tabela(
                        r["Orgao"], r["UF"], r["PortalNome"], ed, r["DescItem"], r["Qtd"], r["Vlr Unit Est"], r["Vlr Total Est"], r["Vlr Unit Hom"], r["Vlr Total Hom"], r["Data Pub"], r["CNPJ"], r["Ano"], r["Sequencial"], r["ModalidadeNome"], r["ObjetoContrato"]
                    ))
                    count += 1

            if self.cancelar_operacao: self.registrar_log("⛔ Busca Local cancelada.")
            msg_status = f"{count} itens encontrados na Base Local."
            self.after(0, lambda: self._finalizar_busca_ui(count, msg_status))

        except Exception as e:
            self.registrar_log(f"❌ Erro ao buscar no SQLite: {e}")
            self.after(0, lambda: self._finalizar_busca_com_erro(str(e)))

    def _buscar_api_pncp_thread(self, termo, data_inicio, data_fim, status_busca, modalidade_id, uf_selecionada, alvo_busca, portais_selecionados):
        self.after(0, self._limpar_tabela)
        
        def reset_ui():
            self.txt_detalhes.configure(state="normal")
            self.txt_detalhes.delete("1.0", "end")
            self.txt_detalhes.configure(state="disabled")
            self.btn_arquivos.configure(state="disabled")
            
        self.after(0, reset_ui)
        
        self.resultados_pncp = []
        chaves_cadastradas = set()

        try:
            radicais_busca = extrair_radicais(termo)
            self.registrar_log(f"Iniciando busca no PNCP para o termo: '{termo}' | UF: {uf_selecionada} | Alvo: {alvo_busca}")

            if status_busca == "A Receber/Recebendo Proposta":
                url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/proposta"
                params_base = {"dataFinal": data_fim}
            else:
                url_base = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
                params_base = {"dataInicial": data_inicio, "dataFinal": data_fim}

            if uf_selecionada != "Todas": params_base["uf"] = uf_selecionada

            modalidades = [int(modalidade_id)] if modalidade_id else [8, 6, 4]
            contratacoes_processadas = set()

            for cod_modalidade in modalidades:
                if self.cancelar_operacao: break
                
                pag = 1
                while True: 
                    if self.cancelar_operacao: break
                    
                    params = params_base.copy()
                    params.update({"codigoModalidadeContratacao": str(cod_modalidade), "pagina": str(pag), "tamanhoPagina": "50"})

                    try:
                        res = self._get_com_retentativa(url_base, params=params, timeout=15)
                        if not res: break
                        
                        if res.status_code == 200:
                            data_json = res.json()
                            lista_contratos = data_json.get("data", []) or []
                            
                            if not lista_contratos: break
                                
                            self.registrar_log(f"Modalidade {cod_modalidade} (Pág {pag}): {len(lista_contratos)} edital(is). Lendo os itens...")
                            
                            self._obter_e_salvar_itens_paginados(
                                lista_contratos, contratacoes_processadas, cod_modalidade, alvo_busca=alvo_busca, radicais_busca=radicais_busca, portais_selecionados=portais_selecionados, chaves_cadastradas=chaves_cadastradas
                            )
                            
                            paginas_restantes = data_json.get("paginasRestantes", 0)
                            if paginas_restantes <= 0: break
                            pag += 1
                        else:
                            erro_msg = res.text[:200].replace('\n', ' ') if res else "Sem resposta"
                            self.registrar_log(f"⚠️ Erro API na pág {pag} Mod {cod_modalidade}. Detalhe: {erro_msg}")
                            break
                    except Exception as err_c:
                        self.registrar_log(f"⚠️ Falha de rede (Mod {cod_modalidade}): {err_c}")
                        break

            qtd_total = len(self.resultados_pncp)
            if self.cancelar_operacao:
                self.registrar_log("⛔ Operação de Busca cancelada.")
                msg_status = f"Busca interrompida! {qtd_total} itens localizados."
            else:
                msg_status = f"{qtd_total} itens correspondentes encontrados e salvos no banco."
                
            self.after(0, lambda: self._finalizar_busca_ui(qtd_total, msg_status))

        except Exception as e:
            self.registrar_log(f"❌ Exceção capturada na busca: {str(e)}")
            self.after(0, lambda: self._finalizar_busca_com_erro(str(e)))

    def _limpar_tabela(self):
        for row in self.tree.get_children(): self.tree.delete(row)

    def _adicionar_item_tabela(self, orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, data_pub, cnpj="", ano="", seq="", mod_nome="", obj_contrato=""):
        self.tree.insert("", "end", values=(orgao, uf, portal, edital, desc, qtd, unit_est, total_est, unit_hom, total_hom, data_pub, cnpj, ano, seq, mod_nome, obj_contrato))

    def _finalizar_busca_ui(self, qtd, msg_status):
        self.btn_buscar.configure(
            text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal"
        )
        self.btn_sincronizar.configure(state="normal")
        self.lbl_status.configure(text=msg_status, text_color="#2ecc71" if qtd > 0 else "#e74c3c")
        self.registrar_log(f"Busca finalizada. {msg_status}")
        self.btn_exportar.configure(state="normal" if qtd > 0 else "disabled")

    def _finalizar_busca_com_erro(self, msg_erro):
        self.lbl_status.configure(text="Erro ao executar busca.", text_color="#e74c3c")
        self.btn_buscar.configure(
            text="🔍 Pesquisar", fg_color=self.default_btn_buscar_fg, hover_color=self.default_btn_buscar_hover, command=self.iniciar_busca, state="normal"
        )
        self.btn_sincronizar.configure(state="normal")
        messagebox.showerror("Erro na Busca", f"Falha na consulta: {msg_erro}")


if __name__ == "__main__":
    try:
        app = BuscadorPNCP()
        app.mainloop()
    except Exception as fatal_e:
        # Se algo impedir o sistema de arrancar, mostra um pop-up de erro global em vez de fechar silenciosamente
        root_error = tk.Tk()
        root_error.withdraw()
        messagebox.showerror("Falha Crítica", f"O sistema não conseguiu iniciar:\n{traceback.format_exc()}")