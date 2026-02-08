<?php
/**
 * ETTEM Admin Panel - Dashboard
 * Lists all licenses with status, machines, and quick actions.
 */
session_start();
require_once __DIR__ . '/../api/config.php';
require_once __DIR__ . '/../api/helpers.php';

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

function require_admin_login(): void {
    if (empty($_SESSION['ettem_admin'])) {
        // Not logged in — show login form
        show_login_form();
        exit;
    }
}

function show_login_form(?string $error = null): void {
    ?>
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ETTEM Admin - Login</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
            .login-box { background: white; padding: 2.5rem; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }
            .login-box h1 { font-size: 1.5rem; margin-bottom: 0.5rem; color: #1a1a2e; }
            .login-box p { color: #666; margin-bottom: 1.5rem; font-size: 0.9rem; }
            .form-group { margin-bottom: 1rem; }
            .form-group label { display: block; font-weight: 600; margin-bottom: 0.3rem; font-size: 0.9rem; }
            .form-group input { width: 100%; padding: 0.75rem; border: 1px solid #ddd; border-radius: 6px; font-size: 1rem; }
            .form-group input:focus { outline: none; border-color: #4361ee; box-shadow: 0 0 0 3px rgba(67,97,238,0.15); }
            .btn { width: 100%; padding: 0.75rem; background: #4361ee; color: white; border: none; border-radius: 6px; font-size: 1rem; font-weight: 600; cursor: pointer; }
            .btn:hover { background: #3a56d4; }
            .error { background: #fee; color: #c00; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; font-size: 0.9rem; }
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>ETTEM Admin</h1>
            <p>License Management Panel</p>
            <?php if ($error): ?>
                <div class="error"><?= htmlspecialchars($error) ?></div>
            <?php endif; ?>
            <form method="POST" action="">
                <input type="hidden" name="action" value="login">
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" name="password" required autofocus>
                </div>
                <button type="submit" class="btn">Login</button>
            </form>
        </div>
    </body>
    </html>
    <?php
}

// Handle login POST
if ($_SERVER['REQUEST_METHOD'] === 'POST' && ($_POST['action'] ?? '') === 'login') {
    $password = $_POST['password'] ?? '';
    if (password_verify($password, ADMIN_PASSWORD_HASH)) {
        $_SESSION['ettem_admin'] = true;
        header('Location: index.php');
        exit;
    } else {
        show_login_form('Invalid password');
        exit;
    }
}

// Handle logout
if (($_GET['action'] ?? '') === 'logout') {
    session_destroy();
    header('Location: index.php');
    exit;
}

require_admin_login();

// ---------------------------------------------------------------------------
// Handle quick actions (POST)
// ---------------------------------------------------------------------------

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $db = get_db();
    $action = $_POST['action'] ?? '';

    if ($action === 'toggle_license') {
        $id = (int) ($_POST['license_id'] ?? 0);
        $new_state = (int) ($_POST['new_state'] ?? 0);
        $stmt = $db->prepare('UPDATE licenses SET is_active = ? WHERE id = ?');
        $stmt->execute([$new_state, $id]);
        header('Location: index.php?msg=updated');
        exit;
    }
}

// ---------------------------------------------------------------------------
// Dashboard data
// ---------------------------------------------------------------------------

$db = get_db();

// Get all licenses with machine counts
$licenses = $db->query("
    SELECT l.*,
           COUNT(CASE WHEN m.is_active = 1 THEN 1 END) AS active_machines,
           COUNT(m.id) AS total_machines
    FROM licenses l
    LEFT JOIN machines m ON m.license_id = l.id
    GROUP BY l.id
    ORDER BY l.created_at DESC
")->fetchAll();

$msg = $_GET['msg'] ?? '';
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETTEM Admin - Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }

        .topbar { background: #1a1a2e; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .topbar h1 { font-size: 1.2rem; }
        .topbar-nav a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 1.5rem; font-size: 0.9rem; }
        .topbar-nav a:hover { color: white; }
        .topbar-nav a.active { color: white; font-weight: 600; }

        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }

        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .stat-card { background: white; padding: 1.5rem; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); }
        .stat-card .label { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
        .stat-card .value { font-size: 2rem; font-weight: 700; margin-top: 0.25rem; }

        .card { background: white; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }
        .card-header { padding: 1rem 1.5rem; border-bottom: 1px solid #eee; font-weight: 600; }

        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 0.75rem 1rem; font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; background: #fafafa; }
        td { padding: 0.75rem 1rem; border-top: 1px solid #f0f0f0; font-size: 0.9rem; }
        tr:hover td { background: #f8f9ff; }

        .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-green { background: #e6f9ed; color: #0a7c3e; }
        .badge-red { background: #fde8e8; color: #c00; }
        .badge-yellow { background: #fff8e1; color: #b27a00; }
        .badge-gray { background: #f0f0f0; color: #666; }

        .key-mono { font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem; letter-spacing: 0.02em; }

        .btn-sm { padding: 0.3rem 0.75rem; border: none; border-radius: 4px; font-size: 0.8rem; cursor: pointer; font-weight: 500; }
        .btn-link { background: none; color: #4361ee; cursor: pointer; border: none; font-size: 0.85rem; text-decoration: underline; }
        .btn-danger { background: #fde8e8; color: #c00; }
        .btn-success { background: #e6f9ed; color: #0a7c3e; }

        .msg { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; background: #e6f9ed; color: #0a7c3e; font-size: 0.9rem; }
    </style>
</head>
<body>
    <div class="topbar">
        <h1>ETTEM Admin</h1>
        <nav class="topbar-nav">
            <a href="index.php" class="active">Dashboard</a>
            <a href="logs.php">Logs</a>
            <a href="index.php?action=logout">Logout</a>
        </nav>
    </div>

    <div class="container">
        <?php if ($msg === 'updated'): ?>
            <div class="msg">License updated successfully.</div>
        <?php endif; ?>

        <?php
        $total = count($licenses);
        $active = count(array_filter($licenses, fn($l) => $l['is_active']));
        $expired = count(array_filter($licenses, fn($l) => $l['expiration_date'] < date('Y-m-d')));
        $total_machines = array_sum(array_column($licenses, 'active_machines'));
        ?>

        <div class="stats">
            <div class="stat-card">
                <div class="label">Total Licenses</div>
                <div class="value"><?= $total ?></div>
            </div>
            <div class="stat-card">
                <div class="label">Active</div>
                <div class="value" style="color:#0a7c3e;"><?= $active ?></div>
            </div>
            <div class="stat-card">
                <div class="label">Expired</div>
                <div class="value" style="color:#c00;"><?= $expired ?></div>
            </div>
            <div class="stat-card">
                <div class="label">Active Machines</div>
                <div class="value"><?= $total_machines ?></div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">Licenses</div>
            <table>
                <thead>
                    <tr>
                        <th>Key</th>
                        <th>Client</th>
                        <th>Expiration</th>
                        <th>Machines</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($licenses)): ?>
                        <tr><td colspan="6" style="text-align:center; color:#999; padding:2rem;">No licenses yet. Licenses are auto-registered when activated from the desktop app.</td></tr>
                    <?php else: ?>
                        <?php foreach ($licenses as $lic): ?>
                            <?php
                            $is_expired = $lic['expiration_date'] < date('Y-m-d');
                            $is_revoked = !$lic['is_active'];
                            ?>
                            <tr>
                                <td><span class="key-mono"><?= htmlspecialchars($lic['license_key']) ?></span></td>
                                <td>
                                    <?php if ($lic['client_name']): ?>
                                        <?= htmlspecialchars($lic['client_name']) ?><br>
                                        <small style="color:#999;"><?= htmlspecialchars($lic['client_email'] ?? '') ?></small>
                                    <?php else: ?>
                                        <span style="color:#999;">ID: <?= htmlspecialchars($lic['client_id']) ?></span>
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <?= date('d/m/Y', strtotime($lic['expiration_date'])) ?>
                                    <?php if ($is_expired): ?>
                                        <br><span class="badge badge-red">Expired</span>
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <?= $lic['active_machines'] ?> / <?= $lic['max_machines'] ?>
                                </td>
                                <td>
                                    <?php if ($is_revoked): ?>
                                        <span class="badge badge-red">Revoked</span>
                                    <?php elseif ($is_expired): ?>
                                        <span class="badge badge-yellow">Expired</span>
                                    <?php else: ?>
                                        <span class="badge badge-green">Active</span>
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <a href="license.php?id=<?= $lic['id'] ?>" class="btn-link">Details</a>
                                    <form method="POST" style="display:inline;">
                                        <input type="hidden" name="action" value="toggle_license">
                                        <input type="hidden" name="license_id" value="<?= $lic['id'] ?>">
                                        <?php if ($lic['is_active']): ?>
                                            <input type="hidden" name="new_state" value="0">
                                            <button type="submit" class="btn-sm btn-danger" onclick="return confirm('Revoke this license?')">Revoke</button>
                                        <?php else: ?>
                                            <input type="hidden" name="new_state" value="1">
                                            <button type="submit" class="btn-sm btn-success">Reactivate</button>
                                        <?php endif; ?>
                                    </form>
                                </td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
