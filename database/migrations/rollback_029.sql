-- ROLLBACK 029_business_channels.sql
-- Story: XCL-HIGH-1.1 — Schema foundation
-- Date: 2026-04-22
--
-- ============================================================
-- ⚠️  WARNING: PRE-CHECK OBRIGATÓRIO ANTES DE ROLLBACK ⚠️
-- ============================================================
--
-- Após XCL-HIGH-1.2 (refactor `_resolve_business` para ler de business_channels),
-- ou após XCL-HIGH-1.3 (UI self-service permitir criação de canais via owner),
-- rollback isolado QUEBRA prod.
--
-- ANTES de rodar este script, executar:
--
--   SELECT COUNT(*) AS non_qatest_channels
--   FROM business_channels
--   WHERE business_id NOT IN (
--       SELECT id FROM businesses WHERE slug = 'qatest-cleaning-co'
--   );
--
-- INTERPRETAÇÃO:
--   - 0 rows  → SAFE para rollback (apenas backfill qatest existe; rollback drop limpo)
--   - >0 rows → NÃO ROLLBACK AUTOMATICAMENTE
--               Outros businesses configuraram canais via UI (HIGH-1.3 deployed).
--               Coordenar com @devops antes:
--                 1. Snapshot dump de business_channels
--                 2. Comunicar owners afetados (canal vai parar de funcionar)
--                 3. Plano de re-config pós-rollback
--                 4. Apenas então prosseguir
--
-- O rollback usa CASCADE pois business_channels não tem dependências de saída
-- (só recebe FK de business_id). CASCADE só removerá referências futuras
-- introduzidas em 1.2/1.3 — confirma que ainda não há.
--
-- ============================================================

BEGIN;

DROP TABLE IF EXISTS business_channels CASCADE;

COMMIT;
