# -*- coding: utf-8 -*-
"""Extrae plazo, vigencia y garantía de TODOS los documentos de un proceso y detecta contradicciones
entre ellos (p. ej. TDR dice 10 días y el proyecto de orden de compra dice 5)."""
import re

PALABRAS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8,
            "nueve": 9, "diez": 10, "quince": 15, "veinte": 20, "treinta": 30, "sesenta": 60, "noventa": 90, "doce": 12}
NUM = r"(?:(\d{1,3})|(" + "|".join(PALABRAS) + r"))"
# número con posible forma duplicada: "diez (10)", "30 (treinta)", "(10)"
NUMERO = r"(?:[a-záéíóú]+\s*)?\(?\s*" + NUM + r"\s*\)?\s*(?:\([a-záéíóú ]+\)\s*)?"

PAT = {
    "plazo": re.compile(r"(?:plazo\s+(?:estimado\s+|m[aá]ximo\s+|total\s+)?(?:de|para)\s+(?:la\s+|el\s+)?(?:ejecuci[oó]n|entrega|prestaci[oó]n)[^.;]{0,160}?(?:es de|ser[aá] de|de|es|:|m[aá]ximo de|estimado[^.;]{0,40}? de)|plazo\s+de|plazo\s+m[aá]ximo\s+de)\s*" + NUMERO +
                        r"(d[ií]as?|semanas?|horas?)\s*(calendario|laborables|h[aá]biles|h[aá]bil)?", re.I),
    "vigencia": re.compile(r"vigencia(?:(?!vigencia|garant)[^.;\d]){0,160}?(?:de|:|m[ií]nima de|m[ií]nimo de)\s*" +
                           NUMERO + r"(d[ií]as?|meses)", re.I),
    "garantia": re.compile(r"garant[ií]a[^.;]{0,160}?(?:de|ser[aá] de|por|:|m[ií]nima de|al menos)\s*" + NUMERO + r"(meses|a[nñ]os?)", re.I),
}


def _valor(m):
    return int(m.group(1)) if m.group(1) else PALABRAS[m.group(2).lower()]


def _plano(t):
    return re.sub(r"\s+", " ", t).strip()


def _contexto(t, m, antes=40, despues=140):
    return t[max(0, m.start() - antes): min(len(t), m.end() + despues)].strip()


def extraer(corpus):
    """corpus: [(fuente, pagina, texto)]. Devuelve {campo: [candidatos]} con valor normalizado, unidad, fuente y cita."""
    res = {"plazo": [], "vigencia": [], "garantia": []}
    for fuente, pag, texto in corpus:
        if texto.startswith("["):
            continue
        t = _plano(texto)
        for campo, rx in PAT.items():
            for m in rx.finditer(t):
                cita = _contexto(t, m)
                if campo == "vigencia" and re.search(r"garant|orden de compra|contrato", t[max(0, m.start() - 60): m.start()], re.I):
                    continue  # vigencia de la garantía/contrato, no de la oferta
                if campo == "plazo" and re.search(r"adicional|correctiv|reposici[oó]n|repuesto", t[max(0, m.start() - 160): m.start()], re.I):
                    continue  # plazo de un servicio adicional, no el de ejecución principal
                if campo == "plazo" and re.search(r"notificaci[oó]n formal", t[m.end(): m.end() + 80], re.I):
                    continue
                if campo == "plazo" and re.search(r"peticion|petici[oó]n|solicitud escrita|requerimiento", t[m.end(): m.end() + 90], re.I):
                    continue  # plazo de respuesta a una petición, no plazo de ejecución
                if re.search(r"COMPLETAR|COLOCAR|\(n[uú]mero|XXXX", m.group(0), re.I):
                    continue
                unidad = m.group(3).lower()
                tipo = (m.group(4) or "").lower() if campo == "plazo" else ""
                v = _valor(m)
                dias = v * (30 if unidad.startswith("mes") else 365 if unidad.startswith("a") else 7 if unidad.startswith("sem") else 1)
                res[campo].append({"valor": v, "unidad": unidad, "tipo": tipo, "dias": dias,
                                   "fuente": fuente.split(" [")[0], "pagina": pag, "cita": cita})
    return res


def resolver(cands):
    """Elige el valor y reporta contradicciones. plazo -> el MENOR (más exigente); vigencia/garantía -> el MAYOR."""
    out = {}
    for campo, lista in cands.items():
        if not lista:
            out[campo] = None
            continue
        distintos = sorted({c["dias"] for c in lista})
        elegir = min if campo == "plazo" else max
        elegido = elegir(lista, key=lambda c: c["dias"])
        out[campo] = {"elegido": elegido, "contradiccion": len(distintos) > 1, "candidatos": lista}
    return out
