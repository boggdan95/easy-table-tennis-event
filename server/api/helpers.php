<?php
/**
 * ETTEM License Server - Shared helpers
 */

require_once __DIR__ . '/config.php';

// ---------------------------------------------------------------------------
// Database
// ---------------------------------------------------------------------------

function get_db(): PDO {
    static $pdo = null;
    if ($pdo === null) {
        $dsn = 'mysql:host=' . DB_HOST . ';dbname=' . DB_NAME . ';charset=utf8mb4';
        $pdo = new PDO($dsn, DB_USER, DB_PASS, [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
    }
    return $pdo;
}

// ---------------------------------------------------------------------------
// JSON response helpers
// ---------------------------------------------------------------------------

function json_success(array $data): void {
    header('Content-Type: application/json');
    http_response_code(200);
    echo json_encode(array_merge(['status' => 'ok'], $data));
    exit;
}

function json_error(string $code, string $message, int $http = 400, array $extra = []): void {
    header('Content-Type: application/json');
    http_response_code($http);
    echo json_encode(array_merge(['status' => 'error', 'code' => $code, 'message' => $message], $extra));
    exit;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------

function require_api_key(): void {
    // Try multiple sources: getallheaders() and $_SERVER (nginx/proxy fallback)
    $key = '';
    if (function_exists('getallheaders')) {
        $headers = getallheaders();
        $key = $headers['X-API-Key'] ?? $headers['x-api-key'] ?? $headers['X-Api-Key'] ?? '';
    }
    if ($key === '' && isset($_SERVER['HTTP_X_API_KEY'])) {
        $key = $_SERVER['HTTP_X_API_KEY'];
    }
    if ($key !== API_KEY) {
        json_error('UNAUTHORIZED', 'Invalid API key', 401);
    }
}

function get_json_body(): array {
    $raw = file_get_contents('php://input');
    $data = json_decode($raw, true);
    if (!is_array($data)) {
        json_error('BAD_REQUEST', 'Invalid JSON body', 400);
    }
    return $data;
}

function get_client_ip(): string {
    return $_SERVER['HTTP_X_FORWARDED_FOR'] ?? $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

// ---------------------------------------------------------------------------
// Rate limiting (file-based, simple)
// ---------------------------------------------------------------------------

function check_rate_limit(): void {
    $ip = get_client_ip();
    $file = sys_get_temp_dir() . '/ettem_rate_' . md5($ip);

    $now = time();
    $requests = [];

    if (file_exists($file)) {
        $data = json_decode(file_get_contents($file), true);
        if (is_array($data)) {
            // Keep only requests within the window
            $requests = array_filter($data, fn($t) => ($now - $t) < RATE_LIMIT_WINDOW);
        }
    }

    if (count($requests) >= RATE_LIMIT_MAX) {
        json_error('RATE_LIMITED', 'Too many requests. Try again later.', 429);
    }

    $requests[] = $now;
    file_put_contents($file, json_encode(array_values($requests)));
}

// ---------------------------------------------------------------------------
// HMAC License Validation (same logic as Python)
// ---------------------------------------------------------------------------

function validate_license_hmac(string $key): ?array {
    // Format: ETTEM-CCCC-MMYY-SSSSSSSS
    $parts = explode('-', strtoupper(trim($key)));
    if (count($parts) !== 4) return null;

    [$prefix, $client_id, $date_part, $signature] = $parts;

    if ($prefix !== 'ETTEM') return null;
    if (strlen($client_id) !== 4 || !ctype_alnum($client_id)) return null;
    if (strlen($date_part) !== 4 || !ctype_digit($date_part)) return null;
    if (strlen($signature) !== 8) return null;

    $month = (int) substr($date_part, 0, 2);
    $year  = (int) substr($date_part, 2, 2);

    if ($month < 1 || $month > 12) return null;

    // Verify HMAC signature
    $data = strtoupper($client_id) . sprintf('%02d%02d', $month, $year);
    $expected = strtoupper(substr(hash_hmac('sha256', $data, HMAC_SECRET), 0, 8));

    if (!hash_equals($expected, $signature)) return null;

    // Calculate expiration (last day of the month)
    $full_year = 2000 + $year;
    if ($month == 12) {
        $exp = new DateTime("$full_year-12-31");
    } else {
        $next_month = $month + 1;
        $exp = new DateTime("$full_year-$next_month-01");
        $exp->modify('-1 day');
    }

    $today = new DateTime('today');
    $days_remaining = (int) $today->diff($exp)->format('%r%a');

    return [
        'client_id'       => $client_id,
        'expiration_date'  => $exp->format('Y-m-d'),
        'days_remaining'   => $days_remaining,
        'is_expired'       => $days_remaining < 0,
        'month'            => $month,
        'year'             => $year,
    ];
}

// ---------------------------------------------------------------------------
// License DB helpers
// ---------------------------------------------------------------------------

function find_or_create_license(string $license_key, array $hmac_info): array {
    $db = get_db();

    $stmt = $db->prepare('SELECT * FROM licenses WHERE license_key = ?');
    $stmt->execute([$license_key]);
    $license = $stmt->fetch();

    if (!$license) {
        // Auto-register: the HMAC signature is proof of authenticity
        $stmt = $db->prepare(
            'INSERT INTO licenses (license_key, client_id, expiration_date) VALUES (?, ?, ?)'
        );
        $stmt->execute([$license_key, $hmac_info['client_id'], $hmac_info['expiration_date']]);

        $stmt = $db->prepare('SELECT * FROM licenses WHERE license_key = ?');
        $stmt->execute([$license_key]);
        $license = $stmt->fetch();
    }

    return $license;
}

function count_active_machines(int $license_id): int {
    $db = get_db();
    $stmt = $db->prepare('SELECT COUNT(*) FROM machines WHERE license_id = ? AND is_active = 1');
    $stmt->execute([$license_id]);
    return (int) $stmt->fetchColumn();
}

function get_active_machines(int $license_id): array {
    $db = get_db();
    $stmt = $db->prepare(
        'SELECT machine_id, machine_label, last_validated_at FROM machines WHERE license_id = ? AND is_active = 1'
    );
    $stmt->execute([$license_id]);
    return $stmt->fetchAll();
}

function log_validation(int $license_id, string $machine_id, string $action, string $result, ?string $app_version = null, ?string $details = null): void {
    $db = get_db();
    $stmt = $db->prepare(
        'INSERT INTO validation_logs (license_id, machine_id, action, result, ip_address, app_version, details) VALUES (?, ?, ?, ?, ?, ?, ?)'
    );
    $stmt->execute([$license_id, $machine_id, $action, $result, get_client_ip(), $app_version, $details]);
}
