-- 002: fontes, documentos originais, fatos bitemporais, séries macro, ingestão.

CREATE TABLE source (
  code        text PRIMARY KEY,                 -- SEC_EDGAR, CVM_DADOS, BCB_SGS, FRED, SIM_DEV
  name        text NOT NULL,
  url         text NOT NULL,
  license     text NOT NULL,
  feed_class  text NOT NULL CHECK (feed_class IN ('realtime','delayed','eod','snapshot','unavailable','simulated')),
  delay_note  text,
  rate_limit_per_s numeric
);

-- payload bruto exatamente como recebido (objeto em storage, conteúdo endereçado por sha256)
CREATE TABLE raw_payload (
  id           bigserial PRIMARY KEY,
  source       text NOT NULL REFERENCES source(code),
  request      text NOT NULL,                   -- URL ou caminho do snapshot
  object_key   text NOT NULL,
  sha256       char(64) NOT NULL,
  bytes        bigint NOT NULL,
  fetched_at   timestamptz NOT NULL,
  mode         text NOT NULL CHECK (mode IN ('live','snapshot','test')),
  UNIQUE (source, sha256)
);

CREATE TABLE document (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  issuer_id     uuid NOT NULL REFERENCES issuer(id),
  source        text NOT NULL REFERENCES source(code),
  external_id   text NOT NULL,                  -- accession number (SEC) / ID_DOC (CVM)
  form          text NOT NULL,                  -- 10-K, 10-Q, DFP, ITR
  period_end    date,
  fiscal_year   int,
  fiscal_period text,
  version       int NOT NULL DEFAULT 1,
  published_at  timestamptz NOT NULL,           -- instante de divulgação
  url           text NOT NULL,                  -- documento original no regulador
  object_key    text,                           -- cópia do original (se baixada)
  content_type  text,
  sha256        char(64),
  raw_payload_id bigint REFERENCES raw_payload(id),
  meta          jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source, external_id)
);

-- Fato bitemporal: período de referência (period_*) x instante de conhecimento (published_at).
-- Uma reapresentação é uma nova linha com published_at posterior; nada é sobrescrito.
CREATE TABLE fact (
  id             bigserial PRIMARY KEY,
  issuer_id      uuid NOT NULL REFERENCES issuer(id),
  source         text NOT NULL REFERENCES source(code),
  concept        text NOT NULL,                 -- tag XBRL ou CD_CONTA
  label          text NOT NULL,
  statement      text NOT NULL CHECK (statement IN ('IS','BS','CF','OTHER')),
  scope          text NOT NULL CHECK (scope IN ('consolidated','individual')),
  period_type    text NOT NULL CHECK (period_type IN ('duration','instant')),
  period_start   date,
  period_end     date NOT NULL,
  fiscal_year    int,
  fiscal_period  text,                          -- FY, Q1..Q4, 9M...
  value          numeric,                       -- NULL = ausente (diferente de zero)
  unit           text NOT NULL,                 -- USD, BRL, shares, USD/shares
  currency       char(3),
  scale          int NOT NULL DEFAULT 0,        -- valor armazenado em unidades; scale = escala exibida no documento (3=mil, 6=milhão)
  basis          text NOT NULL DEFAULT 'reported' CHECK (basis IN ('reported','issuer_adjusted','calculated','user_estimate')),
  document_id    uuid REFERENCES document(id),
  location       jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {ix_id, file, line, cd_conta, ordem_exerc}
  published_at   timestamptz NOT NULL,
  ingested_at    timestamptz NOT NULL DEFAULT now(),
  doc_version    int NOT NULL DEFAULT 1,
  raw_payload_id bigint REFERENCES raw_payload(id),
  natural_key    text NOT NULL,                 -- idempotência: fonte+conceito+período+escopo+documento+versão
  UNIQUE (natural_key)
);
CREATE INDEX fact_lookup_idx ON fact (issuer_id, statement, scope, concept, period_end, published_at);

CREATE TABLE macro_series (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code        text NOT NULL UNIQUE,             -- BR.SELIC, BR.IPCA, BR.PTAX, US.UST10Y, GLOBAL.BRENT
  source      text NOT NULL REFERENCES source(code),
  source_key  text NOT NULL,                    -- SGS 432 / FRED DGS10
  name        text NOT NULL,
  unit        text NOT NULL,
  frequency   text NOT NULL,
  country     char(2),
  notes       text
);

CREATE TABLE macro_observation (
  id            bigserial PRIMARY KEY,
  series_id     uuid NOT NULL REFERENCES macro_series(id),
  obs_date      date NOT NULL,                  -- data de referência
  value         numeric,
  published_at  timestamptz NOT NULL,           -- quando ficou disponível (ou instante da coleta, se a fonte não informa)
  ingested_at   timestamptz NOT NULL DEFAULT now(),
  vintage       int NOT NULL DEFAULT 1,
  raw_payload_id bigint REFERENCES raw_payload(id),
  UNIQUE (series_id, obs_date, vintage)
);

CREATE TABLE ingestion_run (
  id          bigserial PRIMARY KEY,
  connector   text NOT NULL,
  mode        text NOT NULL,
  started_at  timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  status      text NOT NULL DEFAULT 'running',
  stats       jsonb NOT NULL DEFAULT '{}'::jsonb,
  error       text
);

CREATE TABLE quarantine (
  id          bigserial PRIMARY KEY,
  run_id      bigint REFERENCES ingestion_run(id),
  connector   text NOT NULL,
  record      jsonb NOT NULL,
  reason      text NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  replayed_at timestamptz
);

-- precedência explícita por campo quando duas fontes divergem
CREATE TABLE field_precedence (
  field     text NOT NULL,
  rank      int NOT NULL,
  source    text NOT NULL REFERENCES source(code),
  PRIMARY KEY (field, rank)
);

-- última cotação válida por listagem (o feed nunca apaga a anterior em falha)
CREATE TABLE quote_last (
  listing_id   uuid PRIMARY KEY REFERENCES listing(id),
  price        numeric NOT NULL,
  prev_close   numeric,
  observed_at  timestamptz NOT NULL,             -- hora original da observação
  received_at  timestamptz NOT NULL,
  source       text NOT NULL REFERENCES source(code),
  feed_class   text NOT NULL
);
