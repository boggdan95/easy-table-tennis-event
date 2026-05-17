# ETTEM Admin (PHP, Bluehost)

Panel privado para operar ETTEM Cloud desde el servidor de Bluehost. Vive aparte del repo cloud (Next.js) por diseño: lo usás solo vos, no los clientes.

URL destino: `https://ettem.boggdan.com/admin/`

## Stack

PHP 7.4+ (curl + sesiones por cookie). Sin frameworks. Pega directo contra la Supabase Admin API y PostgREST con la `service_role` key.

## Funciones V1

- Login con código único (cookie HMAC, 24h)
- Listar tenants (nombre, slug, país, plan, miembros, fecha, estado)
- Crear tenant + invitar owner por email (magic link de Supabase)

Pendientes futuros:
- Licencias desktop (migrar `generate_license.py` a PHP)
- Métricas de uso por tenant
- Archivar / eliminar tenants

## Despliegue (manual una vez)

1. **Crear `config.php`** localmente desde el template:
   ```bash
   cp config.example.php config.php
   ```
   Editar y llenar:
   - `admin_code` — un string largo único (NO commitear)
   - `cookie_salt` — otro string aleatorio
   - `supabase_url` — `https://kkfidgtmpbxfmzyiwwaa.supabase.co`
   - `supabase_service_role_key` — del dashboard Supabase → Project Settings → API

2. **Subir vía FTP** a Bluehost. La carpeta entera `admin/` debe quedar:
   ```
   public_html/admin/
   ├── .htaccess
   ├── config.php       ← este NO está en git, lo subes manualmente
   ├── config.example.php
   ├── index.php
   ├── tenants.php
   ├── logout.php
   └── lib/
       ├── auth.php
       ├── supabase.php
       └── layout.php
   ```

3. **Probar**: `https://ettem.boggdan.com/admin/` debe pedir el código.

## Modelo de seguridad

- Single-user (vos) con código privado HMAC en cookie firmada (igual patrón que `/descargas`)
- `config.php` denied via `.htaccess` (regla `<FilesMatch>`)
- `service_role` key **nunca** se expone al cliente — todas las llamadas a Supabase pasan por PHP server-side
- HTTPS obligatorio (cookies marcadas `Secure`)

## Notas operativas

- **Emails de invitación** salen del SMTP por defecto de Supabase (~30 emails/hora). Para producción más seria, configurar Resend/SendGrid en Supabase → Auth → SMTP.
- **Si el email ya existe** en `auth.users`, el endpoint `invite` falla y caemos a `get_user_by_email`. Eso permite "re-attachar" un usuario existente a un nuevo tenant.
- **Para revocar acceso a un tenant**: hoy solo se puede hacer directo en Supabase Dashboard (borrar `tenant_members` row). Una próxima versión agregará un botón.

## Recovery — Si te olvidás el código

No hay flujo de recuperación dentro del admin a propósito (menos código = menos
vectores de ataque). Pero **siempre tenés acceso operacional vía FTP**:

1. Conectate a Bluehost por FTP (o cPanel File Manager).
2. Abrí `public_html/admin/config.php`.
3. Cambiá los valores de `admin_code` y `cookie_salt` por nuevos strings.
4. Guardá.
5. Volvé al panel → login con el código nuevo.

Buenas prácticas:
- Guardá `admin_code` y `cookie_salt` en tu password manager cuando configurás
  por primera vez.
- Rotalos cada 6–12 meses como higiene, o de inmediato si sospechás compromiso.

## Workflow recomendado (cliente nuevo)

1. Vos cobrás al cliente (fuera de banda — Stripe link, transferencia, etc.)
2. Entrás a `/admin/tenants.php`
3. Llenás el form con email del owner + datos de la federación
4. Cliente recibe email con magic link
5. Cliente click → setea password → cae en su dashboard de `app.ettem.boggdan.com` ya configurado

## Local dev

```bash
php -S 127.0.0.1:8080 -t docs/website/admin/
```

Asegurate de tener un `config.php` con valores reales para que las llamadas a Supabase no fallen.

Detalles del comportamiento:
- La cookie usa `Secure` solo si la request llegó por HTTPS (detectado vía
  `$_SERVER['HTTPS']` o `X-Forwarded-Proto`). En local HTTP funciona sin Secure;
  en Bluehost HTTPS la cookie es Secure automáticamente.
- Path de cookie es `/` para que funcione tanto en local (root) como en prod
  (donde el admin vive en `/admin/`). Está aislada por nombre (`ettem_admin`)
  + HttpOnly + SameSite=Strict.

## Checklist de despliegue a producción

1. [ ] Copiar `config.example.php` → `config.php` en local
2. [ ] Generar valores fuertes para `admin_code` y `cookie_salt` (16+ caracteres random)
3. [ ] Pegar `supabase_url` y `supabase_service_role_key` del dashboard Supabase
4. [ ] Guardar `admin_code` y `cookie_salt` en password manager
5. [ ] FTP subir TODO `docs/website/admin/` (excepto `config.example.php` no hace falta) a `public_html/admin/`
6. [ ] **Subir `config.php` por separado** — no está en git
7. [ ] Verificar permisos: archivos 644, directorios 755
8. [ ] Probar `https://ettem.boggdan.com/admin/`:
   - [ ] Aparece pantalla de código
   - [ ] Código incorrecto → error
   - [ ] Código correcto → dashboard con tenant count
   - [ ] Lista de tenants se carga (si no, revisar service_role en config.php)
   - [ ] Crear un tenant de prueba → recibís email
9. [ ] Probar que `https://ettem.boggdan.com/admin/config.php` devuelve 403 (Forbidden)
10. [ ] Probar que `https://ettem.boggdan.com/admin/lib/supabase.php` devuelve 403
