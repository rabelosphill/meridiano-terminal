-- 001: universo financeiro. Chave persistente = UUID do instrumento/emissor.
-- Ticker vive em `listing` com vigência; identificadores do provedor em `identifier`.
-- gen_random_uuid() é nativo no PostgreSQL >= 13

CREATE TABLE legal_entity (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  country     char(2) NOT NULL,
  tax_id      text,                       -- CNPJ, EIN...
  lei         text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE issuer (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  legal_entity_id  uuid NOT NULL REFERENCES legal_entity(id),
  name             text NOT NULL,
  short_name       text NOT NULL,
  sector_pack      text NOT NULL DEFAULT 'generic',  -- banks, insurance, oil_gas, mining, software, retail, utilities, real_estate
  fiscal_year_end  char(4),                          -- MMDD
  reporting_std    text,                             -- IFRS / US-GAAP
  description      text,
  status           text NOT NULL DEFAULT 'active',  -- active, merged, delisted
  successor_id     uuid REFERENCES issuer(id)        -- fusão / incorporação
);

CREATE TABLE calendar (
  id    text PRIMARY KEY,                -- BVMF, XNYS
  name  text NOT NULL
);
CREATE TABLE calendar_holiday (
  calendar_id text REFERENCES calendar(id),
  day         date NOT NULL,
  name        text NOT NULL,
  PRIMARY KEY (calendar_id, day)
);

CREATE TABLE exchange (
  mic          text PRIMARY KEY,         -- BVMF, XNAS, XNYS
  code         text NOT NULL UNIQUE,     -- B3, NASDAQ, NYSE (código de comando)
  name         text NOT NULL,
  country      char(2) NOT NULL,
  timezone     text NOT NULL,
  calendar_id  text NOT NULL REFERENCES calendar(id),
  open_local   time NOT NULL,
  close_local  time NOT NULL
);

CREATE TABLE currency (
  code   char(3) PRIMARY KEY,
  name   text NOT NULL,
  minor  smallint NOT NULL DEFAULT 2
);

-- kind: equity_common, equity_pref, adr, etf, index, fx, gov_bond, corp_bond, future, option, commodity, rate
CREATE TABLE instrument (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer_id              uuid REFERENCES issuer(id),
  kind                   text NOT NULL,
  class_name             text,                      -- ON, PN, Common, ADS...
  name                   text NOT NULL,
  currency               char(3) REFERENCES currency(code),
  underlying_id          uuid REFERENCES instrument(id),
  -- derivativos / renda fixa: multiplier, expiry, strike, option_type, exercise, day_count, coupon...
  attrs                  jsonb NOT NULL DEFAULT '{}'::jsonb,
  status                 text NOT NULL DEFAULT 'active',
  CHECK (kind IN ('equity_common','equity_pref','adr','etf','index','fx','gov_bond','corp_bond','future','option','commodity','rate'))
);

CREATE TABLE listing (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  instrument_id  uuid NOT NULL REFERENCES instrument(id),
  exchange_mic   text REFERENCES exchange(mic),     -- NULL p/ OTC, FX, séries
  ticker         text NOT NULL,
  currency       char(3) REFERENCES currency(code),
  valid_from     date NOT NULL,
  valid_to       date,                              -- NULL = vigente
  status         text NOT NULL DEFAULT 'active'     -- active, renamed, delisted, moved
);
CREATE INDEX listing_ticker_idx ON listing (upper(ticker));

CREATE TABLE identifier (
  id           bigserial PRIMARY KEY,
  object_type  text NOT NULL,                       -- legal_entity, issuer, instrument, listing
  object_id    uuid NOT NULL,
  scheme       text NOT NULL,                       -- SEC_CIK, CVM_CODE, CNPJ, ISIN, FIGI, BCB_SGS
  value        text NOT NULL,
  valid_from   date,
  valid_to     date,
  source       text NOT NULL,
  UNIQUE (scheme, value, object_type, valid_from)
);

-- ADR: razão versionada com vigência
CREATE TABLE adr_terms (
  id                bigserial PRIMARY KEY,
  adr_id            uuid NOT NULL REFERENCES instrument(id),
  underlying_id     uuid NOT NULL REFERENCES instrument(id),
  adr_units         numeric NOT NULL CHECK (adr_units > 0),          -- 1 ADS =
  underlying_units  numeric NOT NULL CHECK (underlying_units > 0),   -- N ações subjacentes
  valid_from        date NOT NULL,
  valid_to          date,
  source            text NOT NULL
);

-- eventos corporativos (split, dividendos, troca de ticker, fusão)
CREATE TABLE corporate_action (
  id             bigserial PRIMARY KEY,
  instrument_id  uuid NOT NULL REFERENCES instrument(id),
  kind           text NOT NULL,                   -- split, cash_dividend, ticker_change, merger, delisting
  ex_date        date NOT NULL,
  ratio          numeric,                         -- split: novas/antigas
  amount         numeric,                         -- dividendo por ação
  currency       char(3),
  detail         jsonb NOT NULL DEFAULT '{}'::jsonb,
  source         text NOT NULL,
  UNIQUE (instrument_id, kind, ex_date)
);
