<?php
/**
 * Secure file download — validates cookie before serving file.
 */
$ACCESS_CODE = 'ETTEM2026';
$FILES_DIR = __DIR__ . '/files/';

// Check auth cookie
if (!isset($_COOKIE['ettem_dl']) || $_COOKIE['ettem_dl'] !== hash('sha256', $ACCESS_CODE . 'salt_ettem')) {
    http_response_code(403);
    die('Acceso denegado');
}

$file = basename($_GET['f'] ?? '');
$path = $FILES_DIR . $file;

if (!$file || !file_exists($path) || $file === '.htaccess') {
    http_response_code(404);
    die('Archivo no encontrado');
}

$ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
$mime = $ext === 'exe' ? 'application/x-msdownload' : ($ext === 'dmg' ? 'application/x-apple-diskimage' : 'application/octet-stream');

header('Content-Type: ' . $mime);
header('Content-Disposition: attachment; filename="ETTEM.' . $ext . '"');
header('Content-Length: ' . filesize($path));
readfile($path);
exit;
