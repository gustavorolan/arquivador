import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arquivador as a

COLUNAS = (("nome", "Nome", 220), ("estado", "Estado", 80), ("original", "Original", 90), ("zip", "ZIP", 90), ("data", "Data", 90), ("origem", "Origem", 420))


def tam(b):
    if b >= 1024**3:
        return f"{b / 1024**3:.2f} GB"
    if b >= 1024**2:
        return f"{b / 1024**2:.1f} MB"
    return f"{max(1, round(b / 1024))} KB"


def data_br(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        self.jobs = []
        self.assinatura = None
        raiz.title("Arquivador")
        raiz.geometry("1100x620")
        raiz.minsize(800, 440)
        try:
            raiz.iconbitmap(str(Path(__file__).with_name("arquivador.ico")))
        except tk.TclError:
            pass
        ttk.Style().theme_use("vista" if "vista" in ttk.Style().theme_names() else "clam")
        self.montar()
        raiz.protocol("WM_DELETE_WINDOW", self.fechar_janela)
        self.atualizar()

    def montar(self):
        topo = ttk.Frame(self.raiz, padding=(12, 10, 12, 4))
        topo.pack(fill="x")
        ttk.Label(topo, text="Arquivador", font=("Segoe UI", 16, "bold")).pack(side="left")
        self.livre = ttk.Label(topo, foreground="#667085")
        self.livre.pack(side="right")

        barra = ttk.Frame(self.raiz, padding=(12, 4))
        barra.pack(fill="x")
        self.botoes = {}
        for chave, texto, comando in (
            ("abrir", "Abrir", self.abrir),
            ("pasta", "Abrir pasta", self.abrir_pasta),
            ("guardar", "Guardar de volta", self.guardar),
            ("excluir", "Excluir ZIP", self.excluir),
        ):
            botao = ttk.Button(barra, text=texto, command=comando, state="disabled")
            botao.pack(side="left", padx=(0, 6))
            self.botoes[chave] = botao
        ttk.Button(barra, text="Compactar pasta...", command=self.compactar).pack(side="left", padx=(12, 0))
        self.filtro = tk.StringVar()
        self.filtro.trace_add("write", lambda *_: self.recarregar(forcar=True))
        ttk.Entry(barra, textvariable=self.filtro, width=28).pack(side="right")
        ttk.Label(barra, text="Filtrar:").pack(side="right", padx=(0, 6))

        meio = ttk.Frame(self.raiz, padding=(12, 4))
        meio.pack(fill="both", expand=True)
        self.arvore = ttk.Treeview(meio, columns=[c[0] for c in COLUNAS], show="headings", selectmode="browse")
        for chave, titulo, largura in COLUNAS:
            self.arvore.heading(chave, text=titulo)
            self.arvore.column(chave, width=largura, anchor="e" if chave in ("original", "zip") else "w", stretch=chave == "origem")
        rolagem = ttk.Scrollbar(meio, orient="vertical", command=self.arvore.yview)
        self.arvore.configure(yscrollcommand=rolagem.set)
        self.arvore.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        self.arvore.tag_configure("aberto", foreground="#15803d", font=("Segoe UI", 9, "bold"))
        self.arvore.bind("<<TreeviewSelect>>", lambda *_: self.ajustar_botoes())
        self.arvore.bind("<Double-1>", lambda *_: self.acao_padrao())

        base = ttk.Frame(self.raiz, padding=(12, 6, 12, 12))
        base.pack(fill="x")
        self.status = ttk.Label(base, text="Nada em andamento.")
        self.status.pack(anchor="w")
        self.progresso = ttk.Progressbar(base, maximum=100)
        self.progresso.pack(fill="x", pady=(4, 0))

    def selecionado(self):
        marcados = self.arvore.selection()
        if not marcados:
            return None
        return next((i for i in a.ler_indice() if i["id"] == marcados[0]), None)

    def ajustar_botoes(self):
        item = self.selecionado()
        estados = {
            "abrir": item is not None and not item.get("aberto"),
            "pasta": item is not None and bool(item.get("aberto")),
            "guardar": item is not None and bool(item.get("aberto")),
            "excluir": item is not None and not item.get("aberto"),
        }
        for chave, ativo in estados.items():
            self.botoes[chave].configure(state="normal" if ativo else "disabled")

    def acao_padrao(self):
        item = self.selecionado()
        if item is None:
            return
        self.abrir_pasta() if item.get("aberto") else self.abrir()

    def iniciar(self, alvo, *args):
        self.jobs.append(a.iniciar(alvo, *args))

    def abrir(self):
        item = self.selecionado()
        if item and not item.get("aberto"):
            self.iniciar(a.trabalho_restaurar, item, True)

    def abrir_pasta(self):
        item = self.selecionado()
        if item and Path(item["origem"]).is_dir():
            os.startfile(item["origem"])

    def guardar(self):
        item = self.selecionado()
        if item and item.get("aberto"):
            self.iniciar(a.trabalho_fechar, item)

    def excluir(self):
        item = self.selecionado()
        if item and messagebox.askyesno("Excluir ZIP", f"Excluir definitivamente o ZIP de '{item['nome']}'?\nNao ha como desfazer."):
            a.excluir_item(item)
            self.recarregar(forcar=True)

    def compactar(self):
        pasta = filedialog.askdirectory(title="Escolha a pasta para compactar", initialdir=str(a.HOME), mustexist=True)
        if not pasta:
            return
        try:
            caminho = a.validar_caminho(pasta)
        except ValueError as erro:
            messagebox.showerror("Nao permitido", str(erro))
            return
        resposta = messagebox.askyesnocancel(
            "Compactar",
            f"Compactar '{caminho.name}'?\n\nSim = compactar e apagar o original depois de verificar o ZIP.\nNao = compactar e manter o original.",
        )
        if resposta is not None:
            self.iniciar(a.trabalho_compactar, caminho, resposta)

    def recarregar(self, forcar=False):
        itens = a.ler_indice()
        texto = self.filtro.get().strip().lower()
        visiveis = [i for i in reversed(itens) if texto in i["nome"].lower()]
        assinatura = (texto, tuple((i["id"], bool(i.get("aberto")), i["bytes_zip"]) for i in visiveis))
        if assinatura == self.assinatura and not forcar:
            return
        self.assinatura = assinatura
        escolhido = self.arvore.selection()
        self.arvore.delete(*self.arvore.get_children())
        for i in visiveis:
            aberto = bool(i.get("aberto"))
            self.arvore.insert("", "end", iid=i["id"], tags=("aberto",) if aberto else (), values=(
                i["nome"], "ABERTO" if aberto else "zipado", tam(i["bytes_originais"]), tam(i["bytes_zip"]), data_br(i["data"]), i["origem"]))
        if escolhido and self.arvore.exists(escolhido[0]):
            self.arvore.selection_set(escolhido[0])
        self.ajustar_botoes()

    def atualizar(self):
        self.recarregar()
        self.livre.configure(text=f"Livre no C: {a.livre_gb()} GB  ·  ZIPs em {a.ARQUIVO}")
        self.mostrar_job()
        self.raiz.after(700, self.atualizar)

    def mostrar_job(self):
        if not self.jobs:
            return
        job = self.jobs[-1]
        sufixo = f": {job['erro']}" if job["erro"] else ""
        if job["ok"] is True and job.get("liberado"):
            sufixo = f" · liberou {tam(job['liberado'])}"
        self.status.configure(text=f"{job['nome']} — {job['fase']}{sufixo}")
        self.progresso.configure(value=100 if job["ok"] is True else (job["feito"] / job["total"] * 100 if job["total"] else 0))
        if job["ok"] is False and not job.get("avisado"):
            job["avisado"] = True
            messagebox.showerror("Falhou", f"{job['nome']}\n\n{job['erro']}")

    def fechar_janela(self):
        ocupados = [j for j in self.jobs if j["ok"] is None]
        if ocupados and not messagebox.askyesno("Em andamento", "Ha uma tarefa em andamento. Sair mesmo assim?\n(Pode deixar a pasta incompleta; o original so e apagado depois da verificacao.)"):
            return
        self.raiz.destroy()


def main():
    raiz = tk.Tk()
    App(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
