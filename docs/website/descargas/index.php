<?php
/**
 * ETTEM - Download Page
 * Password-protected download page for clients.
 * Files are uploaded by GitHub Actions with randomized names.
 */

$ACCESS_CODE = 'ETTEM2026';
$FILES_DIR = __DIR__ . '/files/';

$authenticated = false;
$error = '';

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $code = trim($_POST['code'] ?? '');
    if ($code === $ACCESS_CODE) {
        $authenticated = true;
        setcookie('ettem_dl', hash('sha256', $ACCESS_CODE . 'salt_ettem'), time() + 86400, '/');
    } else {
        $error = 'Codigo incorrecto';
    }
} elseif (isset($_COOKIE['ettem_dl']) && $_COOKIE['ettem_dl'] === hash('sha256', $ACCESS_CODE . 'salt_ettem')) {
    $authenticated = true;
}

// Find available files
$files = [];
if ($authenticated && is_dir($FILES_DIR)) {
    foreach (glob($FILES_DIR . '*') as $f) {
        $name = basename($f);
        if ($name === '.htaccess' || $name === 'index.html') continue;
        $ext = strtolower(pathinfo($name, PATHINFO_EXTENSION));
        $label = 'ETTEM';
        if ($ext === 'exe') $label = 'ETTEM para Windows (.exe)';
        elseif ($ext === 'dmg') $label = 'ETTEM para macOS (.dmg)';
        $files[] = [
            'name' => $name,
            'label' => $label,
            'size' => round(filesize($f) / 1048576, 1),
            'date' => date('d/m/Y H:i', filemtime($f)),
            'ext' => $ext,
        ];
    }
    usort($files, fn($a, $b) => filemtime($FILES_DIR . $b['name']) <=> filemtime($FILES_DIR . $a['name']));
}
?>
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="../favicon.svg">
    <title>ETTEM - Descargas</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f7fa; color: #333; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .container { max-width: 500px; width: 90%; }
        .card { background: #fff; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); padding: 2.5rem; }
        .logo { text-align: center; margin-bottom: 1.5rem; }
        .logo h1 { font-size: 1.8rem; color: #10B981; }
        .logo h1 span { color: #F59E0B; }
        .logo p { color: #666; font-size: 0.9rem; margin-top: 0.3rem; }
        .form-group { margin-bottom: 1rem; }
        label { display: block; font-weight: 600; margin-bottom: 0.4rem; font-size: 0.9rem; }
        input[type="text"] { width: 100%; padding: 0.7rem 1rem; border: 1px solid #ddd; border-radius: 8px; font-size: 1rem; text-align: center; letter-spacing: 0.2em; }
        input:focus { outline: none; border-color: #10B981; box-shadow: 0 0 0 3px rgba(16,185,129,0.1); }
        .btn { width: 100%; padding: 0.75rem; background: #10B981; color: #fff; border: none; border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer; }
        .btn:hover { background: #059669; }
        .error { color: #dc3545; font-size: 0.85rem; margin-top: 0.5rem; text-align: center; }
        .file-list { list-style: none; }
        .file-item { display: flex; align-items: center; justify-content: space-between; padding: 1rem; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 0.75rem; }
        .file-info h3 { font-size: 0.95rem; margin-bottom: 0.2rem; }
        .file-info span { font-size: 0.8rem; color: #666; }
        .file-icon { font-size: 1.5rem; margin-right: 1rem; }
        .file-left { display: flex; align-items: center; }
        .btn-dl { padding: 0.5rem 1.2rem; background: #10B981; color: #fff; border: none; border-radius: 6px; text-decoration: none; font-size: 0.85rem; font-weight: 600; }
        .btn-dl:hover { background: #059669; }
        .empty { text-align: center; color: #999; padding: 2rem 0; }
        .back-link { display: block; text-align: center; margin-top: 1.5rem; color: #10B981; text-decoration: none; font-size: 0.9rem; }
        .back-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="logo">
                <h1>ETT<span>EM</span></h1>
                <p>Easy Table Tennis Event Manager</p>
            </div>

            <?php if (!$authenticated): ?>
                <form method="POST">
                    <div class="form-group">
                        <label>Codigo de acceso</label>
                        <input type="text" name="code" placeholder="Ingrese el codigo" autocomplete="off" autofocus>
                    </div>
                    <?php if ($error): ?>
                        <p class="error"><?= htmlspecialchars($error) ?></p>
                    <?php endif; ?>
                    <br>
                    <button type="submit" class="btn">Acceder</button>
                </form>
            <?php else: ?>
                <?php if (empty($files)): ?>
                    <p class="empty">No hay archivos disponibles todavia.<br>Se publicaran con el proximo release.</p>
                <?php else: ?>
                    <ul class="file-list">
                        <?php foreach ($files as $f): ?>
                            <li class="file-item">
                                <div class="file-left">
                                    <span class="file-icon"><?= $f['ext'] === 'exe' ? '🪟' : '🍎' ?></span>
                                    <div class="file-info">
                                        <h3><?= htmlspecialchars($f['label']) ?></h3>
                                        <span><?= $f['size'] ?> MB &middot; <?= $f['date'] ?></span>
                                    </div>
                                </div>
                                <a href="download.php?f=<?= urlencode($f['name']) ?>" class="btn-dl">Descargar</a>
                            </li>
                        <?php endforeach; ?>
                    </ul>
                <?php endif; ?>
            <?php endif; ?>
        </div>
        <a href="https://ettem.boggdan.com" class="back-link">&larr; Volver al sitio</a>
    </div>
</body>
</html>
