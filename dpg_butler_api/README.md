start api by:

```bash
    # from repo root (recommended)
    cd ..
    poetry -C dpg_butler_api install
    poetry -C dpg_butler_api run python -m uvicorn dpg_butler_api.main:app --reload

    # or, if you want to run it while your cwd is dpg_butler_api/
    poetry run python -m uvicorn dpg_butler_api.main:app --reload --app-dir ..
```

.env should speicify API_KEY variable.

You can test the api by:

```bash
    # cached/read-only API smoke test
    poetry run python ../scripts/test_cached_api.py --owner egovernments --repo DIGIT-OSS

    # ad hoc repo scan flow
    poetry run python ../scripts/test_repo_scan_api.py --owner egovernments --repo DIGIT-OSS

    # wait for ad hoc scan completion with visible polling output
    poetry run python ../scripts/test_repo_scan_api.py --owner egovernments --repo DIGIT-OSS --wait-for-scan
```

To load something into the cache database:

```bash
    python ../scripts/refresh_cache.py --owner egovernments --repo DIGIT-OSS
```
