CREATE TABLE IF NOT EXISTS public.flo_momentum_scan (
  name text PRIMARY KEY CHECK (name = 'latest'),
  payload jsonb NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
  is_public boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.flo_momentum_scan ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.flo_momentum_scan FROM anon, authenticated;
GRANT SELECT ON public.flo_momentum_scan TO anon, authenticated;
DROP POLICY IF EXISTS flo_momentum_public_read ON public.flo_momentum_scan;
CREATE POLICY flo_momentum_public_read ON public.flo_momentum_scan
FOR SELECT TO anon, authenticated USING (is_public = true);
-- Never enable public read without market-data vendor redistribution rights.
