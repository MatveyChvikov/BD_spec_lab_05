-- wrk: тот же сценарий, что catalog.lua, но без чтения из Redis (use_cache=false).
-- Сравните RPS/latency с catalog.lua после прогрева кэша (сначала несколько секунд catalog.lua).

wrk.method = "GET"
wrk.path = "/api/cache-demo/catalog?use_cache=false"
