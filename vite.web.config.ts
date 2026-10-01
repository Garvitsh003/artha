import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
export default defineConfig({
  plugins:[react()],
  resolve:{alias:{'@':fileURLToPath(new URL('.',import.meta.url))}},
  server:{host:'0.0.0.0',port:5173,proxy:{'/api':'http://127.0.0.1:5000'}},
  build:{outDir:'dist-web',emptyOutDir:true},
});
