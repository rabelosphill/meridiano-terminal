"""Registro de comandos: sintaxe, sinônimos PT/EN, exemplos, tipos de ativo compatíveis, permissões.

Formas:
  <VERBO> args...                      HELP, MARKETS, FIND, COMPARE, MACRO, WATCH, THESIS
  <TICKER> [BOLSA] <FUNÇÃO> [args]     PETR4 B3 FIN Q
"""
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .services import universe
from .services.universe import norm

EQUITY = ["equity_common", "equity_pref", "equity_unit", "adr", "etf"]
ALL = ["equity_common", "equity_pref", "adr", "etf", "index", "fx", "gov_bond", "corp_bond", "future", "option", "commodity", "rate"]


@dataclass
class Command:
    code: str
    title: str
    syntax: str
    synonyms: List[str]
    examples: List[str]
    description: str
    kinds: Optional[List[str]] = None       # None = comando global (sem ativo)
    permission: str = "view"
    field_group: str = "*"
    args: List[str] = field(default_factory=list)
    status: str = "ready"                   # ready | partial | planned


COMMANDS = [
    Command("HELP", "Ajuda", "HELP [termo]", ["AJUDA", "?", "H"], ["HELP", "HELP FIN"], "Catálogo pesquisável de funções e campos."),
    Command("MARKETS", "Monitor de mercados", "MARKETS <região...>", ["MERCADOS", "MKT", "MON"], ["MARKETS BR US"],
            "Monitor Brasil–EUA: ações, ADRs, índices, câmbio, juros e commodities com estado do feed.", field_group="quotes"),
    Command("FIND", "Busca", "FIND <texto>", ["BUSCAR", "PROCURAR", "SEARCH"], ["FIND PETROBRAS", "FIND APPLE"],
            "Resultados por empresa, instrumento e listagem (inclui tickers históricos)."),
    Command("OVERVIEW", "Visão geral", "<TICKER> [BOLSA] OVERVIEW", ["DES", "PERFIL", "RESUMO", "OV"], ["PETR4 B3 OVERVIEW", "AAPL NASDAQ OVERVIEW"],
            "Perfil, identificadores, listagens, ADRs, cobertura de dados e abas disponíveis.", kinds=ALL),
    Command("FIN", "Demonstrações financeiras", "<TICKER> [BOLSA] FIN [A|Q|LTM] [IS|BS|CF]", ["FA", "DEMONSTRACOES", "DFS", "FINANCIALS"],
            ["PETR4 B3 FIN Q", "AAPL NASDAQ FIN A", "VALE3 B3 FIN LTM CF"],
            "DRE, balanço e fluxo de caixa — anual, trimestral ou LTM — com proveniência por célula.", kinds=EQUITY, field_group="fundamentals",
            args=["freq", "statement"]),
    Command("FILINGS", "Documentos", "<TICKER> [BOLSA] FILINGS", ["DOCS", "DOCUMENTOS", "DOC"], ["AAPL NASDAQ FILINGS", "PETR4 B3 FILINGS"],
            "Documentos e divulgações (10-K/10-Q, DFP/ITR) com versão e instante de publicação.", kinds=EQUITY, field_group="documents"),
    Command("COMPARE", "Comparação", "COMPARE <TICKER:BOLSA> <TICKER:BOLSA>... [CCY=USD|BRL|NATIVE] [A|LTM]", ["COMPARAR", "COMP", "RV"],
            ["COMPARE PETR4:B3 VALE3:B3", "COMPARE PETR4:B3 AAPL:NASDAQ CCY=USD"],
            "Comparação com período e moeda explícitos; conversão por PTAX média (fluxos) e de fechamento (saldos).", field_group="fundamentals"),
    Command("MACRO", "Série macroeconômica", "MACRO <PAÍS> <SÉRIE>", ["ECO", "SERIE"], ["MACRO BR SELIC", "MACRO BR IPCA", "MACRO US UST10Y", "MACRO GLOBAL BRENT"],
            "Série com fonte, unidade, data de referência e de publicação; consulta 'como se sabia em D'.", field_group="macro"),
    Command("WATCH", "Watchlist", "WATCH <NOME> [+TICKER:BOLSA] [-TICKER:BOLSA]", ["LISTA", "MONITORAR", "W"], ["WATCH MINHA-MESA", "WATCH MINHA-MESA +VALE3:B3"],
            "Lista persistente do usuário.", field_group="quotes"),
    Command("THESIS", "Tese de investimento", "THESIS <TICKER:BOLSA>", ["TESE", "TH"], ["THESIS PETR4:B3"],
            "Tese, premissas, DCF versionado e histórico com autor e instante.", field_group="thesis"),
    Command("CHART", "Gráfico", "<TICKER> [BOLSA] CHART [intervalo] [janela]", ["GRAFICO", "GP", "GRAPH", "G"],
            ["PETR4 B3 CHART 1D 2Y", "VALE3 B3 CHART 1W 5Y", "PETR4 B3 CHART 5MIN 1D"],
            "Estação gráfica: candles/OHLC/linha/área, estudos, desenhos, eventos e alertas. 1º argumento = duração do candle; 2º = janela visível.",
            kinds=["equity_common", "equity_pref", "equity_unit", "adr", "etf", "index"], field_group="quotes", args=["interval", "window"]),
    Command("VALUE", "Valuation", "<TICKER> [BOLSA] VALUE", ["VALUATION", "VAL", "MULTIPLOS"], ["PETR4 B3 VALUE"],
            "Múltiplos, DCF, DCF reverso, cenários e matriz WACC × g, com a ponte EV → valor por ação.", kinds=EQUITY, field_group="fundamentals"),
    Command("PEERS", "Pares", "<TICKER> [BOLSA] PEERS", ["PARES", "RV", "COMP"], ["PETR4 B3 PEERS"],
            "Pares editáveis e comparação setorial.", kinds=EQUITY, field_group="fundamentals"),
    Command("EVENTS", "Eventos", "<TICKER> [BOLSA] EVENTS", ["EVENTOS", "EVT", "CORP"], ["PETR4 B3 EVENTS"],
            "Balanços, comunicados materiais, proventos e eventos corporativos, com instante de publicação e 1ª sessão negociável.", kinds=EQUITY, field_group="documents"),
    Command("NEWS", "Notícias", "NEWS <WORLD|BRIDGE|LIVE|BR|US|ASIA|EU|WATCH|TICKER:BOLSA>", ["NOTICIAS", "N", "TOP"],
            ["NEWS WORLD", "NEWS BRIDGE", "NEWS PETR4:B3"], "Central de notícias e comunicados primários, com fonte, tipo editorial e vínculo com ativos.", field_group="news"),
    Command("SCAN", "Rastreador", "SCAN BR [nome]", ["RASTREADOR", "SCREENER", "EQS"], ["SCAN BR"],
            "Rastreador técnico e fundamentalista com explicação por ativo e exclusões declaradas.", field_group="quotes"),
    Command("DCF", "Valuation DCF", "<TICKER> [BOLSA] DCF", ["VALUATION", "FCFF"], ["PETR4 B3 DCF"],
            "DCF de FCFF com matriz WACC×g, cenários e DCF reverso.", kinds=EQUITY, field_group="fundamentals"),
]
BY_CODE = {c.code: c for c in COMMANDS}
SYN = {}
for c in COMMANDS:
    SYN[c.code] = c.code
    for s in c.synonyms:
        SYN[s] = c.code
FREQ = {"A": "A", "ANUAL": "A", "Y": "A", "FY": "A", "Q": "Q", "T": "Q", "TRIM": "Q", "TRIMESTRAL": "Q",
        "LTM": "LTM", "TTM": "LTM", "U12M": "LTM", "12M": "LTM"}
STMT = {"IS": "IS", "DRE": "IS", "INCOME": "IS", "BS": "BS", "BP": "BS", "BALANCO": "BS", "BALANCE": "BS", "CF": "CF", "DFC": "CF", "CAIXA": "CF", "CASH": "CF"}
EXCH_ALIASES = {"B3": "B3", "BVMF": "B3", "BOVESPA": "B3", "NASDAQ": "NASDAQ", "XNAS": "NASDAQ", "NYSE": "NYSE", "XNYS": "NYSE", "US": None, "BR": None}
KIND_PT = {"equity_unit": "unit", "equity_common": "ação ordinária", "equity_pref": "ação preferencial", "adr": "ADR", "etf": "ETF", "index": "índice", "fx": "moeda",
           "gov_bond": "título soberano", "corp_bond": "título corporativo", "future": "futuro", "option": "opção", "commodity": "commodity", "rate": "taxa"}


def catalog() -> List[dict]:
    return [asdict(c) for c in COMMANDS]


def _err(msg: str, suggestions: List[str], code: str = "invalid") -> dict:
    return {"ok": False, "error": code, "message": msg, "suggestions": suggestions}


def _instrument(tok: str, exch: Optional[str] = None):
    if ":" in tok:
        tok, exch = tok.split(":", 1)
    exch_code = EXCH_ALIASES.get(exch.upper(), exch.upper()) if exch else None
    return universe.resolve(tok, exch_code), tok, exch_code


def parse(text: str) -> dict:
    raw = text.strip()
    toks = norm(raw).replace(",", " ").split()
    if not toks:
        return _err("Comando vazio.", ["HELP", "FIND PETROBRAS", "MARKETS BR US"], "empty")
    verb = SYN.get(toks[0])
    if verb in ("HELP",):
        return {"ok": True, "fn": "HELP", "args": {"q": " ".join(toks[1:])}}
    if verb == "MARKETS":
        return {"ok": True, "fn": "MARKETS", "args": {"regions": toks[1:] or ["BR", "US"]}}
    if verb == "FIND":
        if len(toks) < 2:
            return _err("FIND exige um termo de busca.", ["FIND PETROBRAS", "FIND APPLE"])
        return {"ok": True, "fn": "FIND", "args": {"q": " ".join(raw.split()[1:])}}
    if verb == "MACRO":
        if len(toks) < 3:
            return _err("MACRO exige país e série.", ["MACRO BR SELIC", "MACRO BR IPCA", "MACRO US UST10Y"])
        return {"ok": True, "fn": "MACRO", "args": {"code": f"{toks[1]}.{toks[2]}"}}
    if verb == "WATCH":
        if len(toks) < 2:
            return _err("WATCH exige o nome da lista.", ["WATCH MINHA-MESA"])
        return {"ok": True, "fn": "WATCH", "args": {"name": toks[1], "ops": toks[2:]}}
    if verb == "COMPARE":
        ins, opts = [], {"ccy": "NATIVE", "freq": "A"}
        for t in toks[1:]:
            if t.startswith("CCY="):
                opts["ccy"] = t[4:]
            elif t in FREQ:
                opts["freq"] = FREQ[t]
            else:
                r, tk, ex = _instrument(t)
                if not r:
                    return _err(f"Instrumento '{t}' não encontrado.", [f"FIND {tk}"], "not_found")
                if r["instrument"]["kind"] not in EQUITY or not r["issuer"]:
                    return _err(f"{tk} é {KIND_PT[r['instrument']['kind']]}; COMPARE de fundamentos exige emissor com demonstrações.",
                                ["COMPARE PETR4:B3 VALE3:B3", f"{tk} OVERVIEW"], "incompatible")
                ins.append({"ticker": r["listing"]["ticker"], "exchange": r["listing"]["exchange_code"], "instrument_id": str(r["instrument"]["id"]),
                            "issuer_id": str(r["issuer"]["id"])})
        if len(ins) < 2:
            return _err("COMPARE exige ao menos dois instrumentos (TICKER:BOLSA).", ["COMPARE PETR4:B3 VALE3:B3"])
        if opts["ccy"] not in ("NATIVE", "USD", "BRL"):
            return _err(f"Moeda {opts['ccy']} não suportada.", ["CCY=USD", "CCY=BRL", "CCY=NATIVE"])
        return {"ok": True, "fn": "COMPARE", "args": {"instruments": ins, **opts}}
    if verb == "NEWS":
        arg = toks[1] if len(toks) > 1 else "WORLD"
        tabs = {"WORLD": "top", "TOP": "top", "PRINCIPAIS": "top", "LIVE": "live", "AOVIVO": "live", "BR": "br", "US": "us", "EUA": "us",
                "ASIA": "asia", "EU": "eu", "EUROPA": "eu", "BRIDGE": "bridge", "PONTE": "bridge", "WATCH": "watchlist", "WATCHLIST": "watchlist",
                "PORTFOLIO": "portfolio", "CARTEIRA": "portfolio"}
        if arg in tabs:
            return {"ok": True, "fn": "NEWS", "args": {"tab": tabs[arg]}}
        r, tk, ex = _instrument(arg, toks[2] if len(toks) > 2 else None)
        if not r:
            return _err(f"'{arg}' não é aba de notícias nem instrumento.", ["NEWS WORLD", "NEWS BRIDGE", "NEWS PETR4:B3"], "not_found")
        return {"ok": True, "fn": "NEWS", "args": {"tab": "ticker", "ticker": r["listing"]["ticker"]}, **_ctx(r)}
    if verb == "SCAN":
        return {"ok": True, "fn": "SCAN", "args": {"market": toks[1] if len(toks) > 1 else "BR", "name": " ".join(toks[2:]) or None}}
    if verb == "THESIS":
        if len(toks) < 2:
            return _err("THESIS exige TICKER:BOLSA.", ["THESIS PETR4:B3"])
        r, tk, ex = _instrument(toks[1], toks[2] if len(toks) > 2 else None)
        if not r:
            return _err(f"'{tk}' não encontrado.", [f"FIND {tk}"], "not_found")
        return {"ok": True, "fn": "THESIS", **_ctx(r)}
    # forma <TICKER> [BOLSA] <FUNÇÃO>
    tk = toks[0]
    rest = toks[1:]
    exch = None
    if ":" in tk:
        tk, exch = tk.split(":", 1)
    elif rest and rest[0] in EXCH_ALIASES:
        exch = rest[0]
        rest = rest[1:]
    r, _, exch_code = _instrument(tk, exch)
    if not r:
        cands = universe.find(tk)["listings"][:3]
        return _err(f"'{tk}' não é comando nem instrumento conhecido.", [f"{c['ticker']} {c['exchange'] or ''} OVERVIEW".replace("  ", " ") for c in cands]
                    + [f"FIND {tk}", "HELP"], "not_found")
    fn = SYN.get(rest[0]) if rest else "OVERVIEW"
    if fn is None or fn not in BY_CODE:
        return _err(f"Função '{rest[0]}' desconhecida.", [f"{tk} OVERVIEW", f"{tk} FIN A", "HELP"], "unknown_function")
    cmd = BY_CODE[fn]
    kind = r["instrument"]["kind"]
    if cmd.kinds is not None and kind not in cmd.kinds:
        alt = {"fx": ["MACRO BR PTAX", "MARKETS BR US"], "index": ["MARKETS BR US"], "commodity": ["MACRO GLOBAL BRENT"],
               "gov_bond": ["MACRO US UST10Y"], "future": [f"{tk} OVERVIEW"], "option": [f"{tk} OVERVIEW"]}.get(kind, [])
        why = ("sem série OHLCV de fonte autorizada carregada para esse tipo de ativo" if fn == "CHART"
               else "sem emissor com demonstrações financeiras")
        return _err(f"{fn} não se aplica a {tk}: é {KIND_PT.get(kind, kind)}, {why}.",
                    [f"{tk} OVERVIEW"] + alt, "incompatible")
    args: dict = {}
    if fn == "CHART":
        INTERVALS = {"1MIN": "1m", "5MIN": "5m", "1D": "1D", "D": "1D", "1W": "1W", "W": "1W", "1S": "1W", "1MO": "1M", "MO": "1M"}
        WINDOWS = {"1D", "5D", "1M", "3M", "6M", "YTD", "1Y", "2Y", "5Y", "MAX", "1A", "2A", "5A"}
        rest_args = rest[1:]
        args["interval"], args["window"] = "1D", "2Y"
        if len(rest_args) >= 1:
            a0 = rest_args[0]
            if len(rest_args) == 1 and a0 in WINDOWS and a0 not in ("1D", "1M"):
                args["window"] = a0.replace("A", "Y")
            elif a0 in INTERVALS or a0 == "1M":
                args["interval"] = INTERVALS.get(a0, "1M")
            else:
                return _err(f"Intervalo '{a0}' inválido. Use 1MIN, 5MIN, 1D, 1W ou 1M (1º argumento = duração do candle).",
                            [f"{tk} CHART 1D 2Y", f"{tk} CHART 1W 5Y"], "invalid")
        if len(rest_args) >= 2:
            w = rest_args[1].replace("A", "Y") if rest_args[1].endswith("A") else rest_args[1]
            if w not in WINDOWS and w.replace("Y", "A") not in WINDOWS:
                return _err(f"Janela '{rest_args[1]}' inválida (2º argumento = janela visível).", [f"{tk} CHART 1D 2Y", f"{tk} CHART 1D YTD"], "invalid")
            args["window"] = w
        if args["interval"] in ("1m", "5m") and args["window"] not in ("1D", "5D"):
            args["window"] = "1D"
    if fn == "FIN":
        args["freq"], args["statement"] = "A", "IS"
        for t in rest[1:]:
            if t in FREQ:
                args["freq"] = FREQ[t]
            elif t in STMT:
                args["statement"] = STMT[t]
            else:
                return _err(f"Argumento '{t}' inválido para FIN.", [f"{tk} FIN A", f"{tk} FIN Q", f"{tk} FIN LTM CF"])
        if kind == "adr":
            args["note"] = "ADR: demonstrações do emissor subjacente"
    res = {"ok": True, "fn": fn, "args": args, **_ctx(r)}
    if r.get("renamed_to"):
        res["notice"] = f"{tk} é ticker histórico; instrumento hoje negocia como {r['renamed_to']['ticker']}."
    return res


def _ctx(r: dict) -> dict:
    return {"instrument_id": str(r["instrument"]["id"]), "listing_id": str(r["listing"]["id"]), "ticker": r["listing"]["ticker"],
            "exchange": r["listing"]["exchange_code"], "issuer_id": str(r["issuer"]["id"]) if r["issuer"] else None, "kind": r["instrument"]["kind"]}
