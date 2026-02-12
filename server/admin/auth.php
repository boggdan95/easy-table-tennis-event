<?php
/**
 * ETTEM Admin - Shared cookie auth functions
 * Used by license.php and logs.php (index.php has its own copy)
 */

define('AUTH_COOKIE_NAME', 'ettem_admin_auth');
define('AUTH_COOKIE_TTL', 86400);

function verify_auth_token(): bool {
    $raw = $_COOKIE[AUTH_COOKIE_NAME] ?? '';
    if (!$raw) return false;
    $decoded = base64_decode($raw, true);
    if (!$decoded) return false;
    $parts = explode('|', $decoded);
    if (count($parts) !== 3) return false;
    [$label, $expires, $sig] = $parts;
    if ($label !== 'ettem_admin') return false;
    if ((int)$expires < time()) return false;
    $expected = hash_hmac('sha256', $label . '|' . $expires, HMAC_SECRET);
    return hash_equals($expected, $sig);
}
