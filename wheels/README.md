# wheels/ — drop the SDK wheel here

`ameba-ai-sdk` is not published on PyPI. Download the wheel from your
Amebaran doc-hub **Downloads** page (ask your operator for the hub address)
and place it in this folder before running the app:

```
wheels/ameba_ai_sdk-0.3.0-py3-none-any.whl
```

The app resolves the SDK from this exact path (see `pyproject.toml` /
`requirements.txt`). When you download a newer wheel,
update the version in those files to match.
