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
    python scripts/test_api.py
    # or specify owner/repo
    python ../scripts/test_api.py --owner egovernments --repo digit-oss
    # check the docs for more options
```

To load something into the cache database:

```bash
    python ../scripts/refresh_cache.py --owner egovernments --repo DIGIT-OSS
```