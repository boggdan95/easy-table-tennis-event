<?php
/**
 * Thin curl wrapper around the Supabase Admin + PostgREST APIs.
 * Uses the service_role key — bypasses RLS, do NOT expose to clients.
 *
 * All functions return ['ok' => bool, 'data' => ?, 'error' => ?, 'status' => int].
 */

function sb_request(array $cfg, string $method, string $path, ?array $body = null, array $extra_headers = []): array
{
    $url = rtrim($cfg['supabase_url'], '/') . $path;
    $key = $cfg['supabase_service_role_key'];

    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_HTTPHEADER => array_merge([
            'apikey: ' . $key,
            'Authorization: Bearer ' . $key,
            'Content-Type: application/json',
            'User-Agent: ETTEM-Admin/1.0',
        ], $extra_headers),
    ]);

    if ($body !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($body));
    }

    $raw = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $err = curl_error($ch);
    // PHP 8.0+ auto-closes; calling curl_close() is deprecated in 8.5.
    unset($ch);

    if ($raw === false) {
        return ['ok' => false, 'data' => null, 'error' => $err ?: 'curl failed', 'status' => 0];
    }

    $decoded = json_decode($raw, true);

    if ($status >= 200 && $status < 300) {
        return ['ok' => true, 'data' => $decoded, 'error' => null, 'status' => $status];
    }

    $msg = is_array($decoded) ? ($decoded['msg'] ?? $decoded['message'] ?? $decoded['error_description'] ?? $raw) : $raw;
    return ['ok' => false, 'data' => $decoded, 'error' => $msg, 'status' => $status];
}

// --- Auth admin -----------------------------------------------------------

function sb_invite_user(array $cfg, string $email): array
{
    // Sends a magic-link invite email. User clicks the link → /auth/callback
    // exchanges the code for a session, then forwards to /set-password so
    // the client picks their own password (real B2B UX, not Supabase's
    // default magic-link-only flow).
    $body = ['email' => $email];
    if (!empty($cfg['app_url'])) {
        $next = urlencode('/set-password');
        $body['redirect_to'] = rtrim($cfg['app_url'], '/')
            . '/auth/callback?next=' . $next;
    }
    return sb_request($cfg, 'POST', '/auth/v1/invite', $body);
}

function sb_get_user_by_email(array $cfg, string $email): array
{
    // Admin list users; filter by email.
    $r = sb_request($cfg, 'GET', '/auth/v1/admin/users?per_page=200');
    if (!$r['ok']) return $r;
    $users = $r['data']['users'] ?? [];
    foreach ($users as $u) {
        if (strcasecmp($u['email'] ?? '', $email) === 0) {
            return ['ok' => true, 'data' => $u, 'error' => null, 'status' => 200];
        }
    }
    return ['ok' => false, 'data' => null, 'error' => 'user not found', 'status' => 404];
}

function sb_delete_user(array $cfg, string $user_id): array
{
    return sb_request($cfg, 'DELETE', '/auth/v1/admin/users/' . urlencode($user_id));
}

// --- Tenants --------------------------------------------------------------

function sb_list_tenants(array $cfg): array
{
    return sb_request($cfg, 'GET', '/rest/v1/tenants?select=id,slug,name,country_cd,created_at,archived_at,plan:plans(code,name),members:tenant_members(count)&order=created_at.desc');
}

function sb_get_free_plan_id(array $cfg): ?string
{
    $r = sb_request($cfg, 'GET', '/rest/v1/plans?code=eq.free&select=id&limit=1');
    if (!$r['ok'] || empty($r['data'])) return null;
    return $r['data'][0]['id'] ?? null;
}

function sb_create_tenant(array $cfg, array $payload): array
{
    return sb_request($cfg, 'POST', '/rest/v1/tenants', $payload, ['Prefer: return=representation']);
}

function sb_add_tenant_member(array $cfg, string $tenant_id, string $user_id, string $role): array
{
    return sb_request($cfg, 'POST', '/rest/v1/tenant_members', [
        'tenant_id' => $tenant_id,
        'user_id' => $user_id,
        'role' => $role,
    ]);
}
