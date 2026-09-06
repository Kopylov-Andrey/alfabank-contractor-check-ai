# Product UI

The current public demo is deployed as a static site in Yandex Object Storage:

`https://contractor-check-agent-demo.website.yandexcloud.net/`

Observed bucket: `contractor-check-agent-demo`.

## What is currently available

The bucket contains a production build only:

```text
assets/
favicon.svg
index.html
og.png
```

The `assets/` directory contains hashed JavaScript and CSS bundles from several successive builds. No source maps were observed. The original frontend source tree (`src/`, `package.json`, build config, etc.) has not yet been located, so it is not reconstructed from minified production assets here.

## Runtime path

```text
Browser
  -> Object Storage static website
  -> contractor-agent-demo-api Cloud Function
  -> Yandex AI Studio saved agent
```

The browser must not receive a Yandex API key. The deployed backend proxy accepts requests with `X-Demo-Token` and keeps the Yandex credential server-side.

## Import TODO

When the original source project becomes available, place it in this directory without `node_modules`, generated `dist/` history, API keys or local secret files. Preserve the deployed build only as a reference artifact if needed; source files should be canonical.

See [`docs/07_deployed_architecture.md`](../../docs/07_deployed_architecture.md) for the inspected deployment snapshot.
