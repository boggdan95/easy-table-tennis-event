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
