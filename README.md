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

Al abrir el tablero, la barra lateral pide:

- **URL** de tu instancia (ej. `https://tuempresa.odoo.com`)
- **Base de datos**
- **Usuario** (tu correo)
- **Contraseña o API key** — se recomienda crear una API key dedicada en
  Odoo: *tu usuario (arriba a la derecha) → Preferencias → Seguridad de la
  cuenta → Nueva clave API*. Así puedes revocarla sin cambiar tu contraseña.

Las credenciales **no se guardan en disco**: viven solo en la sesión del
navegador mientras el tablero está abierto. El usuario de Odoo que se use
necesita acceso de lectura a `helpdesk.ticket`, `helpdesk.sla` y (si quieres
el desglose de horas por técnico) `account.analytic.line` — el tablero
respeta los permisos y reglas de registro de ese usuario, tal como lo haría
dentro de Odoo.

Tras conectar, define el **rango de fechas a consultar** (por defecto,
últimos 12 meses) y presiona **Cargar / actualizar datos**. Los filtros de
la barra lateral (cliente, técnico, prioridad, etapa, SLA) se aplican en
memoria sobre lo ya cargado, sin volver a consultar Odoo.

### Despliegue compartido (opcional)

Si vas a compartir el tablero (por ejemplo en Streamlit Community Cloud) y
quieres que ya venga conectado sin pedir credenciales, copia
`.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` (ese archivo
está en `.gitignore`, nunca se sube al repo) y completa los datos de tu
instancia.

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
