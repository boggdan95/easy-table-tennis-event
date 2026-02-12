<?php
/**
 * POST /api/validate
 *
 * Periodic license validation (every 30 days).
 */

require_once __DIR__ . '/helpers.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_error('METHOD_NOT_ALLOWED', 'Use POST', 405);
}

check_rate_limit();
require_api_key();

$body = get_json_body();

$license_key = $body['license_key'] ?? '';
$machine_id  = $body['machine_id'] ?? '';
$app_version = $body['app_version'] ?? '';

if (!$license_key || !$machine_id) {
    json_error('BAD_REQUEST', 'license_key and machine_id are required', 400);
}

// Validate HMAC
$hmac_info = validate_license_hmac($license_key);
if (!$hmac_info) {
    json_error('INVALID_KEY', 'License key is not valid', 400);
}

// Find license in DB
$db = get_db();
$stmt = $db->prepare('SELECT * FROM licenses WHERE license_key = ?');
$stmt->execute([$license_key]);
$license = $stmt->fetch();

if (!$license) {
    json_error('NOT_FOUND', 'License not registered. Activate first.', 404);
}

// Check if revoked
if (!$license['is_active']) {
    log_validation($license['id'], $machine_id, 'validate', 'revoked', $app_version);
    json_error('REVOKED', 'This license has been revoked. Contact support.', 403);
}

// Check expiration
if ($hmac_info['is_expired']) {
    log_validation($license['id'], $machine_id, 'validate', 'expired', $app_version);
    json_error('EXPIRED', 'License expired on ' . $hmac_info['expiration_date'], 403);
}

// Find machine
$stmt = $db->prepare('SELECT * FROM machines WHERE license_id = ? AND machine_id = ? AND is_active = 1');
$stmt->execute([$license['id'], $machine_id]);
$machine = $stmt->fetch();

if (!$machine) {
    log_validation($license['id'], $machine_id, 'validate', 'error', $app_version, 'Machine not found');
    json_error('MACHINE_NOT_FOUND', 'This machine is not registered. Re-activate the license.', 404);
}

// Update last validated timestamp
$stmt = $db->prepare('UPDATE machines SET last_validated_at = NOW() WHERE id = ?');
$stmt->execute([$machine['id']]);

$active_count = count_active_machines($license['id']);
log_validation($license['id'], $machine_id, 'validate', 'success', $app_version);

json_success([
    'license' => [
        'client_id'       => $hmac_info['client_id'],
        'expiration_date' => $hmac_info['expiration_date'],
        'days_remaining'  => $hmac_info['days_remaining'],
    ],
    'machine' => [
        'machine_id' => $machine_id,
        'slot'       => $active_count,
        'max_slots'  => (int) $license['max_machines'],
    ],
    'server_time' => gmdate('Y-m-d\TH:i:s\Z'),
]);
