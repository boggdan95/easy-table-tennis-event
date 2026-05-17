<?php
require_once __DIR__ . '/lib/auth.php';

$config_path = __DIR__ . '/config.php';
if (file_exists($config_path)) {
    $cfg = require $config_path;
    admin_logout($cfg);
}
header('Location: index.php');
exit;
