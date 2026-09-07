Yourcast admin SPA. Production URL: `/app/` behind nginx.

```
npm ci
npm run build
```

The FastAPI `admin` role serves `dist/` and `/api/*`.
