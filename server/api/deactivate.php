<?php
/**
 * POST /api/deactivate
 *
 * Release a machine slot from a license.
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

if (!$license_key || !$machine_id) {
    json_error('BAD_REQUEST', 'license_key and machine_id are required', 400);
}

// Validate HMAC
$hmac_info = validate_license_hmac($license_key);
if (!$hmac_info) {
    json_error('INVALID_KEY', 'License key is not valid', 400);
}

// Find license
$db = get_db();
$stmt = $db->prepare('SELECT * FROM licenses WHERE license_key = ?');
$stmt->execute([$license_key]);
$license = $stmt->fetch();

if (!$license) {
    json_error('NOT_FOUND', 'License not registered', 404);
}

// Find and deactivate machine
$stmt = $db->prepare('SELECT * FROM machines WHERE license_id = ? AND machine_id = ?');
$stmt->execute([$license['id'], $machine_id]);
$machine = $stmt->fetch();

if (!$machine) {
    json_error('MACHINE_NOT_FOUND', 'Machine not found for this license', 404);
}

$stmt = $db->prepare('UPDATE machines SET is_active = 0 WHERE id = ?');
$stmt->execute([$machine['id']]);

log_validation($license['id'], $machine_id, 'deactivate', 'success');

json_success(['message' => 'Machine deactivated successfully']);
