"""Modelos de demonstrações e mapeamento de campos padronizados.

US-GAAP (SEC): template fixo com lista de tags candidatas (primeira disponível vence).
CVM: plano de contas oficial (CD_CONTA). Contas ST_CONTA_FIXA='N' são livres por empresa e
podem trocar de código entre documentos — por isso o casamento usa código + rótulo.
"""
import re
from typing import Dict, List

# sign: +1 mantém, -1 inverte (convenção do sistema: despesas e saídas de caixa negativas)
SEC_TEMPLATE: Dict[str, List[dict]] = {
    "IS": [
        {"key": "revenue", "label": "Receita líquida", "en": "Net sales", "tags": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]},
        {"key": "cogs", "label": "Custo dos produtos e serviços", "en": "Cost of sales", "tags": ["CostOfGoodsAndServicesSold", "CostOfRevenue"], "sign": -1},
        {"key": "gross_profit", "label": "Lucro bruto", "en": "Gross margin", "tags": ["GrossProfit"], "bold": True},
        {"key": "rnd", "label": "Pesquisa e desenvolvimento", "en": "R&D", "tags": ["ResearchAndDevelopmentExpense"], "sign": -1, "indent": 1},
        {"key": "sga", "label": "Vendas, gerais e administrativas", "en": "SG&A", "tags": ["SellingGeneralAndAdministrativeExpense"], "sign": -1, "indent": 1},
        {"key": "opex", "label": "Despesas operacionais", "en": "Operating expenses", "tags": ["OperatingExpenses"], "sign": -1},
        {"key": "ebit", "label": "Resultado operacional", "en": "Operating income", "tags": ["OperatingIncomeLoss"], "bold": True},
        {"key": "other_income", "label": "Outras receitas/(despesas)", "en": "Other income/(expense), net", "tags": ["NonoperatingIncomeExpense"]},
        {"key": "pretax", "label": "Lucro antes de impostos", "en": "Income before taxes", "tags": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]},
        {"key": "tax", "label": "Imposto de renda", "en": "Provision for income taxes", "tags": ["IncomeTaxExpenseBenefit"], "sign": -1},
        {"key": "net_income", "label": "Lucro líquido", "en": "Net income", "tags": ["NetIncomeLoss"], "bold": True},
        {"key": "net_income_parent", "label": "Lucro atribuível aos controladores", "en": "Net income to parent", "tags": ["NetIncomeLoss"], "hidden": True},
        {"key": "eps_basic", "label": "LPA básico", "en": "EPS basic", "tags": ["EarningsPerShareBasic"], "unit": "USD/sh"},
        {"key": "eps_diluted", "label": "LPA diluído", "en": "EPS diluted", "tags": ["EarningsPerShareDiluted"], "unit": "USD/sh"},
        {"key": "shares_basic", "label": "Ações médias — básico", "en": "Shares basic", "tags": ["WeightedAverageNumberOfSharesOutstandingBasic"], "unit": "shares"},
        {"key": "shares_diluted", "label": "Ações médias — diluído", "en": "Shares diluted", "tags": ["WeightedAverageNumberOfDilutedSharesOutstanding"], "unit": "shares"},
    ],
    "BS": [
        {"key": "cash", "label": "Caixa e equivalentes", "en": "Cash and cash equivalents", "tags": ["CashAndCashEquivalentsAtCarryingValue"]},
        {"key": "st_investments", "label": "Títulos negociáveis — CP", "en": "Current marketable securities", "tags": ["MarketableSecuritiesCurrent"]},
        {"key": "receivables", "label": "Contas a receber", "en": "Accounts receivable, net", "tags": ["AccountsReceivableNetCurrent"]},
        {"key": "inventory", "label": "Estoques", "en": "Inventories", "tags": ["InventoryNet"]},
        {"key": "current_assets", "label": "Ativo circulante", "en": "Total current assets", "tags": ["AssetsCurrent"], "bold": True},
        {"key": "lt_investments", "label": "Títulos negociáveis — LP", "en": "Non-current marketable securities", "tags": ["MarketableSecuritiesNoncurrent"]},
        {"key": "ppe", "label": "Imobilizado líquido", "en": "Property, plant and equipment, net", "tags": ["PropertyPlantAndEquipmentNet"]},
        {"key": "total_assets", "label": "Ativo total", "en": "Total assets", "tags": ["Assets"], "bold": True},
        {"key": "payables", "label": "Fornecedores", "en": "Accounts payable", "tags": ["AccountsPayableCurrent"]},
        {"key": "commercial_paper", "label": "Commercial paper", "en": "Commercial paper", "tags": ["CommercialPaper"]},
        {"key": "debt_current", "label": "Dívida de longo prazo — parcela CP", "en": "Term debt, current", "tags": ["LongTermDebtCurrent"]},
        {"key": "current_liabilities", "label": "Passivo circulante", "en": "Total current liabilities", "tags": ["LiabilitiesCurrent"], "bold": True},
        {"key": "debt_noncurrent", "label": "Dívida de longo prazo", "en": "Term debt, non-current", "tags": ["LongTermDebtNoncurrent"]},
        {"key": "total_liabilities", "label": "Passivo total", "en": "Total liabilities", "tags": ["Liabilities"], "bold": True},
        {"key": "equity", "label": "Patrimônio líquido", "en": "Total shareholders' equity", "tags": ["StockholdersEquity"], "bold": True},
        {"key": "deferred_tax_liab", "label": "Passivo fiscal diferido (nota de IR)", "en": "Deferred tax liabilities (note)", "tags": ["DeferredIncomeTaxLiabilities"], "note": True},
        {"key": "shares_outstanding", "label": "Ações em circulação", "en": "Shares outstanding", "tags": ["CommonStockSharesOutstanding"], "unit": "shares"},
    ],
    "CF": [
        {"key": "cf_net_income", "label": "Lucro líquido", "en": "Net income", "tags": ["NetIncomeLoss"]},
        {"key": "da", "label": "Depreciação e amortização", "en": "Depreciation and amortization", "tags": ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet"], "indent": 1},
        {"key": "sbc", "label": "Remuneração em ações", "en": "Share-based compensation", "tags": ["ShareBasedCompensation"], "indent": 1},
        {"key": "chg_other_liab", "label": "Variação — outros passivos operacionais", "en": "Other current and non-current liabilities", "tags": ["IncreaseDecreaseInOtherOperatingLiabilities"], "indent": 1},
        {"key": "cfo", "label": "Caixa das operações", "en": "Cash generated by operating activities", "tags": ["NetCashProvidedByUsedInOperatingActivities"], "bold": True},
        {"key": "capex", "label": "Capex (aquisição de imobilizado)", "en": "Payments for PP&E", "tags": ["PaymentsToAcquirePropertyPlantAndEquipment"], "sign": -1},
        {"key": "cfi", "label": "Caixa de investimentos", "en": "Cash used in investing activities", "tags": ["NetCashProvidedByUsedInInvestingActivities"], "bold": True},
        {"key": "dividends_paid", "label": "Dividendos pagos", "en": "Payments for dividends", "tags": ["PaymentsOfDividends"], "sign": -1},
        {"key": "buybacks", "label": "Recompra de ações", "en": "Repurchases of common stock", "tags": ["PaymentsForRepurchaseOfCommonStock"], "sign": -1},
        {"key": "cff", "label": "Caixa de financiamentos", "en": "Cash used in financing activities", "tags": ["NetCashProvidedByUsedInFinancingActivities"], "bold": True},
    ],
}

SEC_TAG_STATEMENT = {t: st for st, lines in SEC_TEMPLATE.items() for ln in lines for t in ln["tags"]}

# Campos padronizados para CVM: código fixo (ST_CONTA_FIXA='S') ou regra por rótulo (contas livres).
CVM_STANDARD = {
    "revenue": {"code": "3.01"}, "cogs": {"code": "3.02"}, "gross_profit": {"code": "3.03"},
    "ebit": {"code": "3.05"}, "pretax": {"code": "3.07"}, "tax": {"code": "3.08"},
    "net_income": {"code": "3.11"}, "net_income_parent": {"code": "3.11.01"},
    "cash": {"code": "1.01.01"}, "total_assets": {"code": "1"}, "current_assets": {"code": "1.01"},
    "current_liabilities": {"code": "2.01"}, "equity": {"code": "2.03"},
    "debt_current": {"code": "2.01.04"}, "debt_noncurrent": {"code": "2.02.01"},
    "cfo": {"code": "6.01"}, "cfi": {"code": "6.02"}, "cff": {"code": "6.03"},
    "capex": {"parent": "6.02", "label_re": r"(aquisi\w*\s+de\s+ativos?\s+imobilizad|adi[cç][oõ]es\s+(ao|de)\s+imobilizad)"},
    "da": {"parent": "6.01", "label_re": r"deprecia"},
}
CVM_STATEMENT_BY_PREFIX = {"1": "BS", "2": "BS", "3": "IS", "6": "CF"}

# Campos que são saldos (instantâneos): jamais somar períodos para formar um saldo.
INSTANT_KEYS = {"cash", "st_investments", "receivables", "inventory", "current_assets", "lt_investments", "ppe", "total_assets",
                "payables", "commercial_paper", "debt_current", "current_liabilities", "debt_noncurrent", "total_liabilities",
                "equity", "deferred_tax_liab", "shares_outstanding", "total_debt", "net_debt"}

# Pacotes setoriais: métricas priorizadas e o que falta para habilitá-las
SECTOR_PACKS = {
    "oil_gas": {"label": "Óleo e gás", "priority": [
        ("production_boed", "Produção (mil boe/d)", "Relatório de produção trimestral (não estruturado na CVM) — requer conector de RI"),
        ("realized_price", "Preço de realização (USD/bbl)", "Relatório de desempenho trimestral — requer conector de RI"),
        ("lifting_cost", "Custo de extração (USD/boe)", "Relatório de desempenho — requer conector de RI"),
        ("capex", "Capex", None), ("cfo", "Caixa das operações", None), ("net_debt", "Dívida líquida", None)]},
    "mining": {"label": "Mineração", "priority": [
        ("iron_ore_shipments", "Vendas de minério (Mt)", "Relatório de produção e vendas — requer conector de RI"),
        ("c1_cost", "Custo C1 (USD/t)", "Relatório de desempenho — requer conector de RI"),
        ("capex", "Capex", None), ("ebit_margin", "Margem operacional", None), ("net_debt", "Dívida líquida", None)]},
    "software": {"label": "Software / plataformas", "priority": [
        ("recurring_revenue", "Receita recorrente", "Divulgada por segmento (Services) — requer tags dimensionais XBRL"),
        ("net_retention", "Retenção líquida", "Não divulgada pelo emissor"),
        ("dilution", "Diluição (ações diluídas a/a)", None), ("fcf", "Fluxo de caixa livre", None), ("gross_margin", "Margem bruta", None)]},
    "banks": {"label": "Bancos", "priority": [
        ("nii", "Margem financeira", "Plano COSIF/IFRS 9 — template bancário a carregar"), ("cost_of_risk", "Custo de crédito", "idem"),
        ("cet1", "Capital principal (CET1)", "Pilar 3 — requer conector"), ("roe", "ROE", None)]},
    "insurance": {"label": "Seguros", "priority": [("combined_ratio", "Índice combinado", "SUSEP/notas — requer conector"), ("roe", "ROE", None)]},
    "retail": {"label": "Varejo", "priority": [("sss", "Vendas mesmas lojas", "Release — requer conector de RI"), ("gross_margin", "Margem bruta", None)]},
    "utilities": {"label": "Utilities", "priority": [("rab", "Base de remuneração regulatória", "ANEEL — requer conector"), ("net_debt", "Dívida líquida", None)]},
    "real_estate": {"label": "Imobiliário", "priority": [("vso", "VSO", "Release — requer conector de RI"), ("net_debt", "Dívida líquida", None)]},
    "generic": {"label": "Genérico", "priority": [("ebit_margin", "Margem operacional", None)]},
}


def cvm_match(std: dict, code: str, label: str) -> bool:
    if "code" in std:
        return code == std["code"]
    if not code.startswith(std["parent"] + "."):   # qualquer descendente; o chamador usa a 1ª ocorrência (menor profundidade)
        return False
    return re.search(std["label_re"], label, re.I) is not None
