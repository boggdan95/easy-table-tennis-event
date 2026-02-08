<?php
/**
 * ETTEM Admin Panel - License Detail
 * View/edit license, manage machines, view logs.
 */
require_once __DIR__ . '/../api/config.php';
require_once __DIR__ . '/../api/helpers.php';
require_once __DIR__ . '/auth.php';

if (!verify_auth_token()) {
    header('Location: index.php');
    exit;
}

$db = get_db();
$id = (int) ($_GET['id'] ?? 0);
if (!$id) { header('Location: index.php'); exit; }

// ---------------------------------------------------------------------------
// Handle POST actions
// ---------------------------------------------------------------------------

$msg = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $action = $_POST['action'] ?? '';

    if ($action === 'update_client') {
        $stmt = $db->prepare('UPDATE licenses SET client_name = ?, client_email = ?, notes = ?, max_machines = ? WHERE id = ?');
        $stmt->execute([
            trim($_POST['client_name'] ?? ''),
            trim($_POST['client_email'] ?? ''),
            trim($_POST['notes'] ?? ''),
            max(1, (int) ($_POST['max_machines'] ?? 2)),
            $id
        ]);
        $msg = 'Client info updated.';
    }

    if ($action === 'deactivate_machine') {
        $machine_db_id = (int) ($_POST['machine_db_id'] ?? 0);
        $stmt = $db->prepare('UPDATE machines SET is_active = 0 WHERE id = ? AND license_id = ?');
        $stmt->execute([$machine_db_id, $id]);
        $msg = 'Machine deactivated.';
    }

    if ($action === 'reactivate_machine') {
        $machine_db_id = (int) ($_POST['machine_db_id'] ?? 0);
        $stmt = $db->prepare('UPDATE machines SET is_active = 1 WHERE id = ? AND license_id = ?');
        $stmt->execute([$machine_db_id, $id]);
        $msg = 'Machine reactivated.';
    }
}

// ---------------------------------------------------------------------------
// Load data
// ---------------------------------------------------------------------------

$stmt = $db->prepare('SELECT * FROM licenses WHERE id = ?');
$stmt->execute([$id]);
$license = $stmt->fetch();
if (!$license) { header('Location: index.php'); exit; }

$stmt = $db->prepare('SELECT * FROM machines WHERE license_id = ? ORDER BY is_active DESC, last_validated_at DESC');
$stmt->execute([$id]);
$machines = $stmt->fetchAll();

$stmt = $db->prepare('SELECT * FROM validation_logs WHERE license_id = ? ORDER BY created_at DESC LIMIT 50');
$stmt->execute([$id]);
$logs = $stmt->fetchAll();

$is_expired = $license['expiration_date'] < date('Y-m-d');
$days_remaining = (int) (new DateTime('today'))->diff(new DateTime($license['expiration_date']))->format('%r%a');
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETTEM Admin - <?= htmlspecialchars($license['license_key']) ?></title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }

        .topbar { background: #1a1a2e; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .topbar h1 { font-size: 1.2rem; }
        .topbar-nav a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 1.5rem; font-size: 0.9rem; }
        .topbar-nav a:hover { color: white; }

        .container { max-width: 1000px; margin: 0 auto; padding: 2rem; }

        .back-link { display: inline-block; margin-bottom: 1.5rem; color: #4361ee; text-decoration: none; font-size: 0.9rem; }
        .back-link:hover { text-decoration: underline; }

        .card { background: white; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; margin-bottom: 1.5rem; }
        .card-header { padding: 1rem 1.5rem; border-bottom: 1px solid #eee; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }
        .card-body { padding: 1.5rem; }

        .key-mono { font-family: 'Consolas', 'Monaco', monospace; font-size: 1.1rem; letter-spacing: 0.03em; }

        .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
        .info-item .label { font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.05em; }
        .info-item .value { font-size: 1rem; font-weight: 500; margin-top: 0.2rem; }

        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem; }
        .form-group { display: flex; flex-direction: column; gap: 0.3rem; }
        .form-group.full { grid-column: 1 / -1; }
        .form-group label { font-size: 0.85rem; font-weight: 600; }
        .form-group input, .form-group textarea { padding: 0.5rem 0.75rem; border: 1px solid #ddd; border-radius: 6px; font-size: 0.9rem; font-family: inherit; }
        .form-group input:focus, .form-group textarea:focus { outline: none; border-color: #4361ee; }

        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 0.6rem 1rem; font-size: 0.8rem; color: #666; text-transform: uppercase; background: #fafafa; }
        td { padding: 0.6rem 1rem; border-top: 1px solid #f0f0f0; font-size: 0.85rem; }

        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-green { background: #e6f9ed; color: #0a7c3e; }
        .badge-red { background: #fde8e8; color: #c00; }
        .badge-yellow { background: #fff8e1; color: #b27a00; }
        .badge-gray { background: #f0f0f0; color: #666; }

        .btn { padding: 0.5rem 1rem; border: none; border-radius: 6px; font-size: 0.85rem; cursor: pointer; font-weight: 500; }
        .btn-primary { background: #4361ee; color: white; }
        .btn-primary:hover { background: #3a56d4; }
        .btn-sm { padding: 0.25rem 0.6rem; font-size: 0.8rem; border-radius: 4px; }
        .btn-danger { background: #fde8e8; color: #c00; border: none; cursor: pointer; }
        .btn-success { background: #e6f9ed; color: #0a7c3e; border: none; cursor: pointer; }

        .msg { padding: 0.75rem 1rem; border-radius: 6px; margin-bottom: 1rem; background: #e6f9ed; color: #0a7c3e; font-size: 0.9rem; }

        .machine-id-short { font-family: 'Consolas', monospace; font-size: 0.8rem; color: #666; }
    </style>
</head>
<body>
    <div class="topbar">
        <h1>ETTEM Admin</h1>
        <nav class="topbar-nav">
            <a href="index.php">Dashboard</a>
            <a href="logs.php">Logs</a>
            <a href="index.php?action=logout">Logout</a>
        </nav>
    </div>

    <div class="container">
        <a href="index.php" class="back-link">&larr; Back to Dashboard</a>

        <?php if ($msg): ?>
            <div class="msg"><?= htmlspecialchars($msg) ?></div>
        <?php endif; ?>

        <!-- License Info -->
        <div class="card">
            <div class="card-header">
                <span>License Detail</span>
                <span class="key-mono"><?= htmlspecialchars($license['license_key']) ?></span>
            </div>
            <div class="card-body">
                <div class="info-grid" style="margin-bottom: 1.5rem;">
                    <div class="info-item">
                        <div class="label">Status</div>
                        <div class="value">
                            <?php if (!$license['is_active']): ?>
                                <span class="badge badge-red">Revoked</span>
                            <?php elseif ($is_expired): ?>
                                <span class="badge badge-yellow">Expired</span>
                            <?php else: ?>
                                <span class="badge badge-green">Active</span>
                            <?php endif; ?>
                        </div>
                    </div>
                    <div class="info-item">
                        <div class="label">Expiration</div>
                        <div class="value">
                            <?= date('d/m/Y', strtotime($license['expiration_date'])) ?>
                            (<?= $is_expired ? abs($days_remaining) . ' days ago' : $days_remaining . ' days left' ?>)
                        </div>
                    </div>
                    <div class="info-item">
                        <div class="label">Created</div>
                        <div class="value"><?= date('d/m/Y H:i', strtotime($license['created_at'])) ?></div>
                    </div>
                    <div class="info-item">
                        <div class="label">Machines</div>
                        <div class="value"><?= count(array_filter($machines, fn($m) => $m['is_active'])) ?> / <?= $license['max_machines'] ?></div>
                    </div>
                </div>

                <!-- Edit Client Info -->
                <form method="POST">
                    <input type="hidden" name="action" value="update_client">
                    <div class="form-row">
                        <div class="form-group">
                            <label>Client Name</label>
                            <input type="text" name="client_name" value="<?= htmlspecialchars($license['client_name'] ?? '') ?>" placeholder="Organization or person name">
                        </div>
                        <div class="form-group">
                            <label>Client Email</label>
                            <input type="email" name="client_email" value="<?= htmlspecialchars($license['client_email'] ?? '') ?>" placeholder="contact@example.com">
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label>Max Machines</label>
                            <input type="number" name="max_machines" value="<?= $license['max_machines'] ?>" min="1" max="10">
                        </div>
                        <div class="form-group">
                            <label>&nbsp;</label>
                            <button type="submit" class="btn btn-primary">Save Changes</button>
                        </div>
                    </div>
                    <div class="form-group full">
                        <label>Notes</label>
                        <textarea name="notes" rows="2" placeholder="Internal notes..."><?= htmlspecialchars($license['notes'] ?? '') ?></textarea>
                    </div>
                </form>
            </div>
        </div>

        <!-- Machines -->
        <div class="card">
            <div class="card-header">Registered Machines</div>
            <table>
                <thead>
                    <tr>
                        <th>Label</th>
                        <th>Machine ID</th>
                        <th>First Activated</th>
                        <th>Last Validated</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($machines)): ?>
                        <tr><td colspan="6" style="text-align:center; color:#999; padding:1.5rem;">No machines registered yet.</td></tr>
                    <?php else: ?>
                        <?php foreach ($machines as $m): ?>
                            <tr>
                                <td><?= htmlspecialchars($m['machine_label'] ?: '(unknown)') ?></td>
                                <td><span class="machine-id-short" title="<?= htmlspecialchars($m['machine_id']) ?>"><?= htmlspecialchars(substr($m['machine_id'], 0, 16)) ?>...</span></td>
                                <td><?= date('d/m/Y H:i', strtotime($m['first_activated_at'])) ?></td>
                                <td><?= date('d/m/Y H:i', strtotime($m['last_validated_at'])) ?></td>
                                <td>
                                    <?php if ($m['is_active']): ?>
                                        <span class="badge badge-green">Active</span>
                                    <?php else: ?>
                                        <span class="badge badge-gray">Inactive</span>
                                    <?php endif; ?>
                                </td>
                                <td>
                                    <form method="POST" style="display:inline;">
                                        <input type="hidden" name="machine_db_id" value="<?= $m['id'] ?>">
                                        <?php if ($m['is_active']): ?>
                                            <input type="hidden" name="action" value="deactivate_machine">
                                            <button type="submit" class="btn-sm btn-danger" onclick="return confirm('Deactivate this machine? The user will need to re-activate.')">Deactivate</button>
                                        <?php else: ?>
                                            <input type="hidden" name="action" value="reactivate_machine">
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

        <!-- Recent Logs -->
        <div class="card">
            <div class="card-header">
                <span>Recent Activity (last 50)</span>
                <a href="logs.php?license_id=<?= $id ?>" style="font-size:0.85rem; color:#4361ee; text-decoration:none;">View all &rarr;</a>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Action</th>
                        <th>Result</th>
                        <th>IP</th>
                        <th>Version</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($logs)): ?>
                        <tr><td colspan="5" style="text-align:center; color:#999; padding:1.5rem;">No activity yet.</td></tr>
                    <?php else: ?>
                        <?php foreach ($logs as $log): ?>
                            <tr>
                                <td><?= date('d/m/Y H:i', strtotime($log['created_at'])) ?></td>
                                <td><span class="badge badge-gray"><?= htmlspecialchars($log['action']) ?></span></td>
                                <td>
                                    <?php
                                    $result_class = match($log['result']) {
                                        'success' => 'badge-green',
                                        'expired', 'revoked', 'machine_limit', 'invalid_key', 'error' => 'badge-red',
                                        default => 'badge-gray',
                                    };
                                    ?>
                                    <span class="badge <?= $result_class ?>"><?= htmlspecialchars($log['result']) ?></span>
                                </td>
                                <td><small><?= htmlspecialchars($log['ip_address'] ?? '') ?></small></td>
                                <td><small><?= htmlspecialchars($log['app_version'] ?? '') ?></small></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
