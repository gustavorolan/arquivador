import struct
import zlib
from pathlib import Path

TAMANHOS = [16, 24, 32, 48, 64, 128, 256]


def dentro(x, y, x0, y0, x1, y1, raio):
    cx = min(max(x, x0 + raio), x1 - raio)
    cy = min(max(y, y0 + raio), y1 - raio)
    return (x - cx) ** 2 + (y - cy) ** 2 <= raio * raio


def misturar(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def amostra(x, y):
    if not dentro(x, y, 0.03, 0.03, 0.97, 0.97, 0.22):
        return None
    cor = misturar((59, 130, 246), (30, 64, 175), (x + y) / 2)
    if dentro(x, y, 0.16, 0.2, 0.48, 0.42, 0.05):
        cor = (219, 234, 254)
    if dentro(x, y, 0.11, 0.3, 0.89, 0.8, 0.06):
        cor = (255, 255, 255)
        if y > 0.62:
            cor = misturar(cor, (219, 234, 254), (y - 0.62) / 0.18)
    if 0.465 <= x <= 0.535 and 0.3 <= y <= 0.8:
        cor = (219, 234, 254)
    for k in range(7):
        topo = 0.33 + k * 0.048
        if topo <= y < topo + 0.03:
            esquerda = 0.4 if k % 2 == 0 else 0.5
            if esquerda <= x <= esquerda + 0.1:
                cor = (37, 99, 235)
    if dentro(x, y, 0.445, 0.6, 0.555, 0.76, 0.03):
        cor = (30, 64, 175)
        if (x - 0.5) ** 2 + (y - 0.69) ** 2 <= 0.014**2:
            cor = (219, 234, 254)
    return cor


def desenhar(tamanho):
    sub = 4 if tamanho <= 64 else 3
    linhas = []
    for py in range(tamanho):
        linha = bytearray([0])
        for px in range(tamanho):
            r = g = b = a = 0
            for sy in range(sub):
                for sx in range(sub):
                    cor = amostra((px + (sx + 0.5) / sub) / tamanho, (py + (sy + 0.5) / sub) / tamanho)
                    if cor is not None:
                        r += cor[0]
                        g += cor[1]
                        b += cor[2]
                        a += 1
            total = sub * sub
            if a:
                linha += bytes([round(r / a), round(g / a), round(b / a), round(255 * a / total)])
            else:
                linha += bytes([0, 0, 0, 0])
        linhas.append(bytes(linha))
    return linhas


def png(tamanho):
    bruto = b"".join(desenhar(tamanho))

    def bloco(tipo, dados):
        corpo = tipo + dados
        return struct.pack(">I", len(dados)) + corpo + struct.pack(">I", zlib.crc32(corpo) & 0xFFFFFFFF)

    cabecalho = struct.pack(">IIBBBBB", tamanho, tamanho, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabecalho) + bloco(b"IDAT", zlib.compress(bruto, 9)) + bloco(b"IEND", b"")


def main():
    imagens = [(t, png(t)) for t in TAMANHOS]
    cabecalho = struct.pack("<HHH", 0, 1, len(imagens))
    deslocamento = 6 + 16 * len(imagens)
    entradas = b""
    dados = b""
    for tamanho, conteudo in imagens:
        lado = 0 if tamanho >= 256 else tamanho
        entradas += struct.pack("<BBBBHHII", lado, lado, 0, 0, 1, 32, len(conteudo), deslocamento + len(dados))
        dados += conteudo
    destino = Path(__file__).with_name("arquivador.ico")
    destino.write_bytes(cabecalho + entradas + dados)
    print(destino, destino.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
