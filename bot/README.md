# Chollo Radar Bot

Bot modular para detectar ofertas, puntuarlas y publicarlas automáticamente en
Telegram con enlaces de afiliado. La primera integración real está preparada
para Amazon España mediante **Amazon Creators API**.

> Un bot no garantiza ingresos. Automatiza la búsqueda y la publicación; el
> dinero depende del tráfico, la confianza de la audiencia, la conversión y las
> condiciones del programa de afiliación.

## Qué hace el MVP

- Recorre por turnos búsquedas de distintas categorías de Amazon España.
- Obtiene precio, ahorro, imagen, vendedor y enlace atribuido por Amazon.
- Descarta descuentos débiles, productos excluidos y precios fuera de rango.
- Puntúa cada oferta de 0 a 100 y publica solo las mejores.
- Evita repetir un producto durante el periodo configurado.
- Limita el número de publicaciones por ejecución para no saturar el canal.
- Publica foto, precio, descuento, enlace y aviso de afiliación en Telegram.
- Funciona en modo demostración sin claves y de forma programada sin depender
  de un ordenador encendido.
- Comparte catálogo, histórico, deduplicación y registro de ejecuciones en
  Supabase.
- Incluye una campaña puente que genera guías SEO y rota recomendaciones con
  enlaces afiliados mientras la cuenta todavía no tiene acceso a Creators API.

## Limitación importante de Amazon

No existe una llamada que entregue «todo Amazon». `SearchItems` devuelve hasta
10 artículos por página y admite hasta 10 páginas por búsqueda. El bot aproxima
una cobertura amplia rotando categorías, palabras clave y páginas. Para usar la
Creators API hay que:

1. Estar aceptado en Amazon Afiliados para España.
2. Haber generado al menos 10 ventas válidas en los últimos 30 días.
3. Crear una aplicación y credenciales de Creators API.
4. Tener una etiqueta de afiliado válida para `amazon.es`.

Hasta cumplir el requisito, el proyecto se puede probar en modo demo y usar la
misma canalización con un feed autorizado de otra red de afiliación.

## Campaña puente para conseguir las 10 ventas

El comando `bootstrap` no necesita `AMAZON_CLIENT_ID`,
`AMAZON_CLIENT_SECRET` ni `AMAZON_PARTNER_TAG`. Trabaja exclusivamente con los
enlaces cortos de afiliado creados previamente en Amazon Afiliados y guardados
en `data/bootstrap_campaign.json`.

La campaña:

- genera una guía editorial nueva cada 48 horas hasta completar el calendario;
- añade automáticamente cada guía a la portada y al sitemap;
- rota dos recomendaciones diarias en Telegram;
- evita repetir un producto durante 72 horas mediante Supabase;
- nunca copia precios ni porcentajes no verificados;
- identifica todos los enlaces remunerados con `#ad` y el aviso de afiliación;
- funciona sin scraping y sin acceso al catálogo de Amazon.

Previsualización local, sin modificar la web ni enviar mensajes:

```bash
DRY_RUN=true chollo-radar bootstrap --site-root ..
```

La automatización está en `.github/workflows/bootstrap-content.yml`. Para
habilitarla crea estas variables de GitHub Actions:

| Variable | Valor inicial | Efecto |
|---|---|---|
| `CHOLLO_RADAR_BOOTSTRAP_ENABLED` | `true` | Habilita las dos ejecuciones diarias |
| `CHOLLO_RADAR_BOOTSTRAP_DRY_RUN` | `true` | Previsualiza sin publicar ni modificar la web |

Solo necesita los secretos `SUPABASE_SECRET_KEY`, `TELEGRAM_BOT_TOKEN` y
`TELEGRAM_CHAT_ID` en el entorno `chollo-radar-production`. Después de validar
una ejecución manual, cambia `CHOLLO_RADAR_BOOTSTRAP_DRY_RUN` a `false`.

El archivo `.chollo-radar-campaign.json` registra las guías ya publicadas. Al
agotarse el calendario, el bot seguirá rotando recomendaciones en Telegram y
dejará de crear páginas hasta que se añadan productos y temas nuevos.

## Inicio rápido en modo demostración

Requiere Python 3.11 o superior.

### Windows, opción sencilla

1. Descomprime el proyecto.
2. Haz doble clic en `1_configurar_windows.bat`.
3. Haz doble clic en `2_probar_demo_windows.bat`.
4. Cuando completes `.env`, inicia el servicio con
   `3_iniciar_bot_windows.bat`.

### Terminal

```bash
cp .env.example .env
cp config.example.json config.json
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
chollo-radar once
```

En Windows PowerShell, activa el entorno con:

```powershell
.venv\Scripts\Activate.ps1
```

El modo demo solo imprime las ofertas; no publica ni genera comisiones.

## Activar Telegram

1. Crea un bot con `@BotFather` y copia su token.
2. Añádelo como administrador del canal, con permiso para publicar.
3. Usa el nombre del canal, por ejemplo `@cholloradar`, o su identificador.
4. Completa `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=@tu_canal
DRY_RUN=false
```

Comprueba la conexión:

```bash
chollo-radar test-telegram
```

## Activar Amazon Creators API

Completa `.env` sin subir nunca este archivo a un repositorio:

```dotenv
BOT_SOURCE=amazon
AMAZON_CLIENT_ID=...
AMAZON_CLIENT_SECRET=...
AMAZON_CREDENTIAL_VERSION=3.2
AMAZON_PARTNER_TAG=tu-etiqueta-21
AMAZON_MARKETPLACE=www.amazon.es
DRY_RUN=true
```

Primero ejecuta con `DRY_RUN=true`:

```bash
chollo-radar once
```

Cuando veas ofertas correctas, configura Telegram y cambia a
`DRY_RUN=false`. El bot conserva sin modificar el enlace atribuido devuelto por
Amazon.

## Automatización en GitHub Actions y Supabase

El repositorio incluye un workflow que despierta el bot cada 30 minutos. Cada
ciclo consulta Amazon, filtra ofertas, evita repeticiones usando Supabase,
publica en Telegram y termina; no necesita un ordenador ni un proceso abierto.

### 1. Secretos del entorno `chollo-radar-production`

Crea en GitHub el entorno `chollo-radar-production` y añade estos secretos:

| Secreto | Contenido |
|---|---|
| `SUPABASE_SECRET_KEY` | Clave `sb_secret_*` del proyecto; también funciona una `service_role` legacy |
| `AMAZON_CLIENT_ID` | Identificador OAuth de Creators API |
| `AMAZON_CLIENT_SECRET` | Secreto OAuth de Creators API |
| `AMAZON_PARTNER_TAG` | Etiqueta de Afiliados para Amazon España |
| `TELEGRAM_BOT_TOKEN` | Token entregado por BotFather |
| `TELEGRAM_CHAT_ID` | Canal, por ejemplo `@cholloradar` |

No pegues estas credenciales en archivos, commits, incidencias ni mensajes.

### 2. Variables del repositorio

| Variable | Valor inicial | Efecto |
|---|---|---|
| `CHOLLO_RADAR_ENABLED` | `true` | Habilita los ciclos manuales y programados |
| `CHOLLO_RADAR_DRY_RUN` | `true` | Analiza y registra, pero no envía mensajes |
| `CHOLLO_RADAR_MODE` | `amazon` | Habilita esta fase solo cuando existan credenciales de Creators API |

Ejecuta manualmente el workflow **Chollo Radar Bot** y revisa en Supabase la
tabla `bot_runs`. Cuando el resultado sea correcto, cambia
`CHOLLO_RADAR_DRY_RUN` a `false`. El horario es `:03` y `:33` de cada hora
(UTC), separado del proceso anterior para reducir solapamientos.

La clave de Supabase es exclusivamente de servidor. Las tablas del bot tienen
RLS activado, no conceden acceso al navegador y solo el rol de backend puede
leer o escribir en ellas.

## Funcionamiento continuo local

```bash
chollo-radar run
```

O con Docker:

```bash
cp .env.example .env
cp config.example.json config.json
docker compose up -d --build
```

Sin las variables de Supabase, la base operativa local queda en
`runtime/chollo_radar.db`. En producción, el backend compartido de Supabase
conserva productos, observaciones de precio, publicaciones, cursor y resultados
de cada ejecución.

## Comandos

- `chollo-radar once`: ejecuta un ciclo.
- `chollo-radar run`: ejecuta ciclos de forma continua.
- `chollo-radar status`: muestra estado y últimas publicaciones.
- `chollo-radar test-telegram`: manda un mensaje de prueba.
- `chollo-radar check-config`: valida la configuración.
- `chollo-radar bootstrap --site-root ..`: ejecuta la campaña previa a
  Creators API.

Todos aceptan `--config ruta/al/config.json`.

## Ajustes principales

Edita `config.json`:

- `query_batch_size`: búsquedas diferentes por ciclo.
- `queries`: categorías, palabras clave, páginas y descuento mínimo.
- `filters.min_discount_percent`: descuento mínimo general.
- `filters.min_savings_eur`: ahorro mínimo en euros.
- `filters.min_score`: calidad mínima para publicar.
- `publishing.max_posts_per_run`: límite de mensajes por ciclo.
- `publishing.cooldown_hours`: tiempo antes de poder repetir un producto.
- `publishing.disclosure`: aviso visible de afiliación.

## Cumplimiento y buenas prácticas

- No hace scraping de Amazon.
- Usa la Creators API y el enlace atribuido que devuelve Amazon.
- Vuelve a consultar los datos de oferta en cada ciclo y no publica desde una
  caché antigua.
- Incluye una declaración visible de afiliación.
- Precio y disponibilidad pueden cambiar; el mensaje lo advierte.
- Empieza en `DRY_RUN=true` y revisa el resultado antes de automatizar.
- No actives dos planificadores de publicación a la vez; primero valida y luego
  retira el proceso anterior.
- Consulta periódicamente las políticas del programa de afiliación.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

## Siguiente ampliación recomendada

Después de validar Telegram y conseguir clics, añadiría dos módulos: un feed de
una segunda red de afiliación para no depender solo de Amazon y un publicador
para la web que retire o refresque automáticamente precios caducados.
