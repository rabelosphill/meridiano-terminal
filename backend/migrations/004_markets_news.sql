-- 004: barras OHLCV brutas, notícias/comunicados com histórias, alertas, desenhos, layouts e consultas salvas.

ALTER TABLE instrument DROP CONSTRAINT IF EXISTS instrument_kind_check;
ALTER TABLE instrument ADD CONSTRAINT instrument_kind_check CHECK (kind IN
  ('equity_common','equity_pref','equity_unit','adr','etf','index','fx','gov_bond','corp_bond','future','option','commodity','rate'));

-- Barras como negociadas (NÃO ajustadas). Ajustes vêm de corporate_action, aplicados na leitura.
CREATE TABLE price_bar (
  listing_id   uuid NOT NULL REFERENCES listing(id),
  interval     text NOT NULL,                  -- 1d | 1m (intradiário)
  ts           timestamptz NOT NULL,           -- início da barra em UTC (diária: abertura da sessão local)
  session_date date NOT NULL,                  -- data da sessão no fuso da bolsa
  open numeric NOT NULL, high numeric NOT NULL, low numeric NOT NULL, close numeric NOT NULL,
  volume       numeric,                        -- quantidade de ações
  fin_volume   numeric,                        -- volume financeiro na moeda da listagem
  trades       int,
  vwap         numeric,                        -- preço médio da sessão calculado pela bolsa sobre negócios individuais (B3 PREMED)
  source       text NOT NULL REFERENCES source(code),
  raw_payload_id bigint REFERENCES raw_payload(id),
  location     jsonb NOT NULL DEFAULT '{}'::jsonb,
  ingested_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (listing_id, interval, ts, source)
);
CREATE INDEX price_bar_date_idx ON price_bar (interval, session_date);

-- Notícia / comunicado. Sem texto integral de terceiros sem licença: guardamos metadados e link.
CREATE TABLE story (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title       text NOT NULL,
  first_at    timestamptz NOT NULL,
  last_at     timestamptz NOT NULL
);
CREATE TABLE news_item (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source         text NOT NULL REFERENCES source(code),   -- quem distribuiu para nós
  outlet         text NOT NULL,                            -- veículo/emissor original
  distributor    text NOT NULL,
  external_id    text NOT NULL,
  url            text NOT NULL,
  lang           char(2) NOT NULL,
  kind           text NOT NULL CHECK (kind IN ('official_release','regulatory_filing','central_bank','report','analysis','opinion','unconfirmed')),
  headline       text NOT NULL,
  summary        text,
  published_at   timestamptz NOT NULL,
  time_precision text NOT NULL DEFAULT 'second',           -- second | day
  updated_at     timestamptz,
  ingested_at    timestamptz NOT NULL DEFAULT now(),
  version        int NOT NULL DEFAULT 1,
  status         text NOT NULL DEFAULT 'published',        -- published | corrected | retracted
  story_id       uuid REFERENCES story(id),
  region         text[] NOT NULL DEFAULT '{}',             -- BR, US, ASIA, EU, GLOBAL
  topics         text[] NOT NULL DEFAULT '{}',
  material       boolean NOT NULL DEFAULT false,
  license        text NOT NULL,
  translation_allowed boolean NOT NULL DEFAULT false,
  raw_payload_id bigint REFERENCES raw_payload(id),
  meta           jsonb NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (source, external_id, version)
);
CREATE INDEX news_pub_idx ON news_item (published_at DESC);

-- vínculo notícia ↔ instrumento/emissor, com natureza da relação (direta, setorial, macro)
CREATE TABLE news_link (
  news_id        uuid NOT NULL REFERENCES news_item(id) ON DELETE CASCADE,
  issuer_id      uuid REFERENCES issuer(id),
  instrument_id  uuid REFERENCES instrument(id),
  relation       text NOT NULL CHECK (relation IN ('direct','sector','macro')),
  rationale      text,
  UNIQUE (news_id, issuer_id, instrument_id)
);

CREATE TABLE alert_rule (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL REFERENCES app_user(id),
  listing_id    uuid NOT NULL REFERENCES listing(id),
  kind          text NOT NULL,          -- price_cross, ma_cross, rsi_level, rel_volume, breakout_high, breakout_low
  params        jsonb NOT NULL,
  mode          text NOT NULL CHECK (mode IN ('intrabar','close')),
  dedupe        text NOT NULL CHECK (dedupe IN ('once','once_per_bar','every')),
  condition_text text NOT NULL,
  active        boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE alert_event (
  id         bigserial PRIMARY KEY,
  rule_id    uuid NOT NULL REFERENCES alert_rule(id) ON DELETE CASCADE,
  bar_ts     timestamptz NOT NULL,
  fired_at   timestamptz NOT NULL DEFAULT now(),
  value      jsonb NOT NULL,
  UNIQUE (rule_id, bar_ts)
);

-- desenhos por usuário × instrumento × base de preço
CREATE TABLE drawing (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       text NOT NULL REFERENCES app_user(id),
  instrument_id uuid NOT NULL REFERENCES instrument(id),
  price_basis   text NOT NULL,          -- raw | adjusted
  kind          text NOT NULL,          -- trend, hline, channel, rect, fib, measure, note
  points        jsonb NOT NULL,         -- [{t: ISO, p: preço}] na base indicada
  style         jsonb NOT NULL DEFAULT '{}'::jsonb,
  text          text,
  locked        boolean NOT NULL DEFAULT false,
  hidden        boolean NOT NULL DEFAULT false,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE saved_layout (
  user_id    text NOT NULL REFERENCES app_user(id),
  name       text NOT NULL,
  state      jsonb NOT NULL,             -- painéis + comando + gráfico (ativo, intervalo, janela, estudos, benchmark)
  builtin    boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, name)
);

CREATE TABLE scan_query (
  user_id    text NOT NULL REFERENCES app_user(id),
  name       text NOT NULL,
  spec       jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, name)
);
