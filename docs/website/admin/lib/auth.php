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

/**
 * True if the current request came over HTTPS. Used to set the cookie's
 * Secure flag conditionally so local dev over HTTP still works while prod
 * (Bluehost over HTTPS) gets a proper Secure cookie.
 */
function admin_request_is_https(): bool
{
    if (!empty($_SERVER['HTTPS']) && strtolower($_SERVER['HTTPS']) !== 'off') {
        return true;
    }
    // Behind a proxy (some hosts), HTTPS info comes via X-Forwarded-Proto.
    if (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https') {
        return true;
    }
    return false;
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
            'path' => '/',
            'secure' => admin_request_is_https(),
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
        'path' => '/',
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
