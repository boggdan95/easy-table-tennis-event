<?php
require_once __DIR__ . '/lib/auth.php';
require_once __DIR__ . '/lib/layout.php';
require_once __DIR__ . '/lib/supabase.php';

$config_path = __DIR__ . '/config.php';
if (!file_exists($config_path)) {
    http_response_code(500);
    echo 'Admin not configured.';
    exit;
}
$cfg = require $config_path;
admin_require_auth($cfg);

$flash = ['type' => '', 'msg' => ''];

// --- Handle create tenant POST ---
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'create') {
    $email = trim($_POST['email'] ?? '');
    $name = trim($_POST['name'] ?? '');
    $slug = strtolower(trim($_POST['slug'] ?? ''));
    $country = strtoupper(trim($_POST['country_cd'] ?? ''));

    $errors = [];
    if (!filter_var($email, FILTER_VALIDATE_EMAIL)) $errors[] = 'Email inválido.';
    if ($name === '') $errors[] = 'Nombre requerido.';
    if (!preg_match('/^[a-z0-9-]{2,50}$/', $slug)) $errors[] = 'Slug inválido (minúsculas, números, guiones, 2–50).';
    if ($country !== '' && strlen($country) !== 3) $errors[] = 'País debe ser ISO-3.';

    if ($errors) {
        $flash = ['type' => 'error', 'msg' => implode(' ', $errors)];
    } else {
        // Step 1: invite the owner (or fetch if already exists)
        $invite = sb_invite_user($cfg, $email);
        $user_id = null;
        if ($invite['ok']) {
            $user_id = $invite['data']['id'] ?? $invite['data']['user']['id'] ?? null;
        } else {
            // Maybe user already exists — try to fetch
            $existing = sb_get_user_by_email($cfg, $email);
            if ($existing['ok']) {
                $user_id = $existing['data']['id'] ?? null;
            } else {
                $flash = ['type' => 'error', 'msg' => 'No se pudo crear/invitar al usuario: ' . $invite['error']];
            }
        }

        // Step 2: get free plan
        $plan_id = $user_id ? sb_get_free_plan_id($cfg) : null;
        if ($user_id && !$plan_id) {
            $flash = ['type' => 'error', 'msg' => 'No hay plan "free" activo en Supabase.'];
        }

        // Step 3: create tenant + membership
        if ($user_id && $plan_id) {
            $tenant = sb_create_tenant($cfg, [
                'slug' => $slug,
                'name' => $name,
                'country_cd' => $country ?: null,
                'plan_id' => $plan_id,
            ]);
            if (!$tenant['ok']) {
                $flash = ['type' => 'error', 'msg' => 'Error creando tenant: ' . $tenant['error']];
            } else {
                $tenant_id = $tenant['data'][0]['id'] ?? null;
                if ($tenant_id) {
                    $mem = sb_add_tenant_member($cfg, $tenant_id, $user_id, 'owner');
                    if (!$mem['ok']) {
                        $flash = ['type' => 'error', 'msg' => 'Tenant creado pero falló la membresía: ' . $mem['error']];
                    } else {
                        $flash = ['type' => 'success', 'msg' => "Tenant \"{$name}\" creado. Invitación enviada a {$email}."];
                    }
                }
            }
        }
    }
}

// --- List tenants ---
$tenantsResp = sb_list_tenants($cfg);
$tenants = $tenantsResp['ok'] ? ($tenantsResp['data'] ?? []) : [];

admin_layout_header('Tenants Cloud');
admin_layout_nav('tenants');
?>
<div class="container">
  <h2>Tenants Cloud</h2>
  <p class="subtitle">Federaciones / clubes con acceso a ETTEM Cloud</p>

  <?php if ($flash['msg']): ?>
    <div class="alert alert-<?= htmlspecialchars($flash['type']) ?>"><?= htmlspecialchars($flash['msg']) ?></div>
  <?php endif; ?>

  <?php if (!$tenantsResp['ok']): ?>
    <div class="alert alert-error">Error: <?= htmlspecialchars($tenantsResp['error']) ?></div>
  <?php endif; ?>

  <div class="card">
    <h3>Crear nuevo tenant</h3>
    <p class="muted" style="font-size: 0.85rem; margin-bottom: 1rem;">
      Manda invitación por email al owner. Cliente recibe un magic link de Supabase para definir su password.
    </p>
    <form method="POST">
      <input type="hidden" name="action" value="create">
      <div class="grid-2">
        <div class="form-group">
          <label for="email">Email del owner *</label>
          <input type="email" name="email" id="email" required placeholder="admin@federacion.com">
        </div>
        <div class="form-group">
          <label for="slug">Slug (URL) *</label>
          <input type="text" name="slug" id="slug" required pattern="[a-z0-9\-]{2,50}" placeholder="fgtm">
        </div>
      </div>
      <div class="grid-2">
        <div class="form-group">
          <label for="name">Nombre *</label>
          <input type="text" name="name" id="name" required maxlength="100" placeholder="Federación Guatemalteca de Tenis de Mesa">
        </div>
        <div class="form-group">
          <label for="country_cd">País (ISO-3)</label>
          <input type="text" name="country_cd" id="country_cd" maxlength="3" style="text-transform: uppercase;" placeholder="GTM">
        </div>
      </div>
      <button type="submit" class="btn">Crear tenant + invitar owner</button>
    </form>
  </div>

  <div class="card">
    <h3>Tenants existentes (<?= count($tenants) ?>)</h3>
    <?php if (empty($tenants)): ?>
      <p class="muted" style="font-size: 0.85rem;">Sin tenants.</p>
    <?php else: ?>
    <div style="overflow-x: auto;">
    <table>
      <thead>
        <tr>
          <th>Nombre</th>
          <th>Slug</th>
          <th>País</th>
          <th>Plan</th>
          <th>Miembros</th>
          <th>Creado</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        <?php foreach ($tenants as $t): ?>
          <tr>
            <td><strong><?= htmlspecialchars($t['name']) ?></strong></td>
            <td><code><?= htmlspecialchars($t['slug']) ?></code></td>
            <td><?= htmlspecialchars($t['country_cd'] ?? '—') ?></td>
            <td><?= htmlspecialchars($t['plan']['code'] ?? '—') ?></td>
            <td><?= (int)($t['members'][0]['count'] ?? 0) ?></td>
            <td class="muted" style="font-size: 0.8rem;"><?= htmlspecialchars(substr($t['created_at'] ?? '', 0, 10)) ?></td>
            <td>
              <?php if (!empty($t['archived_at'])): ?>
                <span class="badge badge-warn">archivado</span>
              <?php else: ?>
                <span class="badge">activo</span>
              <?php endif; ?>
            </td>
          </tr>
        <?php endforeach; ?>
      </tbody>
    </table>
    </div>
    <?php endif; ?>
  </div>
</div>
<?php admin_layout_footer(); ?>
