/// <reference types="vite/client" />

/** Only variables prefixed with VITE_ are exposed to the browser bundle. */
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
