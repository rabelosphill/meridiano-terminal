"""Dados de referência do universo (cadastro). Idempotente.

Fatos reais aqui: CNPJ/CIK/códigos CVM, razões de ADR (PBR 1:2 ON, PBR.A 1:2 PN, VALE 1:1),
splits da Apple (7:1 em 2014-06-09, 4:1 em 2020-08-31), troca FB->META em 2022-06-09.
Feriados 2026 da B3 e da NYSE conforme calendários publicados pelas bolsas.
"""
import json

from .db import tx

SOURCES = [
    ("SEC_EDGAR", "SEC EDGAR (submissions, XBRL companyfacts, Archives)", "https://www.sec.gov/edgar", "Domínio público (17 CFR 200.80); fair access 10 req/s", "eod", "Divulgação por filing; sem atraso adicional", 8),
    ("CVM_DADOS", "CVM Dados Abertos — DFP/ITR", "https://dados.cvm.gov.br", "Licença ODbL (Dados Abertos CVM)", "eod", "Arquivos atualizados semanalmente pela CVM", 2),
    ("BCB_SGS", "Banco Central do Brasil — SGS", "https://api.bcb.gov.br", "Dados abertos BCB", "eod", "Publicação diária; PTAX após 13h BRT", 2),
    ("FRED", "FRED — Federal Reserve Bank of St. Louis", "https://fred.stlouisfed.org", "Uso conforme termos FRED; séries de terceiros (EIA, Treasury)", "eod", "Brent EIA com defasagem de dias", 2),
    ("B3_COTAHIST", "B3 — Séries Históricas de cotações (COTAHIST)", "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/series-historicas/",
     "Arquivo público da B3; uso analítico interno — redistribuição comercial requer licença de market data B3", "eod", "Publicado após o fechamento (D+0 noite)", 1),
    ("TIINGO", "Tiingo — EOD EUA (requer chave)", "https://www.tiingo.com", "Licença Tiingo (uso conforme plano contratado)", "eod", "Fim de dia", 1),
    ("FED_PRESS", "Federal Reserve — press releases", "https://www.federalreserve.gov/feeds/feeds.htm", "Domínio público (governo dos EUA)", "realtime", "RSS oficial", 1),
    ("SIM_DEV", "Feed simulado de desenvolvimento (NÃO É DADO DE MERCADO)", "local://sim", "Fictício — apenas ambiente dev/test", "simulated", "Gerado localmente", None),
    ("USER", "Estimativa do usuário", "local://user", "Privado do usuário", "snapshot", None, None),
    ("SYSTEM", "Cálculo do sistema (biblioteca determinística)", "local://calc", "Derivado", "snapshot", None, None),
]

CALENDARS = {
    "BVMF": ("B3 — pregão", ["2026-01-01 Confraternização", "2026-02-16 Carnaval", "2026-02-17 Carnaval", "2026-04-03 Paixão de Cristo",
                            "2026-04-21 Tiradentes", "2026-05-01 Dia do Trabalho", "2026-06-04 Corpus Christi", "2026-09-07 Independência",
                            "2026-10-12 N. Sra. Aparecida", "2026-11-02 Finados", "2026-11-20 Consciência Negra", "2026-12-24 Véspera de Natal",
                            "2026-12-25 Natal", "2026-12-31 Último dia útil"]),
    "XNYS": ("NYSE/Nasdaq — regular session", ["2026-01-01 New Year's Day", "2026-01-19 MLK Day", "2026-02-16 Washington's Birthday",
                                              "2026-04-03 Good Friday", "2026-05-25 Memorial Day", "2026-06-19 Juneteenth",
                                              "2026-07-03 Independence Day (observed)", "2026-09-07 Labor Day", "2026-11-26 Thanksgiving",
                                              "2026-12-25 Christmas"]),
}

EXCHANGES = [
    ("BVMF", "B3", "B3 S.A. — Brasil, Bolsa, Balcão", "BR", "America/Sao_Paulo", "BVMF", "10:00", "17:00"),
    ("XNAS", "NASDAQ", "Nasdaq Stock Market", "US", "America/New_York", "XNYS", "09:30", "16:00"),
    ("XNYS", "NYSE", "New York Stock Exchange", "US", "America/New_York", "XNYS", "09:30", "16:00"),
]

CURRENCIES = [("BRL", "Real brasileiro"), ("USD", "Dólar americano"), ("EUR", "Euro")]

# (chave, entidade, país, tax_id, emissor, curto, setor, fye, padrão, descrição)
ISSUERS = [
    ("petrobras", "Petróleo Brasileiro S.A. — Petrobras", "BR", "33.000.167/0001-01", "PETROLEO BRASILEIRO S.A. PETROBRAS", "Petrobras",
     "oil_gas", "1231", "IFRS", "Empresa integrada de energia: exploração e produção, refino, gás e energia. Controlada pela União."),
    ("vale", "Vale S.A.", "BR", "33.592.510/0001-54", "VALE S.A.", "Vale", "mining", "1231", "IFRS",
     "Mineradora: minério de ferro, pelotas, níquel e cobre."),
    ("apple", "Apple Inc.", "US", "94-2404110", "Apple Inc.", "Apple", "software", "0930", "US-GAAP",
     "Hardware, software e serviços: iPhone, Mac, iPad, wearables e Services."),
    ("meta", "Meta Platforms, Inc.", "US", "20-1665019", "Meta Platforms, Inc.", "Meta", "software", "1231", "US-GAAP",
     "Exemplo de troca de ticker (FB → META em 2022-06-09). Sem fundamentos carregados."),
]

# (chave, emissor, kind, classe, nome, moeda, subjacente, attrs)
INSTRUMENTS = [
    ("petr3", "petrobras", "equity_common", "ON", "Petrobras ON", "BRL", None, {}),
    ("petr4", "petrobras", "equity_pref", "PN", "Petrobras PN", "BRL", None, {}),
    ("pbr", "petrobras", "adr", "ADS (ON)", "Petrobras ADS — ações ON", "USD", "petr3", {"level": 3, "depositary": "JPMorgan Chase Bank"}),
    ("pbra", "petrobras", "adr", "ADS (PN)", "Petrobras ADS — ações PN", "USD", "petr4", {"level": 3, "depositary": "JPMorgan Chase Bank"}),
    ("vale3", "vale", "equity_common", "ON", "Vale ON", "BRL", None, {}),
    ("vale_adr", "vale", "adr", "ADS (ON)", "Vale ADS", "USD", "vale3", {"level": 3}),
    ("aapl", "apple", "equity_common", "Common", "Apple Inc. Common Stock", "USD", None, {}),
    ("meta", "meta", "equity_common", "Class A", "Meta Platforms Class A", "USD", None, {}),
    ("ibov", None, "index", None, "Índice Bovespa", "BRL", None, {"provider": "B3", "composition": "carteira teórica quadrimestral"}),
    ("spx", None, "index", None, "S&P 500", "USD", None, {"provider": "S&P DJI"}),
    ("usdbrl", None, "fx", None, "USD/BRL", "BRL", None, {"base": "USD", "quote": "BRL", "convention": "BRL por 1 USD"}),
    ("brent", None, "commodity", None, "Petróleo Brent (spot, Europe)", "USD", None, {"unit": "USD/bbl"}),
    ("ust10", None, "gov_bond", None, "U.S. Treasury 10Y (constant maturity)", "USD", None,
     {"day_count": "ACT/ACT", "coupon_freq": 2, "quote": "yield, % a.a.", "note": "série CMT; não é um título específico"}),
    ("di1f27", None, "future", None, "DI1F27 — DI de 1 dia, jan/2027", "BRL", None,
     {"multiplier": 100000, "expiry": "2027-01-04", "quote": "taxa % a.a. base 252", "settlement": "financeira", "unit": "PU"}),
    ("aapl_c250", None, "option", None, "AAPL 2026-12-18 C 250", "USD", "aapl",
     {"multiplier": 100, "expiry": "2026-12-18", "strike": 250, "option_type": "call", "exercise": "american"}),
]

# (instrumento, bolsa, ticker, moeda, de, até, status)
LISTINGS = [
    ("petr3", "BVMF", "PETR3", "BRL", "1968-01-02", None, "active"),
    ("petr4", "BVMF", "PETR4", "BRL", "1968-01-02", None, "active"),
    ("pbr", "XNYS", "PBR", "USD", "2000-08-10", None, "active"),
    ("pbra", "XNYS", "PBR.A", "USD", "2001-02-21", None, "active"),
    ("vale3", "BVMF", "VALE3", "BRL", "1970-01-02", None, "active"),
    ("vale_adr", "XNYS", "VALE", "USD", "2002-06-20", None, "active"),
    ("aapl", "XNAS", "AAPL", "USD", "1980-12-12", None, "active"),
    ("meta", "XNAS", "FB", "USD", "2012-05-18", "2022-06-08", "renamed"),
    ("meta", "XNAS", "META", "USD", "2022-06-09", None, "active"),
    ("ibov", "BVMF", "IBOV", "BRL", "1968-01-02", None, "active"),
    ("spx", None, "SPX", "USD", "1957-03-04", None, "active"),
    ("usdbrl", None, "USDBRL", "BRL", "1994-07-01", None, "active"),
    ("brent", None, "BRENT", "USD", "1987-05-20", None, "active"),
    ("ust10", None, "UST10Y", "USD", "1962-01-02", None, "active"),
    ("di1f27", "BVMF", "DI1F27", "BRL", "2021-01-04", "2027-01-04", "active"),
    ("aapl_c250", None, "AAPL261218C00250000", "USD", "2025-01-01", "2026-12-18", "active"),
]

IDENTIFIERS = [
    ("issuer", "petrobras", "CVM_CODE", "009512"), ("issuer", "petrobras", "CNPJ", "33.000.167/0001-01"),
    ("issuer", "petrobras", "SEC_CIK", "0001119639"),
    ("issuer", "vale", "CVM_CODE", "004170"), ("issuer", "vale", "SEC_CIK", "0000917851"), ("issuer", "vale", "CNPJ", "33.592.510/0001-54"),
    ("issuer", "apple", "SEC_CIK", "0000320193"), ("issuer", "meta", "SEC_CIK", "0001326801"),
    ("instrument", "petr4", "ISIN", "BRPETRACNPR6"), ("instrument", "petr3", "ISIN", "BRPETRACNOR9"),
    ("instrument", "vale3", "ISIN", "BRVALEACNOR0"), ("instrument", "aapl", "ISIN", "US0378331005"),
    ("instrument", "pbr", "ISIN", "US71654V4086"), ("instrument", "pbra", "ISIN", "US71654V1017"),
    ("instrument", "vale_adr", "ISIN", "US91912E1055"),
    ("instrument", "usdbrl", "BCB_SGS", "1"), ("instrument", "brent", "FRED", "DCOILBRENTEU"), ("instrument", "ust10", "FRED", "DGS10"),
]

ADR_TERMS = [("pbr", "petr3", 1, 2, "2000-08-10"), ("pbra", "petr4", 1, 2, "2001-02-21"), ("vale_adr", "vale3", 1, 1, "2002-06-20")]

CORP_ACTIONS = [
    ("aapl", "split", "2014-06-09", 7, None, None, {"note": "7-for-1"}),
    ("aapl", "split", "2020-08-31", 4, None, None, {"note": "4-for-1"}),
    ("meta", "ticker_change", "2022-06-09", None, None, None, {"from": "FB", "to": "META"}),
]

MACRO = [
    ("BR.SELIC", "BCB_SGS", "432", "Meta Selic definida pelo Copom", "% a.a.", "daily", "BR", "Série SGS 432. Valor vigente em cada dia."),
    ("BR.IPCA", "BCB_SGS", "433", "IPCA — variação mensal", "% a.m.", "monthly", "BR", "Série SGS 433 (IBGE via BCB). Data = mês de referência."),
    ("BR.PTAX", "BCB_SGS", "1", "Dólar comercial (venda) — PTAX", "BRL por USD", "daily", "BR", "Série SGS 1. Fechamento PTAX."),
    ("GLOBAL.BRENT", "FRED", "DCOILBRENTEU", "Brent — Europe spot FOB", "USD/bbl", "daily", None, "Fonte primária: U.S. EIA, via FRED."),
    ("US.UST10Y", "FRED", "DGS10", "Treasury 10Y constant maturity", "% a.a.", "daily", "US", "Fonte primária: U.S. Treasury/Federal Reserve H.15, via FRED."),
]

USERS = [("ana", "Ana Lima", "analyst"), ("paulo", "Paulo Reis", "pm"), ("bia", "Bia Souza", "advisor"), ("admin", "Admin", "admin")]
# (usuário, feed, campo, ver, exportar)
ENTITLEMENTS = [
    ("ana", "*", "*", True, False), ("ana", "SEC_EDGAR", "fundamentals", True, True), ("ana", "CVM_DADOS", "fundamentals", True, True),
    ("ana", "BCB_SGS", "macro", True, True),
    ("paulo", "*", "*", True, True),
    ("bia", "*", "*", True, False), ("bia", "BCB_SGS", "macro", True, True), ("bia", "SIM_DEV", "quotes", False, False),
    ("admin", "*", "*", True, True),
]

PRECEDENCE = [("fundamentals.BR", 1, "CVM_DADOS"), ("fundamentals.US", 1, "SEC_EDGAR"), ("fx.USDBRL", 1, "BCB_SGS"), ("fx.USDBRL", 2, "SIM_DEV")]


def seed() -> dict:
    ids: dict = {}
    with tx() as c:
        for s in SOURCES:
            c.execute("""INSERT INTO source(code,name,url,license,feed_class,delay_note,rate_limit_per_s) VALUES (%s,%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (code) DO NOTHING""", s)
        for code, name in CURRENCIES:
            c.execute("INSERT INTO currency(code,name) VALUES (%s,%s) ON CONFLICT DO NOTHING", (code, name))
        for cid, (name, hols) in CALENDARS.items():
            c.execute("INSERT INTO calendar(id,name) VALUES (%s,%s) ON CONFLICT DO NOTHING", (cid, name))
            for h in hols:
                d, n = h.split(" ", 1)
                c.execute("INSERT INTO calendar_holiday VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (cid, d, n))
        for e in EXCHANGES:
            c.execute("INSERT INTO exchange VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", e)
        for key, ent, country, tax, iname, short, sector, fye, std, desc in ISSUERS:
            r = c.execute("SELECT i.id FROM issuer i JOIN legal_entity l ON l.id=i.legal_entity_id WHERE l.tax_id=%s", (tax,)).fetchone()
            if r:
                ids[key] = r["id"]
                continue
            le = c.execute("INSERT INTO legal_entity(name,country,tax_id) VALUES (%s,%s,%s) RETURNING id", (ent, country, tax)).fetchone()["id"]
            ids[key] = c.execute("""INSERT INTO issuer(legal_entity_id,name,short_name,sector_pack,fiscal_year_end,reporting_std,description)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (le, iname, short, sector, fye, std, desc)).fetchone()["id"]
        for key, iss, kind, cls, name, ccy, und, attrs in INSTRUMENTS:
            r = c.execute("SELECT id FROM instrument WHERE name=%s", (name,)).fetchone()
            if r:
                ids[key] = r["id"]
                continue
            ids[key] = c.execute("""INSERT INTO instrument(issuer_id,kind,class_name,name,currency,underlying_id,attrs)
                                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                                 (ids.get(iss) if iss else None, kind, cls, name, ccy, ids.get(und) if und else None, json.dumps(attrs))).fetchone()["id"]
        for ins, mic, tk, ccy, vf, vt, st in LISTINGS:
            if not c.execute("SELECT 1 FROM listing WHERE instrument_id=%s AND ticker=%s", (ids[ins], tk)).fetchone():
                c.execute("INSERT INTO listing(instrument_id,exchange_mic,ticker,currency,valid_from,valid_to,status) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                          (ids[ins], mic, tk, ccy, vf, vt, st))
        for ot, key, scheme, val in IDENTIFIERS:
            c.execute("""INSERT INTO identifier(object_type,object_id,scheme,value,valid_from,source) VALUES (%s,%s,%s,%s,'1900-01-01','seed')
                         ON CONFLICT DO NOTHING""", (ot, ids[key], scheme, val))
        for adr, und, a, u, vf in ADR_TERMS:
            if not c.execute("SELECT 1 FROM adr_terms WHERE adr_id=%s", (ids[adr],)).fetchone():
                c.execute("INSERT INTO adr_terms(adr_id,underlying_id,adr_units,underlying_units,valid_from,source) VALUES (%s,%s,%s,%s,%s,'Form F-6 / depositário')",
                          (ids[adr], ids[und], a, u, vf))
        for ins, kind, d, ratio, amt, ccy, det in CORP_ACTIONS:
            c.execute("""INSERT INTO corporate_action(instrument_id,kind,ex_date,ratio,amount,currency,detail,source) VALUES (%s,%s,%s,%s,%s,%s,%s,'seed')
                         ON CONFLICT DO NOTHING""", (ids[ins], kind, d, ratio, amt, ccy, json.dumps(det)))
        for code, src, key, name, unit, freq, country, notes in MACRO:
            c.execute("""INSERT INTO macro_series(code,source,source_key,name,unit,frequency,country,notes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                         ON CONFLICT (code) DO NOTHING""", (code, src, key, name, unit, freq, country, notes))
        for u in USERS:
            c.execute("INSERT INTO app_user VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", u)
        for e in ENTITLEMENTS:
            c.execute("INSERT INTO entitlement VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", e)
        for p in PRECEDENCE:
            c.execute("INSERT INTO field_precedence VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", p)
    return ids
