-- 003: usuários, permissões por feed/campo/exportação, workspace, watchlists, teses.

CREATE TABLE app_user (
  id        text PRIMARY KEY,                   -- login
  name      text NOT NULL,
  role      text NOT NULL                       -- analyst, pm, advisor, admin
);

-- permissões: feed (fonte) x campo (grupo de campos) x ação
CREATE TABLE entitlement (
  user_id   text NOT NULL REFERENCES app_user(id),
  feed      text NOT NULL,                      -- código da fonte ou '*'
  field     text NOT NULL,                      -- fundamentals, quotes, macro, documents, thesis ou '*'
  can_view  boolean NOT NULL DEFAULT true,
  can_export boolean NOT NULL DEFAULT false,
  PRIMARY KEY (user_id, feed, field)
);

CREATE TABLE workspace_state (
  user_id     text NOT NULL REFERENCES app_user(id),
  workspace   text NOT NULL,
  scope_key   text NOT NULL,                    -- layout | panel:<id> | fn:<instrument>:<function>
  state       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, workspace, scope_key)
);

CREATE TABLE watchlist (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id   text NOT NULL REFERENCES app_user(id),
  name      text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, name)
);
CREATE TABLE watchlist_item (
  watchlist_id  uuid NOT NULL REFERENCES watchlist(id) ON DELETE CASCADE,
  instrument_id uuid NOT NULL REFERENCES instrument(id),
  listing_id    uuid REFERENCES listing(id),
  position      int NOT NULL,
  PRIMARY KEY (watchlist_id, instrument_id)
);

CREATE TABLE peer_group (
  user_id        text NOT NULL REFERENCES app_user(id),
  instrument_id  uuid NOT NULL REFERENCES instrument(id),
  members        uuid[] NOT NULL,
  updated_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, instrument_id)
);

CREATE TABLE thesis (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        text NOT NULL REFERENCES app_user(id),
  instrument_id  uuid NOT NULL REFERENCES instrument(id),
  title          text NOT NULL,
  stance         text NOT NULL DEFAULT 'neutral',  -- long, short, neutral
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, instrument_id)
);
-- histórico imutável: cada salvamento é uma versão com autor e instante
CREATE TABLE thesis_version (
  id           bigserial PRIMARY KEY,
  thesis_id    uuid NOT NULL REFERENCES thesis(id) ON DELETE CASCADE,
  version      int NOT NULL,
  author       text NOT NULL REFERENCES app_user(id),
  created_at   timestamptz NOT NULL DEFAULT now(),
  body         text NOT NULL,
  assumptions  jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{key,label,value,unit,source}]
  dcf          jsonb,                              -- premissas + resultado + versão da biblioteca
  context      jsonb NOT NULL DEFAULT '{}'::jsonb, -- ponto exato: função, célula, rolagem
  UNIQUE (thesis_id, version)
);

CREATE TABLE audit_log (
  id         bigserial PRIMARY KEY,
  user_id    text,
  action     text NOT NULL,
  detail     jsonb NOT NULL DEFAULT '{}'::jsonb,
  allowed    boolean NOT NULL,
  at         timestamptz NOT NULL DEFAULT now()
);
