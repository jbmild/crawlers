# Plataforma de crawlers

Servicio para correr varios crawlers cada cierto tiempo. Cada uno lee una página, evalúa una condición y, si se cumple, ejecuta una acción. El primero vigila el fascículo de [Iron Man – Construí la armadura Mark III](https://brihet.com.ar/producto/iron-man-construi-la-armadura-mark-iii/) en Brihet y avisa por Telegram cuando un botón deja de estar **Agotado**.

En el HTML el botón dice `Añadir al carrito`. Si está deshabilitado, un script del sitio le cambia el texto visible a `Agotado`. El crawler trata como agotado un botón con el atributo `disabled`, la clase `disabled`, o el texto `Agotado`. Mira solo la tabla `variations-table` (foto, nombre del fascículo, precio y botón), no un texto suelto de la página.

La primera vez que un fascículo aparece como disponible, avisa. Si ya quedó anotado como disponible, no repite el mensaje. Si vuelve a agotarse y después hay stock, avisa de nuevo. Con el fascículo 01 agotado, al arrancar no manda nada hasta que el botón deje de estarlo. Si Telegram falla, no se marca como avisado y se reintenta en el ciclo siguiente. Si la página falla 5 veces seguidas, también manda un aviso.

## Telegram

1. Creá un bot con [@BotFather](https://t.me/BotFather) y copiá el token.
2. Abrí una conversación con ese bot y enviá `/start`. Sin ese mensaje, Telegram no deja que el bot te escriba.
3. En el servidor:

```bash
cp .env.example .env
# completá TELEGRAM_BOT_TOKEN
python -m crawler_platform --print-chat-id
# copiá el chat_id a TELEGRAM_CHAT_ID en .env
python -m crawler_platform --test-telegram
```

Para avisar a otra persona desde un crawler distinto, poné `chat_id` en esa acción. Si no está, se usa `TELEGRAM_CHAT_ID`.

## Probar la lectura sin avisar

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
.venv/bin/python -m crawler_platform --once iron-man-mark-iii --dry-run
```

`--dry-run` no escribe `data/state.json` ni llama a Telegram. Hoy el fascículo 01 está deshabilitado, así que el resultado esperado es `agotado` y `a notificar: ninguno`.

## Correrlo en Proxmox

No hace falta abrir puertos de entrada. Solo salida HTTPS hacia `brihet.com.ar` y `api.telegram.org`. Alcanza con 1 vCPU, 512 MB de RAM y unos pocos GB de disco.

La opción más simple en Proxmox es un LXC Debian 12 y systemd. Docker también sirve si ya tenés un contenedor o una VM con Docker.

### LXC Debian y systemd

```bash
apt update && apt install -y python3-venv ca-certificates
useradd --system --create-home --home-dir /opt/crawlers --shell /usr/sbin/nologin crawlers
# copiá este proyecto a /opt/crawlers
cd /opt/crawlers
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
# editá .env con el token y el chat_id
chown -R crawlers:crawlers /opt/crawlers
cp deploy/crawlers.service /etc/systemd/system/crawlers.service
systemctl daemon-reload
systemctl enable --now crawlers
journalctl -u crawlers -f
```

### Docker Compose

En una VM, o en un LXC con nesting habilitado:

```bash
cp .env.example .env
# editá .env
docker compose up -d --build
docker compose logs -f
```

El estado queda en el volumen `crawler-data`. La configuración se lee de `config/crawlers.yaml`, que está montado: editar ese archivo recarga los crawlers sin reconstruir la imagen. El proceso revisa el archivo cada 30 segundos como máximo.

## Sumar un crawler

1. Creá una clase con `type_name` y `async def collect(self, spec) -> list[Item]`. Cada `Item` necesita `key`, `label` y `status`.
2. Registrate en `crawler_platform/crawlers/__init__.py`.
3. Agregá un bloque en `config/crawlers.yaml`.

La condición `field_not_equals` con `trigger: on_change` avisa cuando `field` deja de ser `value`. `while_true` avisa en cada ciclo mientras siga siendo distinto: no lo uses con Telegram si no querés un mensaje cada 5 minutos.

Una acción nueva se agrega igual, en `crawler_platform/actions/`.

El intervalo mínimo es 60 segundos (`MIN_INTERVAL_SECONDS` en `crawler_platform/config.py`). El de Iron Man está en 300.

## Estado

`data/state.json` guarda el último estado de cada fascículo. Borrar ese archivo vuelve a armar los avisos: si algo ya está disponible, el próximo ciclo lo notifica otra vez.

No corras dos copias contra el mismo archivo de estado.
