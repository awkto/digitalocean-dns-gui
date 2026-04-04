const API_BASE_URL = '/api';

async function checkAuth() {
    try {
        const res = await fetch(`${API_BASE_URL}/auth/status`);
        const data = await res.json();
        if (!data.authenticated) { window.location.href = '/login.html'; return false; }
        return true;
    } catch { window.location.href = '/login.html'; return false; }
}

const _originalFetch = window.fetch;
window.fetch = async function(...args) {
    const response = await _originalFetch.apply(this, args);
    if (response.status === 401) {
        const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
        if (!url.includes('/api/auth/')) window.location.href = '/login.html';
    }
    return response;
};

const successMessage = document.getElementById('successMessage');
const errorMessage = document.getElementById('errorMessage');

let isSetupMode = false;

document.addEventListener('DOMContentLoaded', async () => {
    if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

    const isAuth = await checkAuth();
    if (!isAuth) return;

    document.querySelectorAll('.sidebar-item').forEach(btn => {
        btn.addEventListener('click', () => switchPanel(btn.dataset.panel));
    });

    const hash = location.hash.replace('#', '');
    if (hash && document.getElementById(`panel-${hash}`)) switchPanel(hash);

    loadCurrentConfig();
    loadApiToken();
    loadMcpConfig();

    document.getElementById('saveConfigBtn').addEventListener('click', handleSaveConfig);
    document.getElementById('testConnectionBtn').addEventListener('click', handleTestConnection);
    document.getElementById('toggleApiTokenBtn').addEventListener('click', toggleApiTokenVisibility);
    document.getElementById('copyApiTokenBtn').addEventListener('click', copyApiToken);
    document.getElementById('regenerateApiTokenBtn').addEventListener('click', regenerateApiToken);
    document.getElementById('changePasswordBtn').addEventListener('click', handleChangePassword);
    document.getElementById('mcpEnabledToggle').addEventListener('change', handleMcpToggle);
});

function switchPanel(panelId) {
    document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sidebar-item').forEach(b => b.classList.remove('active'));
    const panel = document.getElementById(`panel-${panelId}`);
    const btn = document.querySelector(`.sidebar-item[data-panel="${panelId}"]`);
    if (panel) panel.classList.add('active');
    if (btn) btn.classList.add('active');
    location.hash = panelId;
    hideMessages();
}

async function loadCurrentConfig() {
    try {
        const response = await fetch(`${API_BASE_URL}/config`);
        const data = await response.json();
        if (response.ok) {
            const hasAnyConfig = data.api_token || data.dns_zone;
            isSetupMode = !hasAnyConfig;
            if (isSetupMode) {
                const back = document.getElementById('backNavigation');
                if (back) back.style.display = 'none';
                const desc = document.getElementById('settingsDescription');
                if (desc) desc.textContent = 'Welcome! Configure your DigitalOcean credentials to get started.';
            }
            document.getElementById('apiToken').value = data.api_token || '';
            document.getElementById('dnsZone').value = data.dns_zone || '';
            if (data.has_token) document.getElementById('apiToken').required = false;
        }
    } catch (e) { showError(`Failed to load configuration: ${e.message}`); }
}

async function handleTestConnection() {
    const btn = document.getElementById('testConnectionBtn');
    try {
        hideMessages();
        btn.disabled = true;
        btn.textContent = 'Testing...';
        const config = { api_token: document.getElementById('apiToken').value.trim(), dns_zone: document.getElementById('dnsZone').value.trim() };
        if (!config.api_token || !config.dns_zone) { showError('Please fill in all required fields'); return; }
        const res = await fetch(`${API_BASE_URL}/config/test`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
        const data = await res.json();
        if (res.ok) showSuccess(data.message || 'Connection successful!');
        else showError(data.error || 'Connection test failed');
    } catch (e) { showError(`Test failed: ${e.message}`); }
    finally { btn.disabled = false; btn.textContent = 'Test Connection'; }
}

async function handleSaveConfig() {
    try {
        hideMessages();
        const config = { api_token: document.getElementById('apiToken').value.trim(), dns_zone: document.getElementById('dnsZone').value.trim() };
        if (!config.api_token || !config.dns_zone) { showError('Please fill in all required fields'); return; }
        const res = await fetch(`${API_BASE_URL}/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
        const data = await res.json();
        if (res.ok) {
            showSuccess(`Configuration saved! DNS Zone: ${data.zone}`);
            setTimeout(() => { window.location.href = '/'; }, 2000);
        } else showError(data.error || 'Failed to save configuration');
    } catch (e) { showError(`Save failed: ${e.message}`); }
}

let _apiTokenValue = '';

async function loadApiToken() {
    try {
        const res = await fetch(`${API_BASE_URL}/auth/api-token`);
        if (!res.ok) return;
        const data = await res.json();
        _apiTokenValue = data.api_token;
        document.getElementById('apiTokenDisplay').value = _apiTokenValue;
    } catch {}
}

function toggleApiTokenVisibility() {
    const input = document.getElementById('apiTokenDisplay');
    const btn = document.getElementById('toggleApiTokenBtn');
    if (input.type === 'password') { input.type = 'text'; btn.textContent = 'Hide'; }
    else { input.type = 'password'; btn.textContent = 'Show'; }
}

async function copyApiToken() {
    if (!_apiTokenValue) return;
    try {
        await navigator.clipboard.writeText(_apiTokenValue);
        const btn = document.getElementById('copyApiTokenBtn');
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
    } catch { showError('Could not copy to clipboard'); }
}

async function regenerateApiToken() {
    if (!confirm('Regenerate? Existing scripts using the old token will stop working.')) return;
    try {
        const res = await fetch(`${API_BASE_URL}/auth/api-token/regenerate`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed');
        const data = await res.json();
        _apiTokenValue = data.api_token;
        document.getElementById('apiTokenDisplay').value = _apiTokenValue;
        document.getElementById('apiTokenDisplay').type = 'password';
        document.getElementById('toggleApiTokenBtn').textContent = 'Show';
        showSuccess('API token regenerated.');
    } catch { showError('Failed to regenerate API token'); }
}

async function handleChangePassword() {
    const current = document.getElementById('currentPassword').value;
    const newPw = document.getElementById('newPassword').value;
    const confirmPw = document.getElementById('confirmNewPassword').value;
    hideMessages();
    if (!current || !newPw || !confirmPw) { showError('Fill in all password fields'); return; }
    if (newPw !== confirmPw) { showError('New passwords do not match'); return; }
    if (newPw.length < 8) { showError('New password must be at least 8 characters'); return; }
    try {
        const res = await fetch(`${API_BASE_URL}/auth/change-password`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: current, new_password: newPw }) });
        const data = await res.json();
        if (res.ok) {
            showSuccess('Password changed successfully');
            document.getElementById('currentPassword').value = '';
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmNewPassword').value = '';
        } else showError(data.error || 'Failed to change password');
    } catch (e) { showError(`Failed: ${e.message}`); }
}

async function loadMcpConfig() {
    try {
        const res = await fetch(`${API_BASE_URL}/config/mcp`);
        if (!res.ok) return;
        const data = await res.json();
        const toggle = document.getElementById('mcpEnabledToggle');
        const label = document.getElementById('mcpStatusLabel');
        toggle.checked = data.enabled;
        label.textContent = data.enabled ? 'Enabled' : 'Disabled';
    } catch {}
}

async function handleMcpToggle() {
    const toggle = document.getElementById('mcpEnabledToggle');
    const label = document.getElementById('mcpStatusLabel');
    const enabled = toggle.checked;
    try {
        hideMessages();
        const res = await fetch(`${API_BASE_URL}/config/mcp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        const data = await res.json();
        if (res.ok) {
            label.textContent = data.enabled ? 'Enabled' : 'Disabled';
            showSuccess(`MCP server ${data.enabled ? 'enabled' : 'disabled'}.`);
        } else {
            toggle.checked = !enabled;
            showError(data.error || 'Failed to update MCP setting');
        }
    } catch (e) {
        toggle.checked = !enabled;
        showError(`Failed to update MCP setting: ${e.message}`);
    }
}

function showSuccess(msg) {
    successMessage.textContent = msg; successMessage.style.display = 'block';
    errorMessage.style.display = 'none';
    setTimeout(() => { successMessage.style.display = 'none'; }, 5000);
}
function showError(msg) {
    errorMessage.textContent = msg; errorMessage.style.display = 'block';
    successMessage.style.display = 'none';
}
function hideMessages() {
    successMessage.style.display = 'none';
    errorMessage.style.display = 'none';
}