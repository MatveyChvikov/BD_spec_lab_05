-- wrk: каталог с кэшем (LAB 05)
-- Сравнение с холодным/без кэша:
--   wrk -t4 -c100 -d30s -s loadtest/wrk/catalog.lua http://localhost:8082
-- Замените в локальной копии wrk.path на ...?use_cache=false для второго замера.

wrk.method = "GET"
wrk.path = "/api/cache-demo/catalog?use_cache=true"
