# 🎫 Tablero de Soporte — Firefly

Tablero ejecutivo para el área de soporte, construido sobre `helpdesk.ticket`
de Odoo 19 (+ registro de horas de `helpdesk_timesheet`). Se conecta **en
vivo** a tu instancia de Odoo vía XML-RPC — no requiere exportar nada a mano.

Responde: cuántos tickets se crean/cierran, cómo se distribuyen por etapa,
prioridad y política de SLA, cuánto tiempo se invierte, y cómo va cada
técnico y cada cliente.

## Cómo correrlo

Prerrequisito: instalar `uv` si no lo tienes.

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

1. Sincronizar dependencias

   ```
   uv sync
   ```

2. Ejecutar la app

   ```
   uv run streamlit run streamlit_app.py
   ```

## Conectarse a Odoo

El tablero se conecta **siempre** con las credenciales de
`st.secrets["odoo"]` — no hay formulario de login. Copia
`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` (ese archivo
sí está en `.gitignore`, nunca se sube al repo) y completa:

- **url** de tu instancia (ej. `https://tuempresa.odoo.com`)
- **db**: nombre de la base de datos
- **username**: tu correo
- **api_key**: se recomienda crear una API key dedicada en Odoo — *tu
  usuario (arriba a la derecha) → Preferencias → Seguridad de la cuenta →
  Nueva clave API* — en vez de tu contraseña real, para poder revocarla sin
  cambiar tu acceso.

Para un **despliegue compartido** (Streamlit Community Cloud u otro),
configura la misma tabla `[odoo]` en *Manage app → Settings → Secrets*. El
usuario de Odoo que uses necesita acceso de lectura a `helpdesk.ticket`,
`helpdesk.sla` y, si quieres el KPI de contratos activos, `sale.order`
(módulo `sale_subscription`) — el tablero respeta los permisos y reglas de
registro de ese usuario, tal como lo haría dentro de Odoo.

Ya conectado, define el **rango de fechas a consultar** en la barra lateral
(por defecto, **últimos 6 meses** — el mínimo para ver comparativos
mensuales con sentido). Los datos quedan en caché 10 minutos; usa **🔄
Refrescar datos** para forzar una consulta nueva. Los demás filtros
(cliente, técnico, prioridad, etapa, SLA) se aplican en memoria sobre lo ya
cargado.

Si algo se ve raro (técnico o cliente en blanco, fechas que no cuadran),
abre **🔍 Diagnóstico de conexión** en la barra lateral: muestra 1-2 tickets
tal cual los devuelve Odoo, sin transformar, para comparar contra lo que
esperas.

## Qué muestra

Todo lo relacionado con SLA/resolución/horas se desglosa por **criticidad**
(prioridad) en vez de una sola cifra global, y las comparaciones entre
clientes/técnicos usan **promedio mensual** (no acumulado) para no penalizar
a quien lleva menos tiempo en soporte.

- **Resumen**: tickets abiertos actualmente, promedios mensuales de
  cerrados/horas, horas del mes en curso, clientes con contrato de soporte
  activo, creados vs. cerrados vs. backlog (cola acumulada), etapa de los
  abiertos, prioridad por mes, tasa de efectividad de cierre, top clientes
  (promedio) y top 3 clientes con más tickets abiertos.
- **SLA**: cumplimiento y resolución promedio por criticidad (4 indicadores
  c/u), incumplimiento apilado por criticidad por mes, cumplimiento mensual
  en 4 líneas con el % marcado en cada punto, detalle histórico mes×
  prioridad, horas y primera respuesta promedio por mes (por criticidad).
- **Técnicos**: tickets y horas por técnico y mes, ranking con promedios
  mensuales.
- **Clientes**: volumen y horas por cliente (promedio mensual), ranking.
- **Heatmap**: tickets por cliente × mes, con el número en cada celda y
  totales por mes.

Mientras no te hayas conectado a Odoo, el tablero muestra un dataset de
ejemplo sintético (marcado explícitamente) para que puedas ver el diseño
antes de tener datos reales.
