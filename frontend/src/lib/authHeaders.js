export function getDevAuthHeaders() {
  return {
    'X-Dev-User-Id': 'dev-user',
    'X-Dev-Tenant-Id': 'dev-tenant',
    'X-Dev-Roles': 'admin,user'
  };
}
