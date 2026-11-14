import json
import os
import secrets
import shutil
import stat
import sys
import threading
import time
import webbrowser
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HOME = Path.home()
ARQUIVO = Path(os.environ.get("ARQUIVADOR_DIR", HOME / "Arquivo"))
INDICE = ARQUIVO / "indice.json"
PORTA = int(os.environ.get("ARQUIVADOR_PORTA", "8765"))
TOKEN = secrets.token_urlsafe(24)
def ler_protegidos():
    arquivo = ARQUIVO / "protegidos.txt"
    if not arquivo.exists():
        return []
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    return [Path(linha.strip()) for linha in linhas if linha.strip() and not linha.strip().startswith("#")]


PROTEGIDOS_FIXOS = [HOME / ".claude", HOME / "AppData", ARQUIVO]
RAIZES_SUGERIDAS = ["Documents", "Downloads", "dev", "Projects", "Videos", "Desktop", "OneDrive"]
NOME_TAREFA = "Arquivador-Rotina"
TRAVA = threading.Lock()
JOBS = {}


def lp(caminho):
    texto = os.path.abspath(str(caminho))
    if texto.startswith("\\\\?\\"):
        return texto
    return "\\\\?\\" + texto


def eh_link(caminho):
    try:
        info = os.lstat(lp(caminho))
    except OSError:
        return True
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def tamanho(caminho):
    if eh_link(caminho):
        return 0
    if os.path.isfile(lp(caminho)):
        return os.path.getsize(lp(caminho))
    total = 0
    for raiz, pastas, arquivos in os.walk(lp(caminho)):
        pastas[:] = [p for p in pastas if not eh_link(os.path.join(raiz, p))]
        for nome in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, nome))
            except OSError:
                pass
    return total


def listar_arquivos(caminho):
    base = Path(caminho)
    if base.is_file():
        return [(base, base.name)]
    achados = []
    for raiz, pastas, arquivos in os.walk(lp(base)):
        pastas[:] = [p for p in pastas if not eh_link(os.path.join(raiz, p))]
        relativo = os.path.relpath(raiz, lp(base))
        prefixo = base.name if relativo == "." else base.name + "/" + relativo.replace("\\", "/")
        achados.append((None, prefixo + "/"))
        for nome in arquivos:
            completo = os.path.join(raiz, nome)
            if not eh_link(completo):
                achados.append((completo, prefixo + "/" + nome))
    return achados


def ler_indice():
    if not INDICE.exists():
        return []
    return json.loads(INDICE.read_text(encoding="utf-8"))


def gravar_indice(itens):
    ARQUIVO.mkdir(parents=True, exist_ok=True)
    INDICE.write_text(json.dumps(itens, indent=2, ensure_ascii=False), encoding="utf-8")


def validar_caminho(texto):
    caminho = Path(texto).resolve()
    if HOME not in caminho.parents:
        raise ValueError("Caminho precisa estar dentro da sua pasta de usuario.")
    for protegido in PROTEGIDOS_FIXOS + ler_protegidos():
        if caminho == protegido or protegido in caminho.parents or caminho in protegido.parents:
            raise ValueError(f"Caminho protegido: {protegido}")
    if caminho == HOME or caminho.parent == HOME and caminho.name.startswith("."):
        raise ValueError("Pasta de sistema/configuracao nao e permitida.")
    if not caminho.exists():
        raise ValueError("Caminho nao existe.")
    if eh_link(caminho):
        raise ValueError("Atalho/junction nao e suportado.")
    return caminho


def remover(caminho):
    def forcar(funcao, alvo, _):
        os.chmod(alvo, stat.S_IWRITE)
        funcao(alvo)

    if os.path.isdir(lp(caminho)):
        shutil.rmtree(lp(caminho), onerror=forcar)
    else:
        os.chmod(lp(caminho), stat.S_IWRITE)
        os.remove(lp(caminho))


def atualizar(job, **campos):
    with TRAVA:
        job.update(campos)


def escrever_zip(destino, arquivos, job):
    total = sum(os.path.getsize(c) for c, _ in arquivos if c)
    feito = 0
    with zipfile.ZipFile(lp(destino), "w", zipfile.ZIP_DEFLATED, compresslevel=6, strict_timestamps=False) as zf:
        for completo, arcname in arquivos:
            if completo is None:
                zf.mkdir(arcname.rstrip("/"))
                continue
            zf.write(completo, arcname)
            feito += os.path.getsize(completo)
            atualizar(job, feito=feito, total=total)
    return total


def verificar_zip(destino, arquivos):
    esperados = {nome: os.path.getsize(c) for c, nome in arquivos if c}
    with zipfile.ZipFile(lp(destino)) as zf:
        defeituoso = zf.testzip()
        if defeituoso:
            raise RuntimeError(f"ZIP corrompido em {defeituoso}")
        achados = {i.filename: i.file_size for i in zf.infolist() if not i.is_dir()}
    if achados != esperados:
        raise RuntimeError("ZIP nao confere com a origem (arquivos ou tamanhos diferentes).")


def contar_arquivos(caminho):
    if os.path.isfile(lp(caminho)):
        return 1
    return sum(len(f) for _, _, f in os.walk(lp(caminho)))


def criar_zip_verificado(caminho, job, exigir_completo):
    atualizar(job, fase="Listando arquivos")
    arquivos = listar_arquivos(caminho)
    ARQUIVO.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = ARQUIVO / f"{caminho.name}__{carimbo}-{secrets.token_hex(2)}.zip"
    try:
        atualizar(job, fase="Compactando")
        original = escrever_zip(destino, arquivos, job)
        atualizar(job, fase="Verificando integridade")
        verificar_zip(destino, arquivos)
        quantidade = sum(1 for c, _ in arquivos if c)
        existentes = contar_arquivos(caminho)
        if exigir_completo and existentes != quantidade:
            raise RuntimeError(f"Pasta tem {existentes} arquivos e o ZIP {quantidade}; original mantido.")
    except Exception:
        destino.unlink(missing_ok=True)
        raise
    return {"carimbo": carimbo, "zip": str(destino), "bytes_originais": original, "bytes_zip": destino.stat().st_size, "arquivos": quantidade}


def alterar_item(item_id, **campos):
    with TRAVA:
        indice = ler_indice()
        for item in indice:
            if item["id"] == item_id:
                item.update(campos)
        gravar_indice(indice)


def exigir_pasta_livre(pasta):
    provisoria = pasta.with_name(pasta.name + "__fechando")
    try:
        os.rename(lp(pasta), lp(provisoria))
        os.rename(lp(provisoria), lp(pasta))
    except OSError:
        raise RuntimeError("Pasta em uso por algum programa ou janela; feche e tente de novo.")


def trabalho_compactar(job, caminho, apagar):
    try:
        info = criar_zip_verificado(caminho, job, apagar)
        item = {
            "id": info["carimbo"] + "-" + secrets.token_hex(3),
            "nome": caminho.name,
            "origem": str(caminho),
            "zip": info["zip"],
            "bytes_originais": info["bytes_originais"],
            "bytes_zip": info["bytes_zip"],
            "arquivos": info["arquivos"],
            "data": datetime.now().isoformat(timespec="seconds"),
            "aberto": not apagar,
        }
        with TRAVA:
            indice = ler_indice()
            indice.append(item)
            gravar_indice(indice)
        if apagar:
            atualizar(job, fase="Apagando original")
            remover(caminho)
        atualizar(job, fase="Concluido", ok=True, liberado=item["bytes_originais"] - item["bytes_zip"] if apagar else 0)
    except Exception as erro:
        atualizar(job, fase="Falhou", erro=str(erro), ok=False)


def trabalho_restaurar(job, item, manter_zip):
    try:
        destino = Path(item["origem"])
        if destino.exists():
            raise RuntimeError(f"Ja existe algo em {destino}. Mova ou renomeie antes de abrir.")
        atualizar(job, fase="Extraindo")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(lp(item["zip"])) as zf:
            total = sum(i.file_size for i in zf.infolist())
            feito = 0
            for info in zf.infolist():
                zf.extract(info, lp(destino.parent))
                feito += info.file_size
                atualizar(job, feito=feito, total=total)
        if manter_zip:
            alterar_item(item["id"], aberto=True)
        else:
            Path(item["zip"]).unlink(missing_ok=True)
            with TRAVA:
                gravar_indice([i for i in ler_indice() if i["id"] != item["id"]])
        atualizar(job, fase="Concluido", ok=True)
    except Exception as erro:
        atualizar(job, fase="Falhou", erro=str(erro), ok=False)


def trabalho_fechar(job, item):
    try:
        pasta = Path(item["origem"])
        if not pasta.exists():
            alterar_item(item["id"], aberto=False)
            raise RuntimeError("A pasta de trabalho nao existe mais; o ZIP anterior foi mantido.")
        exigir_pasta_livre(pasta)
        info = criar_zip_verificado(pasta, job, True)
        alterar_item(
            item["id"], zip=info["zip"], bytes_originais=info["bytes_originais"], bytes_zip=info["bytes_zip"],
            arquivos=info["arquivos"], data=datetime.now().isoformat(timespec="seconds"), aberto=False,
        )
        Path(item["zip"]).unlink(missing_ok=True)
        atualizar(job, fase="Apagando pasta de trabalho")
        remover(pasta)
        atualizar(job, fase="Concluido", ok=True, liberado=info["bytes_originais"] - info["bytes_zip"])
    except Exception as erro:
        atualizar(job, fase="Falhou", erro=str(erro), ok=False)


def excluir_item(item):
    Path(item["zip"]).unlink(missing_ok=True)
    with TRAVA:
        gravar_indice([i for i in ler_indice() if i["id"] != item["id"]])


def novo_job(alvo):
    return {"id": secrets.token_hex(4), "fase": "Na fila", "feito": 0, "total": 0, "ok": None, "erro": None, "nome": alvo.name if hasattr(alvo, "name") else alvo["nome"]}


def ultima_modificacao(pasta):
    recente = os.path.getmtime(lp(pasta))
    for raiz, pastas, arquivos in os.walk(lp(pasta)):
        for nome in pastas + arquivos:
            try:
                recente = max(recente, os.path.getmtime(os.path.join(raiz, nome)))
            except OSError:
                pass
    return recente


def registrar(texto):
    ARQUIVO.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO / "rotina.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now().isoformat(timespec='seconds')} {texto}\n")


def rotina(horas_ociosas):
    limite = time.time() - horas_ociosas * 3600
    for item in ler_indice():
        if not item.get("aberto"):
            continue
        pasta = Path(item["origem"])
        if pasta.exists() and ultima_modificacao(pasta) > limite:
            registrar(f"pulou {item['nome']}: mexida ha menos de {horas_ociosas}h")
            continue
        job = novo_job(item)
        trabalho_fechar(job, item)
        registrar(f"{item['nome']}: {job['fase']} {job['erro'] or ''}".strip())


def instalar_rotina(horas_ociosas):
    import subprocess

    if getattr(sys, "frozen", False):
        comando = f'"{sys.executable}" rotina --horas {horas_ociosas}'
    else:
        executavel = Path(sys.executable).with_name("pythonw.exe")
        comando = f'"{executavel}" "{Path(__file__).resolve()}" rotina --horas {horas_ociosas}'
    resultado = subprocess.run(["schtasks", "/Create", "/TN", NOME_TAREFA, "/SC", "HOURLY", "/TR", comando, "/F"], capture_output=True, text=True)
    print(resultado.stdout.strip() or resultado.stderr.strip())
    return resultado.returncode


def remover_rotina():
    import subprocess

    resultado = subprocess.run(["schtasks", "/Delete", "/TN", NOME_TAREFA, "/F"], capture_output=True, text=True)
    print(resultado.stdout.strip() or resultado.stderr.strip())
    return resultado.returncode


def iniciar(alvo, *args):
    job = novo_job(args[0])
    with TRAVA:
        JOBS[job["id"]] = job
    threading.Thread(target=alvo, args=(job, *args), daemon=True).start()
    return job


def varrer(raiz_nome):
    raiz = HOME / raiz_nome
    if not raiz.is_dir():
        return []
    resultado = []
    for filho in raiz.iterdir():
        try:
            validar_caminho(str(filho))
        except ValueError:
            continue
        resultado.append({"nome": filho.name, "caminho": str(filho), "bytes": tamanho(filho), "pasta": filho.is_dir()})
    return sorted(resultado, key=lambda x: -x["bytes"])


def livre_gb():
    return round(shutil.disk_usage(HOME.anchor).free / 1024**3, 1)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def responder(self, codigo, corpo, tipo="application/json"):
        dados = corpo if isinstance(corpo, bytes) else json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def host_valido(self):
        return self.headers.get("Host", "").split(":")[0] in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self.host_valido():
            return self.responder(403, {"erro": "host"})
        url = urlparse(self.path)
        if url.path == "/":
            return self.responder(200, PAGINA.replace("__TOKEN__", TOKEN).encode("utf-8"), "text/html")
        if self.headers.get("X-Token") != TOKEN:
            return self.responder(403, {"erro": "token"})
        if url.path == "/api/estado":
            with TRAVA:
                jobs = list(JOBS.values())
            return self.responder(200, {"itens": ler_indice(), "jobs": jobs, "livre_gb": livre_gb(), "pasta": str(ARQUIVO), "raizes": RAIZES_SUGERIDAS})
        if url.path == "/api/varrer":
            raiz = parse_qs(url.query).get("raiz", [""])[0]
            return self.responder(200, varrer(raiz) if raiz in RAIZES_SUGERIDAS else [])
        self.responder(404, {"erro": "nao encontrado"})

    def do_POST(self):
        if not self.host_valido() or self.headers.get("X-Token") != TOKEN:
            return self.responder(403, {"erro": "token"})
        corpo = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/compactar":
                caminho = validar_caminho(corpo["caminho"])
                return self.responder(200, iniciar(trabalho_compactar, caminho, bool(corpo.get("apagar", True))))
            item = next((i for i in ler_indice() if i["id"] == corpo.get("id")), None)
            if item is None:
                raise ValueError("Item nao encontrado.")
            if self.path == "/api/abrir":
                return self.responder(200, iniciar(trabalho_restaurar, item, True))
            if self.path == "/api/fechar":
                return self.responder(200, iniciar(trabalho_fechar, item))
            if self.path == "/api/explorer":
                if not item.get("aberto") or not Path(item["origem"]).is_dir():
                    raise ValueError("A pasta nao esta aberta.")
                os.startfile(item["origem"])
                return self.responder(200, {"ok": True})
            if self.path == "/api/restaurar":
                return self.responder(200, iniciar(trabalho_restaurar, item, bool(corpo.get("manter_zip", False))))
            if self.path == "/api/excluir":
                excluir_item(item)
                return self.responder(200, {"ok": True})
        except (ValueError, KeyError) as erro:
            return self.responder(400, {"erro": str(erro)})
        self.responder(404, {"erro": "nao encontrado"})


PAGINA = Path(__file__).with_name("index.html").read_text(encoding="utf-8")


def esperar(job):
    while job["ok"] is None:
        time.sleep(0.5)
    print(job["fase"], job["erro"] or "")
    return 0 if job["ok"] else 1


def cli(argumentos):
    comando = argumentos[0]
    indice = ler_indice()
    horas = float(argumentos[argumentos.index("--horas") + 1]) if "--horas" in argumentos else 2.0
    if comando == "listar":
        for item in indice:
            estado = "ABERTO" if item.get("aberto") else "zipado"
            print(f'{item["id"]} | {estado} | {item["nome"]} | {item["bytes_originais"] // 1048576} MB -> {item["bytes_zip"] // 1048576} MB | {item["origem"]}')
        return 0
    if comando == "compactar":
        return esperar(iniciar(trabalho_compactar, validar_caminho(argumentos[1]), "--manter" not in argumentos))
    if comando == "rotina":
        rotina(horas)
        return 0
    if comando == "instalar-rotina":
        return instalar_rotina(horas)
    if comando == "remover-rotina":
        return remover_rotina()
    if comando in ("restaurar", "abrir", "fechar"):
        alvo = argumentos[1].lower()
        achados = [i for i in indice if i["id"] == argumentos[1] or i["nome"].lower() == alvo]
        if len(achados) != 1:
            print("Nenhum item ou mais de um com esse nome; use o id de 'listar'.")
            return 1
        if comando == "fechar":
            return esperar(iniciar(trabalho_fechar, achados[0]))
        return esperar(iniciar(trabalho_restaurar, achados[0], comando == "abrir" or "--manter" in argumentos))
    print("Uso: arquivador.py [listar | abrir <nome|id> | fechar <nome|id> | compactar <caminho> [--manter] | restaurar <nome|id> | rotina [--horas N] | instalar-rotina [--horas N] | remover-rotina]")
    return 1


def main():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        sys.exit(cli(sys.argv[1:]))
    ARQUIVO.mkdir(parents=True, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    url = f"http://127.0.0.1:{PORTA}/"
    print(f"Arquivador em {url}  (Ctrl+C para sair)")
    if "--sem-navegador" not in sys.argv:
        webbrowser.open(url)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
