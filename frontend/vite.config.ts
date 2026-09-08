import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Django serves the built app: index.html as a template, assets through
// whitenoise under STATIC_URL. The base path has to match STATIC_URL.
export default defineConfig({
  plugins: [react()],
  base: "/static/",
  build: { outDir: "dist", emptyOutDir: true },
});
