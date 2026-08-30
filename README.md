# Chollo Radar

Web oficial y bot automático de ofertas de Chollo Radar.

- La web estática se publica con GitHub Pages desde la raíz del repositorio.
- El bot está en [`bot/`](bot/) y se ejecuta cada 30 minutos con GitHub
  Actions.
- Supabase conserva el catálogo, el histórico de precios, la deduplicación y
  los resultados de cada ejecución.

La automatización empieza desactivada y en modo de prueba. Consulta
[`bot/README.md`](bot/README.md) para configurar las credenciales de Amazon
Creators API, Telegram y Supabase antes de habilitar publicaciones reales.

