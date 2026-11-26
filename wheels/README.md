# wheels/ — drop the SDK wheel here

`ameba-ai-sdk` is not published on PyPI. Sign in to the Console, open **Docs**
from the user menu, and download the wheel from the **Downloads** page. Put it
in this folder before running the app:

```
wheels/ameba_ai_sdk-0.4.3-py3-none-any.whl
```

The app installs the SDK from this exact path (`pyproject.toml`,
`[tool.uv.sources]`). If you download a newer version, change the filename
there to match.
