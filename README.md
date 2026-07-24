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
`helpdesk.sla` y (si quieres el desglose de horas por técnico)
`account.analytic.line` — el tablero respeta los permisos y reglas de
registro de ese usuario, tal como lo haría dentro de Odoo.

Ya conectado, define el **rango de fechas a consultar** en la barra lateral
(por defecto, últimos 12 meses) — se vuelve a consultar Odoo automáticamente
si lo cambias. Los datos quedan en caché 10 minutos; usa **🔄 Refrescar
datos** para forzar una consulta nueva. Los demás filtros (cliente, técnico,
prioridad, etapa, SLA) se aplican en memoria sobre lo ya cargado.

Si algo se ve raro (técnico o cliente en blanco, fechas que no cuadran),
abre **🔍 Diagnóstico de conexión** en la barra lateral: muestra 1-2 tickets
tal cual los devuelve Odoo, sin transformar, para comparar contra lo que
esperas.

## Qué muestra

- **Resumen**: tickets creados/cerrados, tasa de cierre, horas invertidas,
  resolución promedio, distribución por etapa y prioridad, top clientes.
- **SLA**: cumplimiento global, cumplimiento por política/nivel de SLA,
  tendencia mensual, tickets vencidos.
- **Tendencias**: horas promedio por mes, primera respuesta, carga por día
  de la semana, resolución por prioridad.
- **Técnicos**: carga y horas por técnico, ranking, evolución mensual.
- **Clientes**: volumen y horas por cliente, ranking.
- **Tickets**: listado completo filtrable, exportable a CSV.
- **Heatmap**: tickets por cliente × mes.

Mientras no te hayas conectado a Odoo, el tablero muestra un dataset de
ejemplo sintético (marcado explícitamente) para que puedas ver el diseño
antes de tener datos reales.
