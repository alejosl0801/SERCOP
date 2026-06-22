# Configuración inicial — PREVIFUEGO Automático

## 1. Activar GitHub Pages

1. Ve a: `https://github.com/alejosl0801/SERCOP/settings/pages`
2. En **Source** selecciona: `GitHub Actions`
3. Guarda. La app quedará en: `https://alejosl0801.github.io/SERCOP/`

---

## 2. Configurar GitHub Secrets

Ve a: `https://github.com/alejosl0801/SERCOP/settings/secrets/actions`

Agrega estos secrets (botón "New repository secret"):

| Secret | Valor |
|--------|-------|
| `GMAIL_USER` | `alejosl0801@gmail.com` |
| `GMAIL_APP_PASS` | Contraseña de aplicación de Gmail (16 caracteres) |
| `P12_PASS` | Contraseña de tu firma electrónica |
| `P12_CERT_B64` | Certificado .p12 en base64 (ver instrucción abajo) |
| `SERCOP_USER` | `0952773976001` (tu RUC) |
| `SERCOP_PASS` | Contraseña del portal compraspublicas.gob.ec |

### Cómo generar P12_CERT_B64

En tu PC donde tienes el archivo .p12:
```bash
base64 -w 0 tu_certificado.p12
```
Copia el resultado completo y pégalo como valor del secret `P12_CERT_B64`.

---

## 3. Verificar que funciona

1. Ve a: `https://github.com/alejosl0801/SERCOP/actions`
2. Abre "NCO Scraper — SERCOP Guayas"
3. Clic en **Run workflow** para probar manualmente
4. Si el scraper encuentra NCOs, el workflow "Proforma" se dispara automáticamente

---

## 4. Instalar la PWA en tu celular/PC

1. Abre Chrome en: `https://alejosl0801.github.io/SERCOP/`
2. Chrome mostrará "Instalar aplicación" (ícono en la barra de dirección)
3. Instala → la app queda como ícono en tu pantalla
4. Activa las alertas dentro de la app → recibirás notificaciones push

---

## Flujo automático completo

```
Cada hora (L-V 6am-9pm)
    └─ GitHub Actions: scraper NCO
           └─ Si hay NCOs nuevos → commit nco-guayas.json
                  └─ Trigger automático: generar proforma
                         └─ Firmar PDF con tu certificado
                                └─ Subir al portal SERCOP
                                       └─ Email de confirmación
                                              └─ Notificación push en la app
```
