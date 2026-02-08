<?php
/**
 * ETTEM Admin Panel - Validation Logs
 * Filterable log of all license validation activity.
 */
require_once __DIR__ . '/../api/config.php';
require_once __DIR__ . '/../api/helpers.php';
require_once __DIR__ . '/auth.php';

if (!verify_auth_token()) {
    header('Location: index.php');
    exit;
}

$db = get_db();

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

$filter_license = (int) ($_GET['license_id'] ?? 0);
$filter_action = $_GET['action_filter'] ?? '';
$filter_result = $_GET['result_filter'] ?? '';
$page = max(1, (int) ($_GET['page'] ?? 1));
$per_page = 100;
$offset = ($page - 1) * $per_page;

// Build query
$where = [];
$params = [];

if ($filter_license) {
    $where[] = 'vl.license_id = ?';
    $params[] = $filter_license;
}
if ($filter_action) {
    $where[] = 'vl.action = ?';
    $params[] = $filter_action;
}
if ($filter_result) {
    $where[] = 'vl.result = ?';
    $params[] = $filter_result;
}

$where_sql = $where ? 'WHERE ' . implode(' AND ', $where) : '';

// Count total
$count_stmt = $db->prepare("SELECT COUNT(*) FROM validation_logs vl $where_sql");
$count_stmt->execute($params);
$total = (int) $count_stmt->fetchColumn();
$total_pages = max(1, ceil($total / $per_page));

// Fetch logs
$sql = "SELECT vl.*, l.license_key
        FROM validation_logs vl
        LEFT JOIN licenses l ON l.id = vl.license_id
        $where_sql
        ORDER BY vl.created_at DESC
        LIMIT $per_page OFFSET $offset";
$stmt = $db->prepare($sql);
$stmt->execute($params);
$logs = $stmt->fetchAll();

// License name for filter display
$license_label = '';
if ($filter_license) {
    $s = $db->prepare('SELECT license_key FROM licenses WHERE id = ?');
    $s->execute([$filter_license]);
    $license_label = $s->fetchColumn() ?: "ID $filter_license";
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETTEM Admin - Logs</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f0f2f5; color: #1a1a2e; }

        .topbar { background: #1a1a2e; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .topbar h1 { font-size: 1.2rem; }
        .topbar-nav a { color: rgba(255,255,255,0.7); text-decoration: none; margin-left: 1.5rem; font-size: 0.9rem; }
        .topbar-nav a:hover { color: white; }
        .topbar-nav a.active { color: white; font-weight: 600; }

        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }

        .filters { background: white; padding: 1rem 1.5rem; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 1.5rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
        .filters label { font-size: 0.85rem; font-weight: 600; }
        .filters select { padding: 0.4rem 0.6rem; border: 1px solid #ddd; border-radius: 4px; font-size: 0.85rem; }
        .filters .btn { padding: 0.4rem 1rem; background: #4361ee; color: white; border: none; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
        .filters .btn-clear { background: #f0f0f0; color: #666; }

        .card { background: white; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); overflow: hidden; }
        .card-header { padding: 1rem 1.5rem; border-bottom: 1px solid #eee; font-weight: 600; display: flex; justify-content: space-between; }

        table { width: 100%; border-collapse: collapse; }
        th { text-align: left; padding: 0.6rem 1rem; font-size: 0.8rem; color: #666; text-transform: uppercase; background: #fafafa; }
        td { padding: 0.6rem 1rem; border-top: 1px solid #f0f0f0; font-size: 0.85rem; }
        tr:hover td { background: #f8f9ff; }

        .badge { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600; }
        .badge-green { background: #e6f9ed; color: #0a7c3e; }
        .badge-red { background: #fde8e8; color: #c00; }
        .badge-gray { background: #f0f0f0; color: #666; }

        .key-mono { font-family: 'Consolas', monospace; font-size: 0.8rem; }
        .machine-id-short { font-family: 'Consolas', monospace; font-size: 0.8rem; color: #666; }

        .pagination { display: flex; justify-content: center; gap: 0.5rem; margin-top: 1.5rem; }
        .pagination a { padding: 0.4rem 0.8rem; border: 1px solid #ddd; border-radius: 4px; text-decoration: none; color: #333; font-size: 0.85rem; }
        .pagination a.active { background: #4361ee; color: white; border-color: #4361ee; }
        .pagination a:hover { background: #f0f0f0; }
    </style>
</head>
<body>
    <div class="topbar">
        <h1>ETTEM Admin</h1>
        <nav class="topbar-nav">
            <a href="index.php">Dashboard</a>
            <a href="logs.php" class="active">Logs</a>
            <a href="index.php?action=logout">Logout</a>
        </nav>
    </div>

    <div class="container">
        <!-- Filters -->
        <form class="filters" method="GET">
            <?php if ($filter_license): ?>
                <input type="hidden" name="license_id" value="<?= $filter_license ?>">
                <span style="font-size:0.85rem;">License: <strong class="key-mono"><?= htmlspecialchars($license_label) ?></strong></span>
            <?php endif; ?>

            <label>Action:</label>
            <select name="action_filter">
                <option value="">All</option>
                <option value="activate" <?= $filter_action === 'activate' ? 'selected' : '' ?>>activate</option>
                <option value="validate" <?= $filter_action === 'validate' ? 'selected' : '' ?>>validate</option>
                <option value="deactivate" <?= $filter_action === 'deactivate' ? 'selected' : '' ?>>deactivate</option>
                <option value="rejected" <?= $filter_action === 'rejected' ? 'selected' : '' ?>>rejected</option>
            </select>

            <label>Result:</label>
            <select name="result_filter">
                <option value="">All</option>
                <option value="success" <?= $filter_result === 'success' ? 'selected' : '' ?>>success</option>
                <option value="expired" <?= $filter_result === 'expired' ? 'selected' : '' ?>>expired</option>
                <option value="revoked" <?= $filter_result === 'revoked' ? 'selected' : '' ?>>revoked</option>
                <option value="machine_limit" <?= $filter_result === 'machine_limit' ? 'selected' : '' ?>>machine_limit</option>
                <option value="invalid_key" <?= $filter_result === 'invalid_key' ? 'selected' : '' ?>>invalid_key</option>
                <option value="error" <?= $filter_result === 'error' ? 'selected' : '' ?>>error</option>
            </select>

            <button type="submit" class="btn">Filter</button>
            <a href="logs.php" class="btn btn-clear" style="text-decoration:none;">Clear</a>
        </form>

        <!-- Logs Table -->
        <div class="card">
            <div class="card-header">
                <span>Validation Logs</span>
                <span style="font-size:0.85rem; color:#666;"><?= number_format($total) ?> entries</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>License</th>
                        <th>Machine ID</th>
                        <th>Action</th>
                        <th>Result</th>
                        <th>IP</th>
                        <th>Version</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                    <?php if (empty($logs)): ?>
                        <tr><td colspan="8" style="text-align:center; color:#999; padding:2rem;">No logs found.</td></tr>
                    <?php else: ?>
                        <?php foreach ($logs as $log): ?>
                            <tr>
                                <td style="white-space:nowrap;"><?= date('d/m/Y H:i:s', strtotime($log['created_at'])) ?></td>
                                <td>
                                    <?php if ($log['license_key']): ?>
                                        <a href="license.php?id=<?= $log['license_id'] ?>" class="key-mono" style="color:#4361ee; text-decoration:none;">
                                            <?= htmlspecialchars(substr($log['license_key'], 6)) ?>
                                        </a>
                                    <?php else: ?>
                                        <span class="key-mono" style="color:#999;">ID <?= $log['license_id'] ?></span>
                                    <?php endif; ?>
                                </td>
                                <td><span class="machine-id-short" title="<?= htmlspecialchars($log['machine_id']) ?>"><?= htmlspecialchars(substr($log['machine_id'], 0, 12)) ?>...</span></td>
                                <td><span class="badge badge-gray"><?= htmlspecialchars($log['action']) ?></span></td>
                                <td>
                                    <?php
                                    $rc = match($log['result']) {
                                        'success' => 'badge-green',
                                        default => 'badge-red',
                                    };
                                    ?>
                                    <span class="badge <?= $rc ?>"><?= htmlspecialchars($log['result']) ?></span>
                                </td>
                                <td><small><?= htmlspecialchars($log['ip_address'] ?? '') ?></small></td>
                                <td><small><?= htmlspecialchars($log['app_version'] ?? '') ?></small></td>
                                <td><small style="color:#999;"><?= htmlspecialchars(substr($log['details'] ?? '', 0, 50)) ?></small></td>
                            </tr>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </tbody>
            </table>
        </div>

        <!-- Pagination -->
        <?php if ($total_pages > 1): ?>
            <div class="pagination">
                <?php
                $query_base = $_GET;
                for ($p = max(1, $page - 3); $p <= min($total_pages, $page + 3); $p++):
                    $query_base['page'] = $p;
                ?>
                    <a href="?<?= http_build_query($query_base) ?>" class="<?= $p === $page ? 'active' : '' ?>"><?= $p ?></a>
                <?php endfor; ?>
            </div>
        <?php endif; ?>
    </div>
</body>
</html>
