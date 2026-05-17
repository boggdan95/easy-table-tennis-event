<?php
/**
 * Admin authentication — single password, HMAC-signed cookie.
 * Matches the pattern used by docs/website/descargas/index.php so the admin
 * UI feels consistent and operationally familiar.
 */

function admin_session_token(array $cfg): string
{
    return hash('sha256', $cfg['admin_code'] . $cfg['cookie_salt']);
}

function admin_is_authenticated(array $cfg): bool
{
    $name = $cfg['cookie_name'];
    if (!isset($_COOKIE[$name])) {
        return false;
    }
    return hash_equals(admin_session_token($cfg), $_COOKIE[$name]);
}

function admin_login(array $cfg, string $submitted_code): bool
{
    if (!hash_equals($cfg['admin_code'], $submitted_code)) {
        return false;
    }
    setcookie(
        $cfg['cookie_name'],
        admin_session_token($cfg),
        [
            'expires' => time() + $cfg['session_ttl_seconds'],
            'path' => '/admin/',
            'secure' => true,
            'httponly' => true,
            'samesite' => 'Strict',
        ]
    );
    return true;
}

function admin_logout(array $cfg): void
{
    setcookie($cfg['cookie_name'], '', [
        'expires' => time() - 3600,
        'path' => '/admin/',
        'secure' => true,
        'httponly' => true,
        'samesite' => 'Strict',
    ]);
}

function admin_require_auth(array $cfg): void
{
    if (!admin_is_authenticated($cfg)) {
        header('Location: index.php');
        exit;
    }
}
