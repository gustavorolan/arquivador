import os
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arquivador as a

NAVEGADORES = [
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
]


def achar_navegador():
    return next((n for n in NAVEGADORES if n.is_file()), None)


def aguardar_tarefas():
    while any(job["ok"] is None for job in list(a.JOBS.values())):
        time.sleep(0.5)


def main():
    navegador = achar_navegador()
    if navegador is None:
        import arquivador_gui

        arquivador_gui.main()
        return
    a.ARQUIVO.mkdir(parents=True, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), a.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_address[1]}/"
    perfil = Path(os.environ.get("LOCALAPPDATA", str(a.HOME))) / "Arquivador" / "perfil"
    perfil.mkdir(parents=True, exist_ok=True)
    janela = subprocess.Popen([
        str(navegador), f"--app={url}", f"--user-data-dir={perfil}", "--window-size=1040,780",
        "--no-first-run", "--no-default-browser-check", "--disable-sync", "--disable-features=Translate,msImplicitSignin,msEdgeEnableNurturingFramework",
    ])
    janela.wait()
    aguardar_tarefas()
    servidor.shutdown()


if __name__ == "__main__":
    main()
