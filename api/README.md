start api by:

```bash
    uvicorn api.main:app --reload
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
    python scripts/refresh_cache.py --owner egovernments --repo DIGIT-OSS
```