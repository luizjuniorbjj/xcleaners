-- Sprint 100% Cleanup — Fase 0 PRE-FLIGHT (READ-ONLY)
-- Data: 2026-04-17
-- Objetivo: confirmar UUIDs + contagens exatas antes do DELETE
\timing off
\pset format aligned

\echo '=== 0.1 xcleaners-demo business ==='
SELECT id, slug, name FROM businesses WHERE slug = 'xcleaners-demo';

\echo '=== 0.2 REVALIDATE business ==='
SELECT id, slug, name, created_at FROM businesses
 WHERE id = '10271d87-85e1-40b8-8e87-8921cc3500b8';

\echo '=== 0.3 REVALIDATE user ==='
SELECT id, email, created_at FROM users
 WHERE id = 'd9897899-ab37-4a4c-8952-07fb204a7a21';

\echo '=== 0.4 Contagens por tabela (escopo que sera afetado) ==='
SELECT 'services'  AS entity, COUNT(*) AS count FROM cleaning_services  WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100-MANUAL]%'
UNION ALL SELECT 'extras',   COUNT(*) FROM cleaning_extras   WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100%'
UNION ALL SELECT 'teams',    COUNT(*) FROM cleaning_teams    WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND name LIKE '[S100-REVALIDATE]%'
UNION ALL SELECT 'clients',  COUNT(*) FROM cleaning_clients  WHERE business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND (first_name LIKE '[S100%' OR last_name LIKE '[S100%')
UNION ALL SELECT 'roles',    COUNT(*) FROM cleaning_user_roles WHERE business_id = '10271d87-85e1-40b8-8e87-8921cc3500b8';

\echo '=== 0.5 FK check - bookings referenciando entidades alvo (ZERO esperado) ==='
SELECT COUNT(*) AS bookings_affected FROM cleaning_bookings
 WHERE team_id = '4b315d01-ab5f-48c4-b362-133caed81226'
    OR client_id = '8cc74525-7182-4615-b9d7-851f62f1431b'
    OR business_id = '10271d87-85e1-40b8-8e87-8921cc3500b8';

\echo '=== 0.6 FK check - team_members (ZERO esperado) ==='
SELECT COUNT(*) AS team_members_affected FROM cleaning_team_members
 WHERE team_id = '4b315d01-ab5f-48c4-b362-133caed81226';

\echo '=== 0.7 FK check - booking_extras transitivos (ZERO esperado) ==='
SELECT COUNT(*) AS booking_extras_affected FROM cleaning_booking_extras be
  JOIN cleaning_extras e ON be.extra_id = e.id
 WHERE e.business_id = 'ef4dcb08-4461-4e55-a593-76ae42295924' AND e.name LIKE '[S100%';

\echo '=== 0.8 User tem roles em outros businesses? (ZERO esperado) ==='
SELECT r.business_id, b.slug, r.role
  FROM cleaning_user_roles r
  LEFT JOIN businesses b ON r.business_id = b.id
 WHERE r.user_id = 'd9897899-ab37-4a4c-8952-07fb204a7a21'
   AND r.business_id != '10271d87-85e1-40b8-8e87-8921cc3500b8';

\echo '=== PRE-FLIGHT DONE ==='
