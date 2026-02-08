<?php
/**
 * POST /api/activate
 *
 * Register a machine for a license. Called on first activation.
 */

require_once __DIR__ . '/helpers.php';

// Only POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    json_error('METHOD_NOT_ALLOWED', 'Use POST', 405);
}

check_rate_limit();
require_api_key();

$body = get_json_body();

$license_key   = $body['license_key'] ?? '';
$machine_id    = $body['machine_id'] ?? '';
$machine_label = $body['machine_label'] ?? '';
$app_version   = $body['app_version'] ?? '';

if (!$license_key || !$machine_id) {
    json_error('BAD_REQUEST', 'license_key and machine_id are required', 400);
}

// Validate HMAC
$hmac_info = validate_license_hmac($license_key);
if (!$hmac_info) {
    json_error('INVALID_KEY', 'License key is not valid', 400);
}

// Find or create license in DB
$license = find_or_create_license($license_key, $hmac_info);

// Check if revoked by admin
if (!$license['is_active']) {
    log_validation($license['id'], $machine_id, 'activate', 'revoked', $app_version);
    json_error('REVOKED', 'This license has been revoked. Contact support.', 403);
}

// Check expiration
if ($hmac_info['is_expired']) {
    log_validation($license['id'], $machine_id, 'activate', 'expired', $app_version);
    json_error('EXPIRED', 'License expired on ' . $hmac_info['expiration_date'], 403);
}

$db = get_db();

// Check if this machine is already registered
$stmt = $db->prepare('SELECT * FROM machines WHERE license_id = ? AND machine_id = ?');
$stmt->execute([$license['id'], $machine_id]);
$existing_machine = $stmt->fetch();

if ($existing_machine) {
    // Re-activation of existing machine - update timestamp and ensure active
    $stmt = $db->prepare('UPDATE machines SET last_validated_at = NOW(), is_active = 1, machine_label = ? WHERE id = ?');
    $stmt->execute([$machine_label ?: $existing_machine['machine_label'], $existing_machine['id']]);

    $active_count = count_active_machines($license['id']);
    log_validation($license['id'], $machine_id, 'activate', 'success', $app_version, 'Re-activation');

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
}

// New machine - check slot limit
$active_count = count_active_machines($license['id']);
if ($active_count >= (int) $license['max_machines']) {
    $machines = get_active_machines($license['id']);
    $machine_list = array_map(fn($m) => [
        'machine_label'  => $m['machine_label'],
        'last_validated' => $m['last_validated_at'],
    ], $machines);

    log_validation($license['id'], $machine_id, 'rejected', 'machine_limit', $app_version);

    json_error('MACHINE_LIMIT',
        "Maximum {$license['max_machines']} machines reached. Deactivate a machine first.",
        403,
        ['machines' => $machine_list]
    );
}

// Register new machine
$stmt = $db->prepare(
    'INSERT INTO machines (license_id, machine_id, machine_label) VALUES (?, ?, ?)'
);
$stmt->execute([$license['id'], $machine_id, $machine_label]);

$active_count = count_active_machines($license['id']);
log_validation($license['id'], $machine_id, 'activate', 'success', $app_version, 'New machine');

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
