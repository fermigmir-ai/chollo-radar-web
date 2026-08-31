# Chollo Radar

Web oficial y bot automático de ofertas de Chollo Radar.

- La web estática se publica con GitHub Pages desde la raíz del repositorio.
- El bot está en [`bot/`](bot/) y se ejecuta cada 30 minutos con GitHub
  Actions.
- Supabase conserva el catálogo, el histórico de precios, la deduplicación y
  los resultados de cada ejecución.
- Mientras se alcanzan las 10 ventas exigidas por Amazon, la campaña puente
  publica guías SEO y recomendaciones con enlaces afiliados ya autorizados en
  Telegram y, cuando se configuren sus credenciales, también en X.

La campaña puente queda programada; la fase de Amazon permanece desactivada
hasta disponer de Creators API. Consulta [`bot/README.md`](bot/README.md) para
configurar Telegram, X, Supabase y, más adelante, las credenciales de Amazon.
