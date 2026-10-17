export default {
  server: {
    host: '127.0.0.1',
    port: 5177,
    strictPort: true,
    proxy: {'/api': 'http://127.0.0.1:8765'},
  },
};
