<?php
require_once __DIR__ . '/lib/auth.php';
require_once __DIR__ . '/lib/layout.php';
require_once __DIR__ . '/lib/supabase.php';

$config_path = __DIR__ . '/config.php';
if (!file_exists($config_path)) {
    http_response_code(500);
    echo 'Admin not configured: copy config.example.php to config.php and fill in values.';
    exit;
}
$cfg = require $config_path;

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $code = $_POST['code'] ?? '';
    if (admin_login($cfg, $code)) {
        header('Location: index.php');
        exit;
    }
    $error = 'Código incorrecto';
}

if (!admin_is_authenticated($cfg)) {
    admin_layout_header('Login');
    ?>
    <div style="max-width: 360px; margin: 8rem auto; padding: 0 1.5rem;">
      <div class="card">
        <h3>Acceso restringido</h3>
        <p class="muted" style="font-size: 0.85rem; margin-bottom: 1.25rem;">Solo personal autorizado.</p>
        <?php if ($error): ?>
          <div class="alert alert-error"><?= htmlspecialchars($error) ?></div>
        <?php endif; ?>
        <form method="POST">
          <div class="form-group">
            <label for="code">Código</label>
            <input type="text" name="code" id="code" autocomplete="off" autofocus required>
          </div>
          <button type="submit" class="btn" style="width: 100%;">Entrar</button>
        </form>
      </div>
    </div>
    <?php
    admin_layout_footer();
    exit;
}

// --- Authenticated: dashboard view ---
$tenantsResp = sb_list_tenants($cfg);
$tenants = $tenantsResp['ok'] ? ($tenantsResp['data'] ?? []) : [];

$totalTenants = count($tenants);
$activeTenants = count(array_filter($tenants, fn($t) => empty($t['archived_at'])));

admin_layout_header('Dashboard');
admin_layout_nav('index');
?>
<div class="container">
  <h2>Dashboard</h2>
  <p class="subtitle">Vista rápida del sistema</p>

  <?php if (!$tenantsResp['ok']): ?>
    <div class="alert alert-error">Error al cargar tenants: <?= htmlspecialchars($tenantsResp['error']) ?></div>
  <?php endif; ?>

  <div class="grid-2">
    <div class="card">
      <h3>Tenants Cloud</h3>
      <p style="font-size: 2rem; font-weight: 600; color: #f1f5f9;"><?= $activeTenants ?></p>
      <p class="muted" style="font-size: 0.85rem;">activos · <?= $totalTenants ?> totales (incl. archivados)</p>
      <p style="margin-top: 1rem;"><a href="tenants.php" class="btn">Gestionar tenants →</a></p>
    </div>

    <div class="card">
      <h3>Próximamente</h3>
      <p class="muted" style="font-size: 0.85rem;">Licencias desktop, métricas de uso, exports.</p>
    </div>
  </div>
</div>
<?php admin_layout_footer(); ?>
