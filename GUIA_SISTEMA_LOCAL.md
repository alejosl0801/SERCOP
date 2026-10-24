# PREVIFUEGO · Sistema SERCOP local — guía

Última actualización: 2026-10-23. Esta es la guía vigente. El `CLAUDE.md` describe la versión antigua en la nube.

## 1. Qué hace

1. **Vigila** el portal de compras públicas (Ínfima Cuantía y Necesidad de Contratación) buscando "extintor", "recarga", "incendio" en Guayaquil, Samborondón, Daule y Durán.
2. **Avisa en grande** (ventana roja siempre encima, con sonido) cuando aparece un proceso nuevo de extintores.
3. **Prepara solo** el proceso: baja todos los anexos, los lee (con OCR y conversión de .doc), extrae plazo/pago/vigencia/garantía/lugar, detecta requisitos peligrosos y deja un borrador de proforma firmado.
4. **Tú decides y envías.** El login y el "Guardar" del portal son tuyos.

## 2. Piezas

| Archivo | Función |
|---|---|
| `vigilante_sercop.py` | Revisa el portal, detecta nuevos, alerta, encola la preparación |
| `alerta_popup.ps1` | Ventana roja de alerta |
| `preparar_proceso.py` | Pipeline de preparación (portal → anexos → análisis → precios → proforma → resumen) |
| `lector_anexos.py` | Lee PDF (con OCR), Word/.doc/.rtf (LibreOffice), Excel, imágenes |
| `extractor_condiciones.py` | Plazo, vigencia y garantía de todos los documentos; detecta contradicciones |
| `politica_sercop.json` | **Política comercial editable** (tarifas por volumen, vigencia por defecto, carta LAFT, umbrales) |
| `generar_proforma.py` | Genera el PDF (WeasyPrint) y lo firma (pyHanko + FirmaEC) |
| `precios.json` | Datos del proveedor y precios de referencia |
| `nco-guayas.json` | Datos locales de procesos (no subir cambios locales) |

Archivos locales que no van a git: `vistos.json`, `estado_vigilante.json`, `vigilante.log`, `ALERTAS.txt`, `alerta_texto.txt`, `cola_preparar.jsonl`, `preparar.log`, `ntfy_topic.txt`.

## 3. Tareas de Windows (Programador de tareas)

| Tarea | Qué hace |
|---|---|
| `SERCOP_Vigilante` | Cada 30 min ejecuta `vigilante_sercop.py` |
| `SERCOP_Alerta` | Muestra la ventana roja en tu sesión |
| `SERCOP_Preparar` | Ejecuta `preparar_proceso.py --cola` (hasta 30 min, en cola si llegan varios) |

Lanzar una a mano (PowerShell): `Start-ScheduledTask SERCOP_Preparar`. Desde Git Bash no uses `schtasks /run` (convierte la ruta).

## 4. Qué deja la preparación

En `Dropbox\Previfuego\ESTADO\<n> <ENTIDAD>\`:

- `00 RESUMEN Y ALERTAS.html` — **léelo primero**: semáforo, alertas con cita textual, condiciones del TDR, obligaciones, ítems con costo/margen/stock.
- `BORRADOR FIRMADO …pdf` o `BORRADOR SIN FIRMAR …pdf` (sin firmar si falta precio de algún ítem).
- `TABLA PARA EL PORTAL.txt` — valores para pegar.
- `ANEXOS DE LA ENTIDAD\`, `TEXTO COMPLETO DE LOS ANEXOS.txt`, copia del RUC, `datos_proceso.json`, `resumen.json`, `PROCESO.txt`.

## 5. Uso manual

```
py preparar_proceso.py NIC-xxxxxxxxxxxxx-2026-00000
py preparar_proceso.py NIC-… --estado Finalizada --salida C:\carpeta   (prueba sobre un proceso cerrado)
py preparar_proceso.py NIC-… --no-firmar
py vigilante_sercop.py --seed        (registra lo que hay hoy sin avisar)
```

## 6. Reglas de negocio (no cambiar sin decisión de Alejandro)

- CPC y descripciones de ítems: **los exactos de la entidad**. Nunca cambiarlos.
- Códigos de producto: solo los reales del catálogo Azur. Verificar stock real antes de cotizar.
- Tarifa de recarga por libra según volumen: ~0,80 con pocos extintores; 0,75 o 0,70 con 50 o más; igual PQS y CO2 (tramos en `politica_sercop.json`, por confirmar).
- El TDR manda sobre cualquier plantilla. Si los documentos se contradicen, se aplica el plazo menor y la garantía mayor, y se alerta.
- **No** se incluye la carta LAFT (declaración bajo juramento) salvo autorización o exigencia de la entidad.
- Procesos que piden notarización o declaración juramentada: se marcan CRÍTICO; Alejandro decide.
- IVA 15 % con redondeo comercial (ROUND_HALF_UP).
- El borrador firmado no es un envío: nada se sube al portal sin Alejandro.

## 7. Qué hacer cuando salta una alerta

1. Abrir `00 RESUMEN…html` y leer CRÍTICO y ATENCIÓN.
2. Revisar "Pendientes de tu decisión" y la tabla de ítems.
3. Comparar con el TDR original si hay dudas (todo el texto está en `TEXTO COMPLETO…txt`).
4. Si participa: entrar al portal, pegar valores de `TABLA PARA EL PORTAL.txt`, guardar, subir el PDF en la segunda etapa y aceptar términos.

## 8. Límites conocidos

- No sube nada al portal ni escribe contraseñas.
- Requiere la PC encendida y con sesión abierta.
- Los requisitos se detectan por palabras clave y patrones; la lista "Obligaciones que impone la entidad" es la red de seguridad. Ante duda, leer el TDR.
- `claude -p` en segundo plano no funciona (sesión expirada).
- Pendiente de decisión: columna de precio de extintores nuevos para entidades públicas, tramos de tarifa, correo del proveedor.

## 9. Seguridad

- La clave del certificado `.p12` **no** debe estar en el repo. Se lee de la variable `P12_PASS` o de un archivo cifrado con DPAPI en `~/.sercop/p12.dpapi`.
- El repo es público: no guardar claves, RUC de clientes ni datos privados en él.
- Pendiente: cambiar la contraseña del `.p12` (el historial de git conserva la anterior).

## 10. Historial de decisiones relevantes

- 2026-10-23: se perdió el plazo de la Prefectura del Guayas (proforma firmada pero nunca registrada en el portal). Origen del sistema de preparación automática.
- 2026-10-23: se descartó dejar que las sesiones envíen correos; solo borradores.
