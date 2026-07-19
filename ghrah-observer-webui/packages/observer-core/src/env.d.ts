// Local ImportMeta.env typing for observer-core (no vite dep).
// Vite injects import.meta.env at build/dev time in observer-web; observer-core
// is a library so we declare the minimal shape consumed by stores.
interface ImportMetaEnv {
  readonly VITE_GHRAH_SUBJECT_WS_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}