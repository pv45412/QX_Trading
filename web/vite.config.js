import {defineConfig} from 'vite';

// SCANNER owns 5173; keep this independent prototype on its own local port.
export default defineConfig({server:{port:5174,strictPort:true,proxy:{'/api':'http://127.0.0.1:8510'}}});
